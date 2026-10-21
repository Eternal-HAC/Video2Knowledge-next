# Decisions

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

## 2026-10-22: Keep beta.3 history, favorites, previews, and source guidance local

Decision: Build template previews from fixed synthetic content through the existing one-pass layout renderer. Query history directly from compact `task.json` summaries with filters and pagination, restore an older task only when it is opened, and store a completed note's optional `favorite` flag atomically in that task manifest. Inspect a pasted URL by hostname plus existing local manifests only; use the result to label support and expose the existing transcript reuse choice.

Reason: These changes make existing local capabilities discoverable without adding a database, a second template format, another LLM call, a platform network probe, or an account synchronization service.

Impact: Local favorites are unrelated to Bilibili, Douyin, YouTube, TikTok, or Xiaohongshu account collections. TikTok and Xiaohongshu remain generic `yt-dlp` compatibility claims. Source inspection never validates live availability and never replaces the downloader's final decision.

Reason: The template, Obsidian, Feishu and export pipelines already existed, but placing their controls only in the settings drawer made working features look absent. Improving discoverability reuses the mature storage and publication paths and avoids a second template system or destination API.

Alternatives considered: keep every control in Settings (rejected because users could not discover core product choices); add a second frontend-only template or export pipeline (rejected because it would duplicate validated backend behavior); split notes into multiple linked files or build an automatic knowledge graph (deferred as a separate product scope).

Impact: `/api/note-templates` returns six built-ins with the same response schema. Browser preferences gain non-sensitive `note_destination_mode`; old non-empty destinations migrate to `custom` without clearing the path. Existing `note_template_id`, `note_destination`, `feishu_upload_enabled` and `feishu_folder` request fields remain unchanged. Interaction research referenced Fabric, video-fetcher-to-markdown, course2md and YouTube Transcript Notes, with no third-party code, prompt, icon or asset copied.

Review condition: Revisit when user evidence supports multi-file notes, note interlinking, an OS-native folder picker, or a broader destination plugin architecture.
