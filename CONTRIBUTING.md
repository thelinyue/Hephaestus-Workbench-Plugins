# 贡献和插件上架指南

感谢你为 Hephaestus Workbench 开发插件。插件商店采用 Pull Request 人工审核，提交者需要同时提供可下载的 Release 资产、清单信息和基本验证证据。

## 提交前准备

1. 为插件建立独立的 GitHub 仓库。
2. 按工作台 EXE 标准协议实现入口程序：

   ```text
   your-plugin.exe --case <case-id> --input <source-path> --output <output-path>
   ```

3. 确认成功退出码为 `0`，并在输出目录生成 `report.html`。
4. 在插件仓库发布 GitHub Release，并上传包含 `manifest.json` 和入口文件的 ZIP 包。
5. 计算 ZIP 文件的 SHA-256：

   ```powershell
   Get-FileHash .\your-plugin-v1.0.0.zip -Algorithm SHA256
   ```

## 修改目录

复制 `templates/plugin-entry.json`，填写真实信息后加入 `catalog.json` 的 `plugins` 数组。以下字段必须准确：

- `id`、`name`、`version` 必须与插件 `manifest.json` 一致。
- `repository` 必须是插件项目主页；闭源插件可以填写官方发行说明仓库，但必须明确许可证和源码不可用状态。
- `packageUrl` 必须是 GitHub Release 资产地址，不能指向可变的分支文件。
- `packageSize` 和 `sha256` 必须与下载资产完全一致，`releaseNotesUrl` 必须使用 HTTPS。
- `sha256` 必须是对应 ZIP 文件的 64 位十六进制 SHA-256 值。
- `license` 必须说明插件实际采用的许可证。
- `manifest.entry` 必须是 ZIP 内的相对入口路径，不能越出插件目录。

Pull Request 中不要上传 EXE、DLL、ZIP 或其他二进制文件。

## 本地校验

在仓库根目录执行：

```powershell
python tools/validate_catalog.py catalog.json
```

校验脚本会检查 JSON 格式、索引版本、重复 ID、必填字段、HTTPS 地址、GitHub Release 地址、SHA-256 格式，以及目录记录和 manifest 字段是否一致。

## Pull Request 要求

Pull Request 描述中请说明：

- 插件解决的问题和适用场景；
- 测试使用的工作台版本和 Windows 版本；
- 使用的日志样例类型，以及是否生成了 `report.html`；
- Release 版本、ZIP 文件名和 SHA-256；
- 插件的许可证和源码仓库；
- 插件是否会联网、写入系统目录或启动额外进程。

维护者会人工检查 Release 资产、清单一致性、报告生成、权限边界和已知风险。CI 通过不是自动上架承诺。
