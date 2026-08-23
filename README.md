# Hephaestus Workbench Extensions

这是 Hephaestus Workbench v2 的公开扩展目录仓库，只维护 Extension Catalog 和独立规则分发元数据，不存储扩展 ZIP、EXE、DLL 或签名私钥。

主目录 `catalog.json` 固定使用 `schemaVersion: 2`，结构与 Workbench PluginSDK 的 `ExtensionCatalogDocument` 一致：

```text
schemaVersion
extensions[]
  id / name / description / publisherId / kind
  releases[]
    version / minHostVersion / url / size / sha256
    signature
      keyId / signature
```

`kind` 只允许：

- `analysis`：受控独立进程或纯内容分析扩展；
- `workspace`：由工作台固定 Workspace Host 承载的页面；
- `maintenance`：只包含 Workflow/Command Profile 的维护内容包。

## manifest v2 允许矩阵

下面四个 JSON 示例完整覆盖 PluginSDK v2 允许的 kind/runtime 组合。为明确文档契约，示例列出各组合允许的全部 capability；实际扩展只应声明自身需要的能力，其中 `workspace/web` 必须包含 `workspace.page`，`analysis/process` 必须包含 `analysis.engine`。只有 workspace 可以声明非空 permissions，且每一项仍须落在发布密钥的宿主信任范围内。

```json
{
  "schemaVersion": 2,
  "id": "sample-workspace",
  "name": "示例工作区",
  "version": "2.0.0",
  "kind": "workspace",
  "publisherId": "thelinyue",
  "hostApiVersion": "1.0",
  "minHostVersion": "2.0.0",
  "runtime": {
    "kind": "web",
    "entry": "web/index.html"
  },
  "capabilities": ["workspace.page"],
  "permissions": ["workspace.readText"],
  "dependencies": []
}
```

```json
{
  "schemaVersion": 2,
  "id": "sample-analysis-process",
  "name": "示例分析进程",
  "version": "2.0.0",
  "kind": "analysis",
  "publisherId": "thelinyue",
  "hostApiVersion": "1.0",
  "minHostVersion": "2.0.0",
  "runtime": {
    "kind": "process",
    "protocol": "analysis-process-v1",
    "entry": "bin/analyzer.exe"
  },
  "capabilities": [
    "analysis.engine",
    "analysis.scope.comprehensive",
    "analysis.scope.storage"
  ],
  "permissions": [],
  "dependencies": []
}
```

```json
{
  "schemaVersion": 2,
  "id": "sample-analysis-content",
  "name": "示例分析内容包",
  "version": "2.0.0",
  "kind": "analysis",
  "publisherId": "thelinyue",
  "hostApiVersion": "1.0",
  "minHostVersion": "2.0.0",
  "runtime": {
    "kind": "content"
  },
  "capabilities": [
    "analysis.rule-pack",
    "analysis.report-template"
  ],
  "permissions": [],
  "dependencies": []
}
```

```json
{
  "schemaVersion": 2,
  "id": "sample-maintenance-content",
  "name": "示例维护内容包",
  "version": "2.0.0",
  "kind": "maintenance",
  "publisherId": "thelinyue",
  "hostApiVersion": "1.0",
  "minHostVersion": "2.0.0",
  "runtime": {
    "kind": "content"
  },
  "capabilities": [
    "maintenance.workflow-pack",
    "maintenance.command-profile"
  ],
  "permissions": [],
  "dependencies": []
}
```

runtime 字段集合是严格的：`web` 只能包含 `kind`、`entry`，`process` 只能包含 `kind`、`protocol`、`entry`，`content` 只能包含 `kind`。

目录不保存 manifest 副本，也不接受 v1 的 `type`、`author`、`category`、`reportPath`、`packageUrl`、`packageSize` 等字段。扩展 ZIP 根目录中的 `manifest.json` 由 Workbench 安装器在下载后独立校验。

## 签名与信任

每个 release 的 Ed25519 `signature` 覆盖原始 ZIP 字节。目录只保存 `keyId` 和 Base64 签名，**不能携带公钥**；`keyId` 是否受信任以及允许的发布者、扩展类别和权限范围，完全由 Workbench 内置信任表决定。

release `url` 必须是安全的绝对 HTTPS 地址：不得包含用户名或密码、fragment 或显式空端口，只能省略端口或显式使用 `443`；主机仅允许 ASCII DNS 名称（国际化域名须使用 punycode）或严格 IPv4；DNS 主机总长最多 253，不允许尾随根点；不支持 IPv6，包括标准无 scope IPv6、scoped IPv6 和 IPvFuture，也不接受方括号 IPv4。路径和查询只允许 ASCII URI 字符，其他字符必须使用百分号编码；原始 `[` 或 `]` 不允许，必须分别编码为 `%5B`/`%5D`。`keyId` 必须匹配 ASCII `[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})`（总长 1–64），不得包含空白、控制字符、路径片段或非 ASCII 字符。

当前尚无可公开发布的真实签名资产，因此 `catalog.json` 只保留 `schemaVersion: 2`，并且 `extensions` 必须保持为空。只有正式发布流水线生成最终 ZIP，并取得真实大小、SHA-256、受信 `keyId` 和 Ed25519 签名且完成反向校验后，才允许向目录加入 release；仓库不得保存或发布占位 release。

## 仓库结构

```text
catalog.json
rules/log-analyzer/catalog.json
rules/log-analyzer/versions/*.json.enc
schema/catalog.schema.json
templates/extension-entry.json
tools/validate_catalog.py
tools/test_validate_catalog.py
tools/validate_rules.py
```

`rules/**` 使用独立的加密规则分发协议，不属于 Extension Catalog v2，本次迁移不改变该协议。

## 本地校验

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
python tools/validate_catalog.py catalog.json
python tools/validate_rules.py
```

校验器不依赖第三方 Python 包，并严格拒绝未知字段、不安全 ID、非 SemVer、非 HTTPS 地址、超出 1 到 209715200 字节范围的大小、非法 SHA-256、非 64 字节 Ed25519 Base64 签名以及重复扩展 ID/发布版本。
