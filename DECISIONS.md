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
