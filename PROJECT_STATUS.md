# Project Status

Updated: 2026-10-24

## Current stage

2026-10-24 Beta.4 local closeout is in progress with explicit user authorization. Product checkpoint `90655e4` passed its independent staged snapshot (1329 passed, 3 existing skips); offline fixture/evidence checkpoint `a129f65` passed its independent snapshot (1381 passed, same skips). Version is now `1.0.0-beta.4`; targeted version/Draft checks pass. G0/G1/G2/G3/history browser matrices each pass nine viewport/theme combinations with synthetic data. New portable build/acceptance is pending. No remote operation is authorized or performed. Publication workflow now prepares a Draft for separate downloaded-asset acceptance. Earlier stage entries are historical.

2026-10-24 release preparation: [Beta.4 closeout plan](docs/strategy/26-beta4-release-closeout-plan.md) is ready, not implemented. It defines dependency-aware local commits, a fresh versioned build and acceptance gates, then separately authorized remote publication. The workflow must produce a Draft first so the actual downloaded CI asset is accepted before public release. Runtime remains Beta.3; no staging, commit, version change or remote mutation this round. Earlier next-step statements below are historical.

2026-10-24 isolated portable candidate: **local packaged acceptance passed, not released**. Built the unchanged-version `1.0.0-beta.3` candidate from 60 hashed explicit inputs in an isolated source/dist, using existing PyInstaller 6.22.3. EXE: 133247311 bytes, SHA-256 `f293e960102fc37a492cdf77be86eb2d6d2bd15d58076c8bb1713acb5f99e458`. Packaged templates/history/favorite restart, Host/Origin/metadata rejection, native HTTP and two SDK SSE sessions pass. HTTP offline ASR produces 3 segments, JSON/MD/SRT and one archive; a separate worker protocol probe confirms actual small/CPU and exit 0. See [candidate evidence and limits](docs/strategy/25-isolated-portable-acceptance.md). No runtime edits or new full pytest run this round; prior 1381/3 source result remains applicable to matching inputs. Owned candidate processes stopped, test WAVs removed. No commit or remote change. Next: Beta.4 version/commit/release-preparation contract; do not rename this candidate into a new version or overwrite published beta.3 assets.

2026-10-24 source/client closeout: prioritized cumulative-diff review and real loopback HTTP/MCP SSE tests are complete. The installed SDK initializes, lists tools and reads synthetic notes/transcripts with absent or same-origin Origin. A smoke-script risk was fixed: both portable scripts now probe only listeners owned by the precise launched process tree, instead of choosing any matching version on 8000–8019. Synthetic PowerShell cases and actual Windows CIM/TCP verification pass (owned health GET=1, unrelated GET=0; user 8000 untouched). Final full regression: `1381 passed, 3 skipped in 83.64s`, unchanged skips. See [scope, evidence and isolated candidate contract](docs/strategy/24-source-review-client-acceptance.md). Runtime/version unchanged this round; no build, ASR, commit or release. Next gate is a separate isolated portable candidate, not a claim that released beta.3 includes these fixes.

2026-10-24 S0: **local source acceptance passed; not packaged or released**. Strict loopback peer/Host, same-origin validation, API/MCP Fetch Metadata checks and disabled Uvicorn proxy-header trust are implemented. Native no-Origin clients and streaming remain supported; fixed errors precede body reads and business operations. Full isolated regression: `1367 passed, 3 skipped in 73.82s`, unchanged Windows symlink skips. Real Chrome cross-port simple POST/GET are rejected (403); same-origin requests/navigation and nine viewport/theme history combinations pass. See [S0 acceptance](docs/strategy/23-local-request-security-acceptance.md). Prior audit statements below describe the pre-fix state. Existing beta.3 assets are unchanged. Next: accumulated-source review and a separately scoped portable compatibility/release gate, not new features or automatic cache optimization.

