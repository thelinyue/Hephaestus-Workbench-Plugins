#!/usr/bin/env python3
"""Validate the static Hephaestus Workbench plugin catalog without third-party packages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import PurePosixPath
from urllib.parse import urlparse


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def is_release_asset_url(value: object) -> bool:
    if not is_https_url(value):
        return False
    parsed = urlparse(value)
    return parsed.netloc.lower() == "github.com" and "/releases/download/" in parsed.path


def is_safe_relative_entry(value: object) -> bool:
    if not is_non_empty_string(value):
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return False
    return ".." not in PurePosixPath(normalized).parts


def validate_manifest(plugin: dict[str, object], errors: list[str]) -> None:
    manifest = plugin.get("manifest")
    prefix = f"插件 {plugin.get('id', '<unknown>')} 的 manifest"
    if not isinstance(manifest, dict):
        errors.append(f"{prefix} 必须是对象。")
        return

    for field in ("id", "name", "version", "type", "entry"):
        if field not in manifest:
            errors.append(f"{prefix} 缺少字段：{field}。")

    manifest_id = manifest.get("id")
    if not isinstance(manifest_id, str) or not ID_PATTERN.fullmatch(manifest_id):
        errors.append(f"{prefix}.id 必须使用小写字母、数字和短横线。")
    if manifest_id != plugin.get("id"):
        errors.append(f"{prefix}.id 必须与插件记录 id 一致。")

    for field in ("name", "version"):
        if not is_non_empty_string(manifest.get(field)):
            errors.append(f"{prefix}.{field} 不能为空。")
        elif manifest.get(field) != plugin.get(field):
            errors.append(f"{prefix}.{field} 必须与插件记录 {field} 一致。")

    if manifest.get("type") not in {"Exe", "Web"}:
        errors.append(f"{prefix}.type 必须是 Exe 或 Web。")
    if not is_safe_relative_entry(manifest.get("entry")):
        errors.append(f"{prefix}.entry 必须是插件目录内的相对路径。")
    if manifest.get("type") == "Web" and not str(manifest.get("entry", "")).lower().endswith((".html", ".htm")):
        errors.append(f"{prefix}.entry Web 插件入口必须是 HTML 文件。")
    for optional in ("runner", "reportPath"):
        if optional in manifest and not isinstance(manifest[optional], str):
            errors.append(f"{prefix}.{optional} 必须是字符串。")
    capabilities = manifest.get("capabilities", [])
    if not isinstance(capabilities, list) or any(not is_non_empty_string(x) for x in capabilities) or len(capabilities) != len(set(capabilities)):
        errors.append(f"{prefix}.capabilities 必须是无重复的非空字符串数组。")
    if manifest.get("type") == "Web" and "standalone-tool" not in capabilities:
        errors.append(f"{prefix}.capabilities 必须包含 standalone-tool。")


def validate_catalog(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["目录根对象必须是 JSON 对象。"]
    if data.get("schemaVersion") != 1:
        errors.append("schemaVersion 必须是 1。")

    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        return errors + ["plugins 必须是数组。"]

    seen_ids: set[str] = set()
    required = (
        "id",
        "name",
        "version",
        "description",
        "author",
        "license",
        "type",
        "minimumAppVersion",
        "repository",
        "packageUrl",
        "sha256",
        "packageSize",
        "releaseNotesUrl",
        "manifest",
    )
    for index, plugin in enumerate(plugins):
        prefix = f"plugins[{index}]"
        if not isinstance(plugin, dict):
            errors.append(f"{prefix} 必须是对象。")
            continue

        for field in required:
            if field not in plugin:
                errors.append(f"{prefix} 缺少字段：{field}。")

        plugin_id = plugin.get("id")
        if not isinstance(plugin_id, str) or not ID_PATTERN.fullmatch(plugin_id):
            errors.append(f"{prefix}.id 必须使用小写字母、数字和短横线。")
        elif plugin_id in seen_ids:
            errors.append(f"插件 ID 重复：{plugin_id}。")
        else:
            seen_ids.add(plugin_id)

        for field in ("name", "version", "description", "author", "license", "type", "minimumAppVersion"):
            if not is_non_empty_string(plugin.get(field)):
                errors.append(f"{prefix}.{field} 不能为空。")
        if not is_https_url(plugin.get("repository")):
            errors.append(f"{prefix}.repository 必须是 HTTPS 地址。")
        if not is_release_asset_url(plugin.get("packageUrl")):
            errors.append(f"{prefix}.packageUrl 必须是 GitHub Release 资产 HTTPS 地址。")
        if not isinstance(plugin.get("sha256"), str) or not SHA256_PATTERN.fullmatch(plugin["sha256"]):
            errors.append(f"{prefix}.sha256 必须是 64 位十六进制 SHA-256。")
        package_size = plugin.get("packageSize")
        if not isinstance(package_size, int) or isinstance(package_size, bool) or not 0 < package_size <= 200 * 1024 * 1024:
            errors.append(f"{prefix}.packageSize 必须是 1 到 200 MB 之间的整数。")
        if not is_https_url(plugin.get("releaseNotesUrl")):
            errors.append(f"{prefix}.releaseNotesUrl 必须是 HTTPS 地址。")
        validate_manifest(plugin, errors)
        manifest = plugin.get("manifest")
        if isinstance(manifest, dict) and manifest.get("type") != plugin.get("type"):
            errors.append(f"{prefix}.type 必须与 manifest.type 一致。")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Hephaestus Workbench 插件目录。")
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

    count = len(data["plugins"])
    print(f"目录校验通过：{count} 个插件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
