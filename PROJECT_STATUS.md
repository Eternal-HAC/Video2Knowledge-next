# Project Status

Updated: 2026-10-19

## Current stage

`Subtitle import and SRT export accepted; selective upstream reliability sync in progress`

The successor Fork and product baseline are established. The configurable final-note destination and approved note-template milestone are complete locally while preserving the upstream download, subtitle, ASR, task, and summary-style architecture.

The first successor customization is complete in local commit `26a53be`: note tasks can export their final Markdown and referenced task attachments to a user-selected absolute directory, including an Obsidian Vault subdirectory. Leaving the destination empty preserves the upstream `workspace/notes` archive behavior. The feature commit has not been pushed, so local `main` remains ahead of `origin/main`.

## Baseline

- Upstream project: VideoToNo
- Adopted release: `v1.4.2`
- Upstream commit: `0b1df7fe6db3035f94603d58b6f6ab0028083c0f`
- Fork baseline commit: `42aa522640f76cff536918fae61e4ecbd1eb4a09`
- Branch at the start of this documentation stage: local `main` synchronized with `origin/main`
- Automated baseline: 309 tests passed, 0 failed, 0 skipped
- License: MIT License with upstream attribution retained

## Evidence levels

Current code and tests show that the upstream-derived implementation already provides:

- subtitle-first processing with automatic-caption support and local ASR fallback;
- UTF-8 Markdown and timestamped transcript artifacts;
- transcript retrieval after a later LLM failure;
- endpoint-bound API key storage, masking, persisted-error redaction, and short-lived cookie files;
- collision-safe filenames for the current `workspace/notes` archive;
- Unicode-safe note filenames.

The successor customizations now provide:

- dedicated output to a selected normal directory or Obsidian Vault, covered by automated tests.
- four immutable built-in note templates and backend-managed custom templates;
- safe single-pass Markdown layouts with immutable task snapshots and deterministic YAML Frontmatter;
- template-aware short and long summarization without a second full-document LLM pass;
- frontend template loading, creation, editing, cloning, deletion, and note-mode visibility behavior.
- read-only Obsidian Vault detection and one-click Vault destination filling in the web UI;
- opt-in Feishu publication of completed notes through the local lark-cli user identity as an online docx with native in-body image blocks for referenced screenshots, with a publication-only retry that never reruns download, ASR, or the LLM.

The following items remain open or partial:

- Wiki/docx import, overwrite/sync, permission management and other deferred cloud-document integrations;
- new platform URL adapters or shop-authorized merchant integrations, only after separate authorization;

## Platform support levels

- Focused support: YouTube, Bilibili, Douyin, and local media.
- Generic compatibility: other URLs handled by the installed `yt-dlp` version, without platform-specific guarantees.
- Pending adaptation: platforms that need separate lawful research and a dedicated adapter.

Automated platform tests prove controlled behavior and regressions; they do not guarantee that a live platform is currently reachable. Live media checks are risk-based and approval-gated rather than a mandatory per-release matrix.

## Isolated evaluation evidence

Earlier isolated evaluation covered these real flows:

- YouTube platform subtitles;
- YouTube forced ASR;
- local-media ASR;
- public Bilibili input;
- DeepSeek-generated Markdown.

This is evaluation evidence for the adopted upstream baseline. It does not replace focused regression tests or a risk-based live check when a platform-specific change is made.

## Completed template milestone

- Four read-only built-ins: General Structured Notes by default, Cornell Review Notes, Tutorial / How-to Notes, and Interview / Viewpoint Analysis.
- Backend-stored custom templates created by cloning or adding a template.
- Safe placeholder layouts with one required `{{content}}`; no executable template language.
- `summary_style` remains separate from the selected template.
- Template changes reuse existing transcripts and create new collision-safe Markdown without overwriting old notes.
- Deterministic YAML Frontmatter with unavailable fields omitted.
- Template ID, version, and immutable snapshot recorded with each task.
- No Feishu integration, new-platform adapter, or media cleanup in this milestone.

Acceptance evidence:

- full automated suite: `380 passed, 1 skipped`;
- JavaScript syntax check and `git diff --check`: passed;
- local browser smoke check: built-ins loaded; custom create and edit worked; clone form preserved all fields; transcript-only mode hid template controls and note mode restored them; a stale stored template ID fell back to the default after successful template loading;
- the temporary smoke-test template file was removed after verification;
- the independent architect review's four required fixes were applied. A later direct independent Review covered the complete milestone diff and found one P3 frontend error-hint ordering defect; the fix and regression test are included. The earlier dedicated code-reviewer lane did not return a verdict because its execution quota was interrupted, so there is no claim of two-lane formal review approval.

## Completed media retention milestone

- After a note task completes successfully and any custom-destination export has succeeded, the task's own `input.*`, `audio.*`, `audio_pN.*` (positive page numbers only), `preview.*`, and matching `.part` / `.ytdl` sidecars are removed.
- Notes, transcripts, the task manifest, everything under `frames/`, unknown files, and custom-destination exports are preserved; cleanup never crosses into another task directory, never recurses, and never follows symlinks.
- Failed, cancelled, upload-only, and transcript-only tasks keep all retry material; restart restoration for uploaded and interrupted work is unchanged.
- Cleanup is idempotent, runs only after the completed state has been durably persisted (a completion-persist failure keeps retry media and fails the task), and an unlink failure degrades to a task-log warning with the file retained and the task still completed.

Acceptance evidence:

- focused retention tests (successful remote/local/multi-page cleanup, artifact preservation, failure and transcript-only retention, idempotency, directory/symlink guards, unlink-failure degradation, and completion-persist ordering) plus the full automated suite: `388 passed, 1 skipped`;
- `git diff --check`: clean;
- the first failing-test run proved the gap before implementation (4 failed on the uncleaned success paths).

## Completed Obsidian and Feishu destination milestone (historical baseline; superseded by the online-docx milestone below)

Historical baseline, superseded by the "Completed native Feishu online docx milestone" below. The Feishu details in this section describe the former cloud native-Markdown + screenshot-ZIP behavior and are no longer the current publication path; the Obsidian part remains current.

- Obsidian detection is read-only: it reads `%APPDATA%\obsidian\obsidian.json` (existing Vaults only, deduplicated, no app launch, no config writes) and the web UI offers refresh, a Vault select, and an editable subfolder that fills the existing `noteDestination` field. The backend still receives only `note_destination`; manual paths keep working unchanged.
- Feishu upload is opt-in and user-identity only: the web UI detects lark-cli readiness (installed, markdown/drive capability, `auth status` user login, minimal `drive:file:upload` + `drive:drive.metadata:readonly` scopes) without logging in or writing to the cloud, and submission is rejected pre-queue with stable errors when the CLI, auth, scope, or folder target is not ready.
- Publication runs after `notes.md` and the local/custom archive succeed: native Markdown via `lark-cli markdown +create --as user`, then a referenced-frames ZIP via `drive +upload`, serially, in a staged temporary directory that is always removed. A failed or timed-out upload keeps the task `completed`, records sanitized status/error metadata in the task manifest, and logs a warning.
- `POST /api/task/{task_id}/feishu-upload` retries publication only: it re-reads `notes.md`, rebuilds the ZIP from current frames, rechecks readiness, and never reruns download, ASR, or the LLM. The web UI shows 重试上传飞书 only for failed publications and warns about possible duplicate remote files before retrying.
- No raw CLI output, tokens, user identity fields, or scope details are persisted; errors map to stable codes (`auth_expired`, `invalid_folder`, `permission_denied`, `rate_limit`, `timeout`, `upload_failed`). Successful-note media cleanup runs regardless of the Feishu outcome.
- Real-machine evidence (read-only, generalized): Vault detection found the machine's existing Vault(s) without exposing paths in project records, and the lark-cli status check reported a ready user identity without persisting identity or scope details. No real cloud upload was performed; a real Feishu smoke test needs separate user authorization and an explicitly supplied Drive folder.

Acceptance evidence:

- focused tests: `tests/test_note_integrations.py` (29), `tests/test_api.py` Feishu/destination integration tests (9), and new `tests/test_frontend_hygiene.py` structure tests (3); the first runs proved the gaps before implementation (3 backend integration failures, 3 frontend structure failures);
- full automated suite: `429 passed, 1 skipped`;
- `node --check frontend/script.js` and `git diff --check`: clean.

## Completed real platform validation milestone

One-off, approval-gated live checks (distinct from the automated suite; no permanent platform availability is implied):

- YouTube: public platform subtitles retrieved successfully on a sample video (anonymous, no login).
- Bilibili: the sample video from the project README has no anonymous subtitles; with explicit user approval its audio was downloaded (`m4a`, 3,776,270 bytes) and transcribed locally with the cached Whisper `base` model on CPU (85 segments, 957 non-empty characters).
- Douyin: the user-supplied `modal_id` link was validated end to end via an Edge temporary-profile login (memory-only cookies), metadata parsing, an `mp4` download (72,283,717 bytes), and local cached Whisper `base` CPU ASR (573.654s media, language `zh` at 1.000 confidence, 464 segments, 3,775 non-empty characters).
- All temporary media, task directories, temporary browser profiles, and associated browser processes were removed after each check; no titles, cookies, transcript text, or machine-private paths are recorded here.
- The upstream `977c735` CDP stability fix (proxy-free localhost CDP calls, explicit WebSocket proxy opt-out, Winsock failure containment) was ported in `fix: stabilize douyin browser login`; the successful Edge login is consistent with this fix, without claiming it as the sole cause.
- Automated suite evidence at milestone close: `467 passed, 1 skipped`.

## Next milestone

The native Feishu online-docx, subtitle-import/SRT-export, static-resource media-type, model context-window diagnosis, long-note resilience, packaged ASR worker, title/page-aware artifact naming, and transcript-archive/completion-page slices are complete locally; none implies a permanent platform, player, or provider guarantee. The next planned slice is Gate 7: harden the LLM test-connection path around local key read/initialization failures; the concrete contract will be supplied by the coordinator. A real portable-build ASR smoke test requires separate authorization. Wiki integration, overwrite/sync, permission management, automatic login, new platform adapters and merchant integrations remain deferred until separately prioritized and authorized.

## Implemented local import and optional age cleanup milestone

- Xiaoe-tech research is closed with a local-import decision: where official permitted download/export supplies a file, use the existing upload, subtitle/ASR, template, Markdown/Obsidian and optional Feishu chain. The local-file source now displays this guidance. No Xiaoe-tech URL downloader or access-control bypass is implemented; merchant OpenAPI is a separate future direction with shop authorization and no current download promise.
- Failed/cancelled media is retained forever by default. Browser-local choices 1/7/30 days enable a single best-effort startup sweep after successful backend connection and a confirmed manual cleanup button. Results and errors are visible in Chinese; cleanup failure does not block generation.
- The existing task layout is WORKSPACE_DIR/<task_id>, not a new tasks subdirectory. Only direct task directories with matching manifests, failed/cancelled status and timezone-aware runtime.finished_at strictly older than the cutoff qualify. Missing/unreliable times remain untouched.
- Active statuses, unfinished jobs and their reuse-source directories are excluded. Only the shared input/audio/positive-page audio_pN/preview name contract and sidecars qualify; notes, transcripts, manifests, frames, unknown files and completed/uploaded/processing tasks remain intact.
- Non-following stat checks reject symlinks/Junctions, hard links and unreliable identities. Opened identity and manifest are rechecked; Windows locks directory/media handles and deletes the verified handle to prevent replacement. Single-file errors become sanitized warnings. Success-note immediate cleanup keeps its existing behavior.
- Validation: targeted retention/API/frontend suite `152 passed, 2 skipped`; full automated suite `500 passed, 2 skipped`; `node --check frontend/script.js` and `git diff --check` passed. Both skips are symbolic-link creation restrictions on this host. Browser behavior was exercised through local DOM/storage/fetch stubs; no real platforms, providers or cloud publication were accessed.
- Portability limit: age-based deletion is supported by verified Windows file/directory handles. Other hosts conservatively keep media and return warnings because a pathname unlink cannot atomically verify file identity; this avoids weakening the replacement-race contract. Other task processing and existing immediate success cleanup are unaffected.
- WATCH: the age-based sweep still runs synchronously inside the event loop, and its performance on a large task library is unverified. Moving it off the event loop later requires task-lifecycle coordination at the same time so the sweep cannot race in-progress tasks. This milestone keeps full-handle validation, the reuse-closure plus uploaded-media-owner protection, the cross-platform test contract, and redacted warnings. It does not switch to `to_thread` and does not add a scheduler or new lock framework.