2026-10-24 local-request audit: **release-blocking REST Host/Origin gaps confirmed, not fixed**. Eighteen direct-ASGI observations use isolated bootstrap and a stubbed login route, with no real service, credentials or side effects. A foreign-Origin empty POST reaches the stub (200), while OPTIONS returns 405; arbitrary Host is also accepted by REST. The installed MCP SDK separately rejects untrusted Host/Origin (421/403), so it is not classified as the same REST gap. Missing peer is fail-open in the current helper. See [audit and S0 repair contract](docs/strategy/22-local-request-security-audit.md) and [sanitized evidence](docs/quality/local-request-audit-20261024.json). Existing API/MCP regression: `195 passed, 1 skipped in 32.20s`. Runtime/test source is unchanged; no full-suite rerun or security-fix acceptance is claimed. S0 failure-first request-boundary repair is the next candidate, before a future release.

2026-10-24 G5.1-D: profiling confirmed repeated Windows path resolution is a major cost in the experimental hit path. The default history list now uses fresh reads again; the cache is retained only behind explicit isolated test/benchmark replacement, with no product setting. Manual refresh and stale-response guards remain unchanged. The new [default-path report](docs/quality/benchmarks/g51-d-default-20261024.json) records 1,000-task default p95 `742.230ms`; all four input/response hashes match C. This is a separate run, not a paired speedup claim, and the 300ms target remains open. See [D evidence](docs/strategy/21-history-cache-default-rollback.md). Earlier A/B/C default-cache statements below are historical. Full isolated regression: `1106 passed, 3 skipped in 75.36s`, unchanged skip reasons; 9 fresh Chrome combinations pass. Python/Node/pip/diff checks pass. Owned server 18754 and browser stopped; user 8000 untouched. No commit, build or release.

D final targeted validation: `396 passed, 1 skipped in 20.29s`; 132 local documentation links and both reports' four source hashes checked. Next recommended bounded step: Host/Origin and local browser request security review; any repair requires a scoped failure-first contract. No automatic database or renewed cache optimization.

2026-10-23 G5.1-C: optional `refresh=true`, filter-preserving first-page refresh and sequence/filter-based stale-response guards are implemented. The isolated Chrome matrix passes 9 viewport/theme combinations. The [paired cache report](docs/quality/benchmarks/g51-c-20261023.json) shows a failed performance gate: 1,000-task default hit p95 `1189.446ms` versus same-run direct `810.114ms`; all four query variants regress despite zero warm manifest reads. Inputs/results match G5. Per contract, the 10,000-task run was stopped. See [C evidence](docs/strategy/20-history-cache-c-acceptance.md). G5.1 is not accepted as a performance improvement; the unreleased cache requires profiling or default-path rollback before release, without weakening path checks or automatically adding SQLite. Earlier pending-C statements below are historical.

C final validation: `393 passed, 1 skipped in 22.21s` targeted; `1103 passed, 3 skipped in 73.28s` isolated full regression, same symlink-permission skips. Python compilation, 3 Node syntax checks, pip and diff checks pass. Synthetic browser evidence and benchmark inputs remain under `.test-tmp/g51-c-*`; the precise isolated server/browser processes were stopped. No user service, credentials, dependency change, build, staging, commit, push or release.

2026-10-23 G5.1-B follow-up: only the history-list reader now uses bounded projections; successful repository replacements and task deletion invalidate the precise entry. Favorite eligibility, recovery, source reuse and artifact access remain uncached. Legacy live/disk precedence, hidden agent transcripts and pagination are preserved. Targeted tests: `153 passed in 6.88s`, including 39 new integration cases. Final isolated regression: `1095 passed, 3 skipped in 70.51s` (unchanged skips); compilation, Node syntax, pip and whitespace checks pass. See [B acceptance](docs/strategy/19-history-cache-b-acceptance.md). Four synthetic query variants read 35 manifests cold and zero warm, with identical responses and zero body reads. No latency improvement is claimed before C remeasurement. Public API and frontend are unchanged; explicit refresh and browser checks remain in C. Earlier A/design-only statements below are historical. No build, commit or release.

2026-10-23 G5.1-A follow-up: standalone `backend/history_cache.py` and 78 failure-first/cache-boundary cases are implemented; together with existing history/repository checks, `114 passed in 3.80s`. Final isolated regression: `1056 passed, 3 skipped in 63.64s` (same three symlink-permission skips). Python compilation, Node syntax, pip and whitespace checks pass. See [A acceptance](docs/strategy/18-history-cache-a-acceptance.md). No product reader/writer/UI is connected to it, so history performance is unchanged and no speedup is claimed. The prior design-only status below is historical. B integration and C refresh/remeasurement remain open.

