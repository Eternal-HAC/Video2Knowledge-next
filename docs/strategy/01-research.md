# 竞品研究与当前代码依据

研究日期：2026-10-22。此文区分公开声明、源码观察与设计推断；未执行竞品真实转录或付费调用。

## 1. 开源产品对照

| 项目与一手来源 | 公开可确认的方向 | 可借鉴 | 我们的选择 |
|---|---|---|---|
| [上游 VideoToNo](https://github.com/like-attract/video-to-note#readme) | README 展示 v1.4.6；字幕优先、本地转录、SRT、Agent Skill、无头启动等 | 复用可靠修复与原始转录出口 | 按提交逐项审查；Headless 仍是独立计划 |
| [BiliNote](https://github.com/JefferyHcool/BiliNote#readme) | 多平台、截图、原片跳转、历史版本、RAG 问答；近期说明强调首启引导与模型就绪 | 首次成功路径、分离服务健康与配置状态 | 模板/截图已很常见；先做好核对和交付，不跟进整套问答平台 |
| [course2md](https://github.com/mizorewww/course2md#readme) | 图文讲义、字幕优先、可选 AI 整理、笔记库、阅读目录、界面语言选择 | 课程阅读与来源画面对应，AI 可选 | 先做目录与转录对照；不复制 Rust/桌面技术栈 |
| [Fabric](https://github.com/danielmiessler/Fabric#readme) | 面向具体任务的可组合 Patterns，支持命令行工作流 | 模板描述、用途与固定样例成套管理 | 沿用现有模板合同，不增加模板执行语言 |
| [Open Notebook](https://github.com/lfnovo/open-notebook#readme) | 多资料研究、全文/向量搜索、来源上下文聊天与播客 | 看重来源证据与资料再利用 | 把跨资料聊天留后续，先解决单视频成稿的可核对性 |
| [Obsidian Web Clipper](https://github.com/obsidianmd/obsidian-clipper#readme) | 网页高亮、模板与持久 Markdown 保存 | 文件所有权、可带走的内容、模板复用 | 与现有笔记软件协作；不另做完整 Vault 编辑器 |
| [video-fetcher-to-markdown](https://github.com/JimmySadek/video-fetcher-to-markdown#readme) | Agent 技能，汇集字幕/本地 Whisper、截图、元数据与时间戳 | 原始材料和来源信息完整输出 | 保留 MCP/Skill 同一任务服务，避免复制下载链 |
| [VideoLingo](https://github.com/Huanshere/VideoLingo#readme) | 字幕切分、翻译、对齐与配音 | 处理阶段可见、字幕质量的重要性 | 属于相邻领域，配音/翻译生产线不进入近期范围 |

上表只表示项目文档公开提供的能力。没有出现在 README 的功能标记为“本轮未确认”，不能据此声称竞品不支持。GitHub Star 数、宣传性能和免费/商业产品的能力都不作为我们的质量证明。BiliNote 的云产品宣传也不直接当作开源本地版实测。

## 2. 真正的差异化机会

**判断 A：更多模板是基础体验，难以单独成为优势。** Fabric 的任务模板、BiliNote 的格式/风格、course2md 的讲义路线都说明“怎么组织内容”已有丰富供给。我们应把模板扩展与固定样例、适用场景和质量评价绑在一起。

**判断 B：可核对比看起来完整更有价值。** 时间戳、转录和 Markdown 已经存在，增加按章节回看原文的成本，明显低于从零建立 RAG 平台。此为工程推断，用户价值需通过小样本观察验证，不能宣传为市场唯一。

**判断 C：Windows + 中文使用体验 + Markdown/Obsidian/飞书交付可以成为聚焦组合。** 这是推荐定位，不是经过市场验证的护城河。长期优势来自路径与 Unicode 兼容、失败恢复、可追溯生成和稳定发布的积累。

**判断 D：进度可信度会影响等待体验。** 阶段是否有真实测量、失败后保留了什么，比装饰性百分比更重要。不同 ASR 引擎能力不同，不能统一声称都有实时百分比。

## 3. 当前源码证据地图

相对路径从仓库根目录计算；行号对应研究时工作区，后续以函数名定位。

| 事实 | 位置 | 设计意义 |
|---|---|---|
| HTTP 路由、任务状态、历史、导出、归档在同一主模块 | `backend/main.py:611 new_task`、`:1523 list_recent_tasks`、`:2770 process_video_task`、`:3822 archive_note` | 优先按职责提取，保留入口兼容层 |
| ASR 打包子进程已有独立协议与清理 | `backend/asr_process.py:397 _consume`、`:536 run_in_child` | 继续复用，不建设第二个 Worker 系统 |
| Whisper 支持时间心跳，Paraformer 本地路由没有传入进度回调 | `backend/main.py:337 run_transcription_local`、`backend/whisper_asr.py:203` | ETA 只能按能力展示；必须测试未知进度 |
| 转录段包含 start/end/text | `backend/transcript.py:12 TranscriptSegment` | 可增加派生段 ID，为核对提供基础 |
| 历史接口扫描清单，并在过滤来源时再次读清单 | `backend/main.py:1523 list_recent_tasks` | 先测性能/消除重复读取，再考虑索引 |
| 默认并发槽为一个 Semaphore | `backend/main.py:470`、`:2752 run_queued_video_task` | 暂不需要 Redis/Celery；队列顺序需来自入队记录 |
| 模板有安全单次替换与快照 | `backend/note_templates.py`、`backend/main.py:780 resolve_task_template_snapshot` | 所有新预设和再生成应沿用 |
| MCP 同进程复用后端函数，历史上有 HTTP 自调阻塞问题说明 | `backend/mcp_server.py`、`backend/main.py:3956` 附近 | 拆模块时测试 MCP，禁止改回隐式 HTTP 自调用 |
| 前端全局任务快照、轮询、配置/渲染耦合 | `frontend/script.js:160`、`:547`、`:3658` | 先把渲染改为显式输入，避免任务 A 响应覆盖任务 B |
| 发布依赖范围未完全固定 | `backend/requirements.txt`、`.github/workflows/release.yml` | 记录实际解析版本；发布约束与开发允许范围分开 |

## 4. 本轮发现的优先审查项

以下是静态观察，不等于已完成漏洞复现或性能基准。

1. `main.py:_trusted_archived_result` 和 `_result_file_for_open` 在 `resolve()` 之后才检查普通路径。解析会消去原始 symlink 路径信息，根目录的上层重解析点也需要考虑。对“拒绝全部链接”的声明证据不足。
2. 归档候选仅检查父目录与普通文件，没有显式限定 `.md`。若清单异常地指向同目录可执行文件，系统默认打开行为风险不同。需构造清单测试并确认目标只为任务预期 Markdown。
3. `frontend/script.js:updateReadinessCard` 将“填有/保存了 Key”称为“可用”，且 pending 未计入“未就绪”摘要。这不能证明鉴权通过、模型存在或路径可写。
4. `asr_progress_snapshot` 给出的是转录阶段剩余时间；UI 仅写“预计剩余”，容易被理解为整项任务。总百分比 28–49 是阶段映射，不是总工作量实测比例。
5. 多 P 循环仍穿插下载阶段的固定进度；只在 ASR 回调中取 max 不保证整条流程百分比不回退。缺少时长时累计展示也需重新定义。
6. 全局异常处理保留异常文本并写日志，`redact_secrets` 不能直接证明任意路径/未知格式凭据都被清除。需对公开错误与诊断导出分层审查。
7. `.github/workflows/release.yml:126` 的“数据不出本机”、`DESIGN.md:41` 的“所有处理在本机”与可选云端 LLM/飞书不一致。产品应说清转录本地处理，启用云模型时文字会发送到所选服务。

前一轮 721 个通过测试证明已有用例通过；它不覆盖上述所有边界。下一轮应优先补行为测试，再决定修复范围。

## 5. 复用与研究纪律

代码引入前记录仓库、完整 SHA、目标文件、许可证与通知义务；GitHub API 的 SPDX 标签只用于筛选，不能替代所复制文件的 LICENSE/NOTICE 审阅。提示词、图标和截图也要核实来源。本轮只借鉴设计，不复制第三方代码/提示词/资产。

可复查的远端快照：上游 `868dcc377d7cb2a6ee088f7913874bc90d3708cf`；BiliNote `90940fde4d224d0f69ad99674f4af0a1ea52d3c4`；course2md `eb11b0673e3e2fb5025eb90ba62a3c26b9a00a29`。这是 API 查询到的默认分支提交，网页可能有缓存，不声称网页内容一定与这些提交逐字一致。个别 API 查询发生 TLS 超时；未得到的状态保留未知。

下一轮上游审查：逐个提交比较需求、现有测试与兼容边界；已移植的 SRT、子进程、长笔记韧性不重复做。Headless 与代理诊断仍需单独合同，不能因为上游已有就直接合并。

### 远端元数据补充

下表来自本轮 GitHub API；许可证是 API 识别结果。`pushed_at` 不等于默认分支提交时间，也不直接代表维护质量。

| 仓库 | archived | API 许可证 | 默认分支提交快照 |
|---|---|---|---|
| like-attract/video-to-note | false | MIT | `868dcc377d7cb2a6ee088f7913874bc90d3708cf` |
| JefferyHcool/BiliNote | false | MIT | `90940fde4d224d0f69ad99674f4af0a1ea52d3c4` |
| mizorewww/course2md | 本轮元数据请求超时 | 网页显示 MIT，API 未复核 | `eb11b0673e3e2fb5025eb90ba62a3c26b9a00a29` |
| danielmiessler/Fabric | false | MIT | commit 请求超时 |
| lfnovo/open-notebook | false | MIT | `a0f6f3081ae06328f0a451b3a3ef2959ca25721d` |
| obsidianmd/obsidian-clipper | false | MIT | `6d56d618b00bd970aa738d6a7a61edee27783e81` |
| JimmySadek/video-fetcher-to-markdown | false | MIT | `c196ba48df72c064811adcb934104c3e6567858b` |
| Huanshere/VideoLingo | false | Apache-2.0 | commit 请求超时 |

任何后续复制行为都须重新核对具体文件许可证。设计研究不意味着已经完成依赖安全审计。
