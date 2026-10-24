# Video2Knowledge Product Baseline

> Beta.4 本地准备已完成：[验收与边界](docs/strategy/27-beta4-local-release-acceptance.md)。进度、显式恢复、阅读/原文对照、历史刷新、本机请求安全已纳入新版本候选；完整 1382/3、打包 HTTP/MCP 和离线 small/CPU 通过。尚未公开发布，也不代表普遍 Provider/平台兼容；下方历史阶段的待办描述以本次验收为准。

> Beta.4 本地收口已获授权，版本目标 `1.0.0-beta.4`。累计能力按 [收口合同](docs/strategy/26-beta4-release-closeout-plan.md) 整理提交并重建验收；源码、候选、公开发布分开记录。Beta.3 仍是现有下载版本，未公开 Beta.4。历史性能目标及真实 Provider 普遍兼容不列为达成。

> 2026-10-24 打包验收更新：[隔离开发候选](docs/strategy/25-isolated-portable-acceptance.md) 已验证请求边界、模板/历史/收藏、HTTP/MCP 和离线 small/CPU 转录。该候选暂保留 Beta.3 版本，原 Release 未替换；下一阶段先确定 Beta.4 版本与提交边界，不能把本地通过写成已发布或全平台兼容。

> 2026-10-24 S0 更新：[请求边界修复](docs/strategy/23-local-request-security-acceptance.md) 已完成源码本地验收，1367 passed、3 个原有权限跳过；真实跨端口简单 POST/GET 均被拒绝，同源、原生请求与流式回归保留。下方审查缺口属于修复前状态。当前 beta.3 发布资产未变，打包兼容和发布验收仍待独立进行。

> 2026-10-24 安全审查更新：[本机请求边界](docs/strategy/22-local-request-security-audit.md) 已确认 REST Host/Origin 缺口，列为下一次发布前阻断项，尚未修复。回环 peer、响应 CSP 或缺少 CORS 放行不能单独证明浏览器来源安全；MCP SDK 已有独立检查，需保留其兼容性。已有 beta.3 Release 未因本轮审查被更新。

> 2026-10-23：[下一阶段产品与架构设计](docs/strategy/README.md) 中 G0–G3 已完成源码本地验收，详见 [G0](docs/strategy/07-g0-acceptance.md)、[G1](docs/strategy/08-g1-acceptance.md)、[G2](docs/strategy/10-g2-acceptance.md) 和 [G3](docs/strategy/12-g3-acceptance.md)。来源前置、阅读器、原子清单、显式恢复、受限提交幂等及原转录对照已经落地；时间命中不代表观点已核验。[G4 离线轨](docs/strategy/14-g4-acceptance.md) 提供合成质量案例、规则/人工评阅与诊断/发布证据工具，未真实模型评分或上线诊断入口。[G5 基准与请求内去重](docs/strategy/16-g5-acceptance.md) 已完成；[G5.1-C](docs/strategy/20-history-cache-c-acceptance.md) 完成刷新/乱序验证，但缓存性能退化，300ms 目标及性能门禁未通过，没有索引。没有提交、构建或发布新版本。

## Brand and version line

历史性能实验遵循 [G5.1 缓存设计合同](docs/strategy/17-history-cache-design.md)，A/B 规则与 [C 刷新/浏览器验证](docs/strategy/20-history-cache-c-acceptance.md) 已完成；C 复测发现缓存整体变慢。[G5.1-D](docs/strategy/21-history-cache-default-rollback.md) 已回退默认缓存接线，历史列表恢复每任务单次新鲜清单读取，收藏资格、恢复和文件访问保持原读取路径。缓存仅用于显式隔离实验，没有产品开关；30 秒 TTL 不再是默认列表的同步期限。可选 refresh=true、保留筛选和迟到响应保护继续保留。300ms 参考目标仍未达到，不为指标削弱路径检查，也不自动增加索引。

