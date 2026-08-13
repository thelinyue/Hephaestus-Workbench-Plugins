#!/usr/bin/env python3
"""校验公开规则目录中的密文包和公开清单，不读取也不输出规则明文。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def validate_catalog(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"无法读取 {path}: {exc}"]
    required = ("schemaVersion", "ruleSetId", "pluginId", "version", "minimumPluginVersion", "algorithm", "rulesUrl", "sha256", "packageSize")
    for field in required:
        if field not in catalog:
            errors.append(f"{path}: 缺少字段 {field}")
    if catalog.get("schemaVersion") != 1:
        errors.append(f"{path}: schemaVersion 必须为 1")
    if catalog.get("ruleSetId") != path.parent.name or catalog.get("pluginId") != "log-analyzer":
        errors.append(f"{path}: 规则集标识不匹配")
    if catalog.get("algorithm") != "AES-256-GCM":
        errors.append(f"{path}: 只支持 AES-256-GCM")
    if urlparse(str(catalog.get("rulesUrl", ""))).scheme != "https":
        errors.append(f"{path}: rulesUrl 必须使用 HTTPS")
    if not SHA256.fullmatch(str(catalog.get("sha256", ""))):
        errors.append(f"{path}: sha256 必须是 64 位十六进制字符串")
    package_path = path.parent / "versions" / f"{catalog.get('version')}.json.enc"
    if not package_path.is_file():
        errors.append(f"{path}: 找不到密文包 {package_path}")
        return errors
    data = package_path.read_bytes()
    if len(data) != catalog.get("packageSize"):
        errors.append(f"{path}: packageSize 与实际密文大小不一致")
    if hashlib.sha256(data).hexdigest().lower() != str(catalog.get("sha256", "")).lower():
        errors.append(f"{path}: 密文 SHA-256 与清单不一致")
    try:
        package = json.loads(data)
        if package.get("schemaVersion") != 1 or package.get("algorithm") != "AES-256-GCM":
            errors.append(f"{package_path}: 密文容器头无效")
        if not package.get("nonce") or not package.get("ciphertext"):
            errors.append(f"{package_path}: 缺少 nonce 或 ciphertext")
    except json.JSONDecodeError as exc:
        errors.append(f"{package_path}: 密文容器不是有效 JSON: {exc}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "rules"
    catalogs = sorted(root.glob("*/catalog.json"))
    if not catalogs:
        print("错误：rules 目录中没有 catalog.json", file=sys.stderr)
        return 1
    errors = [error for catalog in catalogs for error in validate_catalog(catalog)]
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1
    print(f"规则密文目录校验通过：{len(catalogs)} 个规则集")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