2026-10-23 G5.1 design follow-up: the [bounded history-summary cache contract](docs/strategy/17-history-cache-design.md) is written, not implemented. It specifies a process-local, list-only LRU, bounded entries/encoded payload, fixed external-change revalidation, repository write invalidation, manual refresh and stale-response tests. Recovery, favorite eligibility and artifact access remain on uncached paths. Implementation is split into pure-cache tests, integration/invalidation, then UI refresh and comparable measurements. Fresh existing history/repository tests: `36 passed in 2.98s`; 13 local plan/design links checked. The full suite was not rerun; the 978/3 result below belongs to G5. Main/repository/benchmark hashes still match its after-report. No cache/API/source change, performance claim, build or release is included in this documentation step.

2026-10-23 G5 benchmark follow-up: synthetic 100/1,000/10,000-task runs and request-local history deduplication are complete. Each history manifest is read once instead of twice, with one canonical-directory lookup instead of three; all paired dataset and query-response hashes match. Default warm-handler p95 at 1,000 tasks changed from `1755.670ms` to `1011.433ms`, still above the `300ms` reference target. Startup restoration did not consistently improve. See [G5 acceptance](docs/strategy/16-g5-acceptance.md) and [raw reports/method](docs/quality/history-benchmark.md). Targeted tests: `21 passed`; final isolated regression: `978 passed, 3 skipped in 61.92s` (same symlink-permission skips). No cache, index, storage migration, UI rewrite, real calls, build or Git mutation. The next candidate is separately designed bounded summary caching/invalidation, not an already-delivered performance guarantee.

2026-10-23 G4 offline follow-up: 12 original synthetic cases, deterministic rules, an unscored manual-review sheet, a whitelist diagnostic reference projection, an environment collector and four-way local asset comparison are implemented. See [G4 acceptance](docs/strategy/14-g4-acceptance.md) and [tool guide](docs/quality/README.md). Targeted tests: `74 passed`; G4 full regression: `957 passed, 3 skipped in 60.90s`, with only the same three symlink-permission skips. Node/Python syntax, pip check and diff check pass. The rules do not measure semantic accuracy; no real model evaluation, diagnostic UI/API integration, downloads, credentials, build or Git mutation. The former G5-not-started status is superseded above.

2026-10-23 G3 follow-up: read-only timestamp/range transcript lookup, stable content hashes, paged original-text comparison, explicit note refresh, stale-response rejection and mobile keyboard navigation are locally accepted. G3 regression: `883 passed, 3 skipped`; G3/G1/G2/G0 browser matrices each passed all 9 combinations. Source Markdown and exports remain unchanged; time overlap does not establish claim correctness. See [G3 acceptance](docs/strategy/12-g3-acceptance.md). No build, commit, push, credentials or real Provider/Feishu call. The G4-not-started status from that stage is superseded above.

2026-10-23 G2 follow-up: atomic serialized manifest merges, validated transcript recovery, parent/ref provenance, optional request-ID replay across restart, shared HTTP/MCP recovery summaries, and read-only confirmation of uncertain submissions are locally accepted. Full regression: `848 passed, 3 skipped`; G2, G1 and G0 browser matrices each passed 9 viewport/theme combinations. Existing unknown fields and original favorites remain intact; corrupt transcripts never silently trigger source processing during explicit recovery. See [G2 acceptance](docs/strategy/10-g2-acceptance.md). Single-backend-process scope; no build, commit, push, credentials or real Provider/Feishu call. This count describes the earlier G2 stage.

2026-10-23 G1 follow-up: source-first composition, collapsed long template previews, a safe heading outline, literal in-note search, and response-based Markdown/ZIP feedback are locally accepted. Final regression: `800 passed, 3 skipped`; G1 and G0 browser matrices each passed all 9 viewport/theme combinations. No backend contract or original note content changed. See the [G1 acceptance record](docs/strategy/08-g1-acceptance.md). These changes remain uncommitted and unreleased; the earlier counts below describe historical stages.

