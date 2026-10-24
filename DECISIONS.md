# Decisions

## 2026-10-24 Beta.4 Draft 下载后验收再公开

用户另行授权远端流程后，main 快进推送并创建注释标签。Actions active/enabled 但未观察到运行，按既定备用合同手工上传已验收本地构建到 Draft；下载实际资产完成摘要、客户端与离线 ASR 验收后才公开为 Pre-release。公开前后 asset IDs/digests 保持一致，后续证据提交不移动标签。网络 TLS 超时只重试缺失的精确步骤，不重复创建或上传，不把本地构建当成 CI 证据。详见 [发布验收](docs/strategy/28-beta4-remote-release-acceptance.md)。

## 2026-10-24 Beta.4 本地收口与 Draft 发布门禁

Beta.4 冻结新功能，收口累计进度、恢复、阅读/对照、历史刷新和本机请求安全实现。用户授权本地版本修改、聚焦提交及隔离重建验收，未授权本轮远端操作。发布工作流改为仅创建 Draft Pre-release；实际下载的 CI 资产通过摘要、客户端和离线 ASR 验收后才可公开。本地 Python 3.13 候选不能替代 Python 3.11 CI 资产验收。默认历史继续新鲜读取，缓存及 G4 规则工具不作为性能或模型准确率成果。完整合同见 [Beta.4 计划](docs/strategy/26-beta4-release-closeout-plan.md)。

## 2026-10-24 便携 smoke 只选择本次进程

两个便携验收脚本复用 Windows 进程树与监听端口归属检查，再核对健康接口。已有同版本实例不能作为本次候选的验收目标。查询失败则报错，不回退扫描其他实例；不添加产品接口字段。真实 HTTP/MCP SDK 兼容与脚本验证详见 [本轮记录](docs/strategy/24-source-review-client-acceptance.md)。新构建须使用隔离输出并记录脏工作区输入，避免同版本候选覆盖已发布资产。

## 2026-10-24 S0 本机 HTTP 请求边界

保留纯 ASGI 包装和已有 MCP SDK 防护；Host 白名单复用 Starlette，新增小型纯头部策略模块。未知 peer 默认拒绝，HTTP Origin 精确比较协议/主机/有效端口，API/MCP 拒绝 same-site/cross-site Fetch Metadata，Launcher 与模块入口关闭 Uvicorn 代理头信任。原生无 Origin 调用继续可用，不引入 CORS 放行、令牌或远程模式。拒绝发生在正文与副作用前，错误固定且不回显输入。源码完整测试 1367 passed、3 个原有跳过；详见 [验收记录](docs/strategy/23-local-request-security-acceptance.md)。本轮不构建、不提交、不发布；不把本机进程身份认证或真实 DNS rebinding 验证列为已实现成果。

## 2026-10-04: Adopt VideoToNo as the successor foundation

Decision: Develop Video2Knowledge successor as a Fork of VideoToNo `v1.4.2` while preserving upstream history and MIT attribution.

Reason: VideoToNo already provides the download, subtitle, ASR, task, UI, LLM, and Markdown foundation required for the product goal.

Alternatives considered: Continue the independent rewrite; copy selected upstream files into the old repository.

Impact: Successor work starts from verified upstream behavior and carries only focused product differences.

Review condition: Revisit only if a required acceptance path cannot be achieved through a bounded change to the Fork.

## 2026-10-04: Migrate requirements and tests selectively

Decision: Reuse selected requirements, safety rules, and regression tests from the old Video2Knowledge when they remain relevant. Do not migrate its Provider/Pipeline architecture.

Reason: Proven requirements can prevent regressions, while moving the old architecture would duplicate mature upstream subsystems and increase maintenance cost.

Alternatives considered: Port the complete old architecture; ignore all previous work.

Impact: Each migrated item needs a current gap, a narrow acceptance criterion, and an upstream-compatible test.

Review condition: Revisit when a legacy test encodes a product requirement that cannot be expressed against the Fork without architectural change.

## 2026-10-04: Keep a minimal project document set

Decision: Maintain `AGENTS.md`, `PRD.md`, `PROJECT_STATUS.md`, `TODO.md`, and `DECISIONS.md` as the initial successor documentation set. Add another document only when a concrete maintenance need appears.

Reason: The project needs durable product state and decision boundaries without recreating the old repository's documentation burden.

Alternatives considered: Copy the old documentation tree; create roadmap, architecture, program-map, snapshot, and changelog files immediately.

Impact: Current work, product scope, status, and long-term decisions each have one clear home.