## Completed native Feishu online docx milestone

- Feishu publication now creates one online docx via `lark-cli docs +create --as user --doc-format markdown`, embedding referenced screenshots as native in-body image blocks (`![alt](<@./frames/image-NNN.ext>)`). No cloud Markdown file and no screenshot ZIP are created. `docs +media-insert`, DocxXML, Drive import and the former `markdown +create` / `drive +upload` commands are not used.
- Local `notes.md` stays authoritative; the local download ZIP path (`build_note_bundle`) and its endpoints are unchanged. Publication stays opt-in (`feishu_upload_enabled`), default off, `--as user` only, no automatic login and no bot fallback.
- Only images referenced by the final Markdown, resolved inside the task's `frames` directory, present, within `.png/.jpg/.jpeg/.gif/.webp` and <= 20 MiB are staged, in first-appearance order, deduplicated, under controlled ASCII names (`image-001.ext`). Referenced images that are missing, escaping, malformed or too large fail closed (`unsupported_image` / `image_too_large`) before any CLI call.
- Leading-only YAML Frontmatter is stripped from the staged copy; malformed or non-leading Frontmatter is preserved. Original task artifacts are never modified; the per-task `.feishu-stage-*` directory is always removed.
- Readiness requires the `docs` top-level command and three scope groups (create, write, media upload); `docx:document` satisfies create/write, and `docs:document.media:upload` (or the listed equivalent wide scopes) satisfies media upload. `check_feishu_readiness` still returns only `installed`/`capable`/`auth`/`scopes_ready` and never leaks scope detail.
- Publication never changes task status: a failed or timed-out cloud create keeps the task `completed`, stores a sanitized `feishu_publication` (`status`, `format=native_docx`, `document`/`error`, `attempted_at`), and the retry endpoint republishes only. Timeout messaging states that a retry may create a duplicate document. No document id, token, identity or raw CLI output is persisted or shown.
- Source images are copied through a verified open handle: a non-following stat fixes the expected identity, the opened handle is re-checked (links, hard links, replaced or unreliable identities are rejected), and the copy is written from that handle into an exclusive-create target. Uncertain identity or a mid-copy replacement fails closed as `unsupported_image`.
- When the create envelope is `ok=true` but carries a non-empty `data.warnings`, the document stays `uploaded` and no retry is offered; a fixed redacted `warning {code: partial_publication, message: ...}` is stored and the raw warnings are never persisted.
- Automated validation: focused `tests/test_note_integrations.py` (78 passed) and `tests/test_api.py` + `tests/test_frontend_hygiene.py` (140 passed, 1 skipped), plus the full suite (550 passed, 2 skipped); `node --check frontend/script.js` and `git diff --check` passed. These tests use fake runners and made no cloud writes or dependency changes.
- Real-user smoke validation (2026-10-10, separately authorized): one online docx was created in the user-supplied test Drive folder through the project `publish_note` and `build_feishu_docx_staging` path. A read-back confirmed the test heading and list, a native `<img>` block at the referenced body position, removal of leading Frontmatter and its private image reference, and no create warning or fetch tip. The repository records no folder token, document token/URL, identity, or raw CLI output. This is point-in-time evidence for the tested tenant and CLI version, not a guarantee of permanent service behavior or full fidelity for every Markdown construct.

## Completed subtitle import and SRT export milestone

