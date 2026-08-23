#!/usr/bin/env python3
"""Hephaestus Workbench 扩展目录 v2 校验器回归测试。"""

from __future__ import annotations

import base64
import copy
import json
import unittest
from pathlib import Path

from validate_catalog import validate_catalog


VALID_SIGNATURE = base64.b64encode(bytes(range(64))).decode("ascii")
VALID_SHA256 = "0123456789abcdef" * 4
MAX_PACKAGE_BYTES = 209_715_200
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def collect_object_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value.keys())
        for child in value.values():
            keys.update(collect_object_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(collect_object_keys(child))
    return keys


def make_release(version: str = "2.0.0") -> dict[str, object]:
    return {
        "version": version,
        "minHostVersion": "2.0.0",
        "url": "https://example.test/releases/log-analyzer-2.0.0.zip",
        "size": 1024,
        "sha256": VALID_SHA256,
        "signature": {
            "keyId": "test-key",
            "signature": VALID_SIGNATURE,
        },
    }


def make_extension(extension_id: str = "log-analyzer") -> dict[str, object]:
    return {
        "id": extension_id,
        "name": "日志分析",
        "description": "综合日志分析扩展。",
        "publisherId": "thelinyue",
        "kind": "analysis",
        "releases": [make_release()],
    }


def make_catalog() -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "extensions": [make_extension()],
    }