Review condition: Add a document only when existing files can no longer hold the required information without becoming ambiguous or difficult to maintain.

## 2026-10-04: Separate final-note export from task workspace

Decision: Add an optional request-level absolute note destination. When configured, export only the final Markdown and attachments referenced by that note. Keep manifests, transcripts, downloaded media, model caches, and credentials in the task workspace. Leave the setting empty to retain the upstream `workspace/notes` behavior.

Reason: A normal directory or Obsidian Vault needs portable final artifacts without receiving runtime state or sensitive files. Preserving the empty-setting path keeps upstream behavior compatible.

Alternatives considered: Move the entire task directory into the Vault; redefine the global workspace root; add a separate export subsystem or Obsidian plugin.

Impact: The frontend stores the optional path as a non-sensitive local preference. The backend validates it before media processing, uses exclusive collision-safe creation, copies only resolved in-task attachments, and reports custom-export failures instead of silently falling back.

Review condition: Revisit if personal templates, cleanup policy, or a future Obsidian integration requires a different artifact layout or persistent destination model.

## 2026-10-04: Use lightweight platform support levels

Decision: Treat YouTube, Bilibili, Douyin, and local media as focused support; treat other `yt-dlp`-compatible URLs as generic compatibility; research platforms that need dedicated behavior separately.

Reason: The upstream project documents platform scope and limits, and its automated suite uses controlled regression tests rather than a live per-platform certification matrix. Requiring a live end-to-end check for every platform and release would make lawful platform expansion disproportionately expensive.

Alternatives considered: Require every supported platform to pass every subtitle, ASR, screenshot, authentication, and export combination; advertise every `yt-dlp` extractor as equally supported.

Impact: Platform-specific changes need focused tests and clear errors. Global destination, collision, and Unicode behavior is tested once. Live checks are risk-based and remain subject to media, login, cookie, and credential approval boundaries.

Review condition: Tighten a platform's gate when repeated regressions show that controlled tests are insufficient, or when a release makes a stronger compatibility promise.

## 2026-10-04: Separate summary strategy from safe note templates

Decision: Keep the existing `summary_style` pipeline as the generation-depth strategy and add a separate `note_template` contract. Ship four read-only built-ins, store custom templates in the backend, require one `{{content}}` placeholder from a safe allowlist, add deterministic YAML Frontmatter, and snapshot the selected template with each task.

Later extension: the 2026-10-21 beta.2 decision below adds two more read-only built-ins without changing this contract or adding an LLM pass.

Reason: The upstream summarizer already handles short and long transcripts, coverage, reasoning effort, and retry behavior. Templates should organize content and wrap the final Markdown without duplicating that mature pipeline or executing user code.

Alternatives considered: Replace summary styles with templates; run a second full-document LLM formatting call; allow executable Jinja or scripts; generate multiple linked notes per video.

Impact: A video produces one Markdown file per generation. Selecting a different template reuses the transcript, calls the LLM again, preserves earlier notes through collision-safe naming, and leaves built-ins immutable. Local Markdown keeps Frontmatter; a future Feishu uploader may strip it from cloud content.

Review condition: Revisit if deterministic layouts cannot express a required note format or if a future multi-note workflow is approved as a separate milestone.

## 2026-10-05: Obsidian detection is a convenience; Feishu publication is opt-in, user-identity only, and never blocks the local note

Decision: Keep `note_destination` as the single destination contract and make Obsidian Vault detection a read-only UI convenience that fills it. Publish completed notes to Feishu only when the user opts in, only through the local lark-cli `--as user` identity (never bot, never automatic login), as native Markdown plus an optional referenced-frames ZIP, after local artifacts are durably written. A failed publication keeps the task `completed`, records sanitized metadata, and offers a publication-only retry endpoint.

Reason: Local Markdown artifacts remain authoritative. Cloud upload is a side effect that must not re-run download/ASR/LLM work, must not persist raw tokens or identity data, and must not turn a transient cloud failure into a lost note.

Alternatives considered: a second backend destination system alongside `note_destination`; Feishu Wiki/docx import or native image blocks now; overwriting or syncing existing remote files; bot-identity upload as a fallback; failing the note task when the upload fails.

Impact: The backend receives the same `note_destination` as before plus two note-only Feishu request fields; the manifest snapshots only the normalized folder token; errors use stable codes; retry reuses `notes.md` and current frames. Native cloud image blocks, Wiki/docx import, overwrite/sync, permission management, and automatic login stay deferred.