- Ported the timed-subtitle workflow from upstream `662f56b` without cherry-picking. `/api/upload` now accepts `.srt` / `.vtt` alongside media, parses them synchronously through the existing `parse_subtitle_payload`, and registers an already-transcribed uploaded task (`subtitle.<ext>`, `transcript.json` with source `subtitle_import`). Empty or untimed text returns HTTP 415 and removes the task directory.
- Subtitle files use a separate limit (`MAX_SUBTITLE_MB`, default 20 MiB) exposed as `max_subtitle_mb`; the manifest records `subtitle_import` so restart keeps the task resolvable without an `input.*` media match. Submitting it skips metadata probing, subtitle discovery, audio extraction, ASR and screenshots; `include_screenshots` is forced off. Title comes from the original filename stem through the existing safe path.
- `/api/task/{task_id}/transcript?output_format=srt` returns the existing JSON envelope with `format=srt`, `text` rendered by `segments_to_srt` (SubRip `HH:MM:SS,mmm`, CRLF, one cue per segment, integer-millisecond rounding and zero clamping) and a `_safe_filename`-derived `.srt` filename. Export round-trips through the project parser.
- Local `notes.md` stays authoritative; templates, Frontmatter, custom destinations/Obsidian, opt-in Feishu publication, media retention and the local Markdown+attachments ZIP are unchanged. `subtitle.*` is not treated as owned media.
- Validation (fresh): `tests/test_transcript.py` + `tests/test_api.py` + `tests/test_frontend_hygiene.py` 168 passed, 1 skipped; full suite 568 passed, 2 skipped. `node --check frontend/script.js` and `git diff --check` passed.
- Remaining limit: automated tests prove orchestration and local transforms only; real-player SRT rendering and a real platform subtitle import are not exercised. Timed text is required; plain text is rejected instead of inventing timestamps.

## Completed static-asset MIME pinning gate

- Ported upstream `55166ad` without cherry-picking. `NoCacheStaticFiles` now pins `.js` / `.mjs` to `text/javascript; charset=utf-8`, `.css` to `text/css; charset=utf-8`, and `.html` to `text/html; charset=utf-8` from `STATIC_MEDIA_TYPES`, independent of the Windows registry and `mimetypes`.
- Correct types are applied to both 200 responses and 304 revalidation responses; the existing HTML `Cache-Control: no-store`, other-asset `no-cache`, `X-Content-Type-Options: nosniff` and other security headers are unchanged.
- Validation (fresh): `tests/test_api.py` 132 passed, 1 skipped; full suite 569 passed, 2 skipped. The new regression forces `starlette.responses.guess_type` to `text/plain` and asserts the JS/CSS/HTML types plus a 304 carrying the ETag; it failed before the production change.
- Remaining limit: this covers the extensions the bundled frontend serves; new asset kinds need an explicit entry instead of falling back to the OS table.

## Completed model context-window diagnosis gate

- Ported upstream `68117a6` without cherry-picking. `friendly_llm_error` now recognizes `context_length_exceeded`, `context length`, `context window`, `prompt is too long`, `num_ctx`, and `maximum capacity of` case-insensitively before quota/429/401/403/404 matching, so token-count digits such as `9403` no longer hit the 403 branch.
- The user-facing message states that the model-side context window is too small, not a program token setting; it gives `OLLAMA_CONTEXT_LENGTH=16384` and `num_ctx 16384` examples for Ollama / LM Studio / llama.cpp, plus larger-context models or the condensed summary option.
- "Too many tokens per minute" remains a rate-limit error; a dedicated regression pins it and asserts the message does not mention the context window.
- Validation (fresh): the two `friendly_llm_error` regressions passed; `tests/test_api.py` 134 passed, 1 skipped; full suite 571 passed, 2 skipped. The context regression failed before the production change.
- Next: Gate 3, reference upstream `7642479` + `8e02db3` to strengthen long-note resilience; the concrete implementation contract will be given separately by the coordinator.

## Completed long-note resilience gate

