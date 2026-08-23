# Hephaestus Workbench Extension v2 开发文档

本文说明如何为 Hephaestus Workbench v2 开发、打包、签名和登记扩展。Workbench v2 只接受 PluginSDK 定义的 manifest v2、Extension Catalog v2 和签名发布包，**不提供 v1 兼容**。

## 1. 正式版支持范围

Workbench v2 只加载经过宿主校验和受信发布者签名的扩展包：

- 不支持第三方 DLL、WPF View 或 ViewModel 注入。
- 不提供 unsigned/developer mode，本地安装包也必须签名。
- 扩展不能声明侧栏导航、排序、固定状态或替换 Core 页面。
- Workspace 页面统一由固定 Workspace Host 承载。
- Analysis Process 通过独立进程和 JSON 协议运行，不获得数据库、WPF 控件或宿主内部对象。
- Maintenance 扩展只提供声明式 Workflow/Command Profile，不获得凭据、SSH Client、Shell、数据库或本地进程权限。

允许的 kind/runtime/capability 组合如下：

| `kind` | `runtime.kind` | 允许的 capability |
| --- | --- | --- |
| `workspace` | `web` | 必须包含 `workspace.page` |
| `analysis` | `process` | 必须包含 `analysis.engine`；可声明 `analysis.scope.comprehensive`、`analysis.scope.storage` |
| `analysis` | `content` | `analysis.rule-pack`、`analysis.report-template` |
| `maintenance` | `content` | `maintenance.workflow-pack`、`maintenance.command-profile` |

只有 `workspace` 扩展可以声明非空 `permissions`。所有未知字段、未知枚举值和不允许的组合都会被拒绝。

## 2. 扩展包与安装目录

发布资产必须是 ZIP，根目录直接包含 `manifest.json`。process/web 入口应位于同一 ZIP 内，并使用相对于扩展版本目录的安全路径。例如：

```text
sample-analyzer-v2.0.0.zip
├── manifest.json
└── bin/
    └── sample-analyzer.exe
```

安装成功后由宿主管理版本目录：

```text
Extensions/
└── sample-analyzer/
    ├── 2.0.0/
    │   ├── manifest.json
    │   └── bin/sample-analyzer.exe
    ├── current.json
    └── current.json.bak
```

扩展作者不能依赖手工复制、递归扫描或直接修改 `current.json`。安装器会校验 ZIP 路径、manifest、Host API、签名和类型健康状态，再通过 pending/healthy 激活及 rollback 管理版本。

入口路径不能是绝对路径、不能包含词法穿越，也不能经过符号链接、目录联接或其他重解析点。content 运行时不声明 `entry`。

## 3. manifest v2

一个综合日志分析进程扩展的完整 manifest 示例：

```json
{
  "schemaVersion": 2,
  "id": "sample-analyzer",
  "name": "示例日志分析",
  "version": "2.0.0",
  "kind": "analysis",
  "publisherId": "thelinyue",
  "hostApiVersion": "1.0",
  "minHostVersion": "2.0.0",
  "runtime": {
    "kind": "process",
    "protocol": "analysis-process-v1",
    "entry": "bin/sample-analyzer.exe"
  },
  "capabilities": [
    "analysis.engine",
    "analysis.scope.comprehensive"
  ],
  "permissions": [],
  "dependencies": []
}
```

字段要求：

| 字段 | 要求 |
| --- | --- |
| `schemaVersion` | 固定为整数 `2`。 |
| `id` | 稳定扩展 ID，只使用小写字母、数字、点号或连字符，分隔符不能连续。 |
| `name` | 面向用户的非空名称。 |
| `version` | 严格 SemVer，扩展独立版本，不与 Workbench 版本绑定。 |
| `kind` | `workspace`、`analysis` 或 `maintenance`。 |
| `publisherId` | 必须与签名密钥在宿主信任表中绑定的发布者一致。 |
| `hostApiVersion` | v2.0.0 固定为 `1.0`。 |
| `minHostVersion` | 严格 SemVer，声明可以加载该扩展的最低 Workbench 版本。 |
| `runtime` | 声明 `kind`，process 还必须声明 `protocol`，process/web 必须声明安全相对 `entry`。 |
| `capabilities` | 非空数组，只能使用对应 kind/runtime 允许的 capability。 |
| `permissions` | 权限申请数组；非 workspace 扩展必须为空。 |
| `dependencies` | 精确依赖数组，每项包含安全 `id` 和严格 SemVer `version`；不能自依赖或重复。 |

manifest 不声明导航位置、排序、默认固定、Core 页面替换或任意报告入口。

## 4. analysis-process-v1

`analysis/process` 扩展必须通过标准输入接收一个 JSON 请求。宿主写完请求后关闭 stdin；扩展在 stdout 只写一个最终 JSON 响应，诊断信息写入 stderr。进程正常完成时退出码必须为 `0`，非零退出码会直接判定为失败。

请求结构：

```json
{
  "protocol": "analysis-process-v1",
  "requestId": "analysis-001",
  "caseId": "case-001",
  "sourcePath": "C:\\Cases\\case-001\\source.tgz",
  "outputDirectory": "C:\\Cases\\case-001\\Extract\\Report",
  "extractDirectory": "C:\\Cases\\case-001\\Extract",
  "scope": "comprehensive"
}
```

`scope` 只允许：

- `comprehensive`：当前综合日志分析与报告能力。
- `storage`：同一日志分析扩展后续提供的存储专项能力；只有 manifest 声明相应 capability 时才可接收。

成功响应：

```json
{
  "protocol": "analysis-process-v1",
  "requestId": "analysis-001",
  "succeeded": true
}
```

失败响应：

