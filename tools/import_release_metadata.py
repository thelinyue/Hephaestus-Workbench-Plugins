#!/usr/bin/env python3
"""离线校验 release-metadata v2，并生成候选 Catalog；绝不访问网络。"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from validate_catalog import (
    ALLOWED_KINDS,
    MAX_PACKAGE_BYTES,
    SHA256_PATTERN,
    is_https_url,
    is_identifier,
    is_key_id,
    is_non_empty_string,
    is_semantic_version,
    validate_catalog,
    validate_release,
)


METADATA_ROOT_FIELDS = {"schemaVersion", "generatedAtUtc", "packages"}
METADATA_PACKAGE_FIELDS = {"manifest", "file", "url", "size", "sha256", "keyId", "signature"}
MANIFEST_FIELDS = {
    "schemaVersion",
    "id",
    "name",
    "version",
    "kind",
    "publisherId",
    "hostApiVersion",
    "minHostVersion",
    "runtime",
    "capabilities",
    "permissions",
    "dependencies",
}
RUNTIME_FIELDS = {
    ("workspace", "web"): {"kind", "entry"},
    ("analysis", "process"): {"kind", "protocol", "entry"},
    ("analysis", "content"): {"kind"},
    ("maintenance", "content"): {"kind"},
}
MAX_MANIFEST_BYTES = 1_048_576
UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


class MetadataValidationError(ValueError):
    """表示冻结的 release-metadata 离线交接契约未通过。

    此异常只包含可直接交给发布者修复的中文说明。工具不会将这类错误
    降级为警告，避免未审核资产意外进入公开 Catalog。
    """


def object_shape_errors(
    value: object,
    prefix: str,
    required_fields: set[str],
    allowed_fields: set[str],
) -> list[str]:
    """统一执行对象精确字段校验，未知与缺失字段均 fail-closed。"""
    if not isinstance(value, dict):
        return [f"{prefix} 必须是对象。"]

    errors = [f"{prefix} 缺少字段：{field}。" for field in sorted(required_fields - value.keys())]
    errors.extend(f"{prefix} 包含未知字段：{field}。" for field in sorted(value.keys() - allowed_fields))
    return errors


def load_json_document(path: Path, label: str) -> object:
    """读取 JSON 并拒绝重复键，防止解析器静默覆盖发布元数据。"""
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise MetadataValidationError(f"{label} 包含重复 JSON 字段：{key}。")
            result[key] = value
        return result

    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream, object_pairs_hook=reject_duplicate_keys)
    except MetadataValidationError:
        raise
    except FileNotFoundError as exception:
        raise MetadataValidationError(f"{label} 不存在：{path}。") from exception
    except UnicodeDecodeError as exception:
        raise MetadataValidationError(f"{label} 不是 UTF-8 文本：{path}。") from exception
    except json.JSONDecodeError as exception:
        raise MetadataValidationError(f"{label} JSON 无法解析：第 {exception.lineno} 行第 {exception.colno} 列。") from exception


def validate_generated_at_utc(value: object, prefix: str) -> list[str]:
    """接受明确带 Z 的 ISO-8601 UTC 时间，拒绝本地时间和模糊格式。"""
    if not isinstance(value, str) or not UTC_TIMESTAMP_PATTERN.fullmatch(value):
        return [f"{prefix} 必须是 ISO-8601 UTC 时间（以 Z 结尾）。"]
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return [f"{prefix} 不是有效的 UTC 时间。"]
    return []


def validate_manifest(value: object, prefix: str) -> list[str]:
    """校验完整 ExtensionManifestV2 的字段边界和最小类型语义。

    Catalog 不解释 manifest 的业务内容；这里仅确保 metadata 与 ZIP 中的
    manifest 都是完整 v2 清单，使随后“完全一致”比较有明确安全边界。
    """
    errors = object_shape_errors(value, prefix, MANIFEST_FIELDS, MANIFEST_FIELDS)
    if errors or not isinstance(value, dict):
        return errors

    if value.get("schemaVersion") != 2:
        errors.append(f"{prefix}.schemaVersion 必须为 2。")
    if not is_identifier(value.get("id")):
        errors.append(f"{prefix}.id 必须是安全 ID。")
    if not is_non_empty_string(value.get("name")):
        errors.append(f"{prefix}.name 不能为空。")
    if not is_semantic_version(value.get("version")):
        errors.append(f"{prefix}.version 必须是严格 SemVer。")
    if value.get("kind") not in ALLOWED_KINDS:
        errors.append(f"{prefix}.kind 必须是 workspace、analysis 或 maintenance。")
    if not is_identifier(value.get("publisherId")):
        errors.append(f"{prefix}.publisherId 必须是安全 ID。")
    if not is_non_empty_string(value.get("hostApiVersion")):
        errors.append(f"{prefix}.hostApiVersion 不能为空。")
    if not is_semantic_version(value.get("minHostVersion")):
        errors.append(f"{prefix}.minHostVersion 必须是严格 SemVer。")

    runtime = value.get("runtime")
    if not isinstance(runtime, dict):
        errors.append(f"{prefix}.runtime 必须是对象。")
    else:
        runtime_kind = runtime.get("kind")
        expected_runtime_fields = RUNTIME_FIELDS.get((value.get("kind"), runtime_kind))
        if expected_runtime_fields is None:
            errors.append(f"{prefix}.kind 与 runtime.kind 不是允许的 v2 组合。")
        else:
            errors.extend(
                object_shape_errors(runtime, f"{prefix}.runtime", expected_runtime_fields, expected_runtime_fields)
            )
            for field in expected_runtime_fields - {"kind"}:
                if not is_non_empty_string(runtime.get(field)):
                    errors.append(f"{prefix}.runtime.{field} 不能为空。")
        if runtime_kind == "process" and runtime.get("protocol") != "analysis-process-v1":
            errors.append(f"{prefix}.runtime.protocol 必须为 analysis-process-v1。")

    for field in ("capabilities", "permissions", "dependencies"):
        collection = value.get(field)
        if not isinstance(collection, list):
            errors.append(f"{prefix}.{field} 必须是数组。")
        elif any(not is_non_empty_string(item) for item in collection):
            errors.append(f"{prefix}.{field} 只能包含非空字符串。")
    return errors


def validate_metadata_signature(package: dict[str, object], prefix: str) -> list[str]:
    """只校验 keyId 和 Ed25519 签名编码，不在 Catalog 建立公钥信任。"""
    errors: list[str] = []
    if not is_key_id(package.get("keyId")):
        errors.append(f"{prefix}.keyId 必须是 1 到 64 位 ASCII 安全标识。")

    signature = package.get("signature")
    if not is_non_empty_string(signature):
        return errors + [f"{prefix}.signature 必须是 64 字节 Ed25519 签名的 Base64。"]
    assert isinstance(signature, str)
    try:
        decoded = base64.b64decode(signature, validate=True)
    except (binascii.Error, ValueError):
        return errors + [f"{prefix}.signature 必须是 64 字节 Ed25519 签名的 Base64。"]
    if len(decoded) != 64:
        errors.append(f"{prefix}.signature 解码后必须正好为 64 字节。")
    return errors


def validate_metadata_document(metadata: object) -> list[str]:
    """校验所有 metadata 包对象的精确形状；不读取任何网络指针或 latest。"""
    errors = object_shape_errors(metadata, "metadata", METADATA_ROOT_FIELDS, METADATA_ROOT_FIELDS)
    if errors or not isinstance(metadata, dict):
        return errors

    if metadata.get("schemaVersion") != 2:
        errors.append("metadata.schemaVersion 必须为 2。")
    errors.extend(validate_generated_at_utc(metadata.get("generatedAtUtc"), "metadata.generatedAtUtc"))
    packages = metadata.get("packages")
    if not isinstance(packages, list) or not packages:
        return errors + ["metadata.packages 必须是非空数组。"]

    for index, package in enumerate(packages):
        prefix = f"metadata.packages[{index}]"
        package_errors = object_shape_errors(package, prefix, METADATA_PACKAGE_FIELDS, METADATA_PACKAGE_FIELDS)
        errors.extend(package_errors)
        if package_errors or not isinstance(package, dict):
            continue
        if not isinstance(package.get("file"), str) or not package["file"]:
            errors.append(f"{prefix}.file 必须是非空文件名。")
        elif Path(package["file"]).name != package["file"]:
            errors.append(f"{prefix}.file 必须是文件名，不能包含路径。")
        if not is_https_url(package.get("url")):
            errors.append(f"{prefix}.url 必须是安全的绝对 HTTPS 地址。")
        size = package.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_PACKAGE_BYTES:
            errors.append(f"{prefix}.size 必须是 1 到 {MAX_PACKAGE_BYTES} 字节之间的整数。")
        sha256 = package.get("sha256")
        if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
            errors.append(f"{prefix}.sha256 必须是 64 位十六进制 SHA-256。")
        errors.extend(validate_metadata_signature(package, prefix))
        errors.extend(validate_manifest(package.get("manifest"), f"{prefix}.manifest"))
    return errors


def is_safe_zip_entry_name(name: str) -> bool:
    """拒绝绝对路径、盘符、反斜杠、空段和 ..，避免 ZIP 路径混淆。"""
    if not name or "\\" in name or name.startswith("/") or WINDOWS_DRIVE_PATTERN.match(name):
        return False
    raw_parts = name.split("/")
    if name.endswith("/"):
        raw_parts.pop()
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        return False
    return not PurePosixPath(name).is_absolute()


def read_zip_manifest(zip_path: Path) -> object:
    """安全读取 ZIP 根级唯一 manifest.json，并限制读取量和损坏输入。"""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if names.count("manifest.json") > 1:
                raise MetadataValidationError("ZIP 根目录包含重复 manifest.json，拒绝读取。")
            if len(names) != len(set(names)):
                raise MetadataValidationError("ZIP 包含重复入口，拒绝读取。")
            if any(not is_safe_zip_entry_name(name) for name in names):
                raise MetadataValidationError("ZIP 包含路径异常入口，拒绝读取。")

            manifests = [entry for entry in entries if entry.filename == "manifest.json"]
            if len(manifests) != 1:
                raise MetadataValidationError("ZIP 根目录必须且只能包含一个 manifest.json。")
            manifest_entry = manifests[0]
            if manifest_entry.is_dir() or manifest_entry.flag_bits & 0x1:
                raise MetadataValidationError("ZIP 根目录 manifest.json 必须是未加密普通文件。")
            if manifest_entry.file_size > MAX_MANIFEST_BYTES:
                raise MetadataValidationError(f"ZIP 根目录 manifest.json 超过 {MAX_MANIFEST_BYTES} 字节安全上限。")
            try:
                content = archive.read(manifest_entry)
            except (EOFError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exception:
                raise MetadataValidationError("ZIP 根目录 manifest.json 无法安全读取或已损坏。") from exception
    except MetadataValidationError:
        raise
    except FileNotFoundError as exception:
        raise MetadataValidationError(f"本地 ZIP 不存在：{zip_path}。") from exception
    except (OSError, zipfile.BadZipFile) as exception:
        raise MetadataValidationError(f"本地 ZIP 无法打开或已损坏：{zip_path}。") from exception

    if len(content) > MAX_MANIFEST_BYTES:
        raise MetadataValidationError(f"ZIP 根目录 manifest.json 超过 {MAX_MANIFEST_BYTES} 字节安全上限。")
    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=lambda pairs: _reject_zip_duplicate_keys(pairs))
    except MetadataValidationError:
        raise
    except UnicodeDecodeError as exception:
        raise MetadataValidationError("ZIP 根目录 manifest.json 不是 UTF-8 文本。") from exception
    except json.JSONDecodeError as exception:
        raise MetadataValidationError(f"ZIP 根目录 manifest.json JSON 无法解析：第 {exception.lineno} 行第 {exception.colno} 列。") from exception


def _reject_zip_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """供 ZIP 清单 JSON 使用的重复键拒绝钩子。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MetadataValidationError(f"ZIP 根目录 manifest.json 包含重复 JSON 字段：{key}。")
        result[key] = value
    return result


