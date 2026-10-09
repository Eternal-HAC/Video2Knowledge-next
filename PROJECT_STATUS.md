# Project Status

Updated: 2026-10-09

## Current stage

`Local import guidance and opt-in media retention implemented; independent acceptance pending`

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
- opt-in Feishu publication of completed notes through the local lark-cli user identity (native Markdown plus an optional screenshot ZIP), with a publication-only retry that never reruns download, ASR, or the LLM.

The following items remain open or partial:

- native Feishu cloud image blocks and other deferred destination integrations;
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

## Completed Obsidian and Feishu destination milestone

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

After independent acceptance of this local milestone and separate authorization, perform a read-only feasibility and acceptance-plan review for native Feishu cloud image blocks. Start with existing lark-cli capabilities. No implementation, login or cloud writes are implied. Wiki/docx import, overwrite/sync, permission management, automatic login, new platform adapters and merchant integrations remain deferred.

## Implemented local import and optional age cleanup milestone

- Xiaoe-tech research is closed with a local-import decision: where official permitted download/export supplies a file, use the existing upload, subtitle/ASR, template, Markdown/Obsidian and optional Feishu chain. The local-file source now displays this guidance. No Xiaoe-tech URL downloader or access-control bypass is implemented; merchant OpenAPI is a separate future direction with shop authorization and no current download promise.
- Failed/cancelled media is retained forever by default. Browser-local choices 1/7/30 days enable a single best-effort startup sweep after successful backend connection and a confirmed manual cleanup button. Results and errors are visible in Chinese; cleanup failure does not block generation.
- The existing task layout is WORKSPACE_DIR/<task_id>, not a new tasks subdirectory. Only direct task directories with matching manifests, failed/cancelled status and timezone-aware runtime.finished_at strictly older than the cutoff qualify. Missing/unreliable times remain untouched.
- Active statuses, unfinished jobs and their reuse-source directories are excluded. Only the shared input/audio/positive-page audio_pN/preview name contract and sidecars qualify; notes, transcripts, manifests, frames, unknown files and completed/uploaded/processing tasks remain intact.
- Non-following stat checks reject symlinks/Junctions, hard links and unreliable identities. Opened identity and manifest are rechecked; Windows locks directory/media handles and deletes the verified handle to prevent replacement. Single-file errors become sanitized warnings. Success-note immediate cleanup keeps its existing behavior.
- Validation: targeted retention/API/frontend suite `152 passed, 2 skipped`; full automated suite `500 passed, 2 skipped`; `node --check frontend/script.js` and `git diff --check` passed. Both skips are symbolic-link creation restrictions on this host. Browser behavior was exercised through local DOM/storage/fetch stubs; no real platforms, providers or cloud publication were accessed.
- Portability limit: age-based deletion is supported by verified Windows file/directory handles. Other hosts conservatively keep media and return warnings because a pathname unlink cannot atomically verify file identity; this avoids weakening the replacement-race contract. Other task processing and existing immediate success cleanup are unaffected.
- WATCH: the age-based sweep still runs synchronously inside the event loop, and its performance on a large task library is unverified. Moving it off the event loop later requires task-lifecycle coordination at the same time so the sweep cannot race in-progress tasks. This milestone keeps full-handle validation, the reuse-closure plus uploaded-media-owner protection, the cross-platform test contract, and redacted warnings. It does not switch to `to_thread` and does not add a scheduler or new lock framework.

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