Review condition: Revisit if users need multi-account or team-space publishing, native image blocks, or sync/overwrite semantics, each as a separately authorized milestone.

## 2026-10-09: Xiaoe-tech uses permitted local exports

Decision: Close the Xiaoe-tech research scope with guidance to upload local media obtained through official permitted download/export. Reuse the existing subtitle/ASR, templates, Markdown/Obsidian and optional Feishu flow. No URL downloader, credential capture, sniffing or DRM/decryption capability is introduced.

Reason: Existing local media handling already supports the approved input. Merchant OpenAPI is a separate future shop-authorized integration direction, with no current promise of media downloading.

Review condition: A concrete authorized shop integration or lawful public input may justify a separate, tested adapter; permission to view paid content alone does not authorize extracting protected media.

## 2026-10-09: Failed/cancelled media retention is opt-in and conservative

Decision: Default to permanent retention; store only a browser-local forever/1/7/30 choice. A finite choice permits one sweep after successful backend connection per page session and explicit manual cleanup. No timer, daemon or persisted credentials are added.

Age is based solely on timezone-aware persisted runtime.finished_at, strictly older than the cutoff. Missing, malformed or timezone-free values are skipped; file mtime and inferred creation dates are insufficient. Reuse WORKSPACE_DIR/<task_id>, matching existing task_directory and restore logic, rather than relocating manifests into a new tasks directory.

Eligibility requires matching task.json identity and failed/cancelled persisted status. Active tasks, unfinished jobs and their reuse sources are excluded. Share the success-cleanup owned-media name predicate, preserve all other artifacts, and never rewrite status.

Deletion rejects links and uncertain identity, compares opened and non-following path identity, and rechecks the manifest. Windows uses non-delete-sharing handles for task directories and media, then deletes through the verified handle. A locked/replaced file produces a sanitized warning while the sweep continues.

On other hosts, keep candidate media with warnings until an atomic identity-delete primitive is implemented and verified. A portable stat-then-unlink fallback cannot satisfy the replacement-race boundary, so it is deliberately not used.

Impact: A user choosing finite retention may need to reacquire media for future retries. Notes, transcripts, frames, successful-note cleanup, transcript-only completion, Feishu retries and custom destinations keep their contracts. Legacy tasks without reliable terminal time are intentionally retained.

Review condition: Revisit only with evidence that the conservative skips, filesystem-specific guarantees or one-shot sweep cost prevent useful cleanup; broader scheduling or task migration needs separate authorization.

## 2026-10-09: Feishu publication creates an online docx with native image blocks

Decision: Replace the cloud "native Markdown + optional screenshot ZIP" publication with a single `lark-cli docs +create --as user --doc-format markdown` that creates one online docx and inlines referenced screenshots as native image blocks. Local `notes.md`, the local Markdown+attachments ZIP download, custom destinations and Obsidian behavior are unchanged; the ZIP is no longer uploaded to the cloud.

Reason: The `docs +create` Markdown path uploads local images inline (`![alt](<@./frames/image-NNN.ext>)`) at their in-body positions with alt as caption and returns a document id/url, reusing the CLI's own Markdown-to-docx conversion. The `docs +media-insert` shortcut only appends at the end, and a self-built Markdown-to-DocxXML converter would add a large subsystem, so both were rejected.

Consequences: Readiness now requires the `docs` command plus three scope groups (create, write, media upload); the recommended narrow scopes are `docx:document:create`, `docx:document:write_only`, `docs:document.media:upload`, with `docx:document` accepted as a wide create/write substitute. Only referenced, in-task, allowed-format images within 20 MiB are staged; missing, escaping or oversized images fail closed before any CLI call. Publication remains opt-in, `--as user` only, never fails the local task, and still runs exactly one CLI command.

Review condition: Revisit if a real-tenant smoke test shows unacceptable Markdown-to-docx fidelity, if the CLI JSON contract changes, or if overwrite/idempotency for the remote document becomes required.

## 2026-10-19: Import timed subtitles and export SRT from persisted segments

Decision: Accept local `.srt` / `.vtt` as an already-completed timestamped transcript instead of treating them as media, and export any existing transcript as SubRip from the persisted segments. Port the behavior from upstream `662f56b` rather than cherry-picking it.

Reason: The existing parser already produces millisecond-accurate segments; plain text would force invented timestamps into notes and SRT. Rendering SRT on the backend avoids the whole-second Markdown timestamps and keeps one source of truth.