2026-10-22 G0 follow-up: the user authorized continuous execution of all four reliability checkpoints. Source-local repairs and acceptance are complete; see the Chinese [G0 acceptance record](docs/strategy/07-g0-acceptance.md). Result-opening checks now reject unsafe lexical path components and non-Markdown targets, multi-page ASR progress and late callbacks are guarded, readiness/privacy wording is evidence-bounded, and the browser checks cover header/strip overlap and readiness layout. The earlier 721/3 count below is historical; the acceptance record contains the current full-suite result. No build, commit, push or release was performed.

`Video2Knowledge v1.0.0-beta.3 released and remotely re-verified`

The successor Fork and product baseline are established. The configurable final-note destination and approved note-template milestone are complete locally while preserving the upstream download, subtitle, ASR, task, and summary-style architecture.

The product is now branded **Video2Knowledge** with an independent version line starting at `1.0.0-beta.1` (driven solely by `product_info.py`), an original script-generated logo, and a redesigned Knowledge Studio workspace per `DESIGN.md`. Local UI automation, visual acceptance, Windows candidate acceptance, remote publication, asset read-back and downloaded-release offline ASR have passed.

The beta.2 release adds two safe built-in templates (Knowledge Essentials and Study Lecture), surfaces all built-in and custom templates in the main workflow, makes default/custom/Obsidian Markdown destinations explicit, keeps Feishu as an optional additional publication, and gives every result format an explicit export label. Existing request fields, task manifests, one-video-to-one-Markdown behavior, saved custom templates, Obsidian handling and Feishu publication logic remain compatible. The local candidate, published assets and downloaded Release executable have all passed the acceptance recorded below.

The beta.3 release adds deterministic synthetic template previews, manifest-backed history search/filter/pagination, lazy opening of older tasks, local favorites for completed notes, and offline URL support/reuse guidance. The final complete regression passed with `713 passed, 3 skipped`; visual, packaged, release, digest and downloaded-asset smoke gates all passed.

Post-beta.3 development is currently local and unreleased. The completed local slice replaces the fixed ASR percentage with measured media-time progress, exposes queue position and conservative delayed ETA, keeps the current task visible while the user scrolls, summarizes readiness before submission, and adds safe result-file/folder opening. The final complete regression passed with `721 passed, 3 skipped`; both JavaScript syntax checks, `pip check`, and `git diff --check` passed. Real-page Chrome/CDP checks passed at 1440×900, 1024×768, and 390×844 with no page-level horizontal scrolling. No public version, tag, Release asset, external provider call, media/model download, or cloud write is part of this slice.

The first successor customization was completed in commit `26a53be`: note tasks can export their final Markdown and referenced task attachments to a user-selected absolute directory, including an Obsidian Vault subdirectory. Leaving the destination empty preserves the upstream `workspace/notes` archive behavior. It is included with the later template, retention, destination, reliability and prerelease work in the successor release line.

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
- six immutable built-in note templates and backend-managed custom templates;
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

Beta.3 is closed. The next milestone is not selected automatically. Candidate product decisions remain proxy/diagnostics policy (without automatic proxy bypass), headless agent operation, and new platform or Feishu extensions; each requires a separate scoped plan and acceptance contract.

## Implemented beta.3 history and template preview milestone