```json
{
  "protocol": "analysis-process-v1",
  "requestId": "analysis-001",
  "succeeded": false,
  "errorCode": "INPUT_INVALID",
  "errorMessage": "输入日志格式无法识别。"
}
```

请求与响应均严格拒绝未知字段；响应 `requestId` 必须与请求完全一致。成功响应不能包含错误字段，失败响应必须同时包含非空 `errorCode` 和 `errorMessage`。

## 5. 固定报告入口

分析成功时，扩展必须生成：

```text
<extractDirectory>/Report/index.html
```

CSS、JavaScript、图片、`static`、`structured` 等资源必须位于同一 `Report` 目录内并使用相对引用。宿主只解析 `Report/index.html`，并使用电脑默认浏览器打开报告。

进程响应和 manifest 均不能提供自定义报告路径。即使进程退出码为 `0` 且返回成功响应，只要固定入口缺失、越过案例解压目录或经过重解析点，分析仍会失败。

快速单日志分析成功后可以由宿主自动打开唯一报告；批量和监控目录分析只更新任务状态，不应由扩展自行打开浏览器标签。

## 6. Workspace 与 content 扩展

`workspace/web` 扩展使用 `workspace.page`，入口由固定 Workspace Host 加载。页面默认不能访问外部网络、任意文件路径、Shell、进程或系统 API。Host Bridge 使用版本化 JSON-RPC；每个方法必须同时通过 manifest permission 和发布者 trust scope。

`analysis/content` 与 `maintenance/content` 是纯内容包，不启动扩展进程，也不声明入口：

- Analysis 内容包提供规则或报告模板。
- Maintenance 内容包提供声明式 Workflow 或结构化 Command Profile。
- Maintenance Command Profile 使用 executable 和独立 argument tokens，不能要求自由 Shell 字符串拼接。

## 7. Extension Catalog v2

公开目录根对象固定为：

```json
{
  "schemaVersion": 2,
  "extensions": [
    {
      "id": "sample-analyzer",
      "name": "示例日志分析",
      "description": "生成综合工程诊断报告。",
      "publisherId": "thelinyue",
      "kind": "analysis",
      "releases": [
        {
          "version": "2.0.0",
          "minHostVersion": "2.0.0",
          "url": "https://example.invalid/releases/sample-analyzer-v2.0.0.zip",
          "size": 123456,
          "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
          "signature": {
            "keyId": "official-release-key",
            "signature": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+Pw=="
          }
        }
      ]
    }
  ]
}
```

Catalog 条目只包含扩展元数据和 releases，不复制 ZIP 内的 manifest。release 的 `version`、`minHostVersion`、扩展 ID、`publisherId` 和 `kind` 必须与已签名 ZIP 中的 manifest 一致。

Catalog 不能携带公钥。目录中的 `keyId` 只有在 Workbench 内置信任表中绑定到相同发布者、允许 kind 和权限范围时才有效。

## 8. ZIP 哈希与 Ed25519 签名

发布流水线必须按固定顺序生成 release 元数据：

1. 构建最终 ZIP，ZIP 根目录包含 manifest v2 和全部运行资源。
2. 禁止再修改最终 ZIP。
3. 读取最终 ZIP 的实际字节数，写入 release `size`。
4. 对最终 ZIP 计算 SHA-256，写入 release `sha256`。
5. 使用发布 Secrets 中的 Ed25519 私钥签名**原始 ZIP 字节**。
6. 将对应 `keyId` 和 64 字节签名的 Base64 写入 release `signature`。
7. 使用公钥反向校验同一份 ZIP 后再提交 Catalog。

签名私钥不能进入本仓库、扩展源码仓库、构建产物或日志。Catalog 声明的公钥不能自行获得信任；正式信任锚由 Workbench 发行版内置。

同一扩展 ID 和版本必须对应唯一内容。已发布版本不得用不同 ZIP、SHA-256 或签名覆盖，应发布新的 SemVer 版本。

## 9. 本地测试和提交

建议按以下顺序验收：

1. 使用 PluginSDK v2 校验 manifest，并覆盖未知字段、错误 kind/runtime、权限和路径穿越失败场景。
2. 对 analysis process 使用真实子进程测试 stdin EOF、stdout/stderr、退出码、取消和严格响应解析。
3. 验证成功任务生成完整 `Report/index.html` 及其相对静态资源。
4. 生成最终 ZIP 后计算实际 size、SHA-256，并对原始 ZIP 字节执行 Ed25519 签名和反向验签。
5. 更新 `catalog.json`，确认 release 与 manifest 身份字段一致。
6. 在本仓库运行：

```powershell
python -B -m unittest discover -s tools -p "test_*.py" -v
python -B tools/validate_catalog.py catalog.json
python -B tools/validate_rules.py
```

Pull Request 使用 `.github/PULL_REQUEST_TEMPLATE.md` 提供发布资产、签名和类型专属测试证据。正式发布前不得保留占位 size、SHA-256、`keyId` 或签名。

## 10. 安全与版本边界

- 不依赖 Workbench 内部数据库表、WPF 类型或未记录环境变量。
- 不读取或写入其他案例、扩展版本或工作台配置。
- 不在扩展中保存密码、私钥口令或 Credential Manager 内容。
- 不绕过 Host Bridge、网络拦截、路径边界、Host Key 或 Maintenance Policy。
- manifest、Catalog 和进程协议都是严格 v2 边界；未知字段不是扩展点。
- 扩展版本独立发布，但 `minHostVersion` 和 `hostApiVersion` 必须真实反映宿主要求。
- 任何协议或能力变更必须先更新 PluginSDK、验证器和测试，再发布新的扩展版本。
