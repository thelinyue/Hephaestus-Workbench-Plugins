#!/usr/bin/env python3
"""以结构化契约保护公开 v2 文档与文档相关 CI。"""

from __future__ import annotations

import fnmatch
import json
import re
import textwrap
import unittest
from pathlib import Path

from validate_catalog import validate_catalog


ROOT = Path(__file__).resolve().parent.parent
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
DEVELOPMENT_GUIDE = ROOT / "docs" / "plugin-development.md"
WORKFLOW = ROOT / ".github" / "workflows" / "validate-catalog.yml"
FENCE_PATTERN = re.compile(
    r"```(?P<language>json|yaml|yml)\s*\r?\n(?P<body>.*?)```",
    re.IGNORECASE | re.DOTALL,
)
V1_RELEASE_FIELDS = {
    "author",
    "category",
    "manifest",
    "minimumAppVersion",
    "packageSize",
    "packageUrl",
    "releaseNotesUrl",
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


def machine_blocks(text: str) -> list[tuple[str, str]]:
    return [
        (match.group("language").lower(), match.group("body").strip())
        for match in FENCE_PATTERN.finditer(text)
    ]


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(child) for child in value.values()), set())
    if isinstance(value, list):
        return set().union(*(nested_keys(child) for child in value), set())
    return set()


def machine_contract_errors(text: str) -> list[str]:
    """只检查 fenced JSON/YAML 的机器字段，不解释自然语言。"""
    errors: list[str] = []
    for index, (language, body) in enumerate(machine_blocks(text), start=1):
        if language == "json":
            try:
                data = json.loads(body)
            except json.JSONDecodeError as exception:
                errors.append(f"代码块 {index} JSON 无法解析：第 {exception.lineno} 行。")
                continue
            root = data if isinstance(data, dict) else {}
            keys = nested_keys(data)
            schema_version = root.get("schemaVersion")
            root_plugins = "plugins" in root
        else:
            entries = []
            for line in textwrap.dedent(body).splitlines():
                match = re.match(
                    r"^(?P<indent>\s*)(?:-\s+)?(?P<key>[A-Za-z][A-Za-z0-9]*):(?:\s*(?P<value>[^#]*?))?\s*$",
                    line,
                )
                if match:
                    entries.append((len(match.group("indent")), match.group("key"), (match.group("value") or "").strip(" '\"")))
            keys = {key for _, key, _ in entries}
            schema_version = next((value for _, key, value in entries if key == "schemaVersion"), None)
            root_plugins = any(indent == 0 and key == "plugins" for indent, key, _ in entries)

        if schema_version in (1, "1"):
            errors.append(f"代码块 {index} 使用 schemaVersion 1。")
        if root_plugins:
            errors.append(f"代码块 {index} 使用 plugins 根字段。")
        legacy = sorted(keys & V1_RELEASE_FIELDS)
        if legacy:
            errors.append(f"代码块 {index} 包含 v1 release 字段：{legacy}。")
    return errors


def parsed_json_examples(text: str) -> list[dict[str, object]]:
    return [
        data
        for language, body in machine_blocks(text)
        if language == "json"
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

    def test_natural_language_denials_do_not_trigger_machine_checks(self) -> None:
        self.assertEqual([], machine_contract_errors("明确禁止 report.html 和 IAnalysisPlugin，不接受旧协议。"))

    def test_actual_v1_json_and_yaml_examples_fail(self) -> None:
        examples = (
            '''```json
{"schemaVersion": 1, "plugins": [{"packageUrl": "https://example.test/old.zip"}]}
```''',
            '''```yaml
schemaVersion: 1
plugins:
  - packageSize: 100
```''',
        )
        for example in examples:
            with self.subTest(example=example[:10]):
                errors = machine_contract_errors(example)
                self.assertTrue(any("schemaVersion 1" in error for error in errors))
                self.assertTrue(any("plugins 根字段" in error for error in errors))
                self.assertTrue(any(field in " ".join(errors) for field in ("packageUrl", "packageSize")))

    def test_protected_documents_trigger_push_and_pull_request(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for event in ("push", "pull_request"):
            patterns = workflow_paths(text, event)
            for changed_path in ("docs/plugin-development.md", ".github/PULL_REQUEST_TEMPLATE.md"):
                with self.subTest(event=event, path=changed_path):
                    self.assertTrue(any(fnmatch.fnmatchcase(changed_path, pattern) for pattern in patterns))


if __name__ == "__main__":
    unittest.main()