- `/api/note-templates` adds a read-only `preview_markdown` to the existing template payload. Six built-ins use distinct fixed Chinese examples; custom templates use one fixed synthetic body through the existing one-pass layout renderer. The path does not call the summarizer, read user notes, create tasks, or persist preview data.
- `GET /api/tasks` keeps the existing `tasks` field and adds compact manifest-backed search, status/output/platform/favorite filters, offset/limit pagination and `total`/`has_more`. Startup still preloads only `TASK_HISTORY_LIMIT`; opening an older item restores exactly that task and reads its Markdown only then.
- `PATCH /api/task/{task_id}/favorite` atomically stores one optional boolean in `task.json` and accepts only completed note tasks. It does not rewrite the note, transcript, template snapshot, or task status. Favorites are local metadata and are unrelated to platform-account collections.
- `POST /api/source-inspect` validates/classifies the URL host and reuses the existing transcript lookup. It performs no external request, cookie read, media/model download, ASR, or login. Bilibili, Douyin, and YouTube are shown as focused; TikTok, Xiaohongshu, and all other URLs remain generic compatibility only.
- Frontend behavior: template cards update a rendered/Markdown preview; history is always visible with filters, load-more and accessible star controls; pasted links show non-blocking support and reuse/restart actions after a cancellable debounce. Existing task submission, polling, download, Obsidian, Feishu, and one-video-to-one-Markdown behavior remain in place.
- Final local automated evidence: focused backend/frontend/template suite `264 passed, 1 skipped`; complete suite `713 passed, 3 skipped`; both JavaScript syntax checks, the PowerShell smoke-script parse, `pip check`, and `git diff --check` passed. The three skips remain the existing Windows link/reparse permission cases.
- Visual evidence: the real page passed 1440×900 system-theme, 1024×768 light-theme, and 390×844 dark-theme capture checks with `scrollWidth == clientWidth`. The mobile template row scrolls inside its component, history filters form two columns, and visible focus/keyboard contracts remain covered by frontend tests. README home/history/template-preview images use only synthetic titles and an isolated empty workspace.
- Final local Windows candidate: `Video2Knowledge-1.0.0-beta.3-portable.exe`, 133,204,719 bytes, SHA-256 `835ff8b06168f973537f99fa311c5c5e029ec82f08b88a0d05a9369393c3f3cc`. Windows VersionInfo reports ProductName `Video2Knowledge`, FileVersion `1.0.0.0`, and ProductVersion `1.0.0-beta.3`; `SHA256SUMS.txt` matches the candidate.
- Packaged Beta.3 smoke used an isolated synthetic workspace and restarted the exact candidate process: all six previews were non-empty; history pagination returned two compact manifests; one completed-note favorite persisted across restart; the old task was lazily restored; offline YouTube classification found the seeded reusable transcript. A separate cached Whisper `small`/CPU/SAPI smoke completed through the frozen ASR child with 3 Chinese segments plus JSON, Markdown, SRT and a central transcript archive. No media/model download, LLM call, platform login, Cookie read, or Feishu write occurred.
- Release commit `dcfedcb18a5b7088a1302070378e2a4efc371ed4` is the target of the dereferenced annotated tag `v1.0.0-beta.3`. The tag event produced no GitHub Actions run, so the approved manual fallback published the already accepted local assets without rebuilding. The resulting GitHub Release is a non-draft Pre-release.
- GitHub reports `Video2Knowledge-1.0.0-beta.3-portable.exe` as 133,204,719 bytes with digest `sha256:835ff8b06168f973537f99fa311c5c5e029ec82f08b88a0d05a9369393c3f3cc`; `SHA256SUMS.txt` has digest `sha256:47140f7a147d70d1df3d4bd6c75843cdc6c3a1401bea709d02dccdc8889f828f`. Freshly downloaded assets matched both GitHub digests and the checksum file, then passed the packaged Beta.3 history/favorite/source smoke and the cached-Whisper `small` offline ASR smoke again.

## Implemented beta.2 template and export discoverability milestone

- `/api/note-templates` now exposes six ordered, read-only built-ins. The two additions use the same safe `# {{title}}` + `{{content}}` layout, put section decisions in the existing summarizer instruction, snapshot into tasks, and do not add another LLM call.
- The main page renders all built-in and custom templates as keyboard-operable cards synchronized with the existing template select/editor. Loading and failure stay explicit, and a failed template load still blocks note submission.
- Local output is a three-way choice: default `workspace/notes`, a preserved custom absolute path, or a detected Obsidian Vault plus subfolder. Old preferences with a non-empty `note_destination` migrate to `custom`; switching to default does not erase the saved path. Feishu remains off by default and local Markdown remains the primary artifact.
- The result action is labelled `Export Markdown` by default and follows the selected SRT/HTML/JSON/plain-text/PNG format. The request schema and backend export endpoints are unchanged.
- Automated gate: `706 passed, 3 skipped` in the complete suite; the three skips remain the existing Windows link/reparse permission cases. `node --check` passed for both frontend scripts, `pip check` reported no broken requirements, and `git diff --check` passed.
- Visual gate: the real page passed 1440×900, 1024×768 and 390×844 capture checks in system/light and dark rendering; document `scrollWidth` equalled `clientWidth` at every measured viewport. Mobile template cards scroll only inside their own component. The three README screenshots use isolated synthetic data and contain no real key, private path or user task.
- Release evidence is closed by the post-release entry below.