Consequences: Subtitle files use a separate 20 MiB default limit, are stored as `subtitle.<ext>` (never `input.*`), and skip download, ASR and screenshots. Empty or untimed files fail at upload with no task directory. `subtitle.*` is preserved by media retention. Templates, custom destinations/Obsidian, Feishu publication and the local ZIP download are unchanged.

Review condition: Revisit if users need untimed plain text with synthetic timing (a separate product decision), or if additional subtitle export formats become necessary.

## 2026-10-20: Publish the first successor as a lineage-marked prerelease

Decision: Publish the first successor build as `v1.4.2-v2k.1` and keep the VideoToNo runtime/product name for compatibility. Point manual update checks and release links at `Eternal-HAC/Video2Knowledge-next`, while retaining the upstream MIT attribution and v1.4.2 lineage.

Reason: A `v1.5.0` tag could collide conceptually with upstream development, while a broad Video2Knowledge runtime rename would change workspace, credential and user-facing compatibility beyond a release-validation milestone. The suffix identifies the successor without overstating a new independent version line.

Alternatives considered: release as `v1.5.0`; complete a full brand migration before packaging; continue directing the update checker to upstream releases.

Impact: The application/API/frontend expose `1.4.2-v2k.1`; the numeric Windows PE version remains `1.4.2.0`; the update comparator recognizes later `-v2k.N` releases. The GitHub Release is a prerelease because real LLM Provider operation was deliberately outside the authorized offline acceptance.

Review condition: Choose an independent version and brand migration only as a separately scoped compatibility project, or promote a later successor build after its declared real-world acceptance gates pass.

## 2026-10-21: Adopt the independent Video2Knowledge brand, version line, and Knowledge Studio UI

Decision: Rename the user-visible product to **Video2Knowledge**, start an independent version line at `v1.0.0-beta.1` (beta → rc → stable), and redesign the workspace as the Knowledge Studio UI per `DESIGN.md`. `product_info.py` is the single source for product name, version, environment prefixes, and release metadata. The rebrand is bounded by explicit compatibility positions: `/api/health` keeps `service: "VideoToNo"` (with additive `product`/`api_compat` fields), `VIDEO2KNOWLEDGE_*` environment names take priority while `VIDEOTONOTES_*` keep working, non-sensitive browser preferences migrate from `vtn_prefs` to `v2k_prefs` while the old key remains for rollback, the `workspace/` layout stays compatible, and MCP plus Agent Skill discovery recognize both service identities. The brand mark is an original geometric logo generated reproducibly by repository scripts; no third-party or upstream-derived artwork is used.

Reason: Successor differences now cover product identity and interface, not only features, so the transitional `v1.4.2-v2k.N` line understates an independent product. Scoping the rename to product metadata and the frontend — with protocol shims instead of a hard rename — delivers the new brand without breaking workspace, credential, launcher, MCP, or Skill compatibility.

Alternatives considered: keep the `v1.4.2-v2k.N` suffix line (rejected: no independent identity); rename everything including the health `service` field and environment names (rejected: breaks existing launcher/MCP/Skill discovery and saved configurations for no product gain); adopt third-party icon sets or rework the upstream logo (rejected: license and provenance uncertainty).

Impact: Application, API, frontend, build artifact (`Video2Knowledge-1.0.0-beta.1-portable.exe`), and release metadata expose the new brand and version. Documentation (README, PRD, status, release notes) is rewritten around Video2Knowledge with the VideoToNo `v1.4.2` derivation, MIT License, and `UPSTREAM.md` attribution retained. Download, caption, and local-ASR capabilities remain inherited upstream implementations and are not presented as from-scratch work. Local UI automation, visual acceptance, the final full test run, candidate build, packaged offline-ASR acceptance, compatibility smoke and SHA-256 registration passed. The annotated tag and GitHub Pre-release are published; the downloaded release asset matched both checksum sources and passed the offline ASR smoke.

Review condition: Revisit if the compatibility shims (legacy service id, environment aliases) block a required change, if the independent line needs re-alignment with upstream, or if release acceptance evidence requires restating the brand scope.

## 2026-10-21: Make templates, destinations, and exports part of the task flow

Decision: Starting with `v1.0.0-beta.2`, show all six built-in templates and saved custom templates before submission, followed by an explicit local Markdown destination choice: default `workspace/notes`, custom absolute directory, or Obsidian Vault. Feishu remains a separate opt-in additional publication. The result area names the current export action and exposes the other existing formats under a visible label. One input still produces one Markdown note.

