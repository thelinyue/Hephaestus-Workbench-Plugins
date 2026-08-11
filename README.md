# Hephaestus Workbench Plugins

赫菲斯托斯工程工作台（Hephaestus Workbench）的公开插件目录。

本仓库只维护插件元数据索引，不保存插件二进制文件。插件作者通过 GitHub Release 发布 ZIP 包，再通过 Pull Request 提交目录记录；维护者人工审核后合并。

## 当前状态

目录现已接入 Hephaestus Workbench v1.1.1 及以后版本。当前工作台支持 EXE 标准插件，DLL 插件契约尚未接入运行时。

工作台插件运行协议参见：[插件开发文档](docs/plugin-development.md)。

## 仓库结构

```text
catalog.json                    # 插件目录索引
schema/catalog.schema.json      # 索引 JSON Schema
templates/plugin-entry.json     # 上架记录模板
tools/validate_catalog.py       # 本地和 CI 校验脚本
docs/plugin-development.md      # 公开插件开发与运行协议
.github/workflows/               # 只校验，不自动发布或合并
```

## 插件分发约定

每个插件应在自己的 GitHub 仓库中创建 Release，并上传 ZIP 包。ZIP 包至少包含：

```text
your-plugin-v1.0.0.zip
├── manifest.json
└── your-plugin.exe
```

目录记录中的 `packageUrl` 必须指向 GitHub Release 资产，`packageSize` 和 `sha256` 必须与该 ZIP 文件完全一致。商店不会在 Pull Request 中接收 EXE、DLL 或 ZIP 文件。

## 上架流程

1. 在插件自己的仓库发布带版本号的 GitHub Release。
2. 按 `templates/plugin-entry.json` 创建目录记录。
3. 将记录加入 `catalog.json` 的 `plugins` 数组。
4. 在本地运行：

   ```powershell
   python tools/validate_catalog.py catalog.json
   ```

5. 提交 Pull Request，填写上架模板中的测试和安全信息。
6. 维护者核对插件协议、Release 资产、SHA-256、许可证和安全风险后人工合并。

## 目录字段

每条记录包含客户端安装所需的 `id`、`name`、`description`、`version`、`type`、`packageUrl`、`sha256`、`packageSize`、`minimumAppVersion` 和 `releaseNotesUrl`，以及审核使用的 `author`、`license`、`repository` 和 `manifest`。

`manifest` 必须与 ZIP 内的 `manifest.json` 保持一致，且当前目录只接受 `type: "Exe"`。每个插件必须明确声明自己的许可证；本仓库的目录、模板、文档和校验工具保留所有权，未授予额外复用权。

## 安全边界

插件会以用户当前 Windows 权限运行。目录收录不代表对插件安全性的永久担保，用户安装前应自行审查来源和 Release 内容。发现恶意插件、校验值不一致或其他安全问题，请参阅 [SECURITY.md](SECURITY.md)。

## 贡献

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。目录修改必须通过 Pull Request，GitHub Actions 只执行格式和一致性校验，不会自动合并或自动发布插件。