## Published beta.2 release closeout

- Release commit `cf03f4e7ff0958d09c3a916afd920c457529c4d4` contains three focused commits for the templates, main-workflow discoverability and documentation. Remote `main` and the dereferenced annotated tag `v1.0.0-beta.2` both resolve to that commit.
- Local automated acceptance passed with `706 passed, 3 skipped` in 54.39 seconds. The three skips remain the existing Windows link/reparse permission cases. Both JavaScript syntax checks, `pip check` and `git diff --check` also passed.
- The Windows candidate is `Video2Knowledge-1.0.0-beta.2-portable.exe`, 133,192,576 bytes, SHA-256 `50c278fd1d8b659b066b77f7d6157b7d2a92b0f3511268c7e6f58f53d0bde970`. Windows VersionInfo reports ProductName `Video2Knowledge`, FileVersion `1.0.0.0` and ProductVersion `1.0.0-beta.2`.
- Packaged acceptance used an isolated workspace, a Windows SAPI-generated Chinese WAV, cached Whisper `small`, CPU mode and offline Hugging Face settings. The frozen ASR child produced 3 non-empty Chinese segments, JSON, Markdown, standards-shaped SRT and one central transcript archive. No model/media download, LLM call or Feishu write occurred. Separate launches proved both `VIDEO2KNOWLEDGE_*` and legacy `VIDEOTONOTES_*` workspace/browser aliases, the branded home page and all six built-in templates.
- GitHub Release `v1.0.0-beta.2` is a non-draft Pre-release. GitHub reports the EXE at 133,192,576 bytes with digest `sha256:50c278fd1d8b659b066b77f7d6157b7d2a92b0f3511268c7e6f58f53d0bde970`; a fresh download matched that digest, the published `SHA256SUMS.txt` and the local candidate, then passed the same packaged offline-ASR smoke again.
- The tag-triggered Release workflow again produced no Actions run. The authorized manual fallback uploaded the already accepted local assets. Both uploads completed; the first publish transition hit a TLS handshake timeout, and retrying only the missing draft-to-Pre-release transition succeeded. No asset was rebuilt, no tag was moved, and no history was rewritten.

## Implemented independent brand and Knowledge Studio UI milestone