Reason: The template, Obsidian, Feishu and export pipelines already existed, but placing their controls only in the settings drawer made working features look absent. Improving discoverability reuses the mature storage and publication paths and avoids a second template system or destination API.

Alternatives considered: keep every control in Settings (rejected because users could not discover core product choices); add a second frontend-only template or export pipeline (rejected because it would duplicate validated backend behavior); split notes into multiple linked files or build an automatic knowledge graph (deferred as a separate product scope).

Impact: `/api/note-templates` returns six built-ins with the same response schema. Browser preferences gain non-sensitive `note_destination_mode`; old non-empty destinations migrate to `custom` without clearing the path. Existing `note_template_id`, `note_destination`, `feishu_upload_enabled` and `feishu_folder` request fields remain unchanged. Interaction research referenced Fabric, video-fetcher-to-markdown, course2md and YouTube Transcript Notes, with no third-party code, prompt, icon or asset copied.

Review condition: Revisit when user evidence supports multi-file notes, note interlinking, an OS-native folder picker, or a broader destination plugin architecture.

## 2026-10-22: Keep beta.3 history, favorites, previews, and source guidance local

Decision: Build template previews from fixed synthetic content through the existing one-pass layout renderer. Query history directly from compact `task.json` summaries with filters and pagination, restore an older task only when it is opened, and store a completed note's optional `favorite` flag atomically in that task manifest. Inspect a pasted URL by hostname plus existing local manifests only; use the result to label support and expose the existing transcript reuse choice.

Reason: These changes make existing local capabilities discoverable without adding a database, a second template format, another LLM call, a platform network probe, or an account synchronization service.

Impact: Local favorites are unrelated to Bilibili, Douyin, YouTube, TikTok, or Xiaohongshu account collections. TikTok and Xiaohongshu remain generic `yt-dlp` compatibility claims. Source inspection never validates live availability and never replaces the downloader's final decision.

## 2026-10-22: Show measured progress and conservative ETA

Decision: Use faster-whisper's processed and total media seconds to advance the ASR band, delay ETA until enough work has been measured, and render the estimate as a range with an explicit device-speed caveat. Keep stages without reliable measurement indeterminate. Show queue position, pin the active task, add a local readiness summary, and let completed tasks open their result file or containing folder through a task-scoped backend action.

Reason: A fixed percentage looks broken, while a precise countdown built from insufficient samples is misleading. Existing task, Whisper-cache, key-state, destination and manifest data already support a trustworthy feedback loop without another dependency or background service.

Impact: Task status gains optional progress-detail and queue fields; old clients can ignore them. The result-opening endpoint never accepts a filesystem path from the browser and falls back to the fixed task artifact when an archived path cannot be proven to belong to the task's snapshotted destination.

Review condition: Revisit the estimator after collecting local runtime evidence from long CPU and GPU jobs. Do not extend the same formula to downloads or LLM calls until those stages expose stable measurable work units.

## 2026-10-22：G0 可靠性边界收口

决策：结果打开限定为清单目的地下或任务内固定 Markdown，检查解析前路径各级组件、文件类型和身份，默认目的地 null 保持兼容。无法确认时回退安全内部文件或返回固定错误；打开历史结果无需加载完整笔记。转录进度按阶段令牌接收，未知总时长不生成百分比或 ETA，取消与阶段结束清空旧估计。

原因：失败回归确认了危险扩展名、junction、校验后替换、多 P 进度回退与迟到事件问题。读取 Key/路径状态只能说明已提供，不能证明 Provider 鉴权或目录写入成功。浏览器验收还确认了 readiness 网格和窄屏顶栏遮挡问题。

影响：保持现有任务、模板、保存/发布管线及版本不变；新增离线测试与可重复的浏览器矩阵脚本。DESIGN.md 同步了阶段 ETA、未验证配置、数据去向和响应式布局规则。详见 [G0 验收记录](docs/strategy/07-g0-acceptance.md)。

后续复查：系统默认打开仍有路径分发竞争窗口；Host/Origin 安全与便携版验收是发布前独立检查项。本轮没有提交或发布。

## 2026-10-23：G1 来源优先与只读阅读器

决策：来源输入、开始与当前方案摘要前置，保留六模板与目的地入口，长预览默认折叠。目录和正文查找只建立在已安全渲染的 DOM 上，保持原 Markdown 为复制和导出的依据。目录使用程序生成 ID 与元素引用定位；查找按字面处理文本节点，排除公式、图片与显式隐藏区域，最多高亮前 200 处。