class CatalogV2ValidatorTests(unittest.TestCase):
    def assert_invalid(self, data: object, text: str) -> None:
        errors = validate_catalog(data)
        self.assertTrue(errors, "预期目录无效，但校验器返回通过。")
        self.assertTrue(
            any(text in error for error in errors),
            f"预期错误包含 {text!r}，实际错误：{errors}",
        )

    def test_accepts_valid_v2_catalog(self) -> None:
        self.assertEqual([], validate_catalog(make_catalog()))

    def test_rejects_v1_shape_and_compatibility_fields(self) -> None:
        legacy = {"schemaVersion": 1, "plugins": []}
        self.assert_invalid(legacy, "schemaVersion")
        self.assert_invalid(legacy, "未知字段")

        data = make_catalog()
        data["extensions"][0]["author"] = "legacy"
        self.assert_invalid(data, "未知字段")

    def test_rejects_unknown_fields_at_every_level_and_catalog_public_key(self) -> None:
        mutations = [
            ([], "publicKey", "目录"),
            (["extensions", 0], "manifest", "extensions[0]"),
            (["extensions", 0, "releases", 0], "packageSize", "releases[0]"),
            (["extensions", 0, "releases", 0, "signature"], "publicKey", "signature"),
        ]
        for path, field, expected in mutations:
            with self.subTest(field=field):
                data = make_catalog()
                target = data
                for part in path:
                    target = target[part]
                target[field] = "forbidden"
                self.assert_invalid(data, expected)

    def test_rejects_invalid_extension_and_publisher_ids(self) -> None:
        for field, value in (
            ("id", "Log-Analyzer"),
            ("id", "log--analyzer"),
            ("publisherId", "thelinyue."),
            ("publisherId", "the_linyue"),
        ):
            with self.subTest(field=field, value=value):
                data = make_catalog()
                data["extensions"][0][field] = value
                self.assert_invalid(data, field)

    def test_rejects_invalid_semver(self) -> None:
        for field, value in (
            ("version", "2.0"),
            ("version", "02.0.0"),
            ("version", "2.0.0-01"),
            ("minHostVersion", "v2.0.0"),
        ):
            with self.subTest(field=field, value=value):
                data = make_catalog()
                data["extensions"][0]["releases"][0][field] = value
                self.assert_invalid(data, field)

    def test_accepts_semver_prerelease_and_build_metadata(self) -> None:
        data = make_catalog()
        release = data["extensions"][0]["releases"][0]
        release["version"] = "2.1.0-rc.1+build.7"
        release["minHostVersion"] = "2.0.0+release.1"
        self.assertEqual([], validate_catalog(data))

    def test_rejects_non_https_url_non_positive_size_and_invalid_sha(self) -> None:
        cases = (
            ("url", "http://example.test/package.zip"),
            ("size", 0),
            ("size", -1),
            ("size", True),
            ("sha256", "g" * 64),
            ("sha256", "0" * 63),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                data = make_catalog()
                data["extensions"][0]["releases"][0][field] = value
                self.assert_invalid(data, field)

    def test_accepts_https_url_with_valid_hostname_and_port(self) -> None:
        for url in (
            "https://example.test:443/releases/package.zip",
            "https://[2001:db8::1]:443/releases/package.zip",
        ):
            with self.subTest(url=url):
                data = make_catalog()
                data["extensions"][0]["releases"][0]["url"] = url
                self.assertEqual([], validate_catalog(data))

    def test_rejects_https_urls_the_host_cannot_parse(self) -> None:
        for url in (
            "https://[invalid/releases/package.zip",
            "https://example.test:bad/releases/package.zip",
            "https://exa mple.test/releases/package.zip",
            "https://bad..example.test/releases/package.zip",
            "https://example.test|evil/releases/package.zip",
            "https://example.test\\@evil.test/releases/package.zip",
            "https:///releases/package.zip",
            "https://example.test/releases/\npackage.zip",
        ):
            with self.subTest(url=url):
                data = make_catalog()
                data["extensions"][0]["releases"][0]["url"] = url
                self.assert_invalid(data, "绝对 HTTPS 地址")

    def test_release_size_matches_host_download_boundary(self) -> None:
        data = make_catalog()
        data["extensions"][0]["releases"][0]["size"] = MAX_PACKAGE_BYTES
        self.assertEqual([], validate_catalog(data))

        for size in (MAX_PACKAGE_BYTES + 1, 2**63):
            with self.subTest(size=size):
                data = make_catalog()
                data["extensions"][0]["releases"][0]["size"] = size
                self.assert_invalid(data, str(MAX_PACKAGE_BYTES))

    def test_rejects_invalid_ed25519_signature(self) -> None:
        for value in ("not-base64", base64.b64encode(bytes(63)).decode("ascii"), ""):
            with self.subTest(value=value):
                data = make_catalog()
                data["extensions"][0]["releases"][0]["signature"]["signature"] = value
                self.assert_invalid(data, "signature")

    def test_rejects_blank_key_id_and_unknown_kind(self) -> None:
        data = make_catalog()
        data["extensions"][0]["releases"][0]["signature"]["keyId"] = "  "
        self.assert_invalid(data, "keyId")

        data = make_catalog()
        data["extensions"][0]["kind"] = "tool"
        self.assert_invalid(data, "kind")

    def test_rejects_duplicate_extension_ids_and_release_versions(self) -> None:
        data = make_catalog()
        data["extensions"].append(copy.deepcopy(data["extensions"][0]))
        self.assert_invalid(data, "重复扩展")

        data = make_catalog()
        data["extensions"][0]["releases"].append(make_release())
        self.assert_invalid(data, "重复版本")

    def test_rejects_missing_or_empty_release_list(self) -> None:
        data = make_catalog()
        data["extensions"][0]["releases"] = []
        self.assert_invalid(data, "releases")

        data = make_catalog()
        del data["extensions"][0]["releases"]
        self.assert_invalid(data, "缺少字段")

    def test_checked_in_catalog_uses_valid_v2_contract(self) -> None:
        with (REPOSITORY_ROOT / "catalog.json").open("r", encoding="utf-8") as stream:
            catalog = json.load(stream)
        self.assertEqual([], validate_catalog(catalog))
        self.assertEqual(
            {"schemaVersion": 2, "extensions": []},
            catalog,
            "真实签名资产准备完成前，公开 Catalog 必须保持为空。",
        )
        forbidden = {
            "plugins",
            "author",
            "category",
            "reportPath",
            "manifest",
            "minimumAppVersion",
            "packageUrl",
            "packageSize",
            "publicKey",
        }
        self.assertTrue(forbidden.isdisjoint(collect_object_keys(catalog)))

    def test_schema_and_template_describe_only_v2_catalog_fields(self) -> None:
        with (REPOSITORY_ROOT / "schema" / "catalog.schema.json").open("r", encoding="utf-8") as stream:
            schema = json.load(stream)
        self.assertEqual(["schemaVersion", "extensions"], schema["required"])
        self.assertEqual(2, schema["properties"]["schemaVersion"]["const"])
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("extension", schema["$defs"])
        self.assertIn("release", schema["$defs"])
        self.assertIn("signature", schema["$defs"])
        self.assertNotIn("manifest", schema["$defs"])
        self.assertEqual(
            MAX_PACKAGE_BYTES,
            schema["$defs"]["release"]["properties"]["size"]["maximum"],
        )

        with (REPOSITORY_ROOT / "templates" / "extension-entry.json").open("r", encoding="utf-8") as stream:
            extension = json.load(stream)
        self.assertEqual([], validate_catalog({"schemaVersion": 2, "extensions": [extension]}))


if __name__ == "__main__":
    unittest.main()