- The product is renamed to **Video2Knowledge** with an independent version line: `1.0.0-beta.N` → `1.0.0-rc.N` → `1.0.0`. `product_info.py` is the single metadata source for the launcher, backend, build script, and release workflow. The transitional `v1.4.2-v2k.N` line sorts below the independent line in update checks, so existing successor installs still see later versions as updates.
- Compatibility boundaries are preserved by contract: `/api/health` keeps the legacy `service: "VideoToNo"` value and adds `product`/`api_compat` (additive-only); `VIDEO2KNOWLEDGE_*` environment variables take priority while `VIDEOTONOTES_*` names keep working; browser-local preferences migrate from `vtn_prefs` to `v2k_prefs` while the old key remains for rollback and no API key enters localStorage; the `workspace/` layout, credential files, MCP tool names, and Agent Skill directory remain compatible.
- The workspace UI is redesigned as Knowledge Studio per `DESIGN.md`: task-first first screen, settings collected into a slide-out panel, state conveyed by text plus color, system-font-only styling, and `prefers-reduced-motion` support. The brand mark is an original geometric logo generated reproducibly by `scripts/make_brand_assets.py`; no third-party icon sets or upstream-derived artwork are used. Backend APIs, task semantics, and the frontend element-ID contract (`tests/test_frontend_hygiene.py`) are unchanged.
- Acceptance so far: local UI automation checks and visual acceptance of the redesigned workspace have **passed**. The final complete suite passed with `693 passed, 3 skipped`; the three skips remain the existing Windows symbolic-link permission cases.
- Local candidate artifact: `Video2Knowledge-1.0.0-beta.1-portable.exe`, 133,191,612 bytes. Windows VersionInfo reports ProductName `Video2Knowledge`, FileVersion `1.0.0.0`, ProductVersion `1.0.0-beta.1`; SHA-256 is `9c2cda4ecc3316ab926cdb458e37025a39cd05ae8196010d7d4d50b42094aa50`, and the build script rewrote `SHA256SUMS.txt` with this versioned filename.
- Packaged smoke: an isolated Windows SAPI Chinese WAV completed through the frozen ASR child with cached Whisper `small` and Hugging Face offline mode, producing 3 non-empty Chinese segments plus JSON, Markdown, SRT and one central transcript archive. No media/model download, LLM call or Feishu write occurred; the exact process tree and temporary workspace were removed.
- Compatibility/static smoke: a second isolated launch used only legacy `VIDEOTONOTES_WORKSPACE`/`VIDEOTONOTES_NO_BROWSER`; the candidate wrote its log into that workspace, returned `product=Video2Knowledge`, `service=VideoToNo`, `api_compat=1`, version `1.0.0-beta.1`, mode `portable`, and served the branded home page, favicon and PNG icon with correct media types. Its exact process tree and temporary directory were removed.
- Three README screenshots have been generated from the real page with isolated synthetic data by `scripts/capture_readme_screenshots.mjs`; animation is disabled only in the capture page so repeated runs are byte-identical.
- Remote closeout: `main` and the annotated `v1.0.0-beta.1` tag resolve to release commit `dfe83b388f8029cc9903694bda621e7a9be9537c`; the GitHub Release is a non-draft Pre-release. GitHub reported the EXE as 133,191,612 bytes with digest `sha256:9c2cda4ecc3316ab926cdb458e37025a39cd05ae8196010d7d4d50b42094aa50`. A fresh download matched that digest and `SHA256SUMS.txt`, then passed the packaged offline-ASR smoke with 3 Chinese segments and JSON, Markdown, SRT and one central archive.
- Repository metadata closeout: the approved Chinese Description and all 12 Topics were written and read back through GitHub. The tag-triggered Actions run did not start (the Actions API returned zero runs), so the already accepted local artifact was uploaded through the authorized manual fallback; no tag deletion, force push or history rewrite occurred.
- Evidence carried over from earlier stages: the `v1.4.2-v2k.1` offline frozen-build ASR smoke and the limited DeepSeek real-note-chain acceptance below remain valid for that build; they do not by themselves accept the rebranded candidate, and the DeepSeek evidence remains limited to one short synthetic transcript and one model.

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
- Historical gate limits at that point: after `started` there is no overall timeout (only user cancellation); the path check has a TOCTOU window; non-default concurrent model-cache contention is unverified; automated tests used fake `python -c` workers. The later Windows successor prerelease gate below superseded the then-pending build/real-ASR limitation with a successful frozen-build smoke.

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

## Completed LLM test-connection key-read gate

- Ported only the local key-read/initializer boundary from upstream `088b665`; diagnostics endpoints, proxy bypass, DNS/external probes and frontend changes were deliberately excluded.
- `POST /api/llm-test` now catches any non-RuntimeError exception from `resolve_llm_credentials` and returns HTTP 200 with the existing `{ok, error}` envelope and a fixed redacted message; `RuntimeError` business messages are unchanged.
- Summarizer construction/test failures sanitize `str(exc)` with `utf8_safe`, then `redact_secrets(..., api_key)`, then `redact_paths`, so fake keys, Bearer tokens, Windows paths and lone surrogates cannot leak or break JSON. No raw configuration is logged or returned.
- Validation (fresh): `tests/test_api.py` 156 passed, 1 skipped; full suite 653 passed, 3 skipped. `git diff --check` clean.
- Remaining risks: path redaction is pattern-based; unusual path shapes could still appear, and the handler still returns exception type names (never `str(exc)`). No real provider or network request was made.

## Completed Windows successor prerelease gate

Historical record for `v1.4.2-v2k.1`. Its decision to keep the VideoToNo runtime/product name has been superseded by the independent-brand milestone above; the build and acceptance evidence below still stands for that release.