- The user-visible product is **Video2Knowledge**; `VideoToNo` appears only in protocol-compatibility positions (for example the `/api/health` `service` field) and in attribution.
- From `v1.0.0-beta.1` the project uses an **independent version line**: `1.0.0-beta.N` → `1.0.0-rc.N` → `1.0.0`. The transitional `v1.4.2-v2k.N` line always sorts below the independent line in update checks. `product_info.py` is the single source for the product name, version, environment-variable prefixes, and release metadata consumed by the launcher, backend, build script, and release workflow.
- The Windows portable artifact for this line is `Video2Knowledge-<version>-portable.exe`; `v1.0.0-beta.1` has passed its local and downloaded-release acceptance gates and is published as a GitHub Pre-release.
- `v1.0.0-beta.2` keeps the same task/API contracts while making templates, local Markdown destinations, optional Feishu publication, and export formats visible in the task flow. Its release evidence is recorded separately from the already accepted beta.1 artifact.
- `v1.0.0-beta.3` adds deterministic template previews, manifest-backed history search/filter/pagination, local note favorites, and offline source recognition with transcript-reuse hints. It does not add a new downloader or a platform-account favorites sync.

## Compatibility boundaries of the rebrand

The rename must not break existing integrations:

- **Service identity**: `/api/health` keeps returning the legacy `service: "VideoToNo"` alongside `product: "Video2Knowledge"` and `api_compat: 1`. The compat level is additive-only; it bumps only when an existing field's semantics break.
- **API**: endpoint paths, request shapes, and task manifest format are unchanged by the rebrand.
- **Environment variables**: new `VIDEO2KNOWLEDGE_*` names take priority; legacy `VIDEOTONOTES_*` names keep working (`WORKSPACE`, `BACKEND_URL`, `REJECTED_LLM_PARAMS`, `LLM_API_KEY`, and so on).
- **Browser preferences**: non-sensitive localStorage preferences move to `v2k_prefs`. On first launch the app copies legacy `vtn_prefs`, preserves that old key for rollback, and never migrates API keys into localStorage.
- **MCP / Agent Skill**: discovery recognizes both the new `product` field and the legacy `service` value; tool names, the SSE endpoint, and the Skill directory layout are unchanged.
- **Workspace**: the `workspace/` directory layout, credential files, and model cache locations are unchanged.

## Knowledge Studio UI principles

The redesigned workspace ("Knowledge Studio") follows [DESIGN.md](DESIGN.md) as the single design baseline: task-first flow (output type → source and start entry → current-plan summary → template and destination choices), low-frequency model and integration settings collected into a slide-out panel, state conveyed by text and badges rather than color alone, local-trust copy that states where data goes, and restrained motion honoring `prefers-reduced-motion`. Six built-in templates and saved custom templates remain directly selectable; long synthetic previews are collapsed by default. The result reader adds a safe heading outline and literal text search without altering source Markdown, copy, or exports. Local Markdown always remains the primary artifact; Feishu is an opt-in additional publication. The brand mark is an original geometric logo generated reproducibly by repository scripts (`scripts/make_brand_assets.py`); no third-party icon sets or upstream-derived artwork are used. The rebrand does not change backend APIs, task semantics, or the element-ID contract guarded by `tests/test_frontend_hygiene.py`.

## User goal

Turn saved YouTube, Bilibili, and Douyin videos plus local media into reusable Markdown notes that can be imported into Obsidian or another knowledge tool. The successor builds on VideoToNo and should add only the differences needed for this workflow.

## Main flow

```text
YouTube / Bilibili / Douyin / local media
→ prefer available subtitles
→ use local ASR when subtitles are unavailable
→ optionally organize with DeepSeek or another LLM
→ apply a personal Markdown template
→ write to a selected directory or Obsidian Vault
→ optionally upload to a chosen Feishu Drive folder
```

## MVP inputs and outputs

Inputs:

- a public YouTube URL;
- a public Bilibili URL;
- a public Douyin single-video URL or share link;
- a local audio or video file;
- a local `.srt` / `.vtt` subtitle file as an already-timed transcript;
- optional provider configuration for note generation;
- an optional personal Markdown template;
- a selected normal directory or Obsidian Vault destination;
- an optional Feishu Drive folder target for opt-in upload.

Outputs:

- a UTF-8 Markdown note with traceable source information;
- a timestamped transcript that remains available when note generation fails;
- a standards-compliant SubRip `.srt` export for any task with a timestamped transcript;
- optional local image attachments when screenshots are requested;
- no silently overwritten note and no unnecessary retained media by default.

## Platform support contract

- **Focused support:** YouTube, Bilibili, Douyin, and local media use the existing subtitle-first and local-ASR pipeline. Platform-specific behavior requires focused automated regression coverage and actionable errors. Known login, verification, membership, region, and upstream-interface limits must be documented.
- **Generic compatibility:** Other HTTP or HTTPS video URLs supported by the installed `yt-dlp` version may use the generic pipeline on a best-effort basis. They do not receive platform-specific guarantees.
- **Pending adaptation:** A platform that cannot use the generic pipeline is researched separately. Reuse a mature lawful implementation when available, then add the smallest platform-specific behavior and tests justified by demand.

Focused support does not promise that every public video remains reachable, does not require every platform to repeat global destination and Unicode tests, and does not require live network tests for every release. Real-media checks are used when first adapting a platform, investigating a breakage, or preparing a relevant release, subject to the repository's approval boundaries. The project never bypasses DRM, payment, login, verification, or other access controls.

## Completed scope: Xiaoe-tech local import guidance

The Xiaoe-tech research decision is complete: when the platform officially permits export or download, users may obtain a local media file and upload it through the existing local-media pipeline. This reuses subtitles/local ASR, templates, Markdown and Obsidian destinations, and optional Feishu publication. The local-file source displays this boundary.

No Xiaoe-tech URL downloader, credential collector, sniffing, DRM or decryption capability is included. Merchant OpenAPI remains a separate future integration direction requiring authorized shop access; it does not constitute a current media-download promise.

## Optional failed/cancelled media retention

- Default: forever. Optional browser-local policy: 1, 7, or 30 days.
- Only a finite selection enables cleanup: once after a page session connects successfully to the local backend, or through the explicit cleanup button. Changing the selection saves it; the button or next page session runs cleanup. No periodic worker or polling.
- Only direct task directories with persisted failed/cancelled status and an aware, parseable finished_at strictly older than the cutoff qualify. Missing/invalid/timezone-free dates remain untouched. Active tasks, unfinished jobs and their reuse sources are excluded.
- Delete only shared owned-media names: input.*, audio.*, positive-page audio_pN.*, preview.*, including .part/.ytdl sidecars. Preserve manifests, notes, transcripts, frames and unknown files. Cleanup may remove the media needed to retry.
- Reject symlinks/Junctions, hard links and uncertain identities. Verify opened file identity before deletion; Windows uses locked directory/file handles and deletion by verified handle. A failed file produces a warning while other files continue.
- Atomic age-based deletion is currently Windows-only. Other hosts keep media with warnings rather than performing an unsafe pathname unlink.
- The API accepts strictly integer days in {1,7,30} and returns counts, relative owned-file names and sanitized warnings. Frontend failures are visible in Chinese and cannot block note generation.
- Existing success-only cleanup, transcript-only completion, Feishu retry and custom destinations retain their behavior.

## Completed milestone: note templates

The note-template milestone is complete locally with the following contract:

1. Six read-only built-in templates are available: General Structured Notes (default), Cornell Review Notes, Tutorial / How-to Notes, Interview / Viewpoint Analysis, Knowledge Essentials, and Study Lecture.
2. A user can clone a built-in template, then create, edit, and delete custom templates stored by the backend.
3. A template contains a name, description, LLM organization instructions, and a deterministic Markdown layout.
4. Layouts accept only a documented placeholder allowlist and must contain exactly one `{{content}}` placeholder. They never execute Jinja, Python, JavaScript, shell, or other user code.
5. `summary_style` remains an independent generation-depth strategy. `note_template` controls organization and final layout.
6. Each generation produces one Markdown file. Changing the template reuses an existing transcript, calls the LLM again, creates a collision-safe new note, and preserves previous notes.
7. Local Markdown includes YAML Frontmatter for available title, source URL, platform, author, creation time, template, and transcript source. Missing values are omitted.
8. Each task records the selected template ID, version, and an immutable snapshot so later template edits do not rewrite task history.
9. LLM failure leaves the timestamped transcript available.
10. Focused tests and the complete `pytest` suite pass before one local milestone commit is created.
11. Every template exposes a deterministic preview made from synthetic content. Preview rendering reuses the same one-pass layout substitution, never calls an LLM, and never reads a user note.