def select_package(metadata: dict[str, object], zip_path: Path) -> dict[str, object]:
    """根据本地 ZIP 的精确文件名选择唯一包，不采用 latest 或远程解析。"""
    packages = metadata["packages"]
    assert isinstance(packages, list)
    matches = [package for package in packages if isinstance(package, dict) and package.get("file") == zip_path.name]
    if not matches:
        raise MetadataValidationError(f"metadata.packages[*].file 中没有与本地 ZIP 名称一致的包：{zip_path.name}。")
    if len(matches) != 1:
        raise MetadataValidationError(f"metadata.packages 中存在多个同名本地 ZIP 包：{zip_path.name}。")
    return matches[0]


def verify_package_asset(package: dict[str, object], zip_path: Path) -> None:
    """将 metadata 绑定到传入的最终 ZIP 字节及其根 manifest.json。"""
    prefix = "metadata.packages[匹配项]"
    if package["file"] != zip_path.name:
        raise MetadataValidationError(f"{prefix}.file 必须与本地 ZIP 名称完全一致。")
    url_path = urlsplit(str(package["url"])).path
    if url_path.rsplit("/", 1)[-1] != package["file"]:
        raise MetadataValidationError(f"{prefix}.url 最后一个路径段必须与 file 完全一致。")

    try:
        actual_size = zip_path.stat().st_size
    except FileNotFoundError as exception:
        raise MetadataValidationError(f"本地 ZIP 不存在：{zip_path}。") from exception
    except OSError as exception:
        raise MetadataValidationError(f"无法读取本地 ZIP：{zip_path}。") from exception
    if actual_size != package["size"]:
        raise MetadataValidationError(f"{prefix}.size 与本地 ZIP 实际字节数不一致。")
    if actual_size > MAX_PACKAGE_BYTES:
        raise MetadataValidationError(f"本地 ZIP 超过 {MAX_PACKAGE_BYTES} 字节安全上限。")

    digest = hashlib.sha256()
    try:
        with zip_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1_048_576), b""):
                digest.update(block)
    except OSError as exception:
        raise MetadataValidationError(f"无法读取本地 ZIP：{zip_path}。") from exception
    if digest.hexdigest().lower() != str(package["sha256"]).lower():
        raise MetadataValidationError(f"{prefix}.sha256 与本地 ZIP 实际 SHA-256 不一致。")

    zip_manifest = read_zip_manifest(zip_path)
    manifest_errors = validate_manifest(zip_manifest, "ZIP 根目录 manifest.json")
    if manifest_errors:
        raise MetadataValidationError("\n".join(manifest_errors))
    if package["manifest"] != zip_manifest:
        raise MetadataValidationError("metadata package manifest 与 ZIP 根目录 manifest.json 不完全一致。")


