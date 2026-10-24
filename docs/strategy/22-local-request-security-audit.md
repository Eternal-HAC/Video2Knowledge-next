# 本机请求安全审查与修复合同

> 后续更新：2026-10-24 S0 已完成源码本地修复与验收，详见 [验收记录](23-local-request-security-acceptance.md)。下文保留修复前审查事实；已发布资产未更新。

日期：2026-10-24。状态：**审查完成，发现发布阻断缺口；尚未修复**。
本轮只读产品实现，新增审查文档与无隐私证据。没有修改产品源码、版本或现有测试。

## 结论与优先级

| 优先级 | 当前证据 | 发布前要求 |
|---|---|---|
| P1 | REST 只检查连接 peer，本机连接的任意 Host/Origin 可进入处理函数 | 补 Host 与浏览器来源验证，拒绝发生在正文读取/业务操作之前 |
| P1 | 外来 Origin 的无体 `POST /api/douyin-login/start` 在实际路由桩上返回 200；OPTIONS 返回 405 | 同时拦截简单 POST，不能只依赖 JSON 校验、预检失败或响应 CORS 头 |
| P2 | peer 缺失时 `is_loopback_client(None)` 返回 true；非本机 peer 已返回 403 | 运行时未知 peer 默认拒绝，测试适配不扩大产品白名单 |
| 保持 | MCP SDK 当前对外来 Host/Origin 独立返回 421/403 | 不把 MCP 等同 REST，不移除 SDK 防护；验证外层修复不破坏 SSE |

没有证据表明用户已遭攻击或凭据已泄漏。这里确认的是服务端检查缺口。
Host 缺口构成 DNS rebinding 风险条件，未执行真实域名解析切换或浏览器利用。
外来 Origin 的 POST 在 ASGI 层可达，不代表所有浏览器/网络都可完成攻击。
现代浏览器的本地网络访问权限、预检、混合内容等可能增加限制；本产品不能把它们当统一服务端防线。

## 审查范围与实际依据

- `backend/main.py`：`is_loopback_client`、`LocalSecurityMiddleware`、路由与 `/mcp` 挂载。
- `launcher.py`：默认绑定 127.0.0.1，端口动态选择。
- `backend/mcp_server.py`：stdio 的 BackendClient 使用本机 HTTP；SSE 使用 FastMCP，内部工具可直接调用后端。
- 已安装的 Starlette `TrustedHostMiddleware` 与 MCP transport_security/SSE/FastMCP 实现。
- 本机观察版本：FastAPI 0.142.2、Starlette 1.7.0、MCP 1.30.0；没有升级或更改依赖。
- [18 项原始观测与源码 hash](../quality/local-request-audit-20261024.json)。JSON 不含真实地址、Key、用户工作区路径或原始响应正文。

临时探针 `.test-tmp/local-request-audit-20261024/probe.py` 使用真实中间件、真实 app 路由和独立 bootstrap，
禁用 dotenv，不启动 lifespan、不监听 HTTP 端口。ASGI scope 的 18755 只是测试值，没有启动该端口服务。
应用网络连接与子进程在探针中禁止；Windows 事件循环的内部唤醒 socketpair 在禁止规则生效前建立，
不能把它误写成没有任何 socket 系统调用。所有登录操作均为返回固定状态的异步桩。

13 项中间件观察中，标准本机 CLI、同源、外来/opaque/跨端口 Origin、未知/缺失/重复 Host、
cross-site/same-site metadata 及缺失 peer 共 11 种进入了下游；非本机 peer 与伪造 X-Forwarded-For 的非本机 peer 均被拒绝。
另外 3 项实际 REST 路由桩和 2 项真实挂载 MCP SSE 拒绝，共 18 项。

探针初轮暴露了脚本自身的仓库根路径、Windows 事件循环初始化问题，修正后重跑，未把失败轮计作证据。
MCP SSE 在已经发送 421/403 后还抛出 `ValueError`，探针记录了异常类型与单次 response.start；
这不是请求被放行，也未将其升级为已证实的新产品缺陷。本轮没有改 SDK。

## 为什么现有防护不够