## Upstream capability and successor gaps

| Area | Current evidence | Successor status |
| --- | --- | --- |
| Subtitle preference and ASR fallback | `prefer_subtitles` defaults to true; platform subtitles and automatic captions are checked before local ASR; regression tests cover subtitle reuse and ASR paths. A frozen Windows build completed an offline local-media smoke through its isolated ASR child with the cached Whisper `small` model. A separately authorized short synthetic-SRT smoke also completed through DeepSeek `deepseek-flash` without entering download or ASR. | Source and packaged offline transcription paths are accepted for the first successor prerelease. The real-provider evidence is intentionally limited to one short DeepSeek note task and is not a general Provider guarantee. |
| Markdown and transcript artifacts | Upstream writes UTF-8 `notes.md`, `transcript.md`, and `transcript.json`, and exposes completed transcripts through API/MCP paths. | Upstream capability present. |
| Selected directory or Vault output | Note tasks accept an optional absolute final-note destination. Custom destinations receive only the final Markdown and referenced task attachments; leaving it empty preserves `workspace/notes`. Collision, Unicode-path, invalid-path, and credential-boundary tests cover the contract. | Successor customization implemented. A downloaded release asset completed the real chain from imported SRT through DeepSeek to one Markdown file in an isolated custom destination. |
| Personal Markdown template | Six immutable built-ins, backend-stored custom templates, safe deterministic layouts and previews, task snapshots, transcript-reuse regeneration, and frontend management are covered by code and tests. | Successor customization implemented locally. |
| Credential safety | API keys use masked/encrypted local storage on Windows, are bound to endpoints, and errors are scrubbed before persistence. Temporary platform cookie files are deleted. | Covered by code and tests. In the limited DeepSeek smoke, a page-session Key was not saved, `llm_keys.json` was not created, and no key-shaped value or authorization field appeared in the task files, output note, or app log. |
| Media retention | Successful notes retain immediate owned-media cleanup. Failed/cancelled retry media is retained forever by default, with optional 1/7/30-day cleanup. Manifests, notes, transcripts, frames, unknown files and active reuse sources are preserved; uncertain deletion produces warnings. | Success-only cleanup and opt-in age cleanup implemented locally. |
| Same-name output | Default and custom destinations use exclusive creation, safe Unicode filenames, and `-2`, `-3`, and later suffixes. Controlled race tests cover notes and attachment directories without overwriting foreign content. | Covered by automated tests. |
| LLM failure preserves transcript | Transcript artifacts are written before the LLM step and remain readable for failed note tasks. | Covered by code and tests. |
| Unicode and Frontmatter | UTF-8 reads/writes, Chinese filenames, Unicode destination paths, URI-encoded attachment links, deterministic YAML Frontmatter, and YAML-sensitive Unicode escaping are tested. | Covered by automated tests. |
| Brand and workspace UI | Product metadata is centralized in `product_info.py`; the frontend implements the Knowledge Studio layout per `DESIGN.md` with the element-ID contract guarded by `tests/test_frontend_hygiene.py`; brand assets are generated reproducibly by repository scripts. | Brand baseline released in `v1.0.0-beta.1`; beta.2 adds task-flow discoverability; beta.3 adds template previews, local history/favorites, and offline source/reuse guidance. |
| Local history and favorites | `GET /api/tasks` queries compact summaries from persisted task manifests with filters and pagination; one old task is restored only when opened. Completed note tasks can store a local `favorite` flag atomically in `task.json`. | Implemented for beta.3 without a database or Markdown-body scan. Favorites are local metadata, not platform-account collections. |
| Offline source guidance | `POST /api/source-inspect` classifies the URL host and looks for an existing reusable transcript without contacting the platform, reading cookies, or starting download/ASR. | Bilibili, Douyin, and YouTube are labelled focused; TikTok, Xiaohongshu, and other URLs remain generic compatibility only. |
| Task confidence and result handoff | The task status payload exposes queue position plus optional phase progress, processed/total media seconds, and a conservative ETA. The UI keeps the active task visible, runs a local readiness check before submission, and opens only manifest-backed completed files or folders. | Implemented on the post-beta.3 development branch. ETA is intentionally delayed and approximate; unsupported stages remain indeterminate rather than showing fabricated precision. |