原因：模板与长预览占据任务前较多空间，手机首次使用要滚动才能开始。原有渲染和导出管线已经可用，只需补定位与阅读交互；不需要编辑器、全文索引或额外 LLM 调用。

备选：重写前端框架、引入富文本编辑器、把搜索标记写回正文，均超出本阶段需求。保留现有 select、DOM ID、偏好和请求字段，避免双份状态。

影响：新增真实 DOM 浏览器回归脚本，修正卡片和模板管理的焦点返回；Markdown 导出明确告知有可用截图时返回 ZIP，并以响应文件名反馈实际产物。仅本地源码验收，没有版本升级或发布，详见 [G1 验收](docs/strategy/08-g1-acceptance.md)。

后续复查：用户提出跨段落检索、超长目录性能、编辑保存或原转录对照需求时独立评估。该 G1 决策形成时 G2 存储与恢复尚未开始。

## 2026-10-23：G2 清单存储与显式恢复

决策：使用小型 `task_repository` 集中进程内串行读改写与同目录原子替换，保留旧主模块函数入口、任务目录及清单格式。历史浏览容忍损坏清单，写入拒绝覆盖损坏证据；合并保留未知字段。恢复前与执行时校验完整转录，缺失时明确失败，不转入下载/ASR。新任务保存 parent/ref 并继承来源，旧收藏和笔记留在原任务。

原因：测试确认了多套清单写入口、坏转录被识别为可复用/已完成、未知运行字段被覆盖、来源冲突以及提交重放建新任务等缺口。当前单机单后端无需数据库或完整服务重构。

备选：持久请求索引、任务数据库、多进程共享锁、自动付费恢复均未采用。用可选 `client_request_id` 随清单持久化；同 ID 同参数只返回原任务，不同参数 409。指纹排除 API Key/Cookie 和它们的哈希；删除/损坏清单或更换工作区后不保证重放。

影响：HTTP 与 MCP 共用 `recovery` 摘要；网页未知提交只 GET 查询原请求 ID，断线只查询原任务，不自动重复提交。用户明确继续才新建笔记任务；截图勾选仍可能下载预览视频。当前页面外不保存请求或凭据。最终 848 passed、3 个既有跳过，G2/G1/G0 浏览器矩阵各 9 组通过，详见 [G2 验收](docs/strategy/10-g2-acceptance.md)。未提交、构建、发布。

后续复查：G5 测量全历史扫描成本后再决定是否建立可重建索引；多写进程需另定锁/所有权协议；真实 Provider、打包态与 Host/Origin 安全仍按独立授权门禁验收。

## 2026-10-23：G3 只读时间范围对照

决策：在既有转录模块增加稳定内容 hash 和半开时间相交定位；新只读端点分页返回原段，
不寻找最近句、不合并同时间段。界面只在安全正文节点建立时码按钮，原文使用 textContent；
保留单篇 Markdown、原始复制和导出。笔记/转录 hash 与页面版本共同拒绝旧映射、旧分页和迟到响应。

原因：现有字幕和 ASR 已有真实秒级分段；核对入口可以直接复用，不需要改变 summarizer 协议、
二次模型调用、数据库或语义检索。多 P 缺少可靠逐 P 偏移，按累计时间轴说明，不生成视频跳转。
媒体文件不存在只显示“未保留或不可读”，不推断删除原因或承诺可播放。

备选：观点级自动引用、自动 LLM 核验、播放器/逐 P 映射暂缓；先验证人工核对是否有用。
外部改写笔记暴露了内存旧正文问题，使用任务 GET 的可选 refresh_note 参数显式读取当前文件，
默认轮询与 MCP 保持原行为，读取失败不退回旧正文、不写缓存或清单。

影响：本地完整测试 883 passed、3 个既有跳过，四套浏览器矩阵各 9 组通过，详见
[G3 验收](docs/strategy/12-g3-acceptance.md)。未提交、构建或发布，未使用真实凭据、LLM、媒体或云写入。

后续复查：时间命中不能证明概括正确或转录完整；首次读取 hash 也不能证明转录从生成以来从未改写。
长转录每次校验的成本需先测量，再决定缓存/索引；不把本轮短合成数据验收扩大为长视频性能保证。

## 2026-10-23：G4 离线质量与发布证据

决策：先提供独立、无网络的开发工具，复用现有模板和转录纯函数。12 个原创合成案例固定信息点、
字面条件和时间相交关系，不以全文快照或未经验证的综合准确率评价模型。人工评阅各维度分别保留，
当前全部未评；三段两小时时间轴只能证明尾部锚点检查，不能冒充长文本验收。

