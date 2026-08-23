#!/usr/bin/env python3
"""以结构化契约保护公开 v2 文档与文档相关 CI。"""

from __future__ import annotations

import fnmatch
import json
import re
import unittest
from pathlib import Path

from validate_catalog import validate_catalog


ROOT = Path(__file__).resolve().parent.parent
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
DEVELOPMENT_GUIDE = ROOT / "docs" / "plugin-development.md"
README = ROOT / "README.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
WORKFLOW = ROOT / ".github" / "workflows" / "validate-catalog.yml"
FENCE_PATTERN = re.compile(
    r"```json[ \t]*\r?\n(?P<body>.*?)```",
    re.IGNORECASE | re.DOTALL,
)
V1_FIELDS = {
    "author",
    "category",
    "manifest",
    "minimumAppVersion",
    "packageSize",
    "packageUrl",
    "releaseNotesUrl",
    "reportPath",
    "type",
}
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
MANIFEST_MATRIX = {
    ("workspace", "web"): {
        "runtime_fields": {"kind", "entry"},
        "capabilities": {"workspace.page"},
        "permissions": {"workspace.readText"},
    },
    ("analysis", "process"): {
        "runtime_fields": {"kind", "protocol", "entry"},
        "capabilities": {
            "analysis.engine",
            "analysis.scope.comprehensive",
            "analysis.scope.storage",
        },
        "permissions": set(),
    },
    ("analysis", "content"): {
        "runtime_fields": {"kind"},
        "capabilities": {"analysis.rule-pack", "analysis.report-template"},
        "permissions": set(),
    },
    ("maintenance", "content"): {
        "runtime_fields": {"kind"},
        "capabilities": {"maintenance.workflow-pack", "maintenance.command-profile"},
        "permissions": set(),
    },
}


def machine_blocks(text: str) -> list[str]:
    """提取标记为 json 的 fenced 代码块；其他语言不进入机器契约。"""
    return [match.group("body").strip() for match in FENCE_PATTERN.finditer(text)]


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(child) for child in value.values()), set())
    if isinstance(value, list):
        return set().union(*(nested_keys(child) for child in value), set())
    return set()


def machine_contract_errors(text: str) -> list[str]:
    """只检查严格 fenced JSON 的机器字段，不解释自然语言或其他代码块。"""
    errors: list[str] = []
    for index, body in enumerate(machine_blocks(text), start=1):
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exception:
            errors.append(f"代码块 {index} JSON 无法解析：第 {exception.lineno} 行。")
            continue
        root = data if isinstance(data, dict) else {}
        keys = nested_keys(data)
        schema_version = root.get("schemaVersion")
        root_plugins = "plugins" in root

        if schema_version in (1, "1"):
            errors.append(f"代码块 {index} 使用 schemaVersion 1。")
        if root_plugins:
            errors.append(f"代码块 {index} 使用 plugins 根字段。")
        legacy = sorted(keys & V1_FIELDS)
        if legacy:
            errors.append(f"代码块 {index} 包含 v1 字段：{legacy}。")
    return errors


def parsed_json_examples(text: str) -> list[dict[str, object]]:
    return [
        data
        for body in machine_blocks(text)
        for data in [json.loads(body)]
        if isinstance(data, dict)
    ]


def workflow_paths(text: str, event: str) -> set[str]:
    event_match = re.search(rf"^  {re.escape(event)}:\s*$\n(?P<body>.*?)(?=^  \S|\Z)", text, re.MULTILINE | re.DOTALL)
    if event_match is None:
        return set()
    paths_match = re.search(r"^    paths:\s*$\n(?P<body>(?:      - .+\n?)+)", event_match.group("body"), re.MULTILINE)
    return set() if paths_match is None else set(re.findall(r'^      - ["\'](.+)["\']$', paths_match.group("body"), re.MULTILINE))


