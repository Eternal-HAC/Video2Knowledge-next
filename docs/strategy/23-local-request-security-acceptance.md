# S0 本机 HTTP 请求边界验收

日期：2026-10-24。状态：**源码本地验收通过，尚未构建或发布**。产品版本仍为 `1.0.0-beta.3`。

## 实现与边界

沿用 `main.py` 的纯 ASGI 中间件与已安装的 Starlette `TrustedHostMiddleware`，新增小型 `backend/local_security.py` 负责头部语法和来源比较。没有新增依赖、CORS 放行、认证令牌或远程服务模式。

- HTTP peer 缺失、未知或非回环时返回固定 403。移除产品中的测试客户端例外。
- Host 必须唯一，主机只允许 `localhost`、`127.0.0.1`、`[::1]`，允许动态合法端口；非法地址返回固定 400。不接受任意本地域名、其他 127 地址、用户信息或畸形/重复头。
- Origin 存在时必须唯一，scheme、主机和有效端口均与请求一致。拒绝 `null`、跨端口、跨别名和畸形来源，返回固定 403。原生 CLI 无 Origin 请求继续可用。
- `/api`、`/mcp` 及子路径拒绝 `Sec-Fetch-Site: same-site/cross-site`，包括 GET 与简单 POST。元数据重复或非法时拒绝。无 Origin 的外部顶层首页导航仍可用。
- 正文读取、业务副作用之前拒绝请求；保留上传流、SSE 多段输出、断连和取消传播。安全头覆盖拒绝响应，已存在的 CSP 不重复追加，业务自身的 400 不改写。
- Launcher 与模块入口均配置 `proxy_headers=False`，防止 Uvicorn 默认信任回环代理并提前改写 peer/scheme。应用不使用 Forwarded 头授权。

这是浏览器请求边界防护，不提供针对恶意本机进程的身份认证。没有执行真实 DNS rebinding、真实平台登录或完整外部 MCP 客户端认证测试；SDK 自身防护保持原样。已有 Release 资产没有包含本次修改。

## 失败先行与自动化证据

新增 `tests/test_local_security.py` 共 261 个用例。初轮在旧实现上得到 190 failed、21 passed；后续用例进一步暴露 CSP 去重、代理信任和 Host 拒绝优先级问题，分别修正后再回归。

覆盖六种方法、重复/畸形 Host 与 Origin、Fetch Metadata、缺失 peer、伪造代理头、动态端口、IPv6、原生请求、正文未消费、业务处理未进入、SSE 和取消。六个已有测试模块通过 `tests/local_client.py` 使用实际回环地址，没有给产品增加 `testserver` 白名单。

最终隔离完整测试：**1367 passed, 3 skipped in 73.82s**。三个跳过仍为 Windows 符号链接权限：`test_api.py:2025`、`test_asr_process.py:597`、`test_media_retention.py:145`，无新增跳过。

Python 编译、前端与两项浏览器脚本 Node 语法、`pip check` 和 `git diff --check` 均通过。115 个本地文档链接及本轮源码/文档行尾检查通过。核心源码 SHA-256、测试计数及无隐私浏览器观测保存在 [机器可读验收报告](../quality/local-request-security-acceptance-20261024.json)。未将历史基准报告的源码 hash 改写成新值。

## 浏览器证据

使用隔离合成工作区和无个人数据的 Chrome profile，监听本次自建 18756/18757 端口。登录管理器替换成无副作用桩，不调用真实登录。浏览器未关闭同源或本地网络安全功能。

- 同源健康 GET 和显式同源登录桩 POST 均 200。
- 跨端口页面发起 `no-cors` 简单 POST 和 GET，浏览器呈现 opaque 响应；服务端诊断确认两者均 403。登录桩计数仅 1，即显式同源请求。
- 外部页面导航回首页成功。
- 历史/刷新页面完成 1440×900、1024×768、390×844 与亮色/暗色/系统主题九组合验证；筛选、分页、刷新、迟到响应、焦点与页面无横向溢出通过。没有提交真实笔记任务。

最后一次 Host 错误优先级调整后重新执行了上述浏览器验证。证据保留于仓库忽略目录 `.test-tmp/s0-browser-20261024/evidence/` 与 `final-history-evidence/`，可在本机复查；这些临时证据没有作为发布资产上传。

## 交付范围与后续

未 stage、commit、push、构建或发布。未安装依赖、读取 Key、下载模型/媒体、调用 LLM 或写飞书。测试服务和浏览器按本次进程身份清理，用户 8000 服务未操作。前轮 G0–G5 工作区修改保留。

下一步建议先对累计未提交改动做源码与兼容性收口，再单独决定发布候选。打包态需要验证新安全模块收集、Launcher、本地原生/MCP 客户端和离线 ASR；当前源码测试通过不能替代便携版验收。历史 300ms 性能目标继续开放，不自动重启缓存或数据库方案。

历史缺口与原始观测见 [审查合同](22-local-request-security-audit.md)，不要将其旧状态当作本轮状态。