1. 回环 peer 说明 TCP 连接来自本机。用户的浏览器和本机恶意进程也满足这个条件。
2. 当前返回 CSP、nosniff、frame-ancestors 等防护有价值，但这些响应头没有验证请求发起来源。
3. REST 没有配置宽松 CORS，这是应保留的事实。不过，简单表单式 POST 可以不经预检发送，
   不允许脚本读取响应也不能撤销服务端已经执行的操作。[MDN CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
4. `Sec-Fetch-Site` 可以区分 same-origin、same-site、cross-site 与用户主动访问；same-site 不等于 same-origin，
   同一主机的不同端口不能因此自动可信。[MDN Sec-Fetch-Site](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Site)
5. MCP 的官方 HTTP 安全要求包括 Origin 验证和本机绑定。当前 SSE 的具体证据来自已安装 SDK 和实际拒绝结果，
   不能把新版 Streamable HTTP 要求直接当作旧 SSE 的完整符合性认证。[MCP transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)

攻击面优先覆盖有副作用的登录 start/cancel、配置/Key 写入删除、任务提交取消删除、文件上传/打开、
模型管理、清理与飞书重试。历史、笔记、转录和导出等读取接口也需要 Host 验证，避免只保护写接口。
没有向这些真实副作用接口发送有效业务数据；其中仅登录 start 使用了实际路由与桩。

## 下一实施阶段：S0 本机请求边界

### 范围与兼容合同

先补失败测试，再修实现。只允许新增小型请求边界 helper/ASGI 包装，复用已安装 Starlette Host 校验能力，
补其不负责的重复头、Origin 和 Fetch Metadata 检查；先查看当前版本解析行为，不新增依赖或通用鉴权框架。

1. **peer**：维持 127.0.0.1、IPv6 回环和 IPv4-mapped loopback 兼容；缺失/未知 peer 拒绝。
   测试专用 `testclient` 不作为真实 Host 许可，不引入远程代理信任或任意 X-Forwarded-* 豁免。
2. **Host**：只支持产品已有本机入口 `localhost`、`127.0.0.1` 和 `[::1]`，允许合法动态端口。
   其他 DNS 名、伪装后缀、userinfo、空 Host、重复 Host、非法/越界端口拒绝；不做 DNS 查询。
   不使用包含 localhost 的子串匹配，不开放 `*`、`*.localhost`、任意局域网或自定义远程主机。
3. **Origin**：存在时必须是唯一、有效的 HTTP(S) origin，与已验证的请求 scheme/hostname/effective port 完全一致。
   `null`、外来主机、不同端口/协议、重复/多值、带路径/query/fragment/userinfo 的伪 origin 均拒绝。
   默认端口按协议标准化，IPv6/大小写需有测试；Origin 不从未受信任的 Forwarded 头推导。
   `localhost` 与 `127.0.0.1` 是不同 origin，不能互相通配。
4. **无 Origin**：保留原生 CLI、stdio BackendClient、启动器探活和本机 MCP 的调用。
   对 `/api` 与 `/mcp`，显式 cross-site/same-site Fetch Metadata 拒绝；same-origin 或 none 按其余规则判断。
   对 Origin、metadata 同时缺失的原生客户端不强制引入 token。
   异常/重复 metadata 不能绕过判断；metadata 是纵深检查，不能作为任意 Host/Origin 的放行凭据。
5. **页面导航**：允许从 GitHub/外部链接正常导航到本机首页。无 Origin 的顶层导航不是 API 跨站调用许可，
   不能为方便首页入口豁免 `/api/*`、`/mcp/*`。主页与静态资源仍须验证 Host。
6. **拒绝行为**：Host 无效使用 400，peer/Origin/metadata 拒绝使用 403；固定中文安全 JSON，
   不回显恶意头、路径、配置或凭据。拒绝响应保留既有安全头，既不加 CORS 通配也不重定向到用户传入 Host。
   需要验证 duplicate/header 格式失败时的统一收口。
7. **流式兼容**：维持纯 ASGI，不切回 BaseHTTPMiddleware，不消费或缓存上传正文；
   不破坏 SSE 多段响应、断连/取消或已有静态资源 MIME/缓存头。MCP SDK 的内部防护继续启用。

后端 API、任务清单、模板、输出路径和 Provider 配置格式不变。新的可见行为仅是拒绝先前错误放行的来源。
已有跨端口前端、file:// 页面、自定义代理域名会受限，本项目当前无此受支持部署承诺，不新增豁免配置。
如果现有官方 MCP 客户端确实发送非同源 Origin，先用无凭据桩记录头的类别，另议明确 allowlist，不能默默放宽。

### 测试清单

- 纯 ASGI 参数化 peer/Host/Origin/metadata，覆盖 IPv4/IPv6、动态/默认端口、大小写、重复/空/伪造头。
- 明确测试 Host 的合法集合；是否接受尾点、简写 IPv4/其他 127.* 需保持默认严格且写在测试里，不能隐式扩大。
- 以 spy receive 和副作用桩断言拒绝前没有正文读取、任务创建、磁盘写入、配置读取、登录、子进程或外部调用。
- 对 GET/POST/PUT/PATCH/DELETE/OPTIONS，任意恶意来源先被拒绝，不能依靠下游 422/405 冒充安全拒绝。
- 无 Origin 的原生请求、标准同源 POST、localhost/127.0.0.1/[::1] 各自同源，以及直接首页导航正常。
- TestClient 统一使用合法本机 base_url，审查现有默认 testserver 的使用；不能为测试给产品添加 testserver 白名单。
- MCP HTTP 客户端/stdio 工具测试继续通过；挂载 SSE 模拟多段、断连及不合法 Origin，保留 SDK 校验。
- 现有所有 API、上传、取消、模板、收藏、导出、恢复、凭据脱敏和静态资源测试继续通过。
- 完整 `pytest -q -rs`，以 D 的 `1106 passed, 3 skipped` 为历史基线；跳过原因不得增加。
- Node 语法、pip check、tracked/untracked/staged diff 检查；保留当前未提交工作区。
- 隔离服务+独立浏览器 profile 验证本机正常 UI；在第二个本机端口用无副作用测试路由验证跨源请求被拒绝。
  不使用真实登录/Key/任务，不关闭浏览器本地网络防护来伪造利用成功。

### 完成门槛与后续

Host/Origin 缺口和未知 peer 规则通过失败先行与完整回归，再将本项标为源码修复验收完成。
浏览器矩阵通过不代表便携版已修复；新的打包与发布仍需单独验收和授权。
本轮只完成审查及合同，没有修改运行时源码，不把漏洞观察计作修复成功。

建议下一轮范围为限定本地开发：补测试与最小源码修复；本合同本身不授予执行权限，不附带依赖安装、远端 Git、构建、LLM、
模型/媒体下载、真实平台登录、飞书写入或读取已有凭据。若需要 token、远程模式或跨源接入，先重新明确产品合同。

## 验证状态

18 项离线观测及两个源码 hash 已核对；现有 API/MCP 回归 `195 passed, 1 skipped in 32.20s`，仍是 test_api.py:2025 的既有 Windows 符号链接权限跳过。
本轮没有重跑完整套件，`1106 passed, 3 skipped` 属于前轮 D，不是新的安全修复证明。
