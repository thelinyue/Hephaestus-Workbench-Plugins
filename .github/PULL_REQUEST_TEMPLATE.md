## 插件上架申请

### 插件信息

- 插件 ID：
- 插件名称：
- 版本：
- 源码仓库：
- Release 地址：
- SHA-256：
- 许可证：
- 最低工作台版本：

### 验证清单

- [ ] 没有向本仓库提交 EXE、DLL、ZIP 或其他二进制文件。
- [ ] ZIP 内包含 `manifest.json` 和入口文件。
- [ ] `manifest.json` 与 `catalog.json` 中的 `manifest` 字段一致。
- [ ] 插件成功生成 `report.html`。
- [ ] 已运行 `python tools/validate_catalog.py catalog.json`。
- [ ] 已说明插件是否联网、写入系统目录或启动额外进程。
- [ ] 已确认插件许可证允许按当前方式分发。

### 测试说明

请描述测试使用的工作台版本、Windows 版本、日志样例和结果。
