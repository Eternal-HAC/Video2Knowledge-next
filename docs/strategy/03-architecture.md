# 架构演进与兼容合同

2026-10-24 S0 已提取 `backend/local_security.py`，只负责纯头部语法/来源策略；Host 白名单复用 Starlette，ASGI 包装与业务路由仍在 `main.py`。Launcher 和模块入口显式关闭代理头信任。没有新增认证服务或更换 MCP 传输层，见 [验收](23-local-request-security-acceptance.md)。

状态：架构演进提案，部分已按阶段实施。继续使用 **FastAPI 单体 + 本地文件工作区 + 原生 JavaScript + 已有 ASR 子进程**。研究时事实见 [源码地图](01-research.md#3-当前源码证据地图)。除下述 G2 已实现范围，其余模块拆分仍为拟议设计，不能按此宣称已实现。

2026-10-23 G2 已实现 `backend/task_repository.py` 的清单读取、串行读改写和原子替换；`main.py` 保留薄函数入口、历史扫描、提交与恢复编排，未另建 `task_service.py` 或数据库。增加可选请求 ID、parent/ref 和共享恢复摘要，验证范围限单后端进程，详见 [G2 验收](10-g2-acceptance.md)。表格中的“摘要查询”仍留在主模块；其余服务/路由拆分未开始。

2026-10-23 G3 在既有 `transcript.py` 中实现内容 hash 和时间定位，`main.py` 新增只读分页端点及可选当前笔记刷新，前端结果阅读器负责版本/请求令牌和原文显示。没有独立 citation 服务、持久映射、数据库或模型协议变化，见 [G3 验收](12-g3-acceptance.md)。下方其余模块拆分仍为提案。

## 1. 为什么保留当前框架

下载、字幕获取、ASR、模板、凭据与导出已有独立代码和大量测试。核心问题是主模块承担太多职责、状态信息分散，以及边界合同不足。可以通过小步提取改善，无需迁移技术栈。微服务、Redis/Celery、全量数据库、插件市场会先增加安装与故障成本。

建议依赖方向：Web/MCP 入口 → 任务用例服务 → 现有处理模块与存储。路由只校验和调用；ASR/下载/LLM 适配器不导入 HTTP 路由；前端视图不自行决定任务终态。

## 2. 按风险逐步形成的模块

| 拟议模块 | 唯一职责 | 现有提取位置 | 不能承担 |
|---|---|---|---|
| `backend/task_progress.py` | 纯进度/ETA 计算，数值边界 | `main.py:asr_progress_snapshot` | 落盘、路由、下载 |
| `backend/result_access.py` | 解析受限产物，检查文件边界，系统打开 | `main.py:_trusted_archived_result` 等 | 任意路径执行、重新生成 |
| `backend/task_repository.py` | 清单读写、摘要查询、兼容读取 | `read_task_manifest`、`persist_task_runtime`、历史函数 | LLM 配置/凭据存储 |
| `backend/task_service.py` | 提交、取消、复用、终态协调 | `submit_video_task`、`run_queued_video_task` | 平台专有下载实现 |
| `backend/artifact_service.py` | 文件命名、归档、导出、产物身份 | `archive_note`、附件与 bundle 函数 | 云发布重试策略 |
| `backend/publication_service.py` | 发布尝试状态、显式重试 | Feishu staging/retry 编排 | 改写本地任务成功状态 |
| `backend/api/` | 最后才移动路由，保持 URL | 当前 main 的端点函数 | 业务逻辑复制 |

先提取纯函数，再提取存储与文件边界，最后收拢任务编排。一次只动一个边界，避免同时调整 API、状态机和目录。`main.py` 暂时保留旧函数兼容包装，直到 MCP 和旧测试全部换到明确入口。

## 3. 数据的唯一依据

继续以 `workspace/<task_id>/task.json` 和任务产物为依据。`workspace/notes`、`transcripts` 是归档输出，不作为任务目录扫描。新增索引即使存在也必须可删除重建。

演进先增加可选字段，旧清单按默认值读取：

```json
{
  "schema_version": 1,
  "revision": 7,
  "parent_task_id": null,
  "transcript_ref": {
    "task_id": "source-task-id",
    "content_sha256": "sha256-of-canonical-transcript",
    "segment_schema": 1
  },
  "artifacts": [
    {"kind": "note", "relative_path": "notes.md", "sha256": "..."}
  ]
}
```

示例不包含凭据；字段只是建议。外部导出绝对路径继续用已有目的地合同，不能借 `relative_path` 获得任意文件权限。哈希用于完整性/复用判断，不能证明来源内容正确。

兼容规则：缺失版本按旧版处理；未知字段读后写回保留；未知未来 schema 不做破坏性修改；不在启动时批量重写全部清单。更改字段语义时才评估 `api_compat`，附加字段不能悄悄改变旧消费者。

原子替换只能防半文件，不能防两个读改写丢更新。任务仓库应提供 `update(task_id, patch, expected_revision?)`；单实例按任务锁串行合并，临时文件唯一命名，完成时原子替换。收藏、进度、发布结果必须通过同一写入口。多进程共用 workspace 暂不支持，启动时需明确单写者策略；不能以进程内锁声称跨进程安全。

## 4. 任务状态、重试与恢复

保留公开状态 `pending/uploaded/queued/processing/cancelling/completed/failed/cancelled`。内部用 stage 与 artifacts 标识已完成工作，不立刻新增公开状态值。

提交冻结模板、来源、分 P、输出模式及非敏感生成参数；队列显式记录 enqueue 顺序。并发槽继续复用 Semaphore，不按字典插入顺序推断严格排队次序。

任务终态不可被迟到的进度回调覆盖。取消后不启动新的阶段；已完成有效转录仍可读。进程重启后，原 processing/queued 项记录为中断并提供用户恢复操作，不自动恢复付费调用或远端发布。

恢复计划依据实际校验过的产物：

| 已有内容 | 恢复动作 | 不重复执行 |
|---|---|---|
| 完整转录，笔记失败 | 新任务引用原转录，用户确认再生成 | 下载、ASR |
| 笔记成功，飞书失败 | 新发布尝试，沿用同一笔记 | 下载、ASR、LLM |
| 部分转录且无完整校验 | 明示从转录阶段重做 | 不宣称可以无损断点续传 |
| 外部 Markdown 不见了 | 从任务原稿导出新副本 | LLM |
| 模型调用结果不明确 | 先查询原任务，显示风险 | 不自动再提交 |

拟议请求幂等：新客户端可附带 `client_request_id`；同一 ID 与同一非敏感请求指纹返回同一 task_id；同 ID 不同请求返回 409。按工作区持久化有界映射，重复命中不再次调用模型。API Key 及其哈希均不进入幂等存储。显式“重新生成”使用新 ID。

## 5. 可信进度合同

拟议 `progress_detail` 可包含 stage、kind（measured/estimated/indeterminate）、completed_units、total_units、unit、eta_seconds、updated_at。继续输出旧 `progress` 以兼容；旧 progress 作为阶段位置，不能标成精确总耗时完成率。

估算规则：只在同一 stage 的单调采样上估计；重试/切换模型/换页导致速度改变时重新采样；无时长、NaN/Infinity、零速、长停顿返回未知。多 P 按所选页的实际可用时长累计，部分未知时长则显示页计数加当前页时长，不虚构总百分比。

进度事件可高频留内存，落盘按时间/变化量节流，终态必须落盘。上线前以合成长任务验证事件循环与磁盘负担。现阶段继续轮询；只有测得轮询开销影响体验才评估 SSE，并保持断连后 GET 状态恢复能力。

## 6. 可核对笔记的数据设计

原始转录 immutable；为一个固定转录内容哈希下的片段派生稳定 ID，例如 `s000123`。ID 仅在该转录版本内稳定，不能跨 ASR 重跑复用。

第一阶段不修改 LLM 输出协议：从已有章节时间戳定位重叠转录范围，无匹配就显示“无可定位原文”。第二阶段可选择让同一次生成带段 ID 引用，作为可选能力协商，失败回退普通 Markdown；禁止为了强制 JSON 再完整请求一次模型。

如后续需要映射，存放内部 `note_evidence.json`，包含 transcript hash、note hash、heading/block locator 与 segment_ids。它不是第二篇用户笔记。一条视频仍导出一篇 Markdown；内部机器元数据不自动散落到 Obsidian。修改笔记导致哈希不符时映射失效，不误跳旧证据。

Markdown 内可保留可读时间戳作为可迁移引用。检测器只能检查引用合法性、时间范围与源句匹配，不能保证语义蕴含；不得将“找到引用”包装成事实认证。

## 7. 前端模块化

先将状态输入显式化：`renderProgress(snapshot)`、`renderReadiness(configState)`、`renderResult(artifactState)`，禁止渲染时读写全局网络状态。任务切换带 request sequence，旧响应只允许更新所属任务缓存。

随后按模板、历史、任务状态、结果与设置拆分原生模块。保持本地静态资源和 CSP，选择 ES modules 时先验证打包资源路径与 MIME，再更换入口。不能一次删除所有旧 DOM ID 或重写所有事件。

前端测试从检查字符串扩展到行为：真实 DOM 点击、焦点返回、历史切换、请求乱序、断网恢复、导出名与下载体一致。测试工具优先复用现有 Chrome/CDP；引入新工具需独立成本决策。

## 8. 性能与数据规模的升级触发器

G5 实测（2026-10-23）：每任务每请求一读/一规范化后，默认 1,000 条暖态处理函数 p95 为 1011.433ms，10,000 条为 8834.461ms，未达 300ms 参考目标，见 [原始数据与验收](16-g5-acceptance.md)。保持本地 Manifest 为依据，无跨请求缓存或数据库；下一设计需覆盖失效/外部修改/刷新与后台并发，不能按此宣称索引已经实现。

先用合成 100/1,000/10,000 个清单测 history p50/p95、冷启动、内存和文件读取次数。参考目标为 1,000 条下暖查询 p95 < 300ms，记录设备和运行方式；这是待验证目标，不是当前性能。

G5 后续的 [G5.1 设计](17-history-cache-design.md) 规定列表有界投影、写后失效、固定 TTL 及显式刷新，A/B 和 [C 功能验证](20-history-cache-c-acceptance.md) 已完成。恢复、收藏资格、复用和产物访问仍直接读取。C 的缓存命中 resolve 入口从 N 增至 3N，整体耗时退化，性能门禁失败。下一步先剖析并考虑安全去重，收益仍不足则回退默认缓存；不自动增加 SQLite，不放宽路径检查。

首先消除同一请求的重复清单读取，再做缓存与失效。只有指标未达成或全文搜索明确需要时，评估标准库 SQLite FTS 可用性；索引保留 task_id、mtime/hash、必要摘要，不能放密钥。重建期间允许继续使用文件扫描；损坏索引不影响正文或清单。

资源约束先显式设置并发为保守值。下载、ASR 和 LLM 拆槽位前，先测 RAM、显存与取消延迟；不要把“可以并行”直接当成“默认并行更好”。

## 9. 架构验收与退出条件

- 模块提取前后同一 fixture 的 API 字段、Markdown、清单语义一致；旧数据读写不丢未知字段。
- CLI/MCP/Web 共用同一个任务服务，测试不发生 HTTP 自调死锁。
- 取消与终态竞争、收藏与进度竞争、归档与失败回滚均有可重复测试。
- 每次提取可以通过撤回该提交回滚；不做不可逆数据迁移。
- 模块数变多本身不算成功。修改某个功能不再触碰无关配置/模板/路由，且测试定位更明确才算收益。
