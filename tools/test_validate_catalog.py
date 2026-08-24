#!/usr/bin/env python3
"""Hephaestus Workbench 扩展目录 v2 校验器回归测试。"""

from __future__ import annotations

import base64
import copy
import json
import re
import unittest
from pathlib import Path

from validate_catalog import HTTPS_URL_PATTERN_TEXT, validate_catalog


VALID_SIGNATURE = base64.b64encode(bytes(range(64))).decode("ascii")
VALID_SHA256 = "0123456789abcdef" * 4
MAX_PACKAGE_BYTES = 209_715_200
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DNS_LABEL_63 = "a" * 63
DNS_LABEL_64 = "a" * 64
DNS_HOST_253 = ".".join(("a" * 63, "b" * 63, "c" * 63, "d" * 61))
DNS_HOST_254 = ".".join(("a" * 63, "b" * 63, "c" * 63, "d" * 62))
RELEASE_URL_CORPUS = (
    # 基础 HTTPS、DNS、IPv4 和端口边界。
    ("https://example.test/releases/package.zip", True),
    ("HTTPS://downloads.example.test:443/releases/package.zip?source=catalog", True),
    ("https://192.0.2.1/releases/package.zip", True),
    ("https://192.0.2.1:443/releases/package.zip", True),
    ("https://example.test:0443/releases/package.zip", False),
    ("https://example.test:444/releases/package.zip", False),
    ("https://example.test:bad/releases/package.zip", False),
    ("https://example.test:/releases/package.zip", False),
    # DNS label、总长和尾随根点边界。
    (f"https://{DNS_LABEL_63}.example/releases/package.zip", True),
    (f"https://{DNS_LABEL_64}.example/releases/package.zip", False),
    ("https://good-label.example/releases/package.zip", True),
    ("https://-leading.example/releases/package.zip", False),
    ("https://trailing-.example/releases/package.zip", False),
    (f"https://{DNS_HOST_253}/releases/package.zip", True),
    (f"https://{DNS_HOST_253}:443/releases/package.zip", True),
    (f"https://{DNS_HOST_254}/releases/package.zip", False),
    ("https://example.test./releases/package.zip", False),
    ("https://bad..example.test/releases/package.zip", False),
    ("https://bad_name.example.test/releases/package.zip", False),
    ("https://例子.测试/releases/package.zip", False),
    # 严格 IPv4 与非法纯数字主机。
    ("https://0.0.0.0/releases/package.zip", True),
    ("https://255.255.255.255/releases/package.zip", True),
    ("https://256.0.0.1/releases/package.zip", False),
    ("https://01.2.3.4/releases/package.zip", False),
    ("https://1.2.3/releases/package.zip", False),
    ("https://1.2.3.4.5/releases/package.zip", False),
    ("https://999.999.999.999/releases/package.zip", False),
    ("https://1234/releases/package.zip", False),
    # 所有方括号 authority 均拒绝。
    ("https://[2001:db8::1]/releases/package.zip", False),
    ("https://[2001:db8::1]:443/releases/package.zip", False),
    ("https://[fe80::1%25eth0]/releases/package.zip", False),
    ("https://[:::]/releases/package.zip", False),
    ("https://[192.0.2.1]/releases/package.zip", False),
    ("https://[v1.fe80::]/releases/package.zip", False),
    ("https://[invalid/releases/package.zip", False),
    # 凭据、fragment、反斜杠和控制字符。
    ("https://@example.test/releases/package.zip", False),
    ("https://user@example.test/releases/package.zip", False),
    ("https://user:password@example.test/releases/package.zip", False),
    ("https://example.test/releases/package.zip#", False),
    ("https://example.test/releases/package.zip#fragment", False),
    ("https://example.test\\evil.test/releases/package.zip", False),
    ("https://example.test\\@evil.test/releases/package.zip", False),
    ("https://example.test/releases/\npackage.zip", False),
    ("https://example.test/releases/\rpackage.zip", False),
    ("https://example.test/releases/\r\npackage.zip", False),
    ("https://example.test/releases/package.zip\n", False),
    ("https://example.test/releases/package.zip\r", False),
    ("https://example.test/releases/package.zip\r\n", False),
    # 百分号编码、query-only、空 query 和复杂 query。
    ("https://example.test/releases/%5Bpackage%5D.zip", True),
    ("https://example.test/releases/%5bpackage%5d.zip", True),
    ("https://example.test/releases/package.zip?name=%5Bpackage%5D", True),
    ("https://example.test/releases/package.zip?", True),
    ("https://example.test?download=1", True),
    ("https://example.test/releases/package.zip?name=v2.0.0+build%201&mode=full;source=catalog", True),
    ("https://example.test/releases/package%.zip", False),
    ("https://example.test/releases/package%5.zip", False),
    ("https://example.test/releases/package%GG.zip", False),
    # 原始方括号不得出现在 path/query，只允许百分号编码。
    ("https://example.test/releases/[package].zip", False),
    ("https://example.test/releases/package.zip?name=[package]", False),
    ("https://example.test/releases/package.zip?left=%5B&right=%5D", True),
    ("https:///releases/package.zip", False),
)


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

    def test_release_url_corpus_matches_python_validator(self) -> None:
        self.assertEqual(253, len(DNS_HOST_253))
        self.assertEqual(254, len(DNS_HOST_254))
        for url, expected in RELEASE_URL_CORPUS:
            with self.subTest(url=url):
                data = make_catalog()
                data["extensions"][0]["releases"][0]["url"] = url
                self.assertEqual(expected, validate_catalog(data) == [])

    def test_release_url_corpus_matches_schema_pattern_without_format(self) -> None:
        with (REPOSITORY_ROOT / "schema" / "catalog.schema.json").open("r", encoding="utf-8") as stream:
            schema = json.load(stream)
        url_pattern = re.compile(schema["$defs"]["release"]["properties"]["url"]["pattern"])

        for url, expected in RELEASE_URL_CORPUS:
            with self.subTest(url=url):
                self.assertEqual(
                    expected,
                    url_pattern.search(url) is not None,
                    "Schema pattern 必须独立完成安全边界，不能依赖 format assertion。",
                )

    def test_release_url_corpus_has_no_validator_schema_drift(self) -> None:
        with (REPOSITORY_ROOT / "schema" / "catalog.schema.json").open("r", encoding="utf-8") as stream:
            schema = json.load(stream)
        url_pattern = re.compile(schema["$defs"]["release"]["properties"]["url"]["pattern"])

        for url, _ in RELEASE_URL_CORPUS:
            data = make_catalog()
            data["extensions"][0]["releases"][0]["url"] = url
            with self.subTest(url=url):
                self.assertEqual(
                    validate_catalog(data) == [],
                    url_pattern.search(url) is not None,
                )

    def test_release_url_pattern_source_is_identical_in_schema_and_validator(self) -> None:
        with (REPOSITORY_ROOT / "schema" / "catalog.schema.json").open("r", encoding="utf-8") as stream:
            schema = json.load(stream)
        self.assertEqual(
            HTTPS_URL_PATTERN_TEXT,
            schema["$defs"]["release"]["properties"]["url"]["pattern"],
        )

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

    def test_accepts_safe_key_id_boundaries(self) -> None:
        for key_id in ("a", "Official.Release_Key-2026", "A" * 64):
            with self.subTest(key_id=key_id):
                data = make_catalog()
                data["extensions"][0]["releases"][0]["signature"]["keyId"] = key_id
                self.assertEqual([], validate_catalog(data))

    def test_rejects_unsafe_key_ids_and_unknown_kind(self) -> None:
        for key_id in (
            "",
            "  ",
            " leading",
            "trailing ",
            "line\nbreak",
            "control\x00character",
            ".hidden",
            "../official-key",
            "keys/official-key",
            "keys\\official-key",
            "密钥",
            "A" * 65,
        ):
            with self.subTest(key_id=key_id):
                data = make_catalog()
                data["extensions"][0]["releases"][0]["signature"]["keyId"] = key_id
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

        key_id_schema = schema["$defs"]["signature"]["properties"]["keyId"]
        self.assertEqual(1, key_id_schema["minLength"])
        self.assertEqual(64, key_id_schema["maxLength"])
        key_id_pattern = re.compile(key_id_schema["pattern"])
        self.assertIsNotNone(key_id_pattern.fullmatch("Official.Release_Key-2026"))
        for key_id in (".hidden", "../official-key", "密钥", "A" * 65):
            with self.subTest(schema_key_id=key_id):
                self.assertIsNone(key_id_pattern.fullmatch(key_id))

        with (REPOSITORY_ROOT / "templates" / "extension-entry.json").open("r", encoding="utf-8") as stream:
            extension = json.load(stream)
        self.assertEqual([], validate_catalog({"schemaVersion": 2, "extensions": [extension]}))


if __name__ == "__main__":
    unittest.main()