- Release identity is `v1.4.2-v2k.1`: it preserves the VideoToNo runtime name and workspace/credential compatibility while identifying the first Video2Knowledge successor prerelease. Runtime, FastAPI health and frontend display the same successor version.
- The manual update check now reads non-draft releases, including prereleases, from `Eternal-HAC/Video2Knowledge-next`; it no longer directs successor users to an upstream release that lacks successor features. Version comparison recognizes the `-v2k.N` sequence.
- The Windows one-file build used Python 3.13.7, PyInstaller 6.22.3 and its newly installed build-only dependencies. Existing runtime packages were not upgraded, and `pip check` reported no broken requirements.
- Built artifact: `VideoToNo-1.4.2-v2k.1-portable.exe`, 133,634,842 bytes (127.4 MiB), SHA-256 `D4548392E372293A7CDD8E8C0FC34ED7067D06598C2196AFC0D9A073C74016D1`. Windows file/product version remains `1.4.2.0` because PE numeric versions cannot encode the successor suffix; the application and health API report the full version.
- Real frozen-build smoke: an isolated workspace and Windows SAPI-generated Chinese WAV were submitted through the packaged HTTP API with network model access disabled. The cached Whisper `small` model completed through the frozen ASR child, producing 3 non-empty Chinese segments plus JSON, Markdown, standards-shaped SRT and one central transcript archive. The exact launched process tree and all temporary media/workspace files were removed afterward.
- Automated evidence: targeted release tests `194 passed, 1 skipped`; final complete suite `656 passed, 3 skipped`; `node --check frontend/script.js`, tracked and untracked diff checks, PowerShell smoke-script parsing, and `pip check` passed.
- Boundary of the release gate itself: no public media/model download, platform login/cookies, real LLM Provider call or Feishu write was performed. A separate limited real-provider acceptance followed after publication.

## Completed limited real note-chain acceptance

- On 2026-10-21, the published GitHub Release assets were downloaded into an isolated temporary directory. The 133,634,842-byte EXE matched `SHA256SUMS.txt`, the GitHub asset digest, and the expected SHA-256 `D4548392E372293A7CDD8E8C0FC34ED7067D06598C2196AFC0D9A073C74016D1`.
- The downloaded EXE reported `1.4.2-v2k.1` in `portable` mode and used an isolated workspace. A three-segment synthetic Chinese SRT was registered as `subtitle_import`; the task reused all three segments and explicitly skipped subtitle lookup, audio and Whisper.
- One authorized note task used DeepSeek `deepseek-flash`, the built-in general template, `faithful` style and reasoning `off`. It completed in about 3 seconds and exported exactly one Markdown file to the isolated custom destination, with parseable YAML Frontmatter, the expected footer, and all three coverage anchors (`V2K-ALPHA-17`, `CHECK-42`, `DONE-93`).
- The page-session Key was not saved: the isolated workspace contained no `llm_keys.json`, the manifest contained no LLM configuration or API-key field, and targeted scans found no key-shaped or Authorization value in task files, the note, or the app log. The exact two-process portable tree was terminated and port 8000 had no remaining listener.
- This is deliberately narrow evidence for one short synthetic transcript and one DeepSeek model. It does not establish compatibility for other Providers, long videos, public-platform acquisition, unstable networks or paid/login-protected sources.

## Current constraints

- The product brand is Video2Knowledge on an independent version line; the legacy `service: "VideoToNo"` health field, `VIDEOTONOTES_*` environment names, browser preferences, MCP tool names and Skill discovery are compatibility positions that must not be dropped without a dedicated migration decision.
- Successor additions include configurable final-note export, safe templates, destination convenience/publication, permitted local-import guidance and opt-in failed/cancelled media retention.
- Custom destinations receive only the final Markdown and attachments referenced by that note. Task manifests, transcripts, downloaded media, model cache, and credentials remain in the workspace.
- Relative paths, ordinary files, and unavailable destinations are rejected before media processing with stable validation errors.
- Default and custom destinations use exclusive file creation. Controlled race and hard-link tests verify that concurrent foreign content is neither overwritten nor deleted.
- Failed-write cleanup compares the opened file's `fstat` identity with a non-following path `stat`; replaced paths and platforms without a reliable identity are retained instead of risking deletion of foreign content.
- Exported attachment link segments are URI-encoded and resolve back to Unicode and reserved-character filenames.
- The source-boundary implementation rejects attachments that resolve outside the task directory. Its Windows symbolic-link test is skipped when the host does not grant symbolic-link creation permission.
- Real providers, media downloads, model downloads, platform login, cookies, and credentials require explicit user approval.
- Publication of each local commit requires separate user approval.
