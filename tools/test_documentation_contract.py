#!/usr/bin/env python3
"""防止公开贡献指引回退到 Workbench v1 扩展协议。"""

from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
PR_TEMPLATE = REPOSITORY_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
DEVELOPMENT_GUIDE = REPOSITORY_ROOT / "docs" / "plugin-development.md"


class DocumentationV2ContractTests(unittest.TestCase):
    def assert_contains_all(self, text: str, required: tuple[str, ...], source: Path) -> None:
        missing = [item for item in required if item not in text]
        self.assertFalse(missing, f"{source} 缺少 v2 指引：{missing}")

    def assert_contains_none(self, text: str, forbidden: tuple[str, ...], source: Path) -> None:
        found = [item for item in forbidden if item in text]
        self.assertFalse(found, f"{source} 仍包含 v1 指引：{found}")

    def test_pull_request_template_requires_v2_release_evidence(self) -> None:
        text = PR_TEMPLATE.read_text(encoding="utf-8")
        self.assert_contains_all(
            text,
            (
                "publisherId",
                "kind",
                "minHostVersion",
                "size",
                "SHA-256",
                "keyId",
                "Ed25519",
                "原始 ZIP 字节",
                "analysis-process-v1",
                "Report/index.html",
            ),
            PR_TEMPLATE,
        )
        self.assert_contains_none(
            text,
            (
                "catalog.json` 中的 `manifest`",
                "report.html",
                '"type": "Exe"',
                "legacy-log-analyzer",
            ),
            PR_TEMPLATE,
        )

    def test_development_guide_documents_manifest_catalog_and_process_v2_only(self) -> None:
        text = DEVELOPMENT_GUIDE.read_text(encoding="utf-8")
        self.assert_contains_all(
            text,
            (
                '"schemaVersion": 2',
                '"publisherId"',
                '"hostApiVersion"',
                '"minHostVersion"',
                '"runtime"',
                '"capabilities"',
                '"permissions"',
                '"dependencies"',
                '"extensions"',
                '"releases"',
                '"keyId"',
                '"signature"',
                "analysis-process-v1",
                "Report/index.html",
                "Ed25519",
                "原始 ZIP 字节",
                "不提供 v1 兼容",
            ),
            DEVELOPMENT_GUIDE,
        )
        self.assert_contains_none(
            text,
            (
                "schemaVersion` 当前为 `1`",
                "report.html",
                '"type": "Exe"',
                "legacy-log-analyzer",
                "PluginType.Dll",
                "IAnalysisPlugin",
                "保持旧字段可用",
                "兼容命令",
            ),
            DEVELOPMENT_GUIDE,
        )


if __name__ == "__main__":
    unittest.main()
