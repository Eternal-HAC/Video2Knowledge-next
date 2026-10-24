# 隔离便携候选验收

日期：2026-10-24。状态：**本地 Windows 候选通过，未提交或发布**。这是累计 G0–G5 与 S0 改动的本地冻结验证，产品版本暂时保持 `1.0.0-beta.3`，不代表已发布 Beta.3 的资产被替换。

## 候选身份与构建输入

| 项目 | 本次证据 |
|---|---|
| 基础 HEAD | `7ff61e7568a324b9d2e7a31161ff0b7927ca3f9b`，工作区有累计未提交改动 |
| 文件 | `Video2Knowledge-1.0.0-beta.3-portable.exe`，仅本地候选 |
| 大小 | `133247311` 字节 |
| SHA-256 | `f293e960102fc37a492cdf77be86eb2d6d2bd15d58076c8bb1713acb5f99e458` |
| PE 产品 / 数字版本 | Video2Knowledge / `1.0.0.0` |
| PE 产品字符串版本 | `1.0.0-beta.3` |
| 构建环境 | Windows 11、Python 3.13.7、PyInstaller 6.22.3、hooks 2026.8 |

候选与 `SHA256SUMS.txt` 位于仓库忽略目录 `.test-tmp/s2-portable-20261024/source/dist/`。同名不代表同一文件，应以目录和摘要区分原发布资产。

把 60 个明确构建输入复制到独立 source 目录，逐文件核对 SHA-256，调用复制后的原有 `build_exe.ps1 -SkipInstall`，使用项目现有 `.venv`。没有安装或升级依赖，没有复制 `.env`、用户 workspace、凭据或模型进构建目录。

完整输入清单保存在 [机器可读报告](../quality/isolated-portable-acceptance-20261024.json)。它包括未跟踪但已验收的安全/存储模块，不能只用基础 HEAD 代表这些输入。PyInstaller 分析记录包含 `backend.local_security`、`task_repository`、`history_cache` 和 `mcp_server`，运行验证也通过。

准备时旧 EXE 全量摘要读取出现持续等待，停止的仅是本轮准备命令，随后复用已经校验的源码副本继续。未认定等待原因，也未关闭或绕过安全软件。构建输出与原 `dist` 隔离；原 `dist` 的文件名/大小/修改时间及现有校验文件前后检查一致，未重新取得全部旧 EXE 的摘要。候选本身已独立重新计算完整 SHA-256，与候选校验文件一致。

构建警告涉及可选 `curl_cffi`、`yt_dlp_ejs` 以及未找到 `tzdata`；没有为此安装依赖。当前离线验收通过，不能据此承诺相关可选下载功能或所有时区行为。

## 打包态验证

### 模板、历史与持久化

用现有 `smoke_portable_beta3.ps1` 在临时合成 workspace 启动候选，两次启动均经过精确进程/监听归属检查：

- 健康返回 `product=Video2Knowledge`、`service=VideoToNo`、`api_compat=1`、`version=1.0.0-beta.3`、`mode=portable`。
- 六个模板均有预览；历史分页返回两个合成任务，按需恢复笔记成功。
- 收藏修改在候选重启后保留。
- 离线来源识别、转录复用提示和首页相关静态标记通过。

### HTTP 与 MCP

使用独立合成 workspace，设置 dotenv 禁用、禁止浏览器和 Hugging Face 离线环境变量。自建客户端只调用归属候选：

- 非信任 Host 返回 400；外来 Origin、cross-site、same-site 及外来简单上传共四种情况返回 403，拒绝响应包含 CSP。
- 同源 multipart SRT 上传与 SRT 读取正常。
- 标准 MCP SDK 分别在无 Origin 和显式同源情况下完成 SSE 初始化、列工具、读取合成笔记和转录。
- 原生 `BackendClient` 的 HTTP 读取正常；首页、favicon 与 PNG 图标可访问。
- 临时 workspace 不存在 `llm_keys.json`。没有读取已有 Provider 配置或执行 LLM、飞书操作。

这轮不是 Chrome 全视觉矩阵或 Cherry Studio 等宿主认证；S0 的浏览器证据仍见 [此前记录](23-local-request-security-acceptance.md)。也没有单独重测仅旧环境变量入口。

### 离线 ASR 与子进程

先使用现有 `smoke_portable_asr.ps1`、Windows `Microsoft Huihui Desktop` 合成中文 WAV、缓存 `small` 和 CPU 请求，经真实上传/转录 API 完成：

- 任务 completed，中文转录 3 段。
- JSON、Markdown、SRT 可读取，Markdown 100 字符、SRT 157 字符，中央转录归档 1 份。
- 任务内转录文件和清单存在；现有凭据模式检查通过。
- 合成 WAV、API 测试 workspace 和本次进程由脚本清理。

现有 smoke 日志的 `device` 为空，因为公开转录任务结果未包含该字段；不能把该日志当作实际设备证据。因此另做一次限定的直接打包子进程验证：使用第二份合成 WAV，通过现有协议父进程调用候选 `--asr-child`，校验返回载荷。实际 `requested_model=model=small`、`device=cpu`、2 段非空转录，子进程退出码为 0；第二份 WAV 已删除。

两次均使用缓存，设置离线模式，无模型下载、公开视频下载、真实 LLM 或飞书写入。直接工人测试也不会启动托盘或 HTTP 服务。

## 验证边界与下一步

本轮没有产品源码修改，60 个当前源文件的摘要仍与构建输入一致。完整源码回归沿用上一轮 **1381 passed、3 个原有权限跳过**，本轮没有重复整套 pytest；打包结果由上述实际 EXE 验收提供。未在全新 Windows 或无 FFmpeg/无 Python 的干净机器上验证，不宣称所有平台、模型和网络兼容。

所有本轮候选进程均已退出，没有操作其他服务的工作区。模板/ASR smoke 的临时目录已清理；只含合成内容的客户端证据、构建输入、候选和校验文件保留在本轮忽略目录。未 stage、commit、push、tag 或发布，原 Release 未更新。

下一步建议将累计改动收口成 **Beta.4 发布准备计划**：先明确版本和提交边界、排除实验缓存与内部质量工具被误写成已上线功能，再做最终审查与聚焦提交。确定发布版本后需要重新构建并记录新哈希，不能把当前 Beta.3 候选改名后当成新版本。提交、推送、标签和发布另按授权边界执行。历史列表 300ms 目标仍开放，不作为本次候选已经通过的性能指标。
