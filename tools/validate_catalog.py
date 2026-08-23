#!/usr/bin/env python3
"""严格校验 Hephaestus Workbench Extension Catalog v2，不依赖第三方包。"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
import unicodedata
from ipaddress import IPv6Address
from urllib.parse import urlparse


IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_PACKAGE_BYTES = 209_715_200  # 与 Workbench 下载器的 200 MiB 安全上限保持一致。
ALLOWED_KINDS = {"workspace", "analysis", "maintenance"}
ROOT_FIELDS = {"schemaVersion", "extensions"}
EXTENSION_FIELDS = {"id", "name", "description", "publisherId", "kind", "releases"}
RELEASE_FIELDS = {"version", "minHostVersion", "url", "size", "sha256", "signature"}
SIGNATURE_FIELDS = {"keyId", "signature"}


def is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_identifier(value: object) -> bool:
    """保持与 Workbench PluginSDK 相同的安全 ID 语义。"""
    return isinstance(value, str) and bool(IDENTIFIER_PATTERN.fullmatch(value))


def _is_ascii_numeric_identifier(value: str, reject_leading_zero: bool) -> bool:
    if not value or any(character < "0" or character > "9" for character in value):
        return False
    return not reject_leading_zero or len(value) == 1 or value[0] != "0"


def _are_semver_identifiers_valid(value: str, reject_numeric_leading_zero: bool) -> bool:
    identifiers = value.split(".")
    for identifier in identifiers:
        if not identifier:
            return False
        if any(not (character.isascii() and (character.isalnum() or character == "-")) for character in identifier):
            return False
        if reject_numeric_leading_zero and identifier.isascii() and identifier.isdigit():
            if len(identifier) > 1 and identifier[0] == "0":
                return False
    return True


def is_semantic_version(value: object) -> bool:
    """实现 PluginSDK 使用的严格 SemVer 2.0.0 子集，包括预发布和构建元数据。"""
    if not is_non_empty_string(value):
        return False
    assert isinstance(value, str)

    build_split = value.split("+")
    if len(build_split) > 2 or any(not part for part in build_split):
        return False
    if len(build_split) == 2 and not _are_semver_identifiers_valid(build_split[1], False):
        return False

    version_and_prerelease = build_split[0].split("-", 1)
    core = version_and_prerelease[0].split(".")
    if len(core) != 3 or any(not _is_ascii_numeric_identifier(part, True) for part in core):
        return False

    return len(version_and_prerelease) == 1 or _are_semver_identifiers_valid(
        version_and_prerelease[1], True
    )


def is_https_url(value: object) -> bool:
    """按 Workbench 可消费的边界检查绝对 HTTPS 地址。"""
    if not isinstance(value, str):
        return False
    if any(
        character.isspace() or unicodedata.category(character) == "Cc"
        for character in value
    ):
        return False

    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        _ = parsed.port  # 访问属性以触发非法端口校验。
    except ValueError:
        return False

    if parsed.scheme.lower() != "https" or not hostname or "\\" in parsed.netloc:
        return False

    authority = parsed.netloc.rsplit("@", 1)[-1]
    if authority.startswith("["):
        try:
            IPv6Address(hostname)
        except ValueError:
            return False
    else:
        hostname_without_trailing_dot = hostname[:-1] if hostname.endswith(".") else hostname
        try:
            ascii_hostname = hostname_without_trailing_dot.encode("idna").decode("ascii")
        except UnicodeError:
            return False
        labels = ascii_hostname.split(".")
        if any(
            not label
            or any(not (character.isalnum() or character in "-_") for character in label)
            for label in labels
        ):
            return False
    return True


def validate_object_shape(
    value: object,
    prefix: str,
    required_fields: set[str],
    allowed_fields: set[str],
    errors: list[str],
) -> bool:
    """集中处理必填字段和未知字段，确保 Python 校验器与 JSON Schema 同样 fail closed。"""
    if not isinstance(value, dict):
        errors.append(f"{prefix} 必须是对象。")
        return False

    for field in sorted(required_fields - value.keys()):
        errors.append(f"{prefix} 缺少字段：{field}。")
    for field in sorted(value.keys() - allowed_fields):
        errors.append(f"{prefix} 包含未知字段：{field}。")
    return True


def validate_signature(value: object, prefix: str, errors: list[str]) -> None:
    if not validate_object_shape(value, prefix, SIGNATURE_FIELDS, SIGNATURE_FIELDS, errors):
        return
    assert isinstance(value, dict)

    if not is_non_empty_string(value.get("keyId")):
        errors.append(f"{prefix}.keyId 不能为空。")

    signature = value.get("signature")
    if not is_non_empty_string(signature):
        errors.append(f"{prefix}.signature 必须是 64 字节 Ed25519 签名的 Base64。")
        return
    assert isinstance(signature, str)
    try:
        decoded = base64.b64decode(signature, validate=True)
    except (binascii.Error, ValueError):
        errors.append(f"{prefix}.signature 不是有效的 Base64。")
        return
    if len(decoded) != 64:
        errors.append(f"{prefix}.signature 解码后必须正好为 64 字节。")


def validate_release(value: object, prefix: str, errors: list[str]) -> str | None:
    if not validate_object_shape(value, prefix, RELEASE_FIELDS, RELEASE_FIELDS, errors):
        return None
    assert isinstance(value, dict)

    version = value.get("version")
    if not is_semantic_version(version):
        errors.append(f"{prefix}.version 必须是严格 SemVer。")
    if not is_semantic_version(value.get("minHostVersion")):
        errors.append(f"{prefix}.minHostVersion 必须是严格 SemVer。")
    if not is_https_url(value.get("url")):
        errors.append(f"{prefix}.url 必须是绝对 HTTPS 地址。")

    size = value.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_PACKAGE_BYTES:
        errors.append(f"{prefix}.size 必须是 1 到 {MAX_PACKAGE_BYTES} 字节之间的整数。")

    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
        errors.append(f"{prefix}.sha256 必须是 64 位十六进制 SHA-256。")

    validate_signature(value.get("signature"), f"{prefix}.signature", errors)
    return version if isinstance(version, str) else None


def validate_extension(value: object, prefix: str, seen_ids: set[str], errors: list[str]) -> None:
    if not validate_object_shape(value, prefix, EXTENSION_FIELDS, EXTENSION_FIELDS, errors):
        return
    assert isinstance(value, dict)

    extension_id = value.get("id")
    if not is_identifier(extension_id):
        errors.append(f"{prefix}.id 必须由小写字母、数字及分隔符 . 或 - 组成，且分隔符不能连续。")
    elif extension_id in seen_ids:
        errors.append(f"目录包含重复扩展 ID：{extension_id}。")
    else:
        seen_ids.add(extension_id)

    if not is_non_empty_string(value.get("name")):
        errors.append(f"{prefix}.name 不能为空。")
    if not is_non_empty_string(value.get("description")):
        errors.append(f"{prefix}.description 不能为空。")
    if not is_identifier(value.get("publisherId")):
        errors.append(f"{prefix}.publisherId 必须是安全 ID。")
    if value.get("kind") not in ALLOWED_KINDS:
        errors.append(f"{prefix}.kind 必须是 workspace、analysis 或 maintenance。")

    releases = value.get("releases")
    if not isinstance(releases, list) or not releases:
        errors.append(f"{prefix}.releases 必须是非空数组。")
        return

    seen_versions: set[str] = set()
    for index, release in enumerate(releases):
        release_prefix = f"{prefix}.releases[{index}]"
        version = validate_release(release, release_prefix, errors)
        if version is None:
            continue
        if version in seen_versions:
            label = extension_id if isinstance(extension_id, str) else prefix
            errors.append(f"扩展 {label} 包含重复版本：{version}。")
        else:
            seen_versions.add(version)


def validate_catalog(data: object) -> list[str]:
    """返回全部可定位的 v2 契约错误；空列表表示目录通过校验。"""
    errors: list[str] = []
    if not validate_object_shape(data, "目录", ROOT_FIELDS, ROOT_FIELDS, errors):
        return errors
    assert isinstance(data, dict)

    schema_version = data.get("schemaVersion")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version != 2:
        errors.append("schemaVersion 必须是整数 2。")

    extensions = data.get("extensions")
    if not isinstance(extensions, list):
        errors.append("extensions 必须是数组。")
        return errors

    seen_ids: set[str] = set()
    for index, extension in enumerate(extensions):
        validate_extension(extension, f"extensions[{index}]", seen_ids, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Hephaestus Workbench Extension Catalog v2。")
    parser.add_argument("catalog", nargs="?", default="catalog.json", help="目录 JSON 文件路径。")
    args = parser.parse_args()

    try:
        with open(args.catalog, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError:
        print(f"错误：找不到目录文件：{args.catalog}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"错误：目录 JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列。", file=sys.stderr)
        return 1

    errors = validate_catalog(data)
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        print(f"目录校验失败，共 {len(errors)} 个问题。", file=sys.stderr)
        return 1

    count = len(data["extensions"])
    print(f"目录校验通过：{count} 个扩展。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