def make_catalog_release(package: dict[str, object]) -> dict[str, object]:
    """从已验证的 metadata/manifest 构造 Catalog 唯一允许的 release 形状。"""
    manifest = package["manifest"]
    assert isinstance(manifest, dict)
    return {
        "version": manifest["version"],
        "minHostVersion": manifest["minHostVersion"],
        "url": package["url"],
        "size": package["size"],
        "sha256": package["sha256"],
        "signature": {"keyId": package["keyId"], "signature": package["signature"]},
    }


def build_catalog_update(metadata_path: Path, zip_path: Path, catalog_path: Path) -> dict[str, object]:
    """返回确定性的候选 Catalog，整个过程只读三个显式输入文件。

    新扩展没有可受信的 description 来源：metadata 的 manifest v2 不包含该字段，
    因而只能拒绝并要求人工先审核创建 Catalog extension 条目。
    """
    metadata = load_json_document(metadata_path, "release metadata")
    metadata_errors = validate_metadata_document(metadata)
    if metadata_errors:
        raise MetadataValidationError("\n".join(metadata_errors))
    assert isinstance(metadata, dict)

    package = select_package(metadata, zip_path)
    verify_package_asset(package, zip_path)
    release = make_catalog_release(package)
    release_errors: list[str] = []
    validate_release(release, "候选 release", release_errors)
    if release_errors:
        raise MetadataValidationError("\n".join(release_errors))

    catalog = load_json_document(catalog_path, "现有 Catalog")
    catalog_errors = validate_catalog(catalog)
    if catalog_errors:
        raise MetadataValidationError("现有 Catalog 不符合 v2 契约：\n" + "\n".join(catalog_errors))
    assert isinstance(catalog, dict)

    manifest = package["manifest"]
    assert isinstance(manifest, dict)
    matching_extensions = [extension for extension in catalog["extensions"] if extension["id"] == manifest["id"]]
    if not matching_extensions:
        raise MetadataValidationError(
            "Catalog 中不存在该扩展；ExtensionManifestV2 不含 description，"
            "请先经过审核创建包含 description 的 extension 条目。"
        )
    extension = matching_extensions[0]
    for field in ("id", "name", "publisherId", "kind"):
        if extension[field] != manifest[field]:
            raise MetadataValidationError(f"Catalog extension.{field} 必须与 manifest.{field} 完全一致。")

    updated = copy.deepcopy(catalog)
    target = next(extension for extension in updated["extensions"] if extension["id"] == manifest["id"])
    for existing_release in target["releases"]:
        if existing_release["version"] != release["version"]:
            continue
        if existing_release != release:
            raise MetadataValidationError(f"Catalog extension 已存在重复版本 {release['version']}，但 release 内容不一致。")
        return updated

    target["releases"].append(release)
    candidate_errors = validate_catalog(updated)
    if candidate_errors:
        raise MetadataValidationError("候选 Catalog 不符合 v2 契约：\n" + "\n".join(candidate_errors))
    return updated