## Ordered successor roadmap

1. Fork baseline, attribution, and configurable Markdown destination: complete locally.
2. Note template system: complete locally.
3. Media retention policy: complete locally, including optional 1/7/30-day failed/cancelled media cleanup.
4. Obsidian detection and Vault experience, followed by opt-in Feishu publication: complete locally. Feishu publication now creates an online docx with native in-body image blocks for referenced screenshots; no cloud Markdown file or ZIP is created.
5. One-off real validation for YouTube, Bilibili, and Douyin: complete; this does not guarantee permanent availability.
6. Xiaoe-tech research and local import guidance: complete. Other platform or merchant integrations require separate authorization.
7. Subtitle-file import and SRT export: ported from upstream `662f56b`; complete locally.
8. Windows successor prerelease: `v1.4.2-v2k.1` packages the current MVP and has completed an offline frozen-build local-ASR smoke, including JSON, Markdown, SRT and central transcript archive artifacts.
9. Limited real note chain: the GitHub Release EXE completed `short synthetic SRT -> DeepSeek deepseek-flash -> built-in template -> one Markdown file in an isolated custom destination`. This closes the first end-to-end evidence gap without claiming broad Provider, long-video, public-platform or network compatibility.
10. Independent brand, version line, and Knowledge Studio UI: implemented locally. Product metadata is driven by `product_info.py`; the legacy service id, environment-variable aliases, browser preferences, and MCP/Skill discovery remain compatible; local UI automation and visual acceptance have passed.
11. `v1.0.0-beta.1` release: **complete**. The final local gate passed with `693 passed, 3 skipped`; the branded EXE, cached-model packaged ASR, legacy-environment/static-resource smoke and candidate SHA-256 passed. `main`, the annotated tag and GitHub Pre-release are published; the downloaded EXE matched its checksum and GitHub digest and passed the same offline ASR smoke. Repository Description and Topics were read back successfully.
12. `v1.0.0-beta.2` template and export discoverability: **released and remotely re-verified**. Six built-in templates and custom templates are selectable on the main page; default/custom/Obsidian Markdown destinations are explicit; Feishu remains an opt-in additional publication; export labels identify Markdown, SRT, HTML, JSON, plain text and PNG without changing request fields or task formats.
13. `v1.0.0-beta.3` history and template experience: **released and remotely re-verified**. Deterministic previews use synthetic content; history reads compact manifest summaries with filters/pagination and lazy task opening; favorites are local completed-note metadata; source inspection is offline and only guides the existing reuse/restart behavior. The downloaded Release assets matched GitHub digests and `SHA256SUMS.txt`, then passed the packaged Beta.3 workflow smoke and cached-model offline ASR smoke.
14. Post-beta.3 task confidence: **implemented locally, not released**. Local ASR now advances from real processed media time, multi-page transcription uses cumulative progress, queue position is visible, ETA appears only after a stable sample, and completed results can be opened through a path-constrained local endpoint.

## Non-goals for the current phase

- Xiaoe-tech URL downloading or merchant OpenAPI integration;
- Feishu Wiki/docx import, overwrite or sync, permission management, and automatic login;
- automated cookie management;
- platform-account favorites, playlists, or collection synchronization;
- dedicated TikTok or Xiaohongshu download adapters;
- bypassing platform login, verification, or access controls;
- a complete Obsidian plugin;
- custom Agent or MCP product work;
- a new downloader or ASR framework;
- a large frontend or backend architecture rewrite;
- migration of the old Video2Knowledge Provider/Pipeline architecture;
- cleanup or archival of the old repository.