- Ported the capabilities of upstream `7642479` + `8e02db3` without cherry-picking; explicitly excluded `23b057f` (no speed/quality selector or request-protocol change).
- Note-generation organizing calls (chunk compression, hierarchical merge, tail patch) now use a dynamic output budget from material characters: content = int(characters / 1.6 * 0.45) plus a 1500-token thinking reserve, clamped to 1600..5000.
- The condensed path merges short ASR lines before chunking, so timestamp overhead no longer forces extra lossy compression calls; transcript artifacts stay sentence-level. A chunk compression failure falls back to `segments_to_prompt(chunk)` with a warning; a merge failure returns the complete current-level notes for that round; a tail-patch failure or timeout keeps the draft. Cancellation is re-raised before any generic exception handler.
- Thinking reserve is evidence-based: `_THINKING_SEEN_CHANNELS` records a channel only after a stream actually emits reasoning; subsequent `auto` requests for that (model_type, base_url, model) add 2000 tokens unless the channel is DeepSeek-compatible. `requested` uses the caller budget and `omit` sends no limit.
- Advice now depends on `_controls_thinking`: DeepSeek compatibility and glm/qwen/openai keep actionable guidance; custom/ollama-like channels say the program has no thinking switch and suggest concise mode, shorter input, or a larger-output model instead of changing the level.
- Validation (fresh): `tests/test_summarizer.py` 84 passed; `tests/test_api.py` 134 passed, 1 skipped; full suite 588 passed, 2 skipped. The new regressions failed before the production changes.
- Remaining risks: the first request on a channel has no reasoning evidence and may still be short; the evidence cache is process-local and empty after restart; generic failures degrade but cancellation never does; no real provider was called.

## Completed packaged ASR worker gate

- Ported the packaged-worker approach from upstream `6abdce7` + `fb97e8a` + `aa29ca2` without cherry-picking. Frozen builds route `run_transcription` to a child process (protocol v1, UTF-8 NDJSON); source checkouts keep `run_transcription_local` in-process.
- The child is launched as `sys.executable --asr-child` in frozen mode and `python -m backend.asr_process` in source mode; Windows uses CREATE_NO_WINDOW; stderr inherits the log stream or is DEVNULL, never PIPE.
- Strict done validation covers segment times/text, language/device/model/requested_model, duration and the allowed optional fields; malformed events, invalid UTF-8, oversized events, missing terminal events and native crashes fail only the current task with `TranscriptionWorkerDied`. Cancellation via the existing cancel event sends a cancel command and, after the grace period, kills only that child; parent-side cancellation uses shielded cleanup.
- Paths are validated on both sides (workspace, direct safe task id, regular file, no symlink/reparse, single link, owned media name); old task owner directories remain allowed for transcript reuse. A TOCTOU window between validation and opening remains.
- Launcher dispatches only the exact `--asr-child` argv, before port probing, logging redirection, server, browser or tray startup.
- Review follow-up: cancel commands carry protocol=1 (the worker validates it); job fields are strictly typed (use_gpu must be a bool, title str or None, model_name in ASR_MODELS); progress rejects negative values; error codes are limited to worker_error/invalid_job/protocol_error with string messages; up to 16 non-JSON stdout noise lines are ignored while malformed JSON or wrong protocol versions still fail immediately.
- Validation (fresh): `tests/test_asr_process.py` + `tests/test_launcher.py` 46 passed, 1 skipped; `tests/test_api.py` 136 passed, 1 skipped; full suite 631 passed, 3 skipped; `compileall` and `git diff --check` clean.
- Limits/risks: after `started` there is no overall timeout (only user cancellation); the path check has a TOCTOU window; non-default concurrent model-cache contention is unverified; automated tests use fake `python -c` workers and cannot prove noconsole behavior, DLL availability, real model loading or spec collection. A portable real-machine smoke test requires separate authorization; no build was produced and no real ASR ran.

## Completed title/page-aware artifact naming gate

