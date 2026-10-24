# G5.1 有界历史摘要缓存设计与实施合同

2026-10-24 当前状态：[D](21-history-cache-default-rollback.md) 已回退默认列表缓存，安全检查不变；仅隔离实验可显式替换列表读取入口。下文是实验合同与 A/B/C 历史，不是当前默认启用声明。

日期：2026-10-23。状态：**A/B 功能规则及 C 刷新/浏览器门禁已验证；C 成对复测发现性能退化，性能门禁失败，未进入发布**。见 [A](18-history-cache-a-acceptance.md)、[B](19-history-cache-b-acceptance.md)、[C 证据](20-history-cache-c-acceptance.md)。

B 接入列表缓存与写后失效；C 增加可选 refresh 参数和迟到响应保护。当前仅实验分支，1,000 条命中 p95 1189.446ms，慢于同轮直接读取的 810.114ms，已停止 10,000 条扩测。以下接线前源码行号与设计轮结果是历史依据，当前实现及限制以 C 证据为准。

本轮用户认可的是 G5 验收后的下一步建议。这里将缓存细化为可逐项验收的任务，
不把对设计方向的认可扩大为数据库、任务系统重写或发布授权。
当前产品仍为 `1.0.0-beta.3`，分支为 `codex/beta4-progress-result-loop`，
HEAD 为 `7ff61e7568a324b9d2e7a31161ff0b7927ca3f9b`；已有 G0–G5 未提交修改全部保留。

## 1. 要解决的问题与不做的事

G5 已把一次历史查询的清单读取从 2N 降到 N，1,000 条暖查询 p95 仍为
1011.433ms，10,000 条为 8834.461ms。清单里有模板全文和运行日志，历史列表只需要少量字段。
原始报告、方法与限制见 [G5 验收](16-g5-acceptance.md) 和
[历史基准](../quality/history-benchmark.md)。这些是处理函数计时，没有包含 HTTP、DOM 或冷磁盘。

目标：重复查询尽量复用已经读过的磁盘摘要，同时保持收藏、状态、隐藏规则、筛选与分页语义。
参考目标仍为 1,000 条默认暖查询 p95 < 300ms；能否达到须重新测量，不能预先保证。

本阶段不增加数据库、磁盘索引、文件监听依赖、后台线程、全文搜索或缓存管理设置页面。
不改变笔记、清单、工作区结构、预加载上限、下载、ASR、LLM、恢复或删除规则。
不缓存正文，不缓存模型配置、凭据、完整 URL、模板布局/指令、日志或原始异常。
冷查询仍可能较慢；不把首次全量扫描或事件循环阻塞宣称为已经解决。

## 2. 当前实现与接入位置

以下行号是本次设计时的位置，后续修改应以符号名定位：

