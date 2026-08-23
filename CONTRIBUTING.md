# 提交 Extension Catalog v2 记录

提交前请先在扩展源仓库构建 v2 ZIP。ZIP 根目录必须直接包含符合 PluginSDK manifest v2 的 `manifest.json`，并由受信发布者的 Ed25519 私钥对**原始 ZIP 字节**签名。

每个扩展条目只能包含：

- `id`、`name`、`description`、`publisherId`、`kind`；
- 非空 `releases` 数组。

每个 release 只能包含：

- 严格 SemVer 的 `version` 和 `minHostVersion`；
- HTTPS `url`；
- 与 ZIP 完全一致且位于 1 到 209715200 字节范围内的整数 `size`，以及 64 位十六进制 `sha256`；
- `signature.keyId` 和解码后正好 64 字节的 Base64 Ed25519 `signature`。

不要提交：

- v1 `plugins`、`type`、`manifest`、`author`、`category`、`reportPath` 等兼容字段；
- 公钥或可自行授予信任的字段；
- EXE、DLL、ZIP、私钥或其他发布二进制。

新增条目可复制 `templates/extension-entry.json`。提交前运行：

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
python tools/validate_catalog.py catalog.json
```

Pull Request 说明必须包含扩展 ID、版本、发布资产地址、真实 ZIP 大小、SHA-256、签名 `keyId`、本地校验结果，以及 manifest 声明的 kind、capabilities 和 permissions。Catalog 中的 release 身份必须与 ZIP 内 manifest 的 ID、版本、最低宿主版本、发布者和 kind 一致。
