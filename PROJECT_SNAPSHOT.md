# 项目接续快照

更新时间：2026-10-24。

最新：[Beta.4 本地收口验收](docs/strategy/27-beta4-local-release-acceptance.md) 完成。三个本地提交 `90655e4`、`a129f65`、`7df3d51`，候选输入归属 `7df3d51`。最终独立快照 1382 passed、3 个原有跳过；五套九组浏览器、打包新旧环境变量、HTTP/MCP、历史收藏重启、原文对照和离线 ASR 通过，直接 worker 确认 small/CPU/exit 0。EXE 133248935 字节，SHA-256 `f78ed36f707ff8d302f6e721b7b4f18067b0dcd3d64e63ed1f6afa190968dc5b`，保留 `.test-tmp/beta4-closeout-20261024/source/dist/`。本次进程/合成工作区/WAV 已清理，旧 dist 元数据和校验文件未变。未推送、打标签或发布，下一步须单独授权远端 Draft 资产验收与公开流程。下方为历史。

当前：用户已授权本地收口，产品版本已改为 `1.0.0-beta.4`。`90655e4` 产品提交独立快照 1329/3、`a129f65` 工具提交独立快照 1381/3；三个跳过不变。五套浏览器脚本各九组通过，合成截图已更新。版本/文档提交和 Beta.4 重建验收进行中，尚未完成候选验收。未推送、打标签或发布；旧 Beta.3 候选摘要不可复用。下方记录均为历史。

当前入口：[Beta.4 版本与发布收口计划](docs/strategy/26-beta4-release-closeout-plan.md) 已制定，尚未实施。建议按依赖整理产品实现、内部工具、版本/文档三个提交，再重新构建 Beta.4；远端采用 Draft 资产先验收后公开。版本仍为 Beta.3，本轮未暂存、提交或更改远端。下方各阶段的“下一步”均为当时记录，以本段入口为准。

最新：[隔离便携候选验收](docs/strategy/25-isolated-portable-acceptance.md) 已通过。60 个显式输入冻结构建，候选仍为 Beta.3，133247311 字节，SHA-256 `f293e960102fc37a492cdf77be86eb2d6d2bd15d58076c8bb1713acb5f99e458`。模板/历史/收藏重启、安全拒绝、原生 HTTP、MCP SSE、真实离线 ASR 均通过；直接工人验证 small/CPU/exit 0。产物保留 `.test-tmp/s2-portable-20261024/source/dist/`，不能与原发布同名 EXE 混淆。未改产品源码，无新整套 pytest，沿用匹配源码的 1381/3。测试进程已停、WAV 已删，无 stage/commit/push/release。下一步先设计 Beta.4 的版本、聚焦提交和最终发布验收边界，改版本须重新构建。

最新：[累计关键路径复核与本机客户端验收](docs/strategy/24-source-review-client-acceptance.md) 完成，完整 `1381 passed, 3 skipped in 83.64s`，同三项权限跳过。真实 HTTP 上传/读取、MCP SDK SSE 握手/工具/合成笔记转录读取均通过。两个便携 smoke 已增加精确进程归属检查；实际 Windows 验证只请求归属服务，用户 8000 未探测。产品源码/版本未再修改，无提交/构建/发布。下一步按该文档合同进行独立目录候选构建与打包态验收，不能覆盖原发布资产或把 HEAD 当作脏工作区全部构建输入。

当前接续：[S0 请求边界源码验收](docs/strategy/23-local-request-security-acceptance.md) 已通过，完整 `1367 passed, 3 skipped in 73.82s`，同三项 Windows 权限跳过。Host/Origin/Fetch Metadata、未知 peer 与代理头信任已收紧；真实跨端口浏览器 POST/GET 返回 403，同源与九组历史页面通过。下面审查段落的“尚未修复”描述保留为历史。版本、HEAD、已发布资产未变，无 stage/commit/push/build。下一候选为累计源码审查和独立的打包兼容验收，不能把源码通过视为 Release 已修复。

