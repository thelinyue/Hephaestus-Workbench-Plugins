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

目录不保存 manifest 副本，也不接受 v1 的 `type`、`author`、`category`、`reportPath`、`packageUrl`、`packageSize` 等字段。扩展 ZIP 根目录中的 `manifest.json` 由 Workbench 安装器在下载后独立校验。

## 签名与信任

每个 release 的 Ed25519 `signature` 覆盖原始 ZIP 字节。目录只保存 `keyId` 和 Base64 签名，**不能携带公钥**；`keyId` 是否受信任以及允许的发布者、扩展类别和权限范围，完全由 Workbench 内置信任表决定。

当前 `catalog.json` 中的 `replace-before-release`、1 字节大小、占位 SHA-256 和占位签名仅用于完成 v2 契约迁移，宿主不会信任该 key。正式发布前必须由发布流水线用真实 ZIP 的大小、SHA-256、正式 `keyId` 和 Ed25519 签名整体替换，否则扩展安装保持阻断。

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

校验器不依赖第三方 Python 包，并严格拒绝未知字段、不安全 ID、非 SemVer、非 HTTPS 地址、非正整数大小、非法 SHA-256、非 64 字节 Ed25519 Base64 签名以及重复扩展 ID/发布版本。
