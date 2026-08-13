# 提交插件目录记录

提交前请先在插件源仓库创建带版本号的 GitHub Release，并上传 ZIP。ZIP 根目录必须直接包含 `manifest.json` 和入口文件。

目录记录必须包含：

- `id`、`name`、`version`、`description`、`author`、`license`；
- `minimumAppVersion`、`repository`、`packageUrl`、`sha256`、`packageSize`、`releaseNotesUrl`；
- 与 ZIP 内完全一致的 `manifest`。

`manifest.type` 支持 `Exe` 和 `Web`。Web 工具必须使用本地静态资源；入口通常为 `index.html`，并声明 `standalone-tool` 能力，以免被案例分析流程调用。

本地校验：

```powershell
python tools/validate_catalog.py catalog.json
```

Pull Request 中不要提交 EXE、DLL、ZIP 或其他二进制文件。提交说明应包含 Release 地址、ZIP 大小、SHA-256、测试结果及插件是否联网或启动额外进程。
