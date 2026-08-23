# 提交 Extension Catalog v2 记录

提交前请先在扩展源仓库构建 v2 ZIP。ZIP 根目录必须直接包含符合 PluginSDK manifest v2 的 `manifest.json`，并由受信发布者的 Ed25519 私钥对**原始 ZIP 字节**签名。

每个扩展条目只能包含：

- `id`、`name`、`description`、`publisherId`、`kind`；
- 非空 `releases` 数组。

每个 release 只能包含：

- 严格 SemVer 的 `version` 和 `minHostVersion`；
- 安全的绝对 HTTPS `url`：不得包含用户名或密码、fragment 或显式空端口，只能省略端口或显式使用 `443`；主机仅允许 ASCII DNS 名称（国际化域名须使用 punycode）或严格 IPv4；不支持 IPv6，包括标准无 scope IPv6、scoped IPv6 和 IPvFuture，也不接受方括号 IPv4；路径和查询只允许 ASCII URI 字符，其他字符必须使用百分号编码；
- 与 ZIP 完全一致且位于 1 到 209715200 字节范围内的整数 `size`，以及 64 位十六进制 `sha256`；
- `signature.keyId` 必须匹配 ASCII `[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})`（总长 1–64），不得包含空白、控制字符、路径片段或非 ASCII 字符；`signature` 必须是解码后正好 64 字节的 Base64 Ed25519 签名。

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