- 仓库：Video2Knowledge-next；产品版本仍为 `1.0.0-beta.3`。
- 分支：`codex/beta4-progress-result-loop`；HEAD：`7ff61e7568a324b9d2e7a31161ff0b7927ca3f9b`。
- 最新为[本机请求安全审查与 S0 合同](docs/strategy/22-local-request-security-audit.md)：18 项隔离 ASGI 观测确认 REST 缺 Host/Origin 检查、空体外来 POST 可达，未知 peer 默认放行；MCP SDK 另有有效拒绝，不能混同。发现发布阻断风险，尚未修复。现有 API/MCP `195 passed, 1 skipped in 32.20s`；产品与测试源码未动，没有真实服务/登录/凭据操作，没有新完整回归。下一步按 S0 合同先补失败测试再做最小修复，保留原生无 Origin 客户端及 SSE，不能把审查标成修复完成。
- 当前最新完成 [G5.1-D](docs/strategy/21-history-cache-default-rollback.md)：默认历史列表已回退为新鲜读取，缓存仅由隔离实验显式替换 list-only reader；没有产品开关。C 的刷新与乱序保护保留。1,000 条本轮默认 p95 742.230ms，四种输入/响应 hash 与 C 对照一致，仍未达 300ms。完整 `1106 passed, 3 skipped in 75.36s`，同三项权限跳过；新浏览器 9 组通过，Python/Node/pip/diff 检查通过。18754 自建服务和浏览器已停，8000 未动。以下默认缓存启用、等待剖析或等待回退的段落均为历史，无 Git 或发布操作。下一建议为发布前 Host/Origin 安全审查，性能方案另立合同。
- 当前工作区有未提交源码、测试与文档修改。包含前轮进度/结果入口、G0 修复、G1 前端、G2 存储/恢复、G3 原转录对照、G4 离线质量工具、G5 历史基准/请求内去重和 G5.1-A/B 历史缓存，全部保留，未 stage/commit/push。
- 最新完成 G5.1-B：仅历史列表使用投影缓存，repository 成功替换后和任务删除后精确失效；收藏资格、恢复、复用与产物操作继续新鲜读取。专项 `153 passed in 6.88s`，最终隔离完整 `1095 passed, 3 skipped in 70.51s`，同三项 Windows 权限跳过；编译、Node、pip 与差异检查通过，见 [B 验收](docs/strategy/19-history-cache-b-acceptance.md)。35 条四种合成查询暖态清单读取为 0、正文读取为 0，响应一致；没有进行性能计时或宣称达标。前端和旧基准脚本 hash 未变化。
- 最新 G5.1-C 已实现可选 refresh 参数、保留筛选的首屏刷新、请求序号/筛选快照保护；Chrome 9 组通过，见 [C 证据](docs/strategy/20-history-cache-c-acceptance.md)。独立服务 18753 已精确停止，8000 未动。合成证据目录 `.test-tmp/g51-c-browser-20261023/evidence/`。
- C 性能门禁失败：1,000 条默认 p95，缓存命中 1189.446ms，同轮直接读取 810.114ms；四种查询均变慢，虽然暖清单读取为 0。resolve 入口从 N 增为 3N。输入和响应 hash 与 G5 一致，按停止规则没有运行 10,000 条，报告见 `docs/quality/benchmarks/g51-c-20261023.json`。下一候选是先剖析检查/投影成本，无法安全获益则回退默认缓存；不自动上数据库，不把本轮标成性能优化成功。以下 A/B/设计轮描述保留为历史记录。
- C 最终针对性 `393 passed, 1 skipped in 22.21s`，隔离完整 `1103 passed, 3 skipped in 73.28s`，同三项权限跳过；Python/3 项 Node/pip/差异检查通过。完整回归目录 `.test-tmp/g51-c-regression-20261023/workspace/`，禁用 dotenv。原 HEAD/版本与未提交状态保持不变。
- G0.1–G0.4 已通过源码本地验收：`796 passed, 3 skipped`；Node 三项语法检查、pip check、diff check 通过；9 组浏览器矩阵通过。
- 唯一未完成的环境清理：工具策略拦截删除 `%TEMP%\Video2Knowledge-g0-20261022-233920`，其中没有文件，仅保留空目录结构。隔离服务已停止，截图证据留在 `.test-tmp/g0-acceptance-20261022/`。
- 详细证据与边界：[G0 验收记录](docs/strategy/07-g0-acceptance.md)。后续合同：[交付计划](docs/strategy/05-delivery-plan.md)。
- G1 已完成来源先行、折叠长模板预览、目录与正文查找、MD/ZIP 下载反馈及焦点修复；最终完整回归 `800 passed, 3 skipped`。G1 与 G0 浏览器矩阵各 9 组通过，证据留在 `.test-tmp/g1-acceptance-20261023/`，详见 [G1 验收记录](docs/strategy/08-g1-acceptance.md)。
- G1 的隔离服务与浏览器已停止，临时浏览器 profile 已清理；截图与空隔离 workspace 保留。用户原有服务实例未动。
- G2 已完成任务清单串行原子合并、完整转录校验、来源/parent/ref、可选请求 ID 幂等与只读未知态查询、HTTP/MCP 恢复摘要及失败 UI；最终 `848 passed, 3 skipped`，G2/G1/G0 浏览器各 9 组通过。见 [G2 验收记录](docs/strategy/10-g2-acceptance.md)，实现入口 `backend/task_repository.py`、`backend/main.py`、`backend/mcp_server.py` 和前端失败面板。
- G2 测试替身验证 LLM 失败后恢复的音频下载/平台读取/ASR 次数为零；没有真实模型、凭据或飞书调用。幂等依赖当前工作区完整清单，限单后端进程；删除/损坏/换工作区后不保证重放。浏览器请求 ID 只在当前页面保留。
- G2 无隐私证据位于 `.test-tmp/g2-acceptance-20261023/`；测试服务精确进程 28544 与浏览器已停止，临时浏览器 profile 已清理，保留截图与无任务数据的隔离 workspace。
- G3 已完成时间范围原转录对照、稳定 hash、100 段分页、笔记与转录版本冲突保护、迟到响应隔离、键盘返回及当前笔记显式刷新。最终 `883 passed, 3 skipped`，G3/G1/G2/G0 浏览器各 9 组通过，见 [G3 验收](docs/strategy/12-g3-acceptance.md)。不增加 LLM 调用、不修改 Markdown 或任务格式。
- G3 原文使用文本节点；时码按钮跳过代码/公式/链接，最多 200 个。多 P 使用累计时间轴，不提供不可靠的逐 P 视频跳转。时间命中不证明观点正确；完整转录/笔记每次重新校验，尚无超长任务性能保证。
- G3 隔离证据在 `.test-tmp/g3-acceptance-20261023/`，81 张截图及 3 个无隐私合成任务文件保留；8018 隔离服务和浏览器已停止、profile 已清理，用户原服务未动。
- G4 离线轨已按用户「继续」实现：12 合成案例/36 个字面信息点、规则 CLI、未评分人工表、诊断白名单参考投影、环境清单和资产本地四方对照。针对性 `74 passed`，最终完整 `957 passed, 3 skipped`；Python/Node 语法、pip 和 diff 检查通过。无模型、用户工作区、构建或外部 Git 操作，见 [G4 验收](docs/strategy/14-g4-acceptance.md)。诊断尚无产品 API/UI；字面规则通过不证明事实正确。
- G4 无隐私报告保留在 `.test-tmp/g4-acceptance-20261023/`，最终规则文件是 `reference-rules-final.json`。观察环境 Windows 11 / Python 3.13.7 / PyInstaller 6.22.3，CI/Release Python 3.11 未在本轮验证。
- G5 基准与最小优化已实施：100 / 1,000 / 10,000 合成清单；每请求每任务一次清单读取和目录规范化，保持 HTTP 字段与隐藏 agent 转录语义。相同输入、四种查询响应 hash 一致，专项 `21 passed`，最终隔离完整 `978 passed, 3 skipped`（同三项权限跳过），见 [G5 验收](docs/strategy/16-g5-acceptance.md)。
- G5 1,000 条默认暖查询 p95 从 1755.670ms 降到 1011.433ms，未达 300ms 参考目标；10,000 条仍为 8834.461ms。清单读取减半、列表不读正文，但仍 O(N) 扫描，启动恢复也没有一致改善。没有缓存或数据库。
- G5 原始报告和合成数据保留在 `.test-tmp/g5-before-20261023/`、`.test-tmp/g5-after-20261023/`，无隐私报告副本位于 `docs/quality/benchmarks/`；进程自然退出、没有测试服务。完整回归使用 `.test-tmp/g5-regression-20261023/workspace/` 并禁用 dotenv，不触碰用户服务。
- 下一候选的设计已细化为 [G5.1 有界历史摘要缓存合同](docs/strategy/17-history-cache-design.md)：单进程内存 LRU、12,000 条/16 MiB 编码负载、30 秒固定复核 TTL，repository 写后精确失效，列表手动刷新计划增加可选 refresh 参数。缓存只用于历史列表，恢复/收藏资格/复用/导出等继续新鲜读取。当前只有设计，尚未修改源码或接口，也未运行缓存验收。
- 后续实施按 A 纯缓存与红测 → B 列表接入和失效 → C 刷新/乱序保护及同数据复测逐步推进；现有性能目标继续开放。外部完全同指纹修改允许在 TTL 到期后的下一次查询复核，手动刷新可立即重读磁盘摘要，但不覆盖现有 live 优先级。无数据库、后台线程或发布扩展。
- G5.1 设计轮仅改文档，当前历史/存储专项新鲜结果 `36 passed in 2.98s`，13 个设计/计划本地链接检查通过；main/repository/基准工具 hash 与 G5 报告一致。没有重跑完整套件，978/3 仍是前轮结果；没有缓存测试或实现通过的声明。
- 后续 G5.1-A 按用户「开始」实施：新增独立 `backend/history_cache.py` 和 78 项缓存测试；与旧历史/存储规则合跑为 `114 passed in 3.80s`，详见 [A 验收](docs/strategy/18-history-cache-a-acceptance.md)。固定 TTL、有界负载/LRU、路径/身份校验、单项/工作区失效、有限重读与并发失效已测试。未接入 main/repository/前端，没有公开 refresh 参数或产品性能提升结论；B/C 待实施。上面的“只有设计”是 A 之前的历史状态。
- G5.1-A 最终隔离完整回归 `1056 passed, 3 skipped in 63.64s`，同三项 Windows 符号链接权限跳过；编译、两项 Node 语法、pip 和 whitespace 检查通过。使用 `.test-tmp/g51-a-regression-20261023/workspace/` 且禁用 dotenv，未启动测试服务；原 main/repository/基准/前端 script 的 hash 不变。
- 发布前额外关注：Host/Origin 与浏览器来源安全审查；真实默认程序打开、便携版构建与打包态验收。源码通过不等于发布资产已验证。
- 用户偏好：默认主对话自行开发，不主动更换模型、不调用 worker/子智能体；按限定阶段交付，保留 dirty workspace。
- 未授权：依赖安装、真实 LLM/凭据读取、模型/媒体下载、平台登录、飞书写入、Git 提交/推送、标签与发布。本次没有使用这些权限。
