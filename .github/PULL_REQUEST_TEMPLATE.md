## Extension Catalog v2 发布申请

### 扩展与发布信息

- 扩展 ID（`id`）：
- 扩展名称（`name`）：
- 发布者 ID（`publisherId`）：
- 扩展类别（`kind`，仅 `analysis` / `workspace` / `maintenance`）：
- 扩展版本（release `version`）：
- 最低宿主版本（`minHostVersion`）：
- 源码仓库：
- Release ZIP 地址（`url`，HTTPS）：
- ZIP 实际大小（`size`，字节）：
- ZIP SHA-256：
- 签名密钥 ID（`keyId`）：
- Ed25519 Base64 签名（`signature`）：

### v2 契约检查

- [ ] ZIP 根目录直接包含 `manifest.json`，且清单使用 `schemaVersion: 2`。
- [ ] manifest 的 `id`、`version`、`publisherId`、`kind`、`minHostVersion` 与 Catalog release 一致。
- [ ] manifest 的 `kind`、`runtime.kind`、`capabilities` 和 `permissions` 符合 PluginSDK v2 允许矩阵。
- [ ] Catalog 只包含扩展元数据和 releases，不内嵌 manifest，也不携带公钥。
- [ ] `size` 和 SHA-256 均由最终 ZIP 计算，未在签名后重新打包或修改 ZIP。
- [ ] Ed25519 签名覆盖最终发布资产的**原始 ZIP 字节**，解码后正好为 64 字节。
- [ ] `keyId` 已由 Workbench 宿主信任表绑定到正确的 `publisherId`、kind 和权限范围。
- [ ] 没有向本仓库提交 EXE、DLL、ZIP、私钥或其他发布二进制。

### 类型专属检查

- [ ] `analysis/process` 扩展使用 `analysis-process-v1`，stdin/stdout JSON 可被严格解析。
- [ ] `analysis/process` 成功时生成固定入口 `<extractDirectory>/Report/index.html`，响应不返回自定义报告路径。
- [ ] `workspace/web` 页面只申请必要权限，不依赖未授权网络、文件系统、Shell 或进程能力。
- [ ] `analysis/content` 或 `maintenance/content` 不声明可执行入口。
- [ ] 不适用的类型专属项目已在“测试说明”中注明原因。

### 本地验证

- [ ] 已运行 `python -B -m unittest discover -s tools -p "test_*.py" -v`。
- [ ] 已运行 `python -B tools/validate_catalog.py catalog.json`。
- [ ] 已验证 ZIP 大小、SHA-256 和 Ed25519 签名可由发布流水线反向校验。

### 测试说明

请说明使用的 Workbench 版本、Windows 版本、扩展 kind/runtime、manifest capabilities/permissions、测试输入、成功结果和失败场景。分析进程扩展还需说明退出码、stderr 诊断、协议响应以及 `Report/index.html` 和静态资源验证结果。
