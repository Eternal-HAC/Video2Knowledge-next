# Current TODO

This file holds only the active gap-verification queue. For every item: close it when upstream already satisfies the requirement; add a test when evidence is insufficient; change implementation only after the test demonstrates a gap.

1. [x] Selected directory or Obsidian Vault output
   - Closed by the optional absolute-path destination setting, preflight validation, final-note-only export, referenced-attachment copying, relative-link rewriting, and collision tests.
   - Leaving the setting empty keeps the existing `workspace/notes` behavior.
2. [x] Personal Markdown template
   - Closed locally by six read-only built-ins, backend-stored custom templates, safe deterministic layouts, immutable task snapshots, YAML Frontmatter, and transcript-reuse regeneration.
   - Keep `summary_style` independent from `note_template`; do not add a second full-document LLM pass.
3. [x] Subtitle-first and local-ASR fallback
   - Closed for gap verification by current code and tests. Live checks are performed only when platform work or release risk justifies them.
4. [x] Credential safety
   - Closed for gap verification by storage, masking, error-redaction, and temporary-cookie tests. Real-provider use remains authorization-gated.
5. [x] Media and intermediate-file retention
   - Closed locally: after a note task completes successfully, its own `input.*`, `audio.*`, `audio_pN.*`, `preview.*`, and matching download sidecars are removed; notes, transcripts, the task manifest, frames, unknown files, and custom-destination exports are preserved.
   - Failed/cancelled retry media is retained forever by default. Optional 1/7/30-day cleanup uses persisted terminal time, excludes active jobs and their reuse sources, and preserves manifests, notes, transcripts, frames and unknown files. Upload-only and completed transcript-only media stays intact.
   - Age-based cleanup is implemented locally with browser-local preferences, one startup attempt after backend connection, a manual button and sanitized Chinese feedback. Identity/link/manifest checks retain uncertain files with warnings.
6. [x] Same-name output protection
   - Closed for both destinations by exclusive-create collision and controlled-race tests. Custom attachment directories are tied to each final note stem; failure cleanup uses verified file identity so existing or replacement foreign files are not overwritten or removed.
7. [x] Transcript availability after LLM failure
   - Closed by transcript persistence and failed-task retrieval tests.
8. [x] YAML Frontmatter
   - Unicode UTF-8 output, Chinese filenames, and Unicode custom destination paths are covered.
   - Closed by deterministic YAML Frontmatter that omits unavailable values and safely escapes YAML-sensitive Unicode code points.

## Active release task

- [ ] `v1.0.0-beta.3` history and template preview release:
  1. [x] Add deterministic previews for six built-ins and custom layouts without an LLM call or user-note read.
  2. [x] Upgrade local history with manifest-backed search, filters, pagination, lazy task opening, and completed-note favorites.
  3. [x] Add offline URL platform labels and reusable-transcript hints without network, cookies, download, or ASR.
  4. [x] Focused tests and the first complete regression passed with `712 passed, 3 skipped`; no skip was added.
  5. [x] Finish 1440/1024/390 system/light/dark and keyboard-contract acceptance; regenerate synthetic home, history, and template-preview screenshots without page-level horizontal scrolling.
  6. [ ] Build and inspect `Video2Knowledge-1.0.0-beta.3-portable.exe`; pass isolated packaged history/favorite/source inspection and cached-Whisper `small` ASR smoke.
  7. [ ] Push `main`, publish the annotated tag and Pre-release, verify the downloaded assets and rerun packaged smoke checks.
  8. [ ] Record remote evidence in a post-release documentation commit without moving the release tag.

## Later roadmap