原因：现有测试已覆盖业务恢复与安全渲染，新增第二套模型调用或评测管线会扩大权限与成本。
本轮无真实模型授权，先让模板/格式变化具备可重复的检查资产，并保留真实语义判断缺口。

影响：诊断仅有白名单纯函数参考，拒绝自由模型名、路径、原文、原始异常和未知字段；未接入产品日志/API/UI。
环境工具观察当前安装版本，不锁定/升级依赖。资产对照验证四方摘要与大小，不执行或下载 EXE，
也不代替标签 commit、下载来源和打包 smoke 证据。工具报告只新建、不覆盖、错误不回显输入。
说明与验证见 [G4 验收](docs/strategy/14-g4-acceptance.md)。本轮未提交、构建或发布。

后续复查：真实评测先限定 Provider/模型、输入、请求/重试/费用上限及停止条件；诊断产品化另立集成合同。
G5 先测历史规模再选择优化，发布前仍需 Host/Origin 审查和当前候选打包验收。

## 2026-10-23：G5 先测量并消除请求内重复工作

决策：保留现有 Manifest 和查询协议，只复用一次请求中已验证目录与一次清单快照。
列表可见性与摘要来自同一清单，不跨请求缓存，收藏/外部更新继续即时扫描。原摘要函数保留薄包装入口。

原因：100/1,000/10,000 合成基准观察到每个清单读取两次；剖析确认每目录规范化三次。
专项失败用例还证明两次来源快照可能不一致。最小修复即可减少这项成本，不需要先引入数据库。

影响：清单读取从 2N 降为 N，规范化从 3N 降为 N，列表不读取正文。成对输入及所有查询结果 hash 相同。
1,000 条默认暖态 p95 从 1755.670ms 降到 1011.433ms，仍高于 300ms 参考目标；启动恢复未一致改善。
详见 [G5 验收](docs/strategy/16-g5-acceptance.md)。未提交、打包或发布，没有真实模型/平台/飞书操作。

后续复查：基准与去重交付完成，性能目标继续开放。后续缓存必须定义 repository 写入、收藏、删除、外部替换、
损坏恢复、工作区切换和显式刷新的失效语义；全文需求确认或缓存不足时再考虑可重建 SQLite 投影。
不把 7 个样本的本机百分位宣传为通用 SLO，不扩大到用户 Vault 扫描或自动数据库迁移。

## 2026-10-23：G5.1 缓存设计先明确新鲜度与边界

设计选择：后续先尝试单进程、仅历史列表使用的有界内存摘要缓存，不引入数据库或磁盘缓存。
初始合同为 12,000 条、16 MiB 编码负载、单项 64 KiB；命中不延长 30 秒外部复核期限。
repository 写成功后精确失效；元数据变化在下一次查询发现，同指纹外部改写靠固定 TTL 或显式刷新复核。
完整设计和待执行用例见 [G5.1 合同](docs/strategy/17-history-cache-design.md)。这是待实施方案，未改产品源码。

原因：G5 证明全量清单读取仍较贵，但尚未证明确需数据库。缓存必须保持旧 live 优先级和隐藏规则，
不能让收藏资格、恢复、复用或打开文件依赖可能过期的摘要。保留当前直接 reader，缓存只接入列表。

备选：缓存整份清单/正文、永久 per-task revision 表、后台线程或文件监听均暂不采用；SQLite/FTS 继续延期。
容量约束针对编码负载，不把它说成 RSS 上限；stat/resolve、发现、归并和排序仍可能限制性能。

影响：计划 A 纯缓存规则与红测、B 列表和失效接线、C 手动刷新与乱序防护及复测，分步验收。
拟增加的可选 refresh 查询参数尚不存在。所有 G0–G5 dirty 源码与既有性能证据保持不动，未提交或发布。

后续复查：缓存实际收益、同指纹改写体验、容量淘汰、写后新鲜度与跨工作区隔离均有证据后再决定下一步。
若 1,000 条仍未达 300ms，记录原因并另行评估，不能减少历史或弱化安全检查以满足指标。

## 2026-10-23：G5.1-A 独立核心先验收，不直接接全局 reader

实施：新增显式实例化的历史投影缓存及 78 项离线规则用例，保留 main、repository 和前端原样。
投影以 UTF-8 JSON 字节保存，命中解码为新对象；不支持/超限数据不缓存，业务兼容判断留在接线阶段。
读取前后复查指纹，最多一次额外读取；失效不做 I/O，与 loader 共用 RLock，后续 writer 在返回前精确失效。