- Ported upstream `7236040` without cherry-picking. Added `download_stem(title, meta, output)` and `SAFE_NAME_LIMIT=80`: normal or all-page tasks use the title, a single processed page uses `标题【P2 分P名】`, a partial multi-page set uses `标题【P1、3】`, and transcript output appends `【转录】`. Titles are trimmed first, part names next; P markers and the transcript suffix are preserved; `_safe_filename` still removes Windows-invalid and control characters.
- New manifest metadata (`bili_selected_pages`, `bili_total_pages`) is written from `BiliSubtitleOutcome.pages`/`total_pages` for both subtitle-success and missing-subtitle ASR paths and restored on reuse. The existing request-shaped `bilibili_pages` (list[int] or None) is untouched, so `previous_bili_pages` keeps working. Old manifests without realized metadata fall back to the safe title.
- `/api/task` now exposes `download_name`; `/api/download` md/ZIP and the ZIP-inner note, note archive (default/custom/Obsidian), and SRT export all use the same stem. SRT always gets the transcript suffix; Feishu document titles, task-local `notes.md`/`transcript.md`, Frontmatter and Markdown H1 are unchanged.
- The frontend tracks `currentDownloadName` from history and polling completion; txt/html/json/png/paginated PNG, Markdown/ZIP and SRT prefer the backend name, and reset clears it. The script cache version was bumped; the product version was not.
- Validation (fresh): `tests/test_api.py` + `tests/test_frontend_hygiene.py` + `tests/test_transcript.py` 181 passed, 1 skipped; full suite 639 passed, 3 skipped. `node --check` and `git diff --check` clean.
- Remaining risks: the stem is computed from persisted manifest metadata only; a task whose manifest lacks realized pages intentionally falls back to the title. Long multi-page lists are trimmed inside the marker, and the 80-character budget is a display/OS choice rather than a hard filesystem limit.

## Completed transcript archive and completion-page gate

- Ported upstream `6d05b08` + `fedb621` without cherry-picking. Added `NOTES_DIR_NAME` / `TRANSCRIPTS_DIR_NAME` and an internal archive `folder` keyword restricted to those two; a custom destination still bypasses the folder and keeps the existing attachment/identity/collision logic.
- Successful transcript-only tasks now read the already-persisted `transcript.md` and best-effort archive it to `workspace/transcripts/<download_stem(..., output="transcript")>.md`. Same-name collisions use `-2`/`-3` with the existing exclusive-create race handling. The task remains `completed` on archive failure, with `archived_path=None` and a fixed warning; `transcript.md` stays downloadable.
- `workspace/notes` and `workspace/transcripts` contain no `task.json`; restore, reuse lookup and media-retention scans do not treat them as tasks or remove their files (covered explicitly).
- The completion notice now shows the archive file as the primary line (`已保存到 ...`) and keeps the task directory as secondary information; tasks without an archive keep the task/output directory as the primary line. Task-local names, custom destinations, attachments, Feishu retry and agent-origin history rules are unchanged.
- Validation (fresh): `tests/test_api.py` + `tests/test_frontend_hygiene.py` + `tests/test_media_retention.py` 203 passed, 2 skipped; full suite 647 passed, 3 skipped. `node --check` and `git diff --check` clean.
- Remaining limits: transcript archive is workspace-local only (no Obsidian/Feishu transcript sync); a custom destination is never used for transcripts; the completion page displays paths rather than linkifying them.

## Current constraints

- Successor additions include configurable final-note export, safe templates, destination convenience/publication, permitted local-import guidance and opt-in failed/cancelled media retention.
- Custom destinations receive only the final Markdown and attachments referenced by that note. Task manifests, transcripts, downloaded media, model cache, and credentials remain in the workspace.
- Relative paths, ordinary files, and unavailable destinations are rejected before media processing with stable validation errors.
- Default and custom destinations use exclusive file creation. Controlled race and hard-link tests verify that concurrent foreign content is neither overwritten nor deleted.
- Failed-write cleanup compares the opened file's `fstat` identity with a non-following path `stat`; replaced paths and platforms without a reliable identity are retained instead of risking deletion of foreign content.
- Exported attachment link segments are URI-encoded and resolve back to Unicode and reserved-character filenames.
- The source-boundary implementation rejects attachments that resolve outside the task directory. Its Windows symbolic-link test is skipped when the host does not grant symbolic-link creation permission.
- Real providers, media downloads, model downloads, platform login, cookies, and credentials require explicit user approval.
- Publication of each local commit requires separate user approval.
