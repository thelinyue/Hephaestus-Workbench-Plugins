#!/usr/bin/env python3
"""release-metadata v2 离线消费工具的契约测试。"""

from __future__ import annotations

import base64
import contextlib
import io
import hashlib
import json
import socket
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

from import_release_metadata import MetadataValidationError, build_catalog_update, main


VALID_SIGNATURE = base64.b64encode(bytes(64)).decode("ascii")


def make_manifest() -> dict[str, object]:
    """构造一个完整且最小的 ExtensionManifestV2 输入。"""
    return {
        "schemaVersion": 2,
        "id": "log-analyzer",
        "name": "日志分析",
        "version": "2.0.0",
        "kind": "analysis",
        "publisherId": "thelinyue",
        "hostApiVersion": "1.0",
        "minHostVersion": "2.0.0",
        "runtime": {
            "kind": "content",
        },
        "capabilities": ["analysis.rule-pack"],
        "permissions": [],
        "dependencies": [],
    }


def make_catalog(releases: list[dict[str, object]] | None = None) -> dict[str, object]:
    """构造含已审核扩展条目的 Catalog；description 只在 Catalog 中存在。"""
    if releases is None:
        releases = [
            {
                "version": "1.0.0",
                "minHostVersion": "2.0.0",
                "url": "https://example.test/releases/log-analyzer-1.0.0.zip",
                "size": 123,
                "sha256": "0" * 64,
                "signature": {"keyId": "test-key", "signature": VALID_SIGNATURE},
            }
        ]
    return {
        "schemaVersion": 2,
        "extensions": [
            {
                "id": "log-analyzer",
                "name": "日志分析",
                "description": "综合日志分析扩展。",
                "publisherId": "thelinyue",
                "kind": "analysis",
                "releases": releases,
            }
        ],
    }


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_zip(path: Path, manifest: dict[str, object], extra_entries: list[tuple[str, bytes]] | None = None) -> None:
    """写入测试 ZIP；调用方可显式添加异常入口。"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for name, content in extra_entries or []:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(name, content)


class ReleaseMetadataImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.zip_path = self.root / "log-analyzer-2.0.0.zip"
        self.metadata_path = self.root / "release-metadata.json"
        self.catalog_path = self.root / "catalog.json"
        self.manifest = make_manifest()
        write_zip(self.zip_path, self.manifest)
        write_json(self.catalog_path, make_catalog())

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def metadata(self) -> dict[str, object]:
        content = self.zip_path.read_bytes()
        return {
            "schemaVersion": 2,
            "generatedAtUtc": "2026-08-24T00:00:00Z",
            "packages": [
                {
                    "manifest": self.manifest,
                    "file": self.zip_path.name,
                    "url": f"https://example.test/releases/{self.zip_path.name}",
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "keyId": "test-key",
                    "signature": VALID_SIGNATURE,
                }
            ],
        }

    def write_inputs(self, metadata: dict[str, object] | None = None) -> dict[str, object]:
        data = self.metadata() if metadata is None else metadata
        write_json(self.metadata_path, data)
        return data

    def assert_rejected(self, text: str, metadata: dict[str, object] | None = None) -> None:
        self.write_inputs(metadata)
        with self.assertRaisesRegex(MetadataValidationError, text):
            build_catalog_update(self.metadata_path, self.zip_path, self.catalog_path)

    def test_rejects_manifest_identity_or_full_content_not_identical_to_zip_manifest(self) -> None:
        for field, value in (("id", "other-analyzer"), ("capabilities", ["analysis.report-template"])):
            with self.subTest(field=field):
                metadata = self.metadata()
                package = metadata["packages"][0]
                assert isinstance(package, dict)
                manifest = package["manifest"]
                assert isinstance(manifest, dict)
                manifest[field] = value
                self.assert_rejected("manifest 与 ZIP 根目录 manifest.json 不完全一致", metadata)

    def test_rejects_wrong_zip_size_or_sha256(self) -> None:
        for field, value in (("size", 1), ("sha256", "0" * 64)):
            with self.subTest(field=field):
                metadata = self.metadata()
                package = metadata["packages"][0]
                assert isinstance(package, dict)
                package[field] = value
                self.assert_rejected(field, metadata)

    def test_rejects_file_or_url_last_segment_not_matching_local_zip_name(self) -> None:
        metadata = self.metadata()
        package = metadata["packages"][0]
        assert isinstance(package, dict)
        package["file"] = "another.zip"
        self.assert_rejected("file", metadata)

        metadata = self.metadata()
        package = metadata["packages"][0]
        assert isinstance(package, dict)
        package["url"] = "https://example.test/releases/another.zip"
        self.assert_rejected("url", metadata)

    def test_rejects_catalog_extension_identity_not_matching_manifest(self) -> None:
        catalog = make_catalog()
        extension = catalog["extensions"][0]
        assert isinstance(extension, dict)
        extension["publisherId"] = "other-publisher"
        write_json(self.catalog_path, catalog)

        self.assert_rejected("publisherId", self.metadata())

    def test_rejects_duplicate_catalog_version_with_different_release_data(self) -> None:
        existing = {
            "version": "2.0.0",
            "minHostVersion": "2.0.0",
            "url": "https://example.test/releases/log-analyzer-2.0.0.zip",
            "size": 123,
            "sha256": "0" * 64,
            "signature": {"keyId": "test-key", "signature": VALID_SIGNATURE},
        }
        write_json(self.catalog_path, make_catalog([existing]))

        self.assert_rejected("重复版本", self.metadata())

    def test_rejects_unknown_root_package_or_manifest_fields_without_parsing_latest(self) -> None:
        cases: list[tuple[str, str, dict[str, object]]] = []

        metadata = self.metadata()
        metadata["latest"] = "https://example.test/latest.json"
        cases.append(("root", "未知字段：latest", metadata))

        metadata = self.metadata()
        package = metadata["packages"][0]
        assert isinstance(package, dict)
        package["publicKey"] = "not-allowed"
        cases.append(("package", "未知字段：publicKey", metadata))

        metadata = self.metadata()
        package = metadata["packages"][0]
        assert isinstance(package, dict)
        manifest = package["manifest"]
        assert isinstance(manifest, dict)
        manifest["description"] = "manifest v2 does not contain this field"
        cases.append(("manifest", "未知字段：description", metadata))

        for label, expected, candidate in cases:
            with self.subTest(level=label):
                self.assert_rejected(expected, candidate)

    def test_rejects_missing_contract_fields_and_invalid_signature_format(self) -> None:
        metadata = self.metadata()
        del metadata["generatedAtUtc"]
        self.assert_rejected("缺少字段：generatedAtUtc", metadata)

        metadata = self.metadata()
        package = metadata["packages"][0]
        assert isinstance(package, dict)
        del package["keyId"]
        self.assert_rejected("缺少字段：keyId", metadata)

        metadata = self.metadata()
        package = metadata["packages"][0]
        assert isinstance(package, dict)
        manifest = package["manifest"]
        assert isinstance(manifest, dict)
        del manifest["runtime"]
        self.assert_rejected("缺少字段：runtime", metadata)

        metadata = self.metadata()
        package = metadata["packages"][0]
        assert isinstance(package, dict)
        package["signature"] = "not-base64"
        self.assert_rejected("64 字节", metadata)

    def test_rejects_new_extension_because_metadata_cannot_supply_catalog_description(self) -> None:
        write_json(self.catalog_path, {"schemaVersion": 2, "extensions": []})

        self.assert_rejected("description", self.metadata())

    def test_rejects_duplicate_manifest_and_path_anomaly_in_zip(self) -> None:
        write_zip(
            self.zip_path,
            self.manifest,
            [("manifest.json", b"{}"), ("payload/../escape.txt", b"bad")],
        )
        self.assert_rejected("重复 manifest.json", self.metadata())

        write_zip(self.zip_path, self.manifest, [("payload/../escape.txt", b"bad")])
        self.assert_rejected("路径异常", self.metadata())

        write_zip(self.zip_path, self.manifest, [("payload//ambiguous.txt", b"bad")])
        self.assert_rejected("路径异常", self.metadata())

    def test_check_and_output_modes_are_offline_and_never_modify_input_catalog(self) -> None:
        self.write_inputs()
        catalog_before = self.catalog_path.read_bytes()
        output_path = self.root / "updated-catalog.json"

        with (
            mock.patch.object(socket, "create_connection", side_effect=AssertionError("不得联网")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                0,
                main(
                    [
                        "--metadata",
                        str(self.metadata_path),
                        "--zip",
                        str(self.zip_path),
                        "--catalog",
                        str(self.catalog_path),
                        "--check",
                    ]
                ),
            )
            self.assertEqual(
                0,
                main(
                    [
                        "--metadata",
                        str(self.metadata_path),
                        "--zip",
                        str(self.zip_path),
                        "--catalog",
                        str(self.catalog_path),
                        "--output",
                        str(output_path),
                    ]
                ),
            )

            self.assertEqual(catalog_before, self.catalog_path.read_bytes())
            first_output = output_path.read_bytes()
            output_catalog = json.loads(first_output)
            output_release = output_catalog["extensions"][0]["releases"][-1]
            package = self.metadata()["packages"][0]
            assert isinstance(package, dict)
            manifest = package["manifest"]
            assert isinstance(manifest, dict)
            self.assertEqual(manifest["version"], output_release["version"])
            self.assertEqual(manifest["minHostVersion"], output_release["minHostVersion"])
            self.assertEqual(package["url"], output_release["url"])
            self.assertEqual(package["size"], output_release["size"])
            self.assertEqual(package["sha256"], output_release["sha256"])
            self.assertEqual(package["keyId"], output_release["signature"]["keyId"])
            self.assertEqual(package["signature"], output_release["signature"]["signature"])
            self.assertEqual(
                0,
                main(
                    [
                        "--metadata",
                        str(self.metadata_path),
                        "--zip",
                        str(self.zip_path),
                        "--catalog",
                        str(self.catalog_path),
                        "--output",
                        str(output_path),
                    ]
                ),
            )
        self.assertEqual(first_output, output_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