1. [x] Optional age-based cleanup of failed/cancelled-task media: implemented locally.
2. ~~On-demand real checks for YouTube, Bilibili, and Douyin.~~ Completed as a one-off real validation milestone (see PROJECT_STATUS.md): YouTube platform subtitles, Bilibili audio download plus local ASR, and Douyin login through local ASR all passed. Automated tests remain the durable evidence; live results are point-in-time and do not guarantee ongoing platform availability.
3. [x] Xiaoe-tech research: official permitted download/export followed by existing local import; no URL downloader. Other requested platforms and shop-authorized merchant OpenAPI remain separate future work.
4. [x] Feishu native cloud image blocks: implemented as an online docx with inline image blocks and verified once against a real user-authorized test folder. Deferred: Wiki/docx import, overwrite or sync, permission management, automatic login.
5. [x] Subtitle-file import and SRT export: ported from upstream `662f56b`. `.srt` / `.vtt` imports become an already-timed transcript without download or ASR; any transcript exports standard SubRip from backend segments.
6. [x] Windows static-asset MIME pinning: ported from upstream `55166ad`. `.js` / `.mjs` / `.css` / `.html` types are fixed in code (including 304 revalidation), independent of the OS registry; cache and security headers are unchanged.
7. [x] Model context-window diagnosis: ported from upstream `68117a6`. Context-window markers are recognized before generic status codes, with actionable local-model guidance; `Too many tokens per minute` remains a rate-limit error.
8. [x] Long-note resilience: adopted the capabilities of upstream `7642479` + `8e02db3` (dynamic note budgets, short-line merging before chunking, chunk/merge/tail-patch degradation, evidence-based thinking reserve, accurate advice for uncontrollable thinking). Explicitly excluded `23b057f`; no speed/quality UI or request-protocol change was introduced.
9. [x] Packaged ASR worker: frozen builds run faster-whisper/paraformer in a child (protocol v1), source checkouts stay in-process; fake-worker tests cover crash, protocol errors, cancellation and exact-child cleanup. A real Windows frozen-build smoke passed with a SAPI-generated local WAV and the cached Whisper `small` model, producing JSON, Markdown, SRT and a central transcript archive without a media/model download or LLM call.
10. [x] Title/page-aware artifact names: ported from upstream `7236040`. Download/archive/SRT names include B站 page selection and a transcript suffix via `download_stem`; request `bilibili_pages` is preserved and realized metadata is stored separately.
11. [x] Transcript-only central archive and completion-page lead: ported from upstream `6d05b08` + `fedb621`. Successful transcripts archive to `workspace/transcripts` with the Gate 5 stem; archive failure keeps the task completed; the completion notice leads with the archived file and keeps the task directory as secondary.
12. [x] LLM test-connection key-read/initializer boundary: selected part of upstream `088b665` (no diagnostics, proxy bypass, DNS probes or frontend). Non-RuntimeError key resolution failures return fixed redacted 200 JSON; initializer errors are utf8_safe plus secret and path redacted.
13. [x] First successor Windows prerelease: version/update metadata targets `Eternal-HAC/Video2Knowledge-next`; PyInstaller is pinned to 6.22.3; `VideoToNo-1.4.2-v2k.1-portable.exe` passed the authorized offline packaged-ASR smoke. The release gate itself made no real-provider claim; the separate post-release acceptance is recorded below.
14. [x] Limited real note chain: the downloaded GitHub Release EXE processed a three-segment synthetic SRT with DeepSeek `deepseek-flash`, the general template, `faithful` style and an isolated custom destination. It produced one Markdown file with parseable Frontmatter and all coverage anchors, without saving the page-session Key.
15. [x] Independent brand and Knowledge Studio UI: product metadata centralized in `product_info.py` (Video2Knowledge, independent `1.0.0-beta.N` line); legacy service id, `VIDEOTONOTES_*` env aliases, browser preferences, MCP tool names and Skill discovery kept compatible; workspace redesigned per `DESIGN.md` with an original script-generated logo. Local UI automation and visual acceptance have passed. This closes the local implementation slice only — it is not release acceptance.

## Completed release task

- [x] `v1.0.0-beta.2` template and export discoverability release:
  1. [x] Add Knowledge Essentials and Study Lecture as safe built-in templates without a second LLM call.
  2. [x] Surface built-in/custom template cards, default/custom/Obsidian destinations, optional Feishu publication and explicit export labels in the main workflow.
  3. [x] Finish 1440/1024/390 light/dark/system and keyboard acceptance; regenerate the three synthetic README screenshots without page-level horizontal scrolling.
  4. [x] Complete suite passed with `706 passed, 3 skipped`; built `Video2Knowledge-1.0.0-beta.2-portable.exe` and passed packaged offline-ASR plus new/legacy environment compatibility smoke with the cached Whisper `small` model.
  5. [x] Pushed `main`, published the annotated tag and Pre-release, verified the downloaded EXE against GitHub's digest and `SHA256SUMS.txt`, and passed the downloaded-asset offline-ASR smoke. Final evidence is recorded in the separate documentation commit after the release tag.

- [x] `v1.0.0-beta.1` remote release closeout:
  1. [x] Run the complete `pytest` suite on the intended release branch and repeat it after the build-script fix.
  2. [x] Build `Video2Knowledge-1.0.0-beta.1-portable.exe` with the existing PyInstaller 6.22.3.
  3. [x] Pass packaged offline-ASR acceptance with cached Whisper `small`, plus legacy environment-variable and static-resource smoke checks.
  4. [x] Generate byte-stable Knowledge Studio README screenshots and a candidate `SHA256SUMS.txt` (`9c2cda4e...aa50`).
  5. [x] Push `main`, create the annotated tag and GitHub Pre-release, verify the downloaded EXE against `SHA256SUMS.txt` and GitHub's digest, rerun packaged offline ASR, and read back the approved Description/Topics.

Other future directions still require a separate product decision: proxy/diagnostics policy (no automatic bypass), headless agent operation, and new platform/Feishu extensions. No further automatic coding gate is queued.