class DocumentationV2ContractTests(unittest.TestCase):
    def test_pull_request_template_requires_v2_release_evidence(self) -> None:
        text = PR_TEMPLATE.read_text(encoding="utf-8")
        self.assertEqual([], machine_contract_errors(text))
        identifiers = set(re.findall(r"`([A-Za-z][A-Za-z0-9.]*)`", text))
        self.assertTrue(
            {"publisherId", "kind", "version", "minHostVersion", "url", "size", "keyId", "signature"}
            <= identifiers
        )
        self.assertIn("SHA-256", text)
        checklist = [line for line in text.splitlines() if line.startswith("- [ ]")]
        self.assertTrue(any("Ed25519" in line and "原始 ZIP 字节" in line for line in checklist))
        self.assertTrue(any("Catalog" in line and "不内嵌 manifest" in line and "不携带公钥" in line for line in checklist))
        self.assertTrue(any("固定入口" in line and "Report/index.html" in line for line in checklist))

    def test_document_examples_are_v2_and_catalog_uses_real_validator(self) -> None:
        text = DEVELOPMENT_GUIDE.read_text(encoding="utf-8")
        self.assertEqual([], machine_contract_errors(text))
        examples = parsed_json_examples(text)

        catalogs = [example for example in examples if "extensions" in example]
        self.assertTrue(catalogs)
        for catalog in catalogs:
            self.assertEqual([], validate_catalog(catalog))

        manifests = [example for example in examples if "runtime" in example]
        self.assertTrue(manifests)
        for manifest in manifests:
            self.assertEqual(2, manifest["schemaVersion"])
            self.assertEqual(MANIFEST_FIELDS, set(manifest))

        for requirement in ("analysis-process-v1", "Report/index.html", "Ed25519", "原始 ZIP 字节"):
            self.assertIn(requirement, text)

    def test_readme_manifest_examples_cover_complete_v2_matrix(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertEqual([], machine_contract_errors(text))
        manifests = [
            example
            for example in parsed_json_examples(text)
            if set(example) == MANIFEST_FIELDS
        ]
        actual = {}
        for manifest in manifests:
            self.assertEqual(2, manifest["schemaVersion"])
            runtime = manifest["runtime"]
            self.assertIsInstance(runtime, dict)
            combination = (manifest["kind"], runtime["kind"])
            self.assertNotIn(combination, actual, f"README 重复 manifest 组合：{combination}")
            actual[combination] = manifest

        self.assertEqual(set(MANIFEST_MATRIX), set(actual))
        for combination, expected in MANIFEST_MATRIX.items():
            with self.subTest(combination=combination):
                manifest = actual[combination]
                runtime = manifest["runtime"]
                capabilities = manifest["capabilities"]
                permissions = manifest["permissions"]
                self.assertEqual(expected["runtime_fields"], set(runtime))
                self.assertEqual(expected["capabilities"], set(capabilities))
                self.assertEqual(len(capabilities), len(set(capabilities)))
                self.assertEqual(expected["permissions"], set(permissions))
                self.assertEqual(len(permissions), len(set(permissions)))
                if combination == ("analysis", "process"):
                    self.assertEqual("analysis-process-v1", runtime["protocol"])
                if combination[1] in {"process", "web"}:
                    self.assertTrue(runtime["entry"])

    def test_publication_docs_state_url_and_key_id_security_boundary(self) -> None:
        for source in (README, CONTRIBUTING):
            with self.subTest(source=source.name):
                text = source.read_text(encoding="utf-8")
                self.assertIn("不得包含用户名或密码", text)
                self.assertIn("fragment", text)
                self.assertIn("显式空端口", text)
                self.assertIn("只能省略端口或显式使用 `443`", text)
                self.assertIn("ASCII DNS", text)
                self.assertIn("严格 IPv4", text)
                self.assertIn("不支持 IPv6", text)
                self.assertIn("scoped IPv6", text)
                self.assertIn("路径和查询只允许 ASCII URI 字符", text)
                self.assertIn("[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})", text)

    def test_natural_language_denials_do_not_trigger_machine_checks(self) -> None:
        self.assertEqual([], machine_contract_errors("明确禁止 report.html 和 IAnalysisPlugin，不接受旧协议。"))

    def test_actual_v1_json_examples_fail(self) -> None:
        example = '''```json
{"schemaVersion": 1, "plugins": [{"packageUrl": "https://example.test/old.zip"}]}
```'''
        errors = machine_contract_errors(example)
        self.assertTrue(any("schemaVersion 1" in error for error in errors))
        self.assertTrue(any("plugins 根字段" in error for error in errors))
        self.assertTrue(any("packageUrl" in error for error in errors))

    def test_non_json_fences_are_not_machine_contracts(self) -> None:
        example = '''```yaml
schemaVersion: 1
description: "迁移说明, type: process"
plugins:
  - packageSize: 100
```'''
        self.assertEqual([], machine_blocks(example))
        self.assertEqual([], machine_contract_errors(example))

    def test_actual_v1_manifest_json_fields_fail(self) -> None:
        example = """```json
{"id": "legacy-analyzer", "type": "Exe", "reportPath": "report/report.html"}
```"""
        errors = " ".join(machine_contract_errors(example))
        self.assertIn("type", errors)
        self.assertIn("reportPath", errors)

    def test_readme_keeps_catalog_empty_until_real_signed_assets_exist(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertIn("真实签名资产", text)
        self.assertIn("extensions` 必须保持为空", text)
        self.assertNotIn("replace-before-release", text)

    def test_protected_documents_trigger_push_and_pull_request(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for event in ("push", "pull_request"):
            patterns = workflow_paths(text, event)
            for changed_path in ("docs/plugin-development.md", ".github/PULL_REQUEST_TEMPLATE.md"):
                with self.subTest(event=event, path=changed_path):
                    self.assertTrue(any(fnmatch.fnmatchcase(changed_path, pattern) for pattern in patterns))


if __name__ == "__main__":
    unittest.main()