def main(argv: list[str] | None = None) -> int:
    """执行纯 check 或向显式 output 写入确定性 JSON；默认永不改写 Catalog。"""
    parser = argparse.ArgumentParser(description="离线导入并校验 release-metadata v2。不会联网或读取 latest。")
    parser.add_argument("--metadata", type=Path, required=True, help="显式 release-metadata JSON 路径")
    parser.add_argument("--zip", dest="zip_path", type=Path, required=True, help="显式本地最终 ZIP 路径")
    parser.add_argument("--catalog", type=Path, required=True, help="显式现有 catalog.json 路径")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="仅校验，绝不写入文件")
    mode.add_argument("--output", type=Path, help="将确定性候选 Catalog 写到显式路径")
    arguments = parser.parse_args(argv)

    try:
        updated = build_catalog_update(arguments.metadata, arguments.zip_path, arguments.catalog)
    except MetadataValidationError as exception:
        print(f"release-metadata 校验失败：{exception}", file=sys.stderr)
        return 1

    if arguments.output is not None:
        try:
            arguments.output.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exception:
            print(f"无法写入候选 Catalog：{arguments.output}：{exception}", file=sys.stderr)
            return 1
        print(f"离线校验通过，候选 Catalog 已写入：{arguments.output}")
    else:
        print("离线校验通过：未修改现有 Catalog。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