原因：先把固定过期、容量、身份和并发失效的规则证明清楚，再处理 live/disk 归并与产品写入口。
补测实际发现缺失清单会错误清空全部条目，已改为单项失效；根身份变化才清空全部工作区缓存。

影响：只是独立模块，不创建默认单例、不持久化索引、不改变公开 API。运行目录检查仍有成本和竞争窗口，
编码负载不等同于 RSS。源码本地验收与后续限制见 [A 验收](docs/strategy/18-history-cache-a-acceptance.md)。

后续复查：B 必须保留未缓存 reader、收藏资格及恢复/复用验证；C 再验证刷新、迟到响应和同输入性能。
未接入的核心通过不能写成当前产品查询已变快；没有提交、打包或发布。

## 2026-10-23：G5.1-B 缓存只接历史列表，写后集中失效

决策：共享白名单投影与 live/disk 归并逻辑，列表使用进程内唯一缓存；通用 reader、收藏资格、
恢复和来源复用继续新鲜读取。repository 的原子替换成功后，在返回前精确失效，删除成功后补失效。

原因：防止过期列表字段参与有副作用的判断，避免在每个调用点手动维护失效。加载只走无写锁 reader，
写入按 repository → cache 锁顺序等待并失效，不维护永久任务 revision 表或监听回调。

影响：保留旧结果空字典、progress=0、平台、origin、严格收藏与实时耗时语义；不支持缓存的旧类型
沿用直接读取。公开 API、前端及版本不变。39 项接线测试加入后，专项 153 项、完整 1095/3 通过，
见 [B 验收](docs/strategy/19-history-cache-b-acceptance.md)。没有构建、Git 提交或外部操作。

后续复查：C 补显式刷新和迟到响应防护，再测空缓存、命中、刷新、写后失效及容量压力。
目前只有暖查询清单读取减少的确定性证据，不能当作耗时或 RSS 保证；300ms 参考目标继续开放。

## 2026-10-23：G5.1-C 功能通过，性能退化阻止优化验收

决策：保留筛选的手动刷新使用可选 refresh=true；普通重载不清全库。序号与筛选快照决定
响应归属，取消 fetch 不证明后台已停止，失败不清空已有列表。沿用 DESIGN 的组件和固定错误文案。

证据：9 组真实浏览器组合通过，输入/响应 hash 与 G5 一致。1,000 条默认 p95 命中 1189.446ms，
同轮直接读取 810.114ms；四种查询均退化，resolve 入口由 N 增至 3N。计数不等于耗时归因。
按合同停止 10,000 条，不修改 TTL、容量或路径保护，不自动转 SQLite。见 [C 证据](docs/strategy/20-history-cache-c-acceptance.md)。

影响：刷新与一致性实现可审查，但缓存仍为未发布实验，不能将 G5.1 标成性能交付成功。
下一步先剖析身份与投影成本；安全去重仍无收益时回退默认缓存，在性能门禁通过前不进入发布。
没有提交、推送、构建或真实业务操作。

## 2026-10-24：G5.1-D 回退默认缓存，保留刷新保护

后续安全审查：已形成 [S0 合同](docs/strategy/22-local-request-security-audit.md)。18 项隔离观测确认 REST Host/Origin 缺口，下一轮先补失败测试再做请求边界修复，作为发布阻断项。原生无 Origin 调用、动态本机端口与 MCP SSE 保持兼容；不引入依赖、通配 CORS、远程模式或 token 架构。这里只记录审查取舍，尚未修改运行时源码或发布资产。

决策：默认历史列表回到 G5 的每任务一次新鲜清单读取；缓存模块、写后失效和实验测试保留，
通过隔离测试/基准显式替换 list-only reader，无产品开关。收藏资格、恢复、复用不接该入口。

原因：C 的同轮四种查询均退化。D 的 cProfile 进一步观察到 1,000 条缓存命中产生 3,000 次 resolve，
主要累计成本落在 Windows 路径解析和快照检查。剖析有插桩开销，不能当 p95 或跨设备承诺。
不为收益去掉 reparse/身份检查，不增加数据库。默认回退可确定地移除该实验路径的额外工作。

影响：C 的 refresh 参数、筛选、分页、迟到响应隔离及安全错误提示保持；30 秒 TTL 只属实验。
本轮默认 p95 742.230ms，仍未达 300ms；[D 记录](docs/strategy/21-history-cache-default-rollback.md) 保存证据和后续边界。
没有构建、提交、推送或发布。
