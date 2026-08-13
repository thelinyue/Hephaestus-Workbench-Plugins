# Hephaestus Workbench Plugins

这是 Hephaestus Workbench 的公开插件目录，只维护插件元数据，不存储二进制发布包。插件作者通过 GitHub Release 发布 ZIP，再通过 Pull Request 提交目录记录。

目录支持两类插件：

- `Exe`：由工作台案例分析流程启动的分析插件；
- `Web`：由工作台独立 WebView2 工具窗口承载的本地静态页面。

目录记录中的 `packageUrl` 必须指向 GitHub Release 资产，`sha256` 和 `packageSize` 必须与 ZIP 文件一致。Pull Request 不应提交 EXE、DLL、ZIP 或其他二进制文件。

## 仓库结构

```text
catalog.json
schema/catalog.schema.json
templates/plugin-entry.json
tools/validate_catalog.py
```

## 本地校验

```powershell
python tools/validate_catalog.py catalog.json
```

每条记录的 `manifest` 必须与 ZIP 根目录中的 `manifest.json` 保持一致。Web 插件的入口必须是插件目录内的 HTML 文件，并通过 `capabilities: ["standalone-tool"]` 声明其不参与案例分析流程。
