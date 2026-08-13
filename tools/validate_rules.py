#!/usr/bin/env python3
"""校验公开规则目录、明文规则包的完整性和签名字段格式。"""

from __future__ import annotations

import base64
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

    required = (
        "schemaVersion",
        "ruleSetId",
        "pluginId",
        "version",
        "minimumPluginVersion",
        "signatureAlgorithm",
        "packageUrl",
        "sha256",
        "packageSize",
        "signature",
        "keyId",
    )
    for field in required:
        if field not in catalog:
            errors.append(f"{path}: 缺少字段 {field}")
    if catalog.get("schemaVersion") != 1:
        errors.append(f"{path}: schemaVersion 必须为 1")
    if catalog.get("ruleSetId") != path.parent.name or catalog.get("pluginId") != "log-analyzer":
        errors.append(f"{path}: 规则集标识不匹配")
    if catalog.get("signatureAlgorithm") != "Ed25519":
        errors.append(f"{path}: 只支持 Ed25519")
    if urlparse(str(catalog.get("packageUrl", ""))).scheme != "https":
        errors.append(f"{path}: packageUrl 必须使用 HTTPS")
    if not SHA256.fullmatch(str(catalog.get("sha256", ""))):
        errors.append(f"{path}: sha256 必须是 64 位十六进制字符串")
    try:
        signature = base64.b64decode(catalog.get("signature", ""), validate=True)
        if len(signature) != 64:
            errors.append(f"{path}: Ed25519 签名必须为 64 字节")
    except (ValueError, TypeError):
        errors.append(f"{path}: signature 必须是有效的 Base64")

    package_path = path.parent / "versions" / f"{catalog.get('version')}.json"
    if not package_path.is_file():
        errors.append(f"{path}: 找不到明文规则包 {package_path}")
        return errors
    data = package_path.read_bytes()
    if len(data) != catalog.get("packageSize"):
        errors.append(f"{path}: packageSize 与实际规则包大小不一致")
    if hashlib.sha256(data).hexdigest().lower() != str(catalog.get("sha256", "")).lower():
        errors.append(f"{path}: 规则包 SHA-256 与清单不一致")
    try:
        package = json.loads(data)
        if package.get("version") != catalog.get("version"):
            errors.append(f"{package_path}: 规则版本与清单不一致")
        if not isinstance(package.get("files"), list):
            errors.append(f"{package_path}: files 必须是数组")
        else:
            # 客户端合并时会按“文件 + 规则 + 正则标记”建立唯一索引，发布前必须拦截重复项。
            for file_entry in package["files"]:
                if not isinstance(file_entry, dict) or not isinstance(file_entry.get("keywords"), list):
                    continue
                seen_rules: set[tuple[str, bool]] = set()
                for rule in file_entry["keywords"]:
                    if not isinstance(rule, dict):
                        continue
                    rule_key = (str(rule.get("term", "")), bool(rule.get("regex", False)))
                    if rule_key in seen_rules:
                        errors.append(
                            f"{package_path}: 文件 {file_entry.get('name', '<unknown>')} 存在重复规则 {rule_key[0]}"
                        )
                    seen_rules.add(rule_key)
    except json.JSONDecodeError as exc:
        errors.append(f"{package_path}: 规则包不是有效 JSON: {exc}")
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
    print(f"规则目录校验通过：{len(catalogs)} 个规则集")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