| 当前入口 | 已核对的行为 | 缓存接入约束 |
|---|---|---|
| [main.py:970](../../backend/main.py#L970) `_read_history_manifest` | 验证 task ID/目录，读取完整清单；也供按需恢复使用 | 保留直接读取，禁止把通用 reader 改成缓存 reader |
| [main.py:982](../../backend/main.py#L982) `_history_task_record` | 合并磁盘和内存字段，返回摘要与同一清单 | 提取纯摘要归并，先锁定旧行为，再接列表专用缓存 |
| [main.py:1033](../../backend/main.py#L1033) `iter_history_task_ids` | 合并内存 ID 和当前文件夹发现结果 | 每个请求继续发现新增/删除，不缓存 task ID 集合 |
| [main.py:1657](../../backend/main.py#L1657) `list_recent_tasks` | 全量摘要、隐藏 agent 转录、筛选、稳定排序再分页 | 唯一默认启用缓存的业务入口；不改 total 口径 |
| [main.py:1718](../../backend/main.py#L1718) `set_task_favorite` | 新鲜摘要决定 404/409，再合并写入 favorite | 收藏资格检查继续绕过列表缓存 |
| [main.py:1732](../../backend/main.py#L1732) `inspect_source` | 复用判断后返回摘要 | 不因历史缓存改变转录可复用判断 |
| [task_repository.py:54](../../backend/task_repository.py#L54) `update` | 条带锁内原子替换，merge 也经过这里 | 写入成功后集中使该清单缓存失效 |
| [main.py:2952](../../backend/main.py#L2952) `delete_task` | 等待既有 cleanup，再移除内存任务 | 完成后精确失效，发现扫描仍为删除兜底 |
| [script.js:820](../../frontend/script.js#L820) `loadRecentTasks` | 共享搜索、加载更多和刷新请求 | 手动刷新与普通读取区分；补迟到响应保护 |

只允许列表读取走缓存。任务 GET、按需恢复、完整转录验证、幂等检查、收藏资格、
文件打开和导出继续使用各自的新鲜读取及安全检查，不能用摘要替代这些判断。

## 3. 选定的缓存边界

采用**单进程、仅内存、按清单粒度的 LRU 投影缓存**。进程退出即丢弃，启动不加载缓存文件。
`task.json` 仍为磁盘依据，内存任务保持当前优先级。任何条目缺失、不可缓存或被淘汰都走原 reader。

建议新增 `backend/history_cache.py`，只处理容量、指纹、TTL、失效与只读投影。
依赖方向为 main → history_cache、main → task_repository、task_repository → history_cache；
history_cache 不导入 main 或 repository。需要读取时由调用者传入只读 loader，
loader 不允许调用 update、restore 或任何写操作，避免依赖循环和锁反转。

首个实现固定以下内部默认值，不新增环境变量或用户配置：

| 项目 | 初始合同 | 超出时的行为 |
|---|---|---|
| 条目数 | 最多 12,000 个，涵盖当前 10,000 条实验 | LRU 淘汰，不截断可查询历史 |
| 投影负载 | 总编码负载最多 16 MiB，单项最多 64 KiB | 单项超限不缓存，继续新鲜读取；总量超限先淘汰 |
| 外部同指纹复核 | 自上次成功读取起最多 30 秒 | 下次查询重新读取；命中不延长此期限 |
| 工作区 | 一次只服务当前规范化工作区及根目录身份 | 根路径或身份变化即清空；A→B→A 也重建 |
| 错误/空清单 | 不做负缓存 | 后续请求仍尝试读取，修复后可恢复 |

16 MiB 是投影编码负载上限，不是 Python RSS 保证。字典、字符串、路径、锁和 LRU 管理
有额外成本，验收必须单独记录 tracemalloc 及其边界。不能为了让大条目入缓存截断标题或改变筛选。
若大部分条目因负载限制不能命中，按报告说明原因，不在本阶段自动扩大容量。

### 3.1 投影字段与旧行为

只保留摘要归并所需的标量：磁盘标题回退值、运行结果标题、output、origin、favorite、
模板名称、created_at/finished_at、状态、step_name、progress、elapsed_seconds，以及平台判定所需的派生标记。
原始 source_url 在投影生成时转换为平台类别；不保留 URL、查询参数或上传文件绝对路径。
上传文件名只派生标题回退值及“存在上传文件名”标记。

投影和返回的摘要不能共享可变字典。归并每次产生新结果，外部调用者修改结果不会污染下一次查询。
遇到未覆盖的旧值类型先回退直接路径，不能通过新类型强转悄悄改变旧数据行为。
缓存项仍包含用户任务标题，它是进程内查询数据，不能把整个缓存导出为诊断或写入报告。

尤其保留以下容易出错的现有优先级，参见 `_history_task_record` 和 `_history_platform`：

- 存在 live result 字典时，即使是空字典，也不回退 runtime result；标题再取磁盘标题/文件名。
- live progress=0 必须保留；不能用 truthy 回退覆盖。status、step_name 等沿用各自原规则。
- favorite 只认清单中的布尔 true，不读取 live favorite，不把字符串 `"true"` 当成 true。
- manifest origin 优先于 live `_origin`；只有 web 来源的纯转录显示在历史。
- 平台的清单来源、live result.source、上传文件标记顺序保持原样；提前分类不能丢失 live 回退。
- 活跃任务 elapsed_seconds 在每次查询现场计算；不能被冻结为缓存建立时的数值。
- has_transcript 每次检查当前文件存在性，不缓存；它不证明转录可用，复用仍走完整验证。

运行态与隐藏规则来自本次的同一份投影，再叠加当前 live 字段，不重复读取两个磁盘快照。
缓存不能导致全量历史被加载进 `tasks`；也不调用 `restore_task_on_demand` 来生成列表。

### 3.2 指纹与读取过程

命中前继续验证 task ID、工作区、规范化任务目录，以及当前清单为独立普通文件。
文件指纹至少含 st_dev/st_ino、st_mode、st_nlink、Windows 文件属性、st_size、st_mtime_ns、st_ctime_ns；
目录身份变化也触发失效。缺少可靠身份或元数据读取失败时绕过缓存，不以字段缺失值视作可靠命中。
符号链接、Junction/reparse point、硬链接或目录不能从旧缓存获得合法性，沿用既有拒绝规则。

未命中时：检查指纹 → 经原 reader 读取 → 白名单投影 → 再检查指纹 → 仅在两次相符时入缓存。
中途变动则丢弃候选，最多再新鲜读取一次；持续变动不入缓存，沿用现有直接读取的容错边界。
不要引入无限重试，也不要在读取失败时返回上次成功投影。

这不形成全工作区原子快照，也不能消除外部进程并发替换的全部 TOCTOU。
本阶段保留每请求 O(N) 的发现、身份检查和归并，以及排序成本，不能把缓存命中等同于 O(1) 列表查询。

## 4. 更新与失效合同

| 事件 | 必须表现 | 机制/测试 |
|---|---|---|
| 同进程 repository 成功更新 | 写操作返回后发起的下一次查询可见变化 | os.replace 成功后、update 返回前精确失效；收藏/进度/发布共用入口 |
| repository 写入失败 | 保留旧文件；不得把候选值写进缓存或返回成功 | 沿用原异常；补 replace/change 失败回归 |
| live 状态或结果改变 | 下一次归并使用当前内存值 | 不缓存完整最终响应；计时现场计算 |
| 删除任务成功 | 下一次查询不出现被删除磁盘任务 | 删除后失效 + 每次重新发现；不新增自动删除 |
| 外部新增、删除、普通修改、原子替换 | 下一次查询发现新增/删除或指纹变化并重读 | 每次发现与身份检查；不缓存缺失/损坏状态 |
| 外部同大小且恢复 mtime 的修改 | ctime/身份变化时立即重读；若所有指纹均未变则允许暂时旧投影 | 从成功读取起 30 秒后下一次查询强制复核，或手动刷新立即重读 |
| 外部损坏清单 | 检出变化后不再使用旧投影；仍按当前损坏清单/内存回退规则处理 | 先失效，不能 stale-if-error；修复后重新读取 |
| 转录文件新增/删除 | 下一次 has_transcript 反映现况 | 不缓存该文件存在性；正文和 hash 校验不受缓存影响 |
| 工作区切换、同路径根目录被替换 | 不出现另一个工作区的条目 | 规范化路径和根身份绑定；清空并重建 |
| 重启、容量淘汰、手动刷新 | 可完全从清单恢复 | 无持久缓存、无迁移；对照直接路径响应 |

“30 秒”是有查询触发时的复核期限，后台不会定时扫描。机器休眠或无人操作后，下一次查询检查单调时钟期限。
外部修改的立即性只针对指纹能检测的变化；元数据完全相同的改写无法同时满足零读取和即时发现。
这属于明确的行为取舍，不能在 README 中写成所有外部修改立即同步。

磁盘字段重读后仍受原有 live 优先级约束。例如已加载任务的 live result.title 不会因刷新清单
被强制替换。清单损坏但任务仍在内存时也沿用当前内存回退，不能借本阶段改变该语义。

### 4.1 并发与失效顺序

不启动后台扫描或把任务列表移到线程。缓存自己用有界 RLock 保护条目查找/装入和精确失效，
锁只覆盖单条记录，不覆盖全量扫描。repository 保留原条带锁，锁顺序只能是 repository → cache。
cache 内的 loader 调用现有无写锁 reader，不能尝试获取 repository 写锁。

若加载旧清单与写入发生重叠，writer 在替换后等待该缓存临界区结束，失效后才返回。
因此写成功之后开始的查询不能命中这份旧项；已经开始的并发查询允许沿用当时读取结果。
不要为此建立永久增长的 per-task revision 表或任意 observer 列表。精确失效不做 I/O、不调用插件。
内存分配故障等灾难性异常不在可恢复缓存承诺内；普通缓存数据异常按清空/直接路径降级。

## 5. 手动刷新与接口兼容

实际仅新增 `GET /api/tasks?refresh=true` 的可选布尔参数，默认 false；响应仍为
tasks/total/offset/limit/has_more，摘要字段不增加缓存内部信息。
refresh=true 只清空当前工作区的历史摘要缓存，再按当前筛选执行全量发现/读取；
与任意缓存 miss 一样可按容量重新装入，不修改任务、笔记或模型配置。
非法布尔值按 FastAPI 现有校验返回 422；旧调用和 MCP 行为继续兼容。

现有 `#refreshRecentTasksBtn` 对应一次 refresh=true 请求，保留筛选，从 offset=0 重载。
普通搜索、筛选、加载更多、收藏后的重载、轮询后重载不强制刷新全库，避免抵消缓存。
可以为 loadRecentTasks 增加默认 false 的第三个参数，保留已有前两个参数的含义。
当前 fetch 的 `cache: 'no-store'` 继续保留，它只影响 HTTP 缓存，不等于后端清单缓存失效。

前端同时补历史请求序号和筛选快照校验：刷新/换筛选后到达的旧搜索或旧追加页不能覆盖新列表。
AbortController 只用来取消旧 fetch，不据此认定服务器已经中止扫描；刷新按钮的 disabled
状态只能由当前请求恢复。失败保留现有列表并提示，不显示“已刷新”或自动无限重试。

## 6. 分步实施，逐步验收

本设计之后的实施按下列三步开展。每一步都可停留在有测试证据的检查点，不能把步骤 A 完成写成整个 G5.1 完成。

### A：纯缓存与新鲜度规则

允许文件：新增 backend/history_cache.py、tests/test_history_cache.py；必要时只补原 repository 测试。
先写红测再实现 LRU、双重上限、固定 TTL、工作区隔离、指纹变化与不缓存失败。
测试注入单调时钟和 loader，不 sleep、不触碰用户工作区、不启动服务。
验收：完全离线、限制可重复断言、命中不延长 TTL、返回值不能污染缓存。
这一步暂不接入生产列表，功能行为不变。完成后审阅代码再进入 B。

后续状态：用户已授权开始 A，独立模块及测试已交付，结果见 [A 验收](18-history-cache-a-acceptance.md)。
这不表示本节后续 B/C 的接线或性能门禁已经通过。

### B：接入历史与统一失效

允许文件：backend/history_cache.py、backend/task_repository.py、backend/main.py、
tests/test_history_cache.py、tests/test_task_repository.py、tests/test_history_performance.py、
tests/test_api.py，必要时新增 tests/test_history_cache_integration.py。
先锁定归并优先级和直接路径对照，再接列表、repository 精确失效及删除兜底。
通用清单 reader、按需恢复、收藏资格、来源复用完整校验均不使用缓存。
将 G5 的“无跨请求缓存”测试改名为“更新/删除即时可见”，保留原断言，不能删掉兼容门禁。
验收：冷路径与命中路径响应相同；写后立即可查；不加载正文、不加载全部任务进内存。

### C：刷新交互、重测与收口

额外允许文件：frontend/script.js、tests/test_frontend_hygiene.py、
新增 scripts/verify_history_cache_browser.mjs、scripts/benchmark_history.py、
本合同关联文档及 docs/quality/benchmarks/ 下新增无隐私报告。
补 API 可选 refresh 和前端手动刷新/迟到响应行为；不重排页面或扩展其他功能。
用合成数据跑真实浏览器刷新和筛选乱序；当前用户服务不动，若需服务只使用明确归属的隔离实例。
若没有执行浏览器验收，明确该缺口，不以字符串断言代替点击行为。
同设备、相同输入、相同查询、相同排序下测 cache-empty、hit、refresh、失效、超过容量六种状态。
针对性与完整回归、源码审阅通过后同步状态文档。无版本升级、构建、提交或发布。

## 7. 可直接编写的测试清单

以下是分阶段验收要求。A 覆盖核心 C01–C10；B 已补真实 repository 并发、列表与 I 类集成证据。
C 已验证 I01 refresh 与 U 类前端门禁；性能对照失败且按规则停止扩测。设计本身不证明实施门禁通过，按对应验收记录核对。

| 编号 | 输入/操作 | 可重复的通过条件 |
|---|---|---|
| C01 | 相同指纹连续读取 | 首次 loader=1，命中不再读清单；正文读取=0 |
| C02 | 改 mtime/size/identity/ctime/类型/链接数或 Windows 属性 | 每个变化拒绝旧项；不安全类型拒绝命中 |
| C03 | 模拟完全相同指纹，改变 loader 内容 | 29.9 秒可命中，30 秒后首次查询重读；无需 sleep |
| C04 | 第 29 秒反复命中 | 最初 30 秒期限不后移 |
| C05 | 极小测试容量，交替访问 | LRU 顺序准确，条目数/负载从不超上限；淘汰不影响查询总数 |
| C06 | 单项超限、空/坏 JSON、loader 抛错 | 无负缓存，不返回旧项；随后修复可重新加载 |
| C07 | 改返回的字典、嵌套值 | 下次结果不变；投影不持有完整原清单引用 |
| C08 | A→B→A、同路径工作区换身份 | 不跨区命中；旧 cache 对象重建可恢复相同列表 |
| C09 | 读取期间换文件，连续换文件 | 变动候选不入缓存，有限尝试；无自旋/无限等待 |
| C10 | 两个线程通过 barriers 重叠加载/成功写入 | writer 返回后的读取没有旧 favorite；按约定锁顺序无死锁 |
| I01 | 所有 G5 四种查询，cold/hit/refresh | tasks 与分页字段逐项一致，排序 tie-break 不变 |
| I02 | live result={}、progress=0、运行计时增加 | 与旧归并完全相同；活跃耗时不冻结 |
| I03 | web/agent origin 与 live origin 冲突 | 与 G5 同快照隐藏规则一致，缓存内部标记不泄漏到 API |
| I04 | 已命中后 repository.merge favorite；直接 update runtime | 写成功后下一请求即见变化，不依赖 TTL 或文件时间精度 |
| I05 | change/serialize/replace 失败 | 原清单保留，无候选值入缓存，无临时文件残留 |
| I06 | 冷清单为空/损坏；已有项被破坏再修复 | 不使用 stale-if-error；保留既有 live 回退语义，不回写损坏文件 |
| I07 | 外部新增/删除/原子替换 | 非预加载旧任务仍可查；无缓存幽灵项；tasks 体积不随历史增长 |
| I08 | 转录文件存在性改变 | has_transcript 下次变化；复用资格仍由完整验证决定 |
| I09 | 返回标题/路径等放入合成敏感哨兵 | 缓存只保留白名单；报告与日志不输出原清单、标题或路径 |
| I10 | 收藏/恢复/源预检/导出/打开文件 | 这些入口不依赖可能过期的列表缓存作授权或可用性判断 |
| U01 | 当前筛选下点刷新 | 一次 refresh=true、offset=0；筛选保留；不提交任务 |
| U02 | 普通搜索/加载更多/收藏后重载 | 无 refresh=true；分页按原 offset/limit |
| U03 | 延迟旧搜索或旧追加页，随后刷新/换筛选 | 旧响应不覆盖/追加当前列表；按钮状态归当前请求 |
| U04 | 刷新失败、空列表、390px 键盘操作 | 保留旧列表/解释空状态；可重试、焦点可达、无整体横向溢出 |

路径拒绝用无特权 stat/reader 替身覆盖，保留既有真实符号链接测试，不能因环境限制增加 skip。
并发测试用 barrier/event 而非时间碰运气；不启动真实 LLM、下载器或 Feishu。

## 8. 基准与最终门禁

复用 [benchmark_history.py](../../scripts/benchmark_history.py) 的合成数据及四种查询。
新报告使用新 schema/测量标识并记录 cache mode、TTL、容量、hit/miss/eviction、读取次数、
时间样本、数据身份与源码 hash；不能用旧 G5 schema 隐藏缓存状态。
旧 G5 JSON 保留，不覆盖。固定终态合成数据用于响应 hash 对照，活跃任务计时另做行为测试。

- 在 100 / 1,000 / 10,000 条分别测空缓存首查、全部装入后的重复查询和显式刷新。
- 命中计时批次控制在 TTL 内；每批记录起止时间，跨期限样本另记为重读，不混称纯命中。
- 单项修改后测失效重读，另用小容量完整扫描验证没有漏记录或不可终止的淘汰循环。
- 静态、容量足够、TTL 内的完整命中查询期望清单 open=0、正文 open=0；stat/resolve 仍发生，单列计数。
- 计时与 IO/内存 instrumentation 分开，不把 Python allocation 当 RSS，不把 7 个样本当稳定 SLO。
- 先测 1,000 条验证方向；无收益或明显退化时停止扩大实现，保留原因，不自动转 SQLite。
- 测量正确时即使超过 300ms，也如实记录“功能规则通过、性能目标未达”。不得靠限制历史数量达标。

最终命令在独立 VIDEO2KNOWLEDGE_WORKSPACE、WHISPER_CACHE_DIR 且 PYTHON_DOTENV_DISABLED=1 下运行，
避免导入 main 时扫描用户目录或读取项目 .env：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_history_cache.py tests/test_history_cache_integration.py tests/test_history_performance.py tests/test_task_repository.py tests/test_api.py tests/test_frontend_hygiene.py -q
.venv\Scripts\python.exe -m pytest -q -rs
node --check frontend/script.js
node --check scripts/verify_history_cache_browser.mjs
node --check scripts/capture_readme_screenshots.mjs
.venv\Scripts\python.exe -m pip check
git diff --check
git diff --cached
git status --short
```

新文件/脚本未创建前不要把上述整组命令标为已执行。完整回归基线为 G5 的
978 passed、3 个既有 Windows 符号链接权限跳过，不能新增 skip。
最终独立审阅 tracked/staged/untracked diff，保留 G0–G5 修改，逐项区分设计、实现、测试和发布。

## 9. 风险、回退与权限

- 只省 JSON 读取仍有 O(N) 文件元数据成本：按相同基准决定收益，达不到目标也不削弱路径校验。
- 缓存键/投影污染：限定单工作区、有界内存、只读副本、白名单投影；不缓存异常原文。
- 外部同指纹改写最多等待复核：30 秒硬 TTL + 明确手动刷新；涉及副作用的资格判断绕开缓存。
- 清单本来可能很大：此设计不承诺限制原 reader 的全部瞬时分配；大清单读取上限是另一个兼容性议题。
- 运行态与磁盘并发：保持当前 live 优先级和单后端范围，不声称跨进程事务一致性。
- 回退：撤回列表缓存入口及写入失效接线即可恢复 G5 的直接扫描；无数据迁移、无文件需要删除。

原设计轮只落设计与项目状态，后续 A 已单独实施。后续本地源码/测试实施按 A→B→C 逐步确认和验收；
不需要安装依赖或更换模型。后续若要启动测试服务，使用隔离目录/端口并记录精确进程所有权。
Git commit/push/tag/release、构建、真实 LLM、凭据、模型/媒体下载、平台登录和飞书写入
仍不包含在这份缓存合同的实施范围内。不得把旧 beta 发布授权沿用到本阶段。

## 10. 原设计轮的检查结果（A 实施前）

本轮仅修改本设计、规划入口及相关项目文档。没有新增缓存模块、接口、前端行为或缓存测试。
独立工作区 `.test-tmp/g51-design-20261023/workspace/` 下，禁用 dotenv 后运行：

```text
pytest tests/test_history_performance.py tests/test_task_repository.py -q
36 passed in 2.98s
```

这些用例验证当前 G5 历史/存储基线，没有验证尚未实现的缓存。完整 978 passed / 3 skipped
是上一轮 G5 结果，本轮没有重跑完整套件。新设计与规划入口的 13 个本地链接及行号范围检查通过，
tracked diff 和两份新文件的 whitespace 检查无错误；staged diff 为空。
main、task_repository 和基准工具的 SHA-256 与 G5 优化后报告一致，没有改写这三份代码或旧基准报告。
未启动测试服务，未接触用户工作区/凭据，未执行 Git 提交、构建或发布。
