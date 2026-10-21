# Video2Knowledge Product Baseline

## Brand and version line

- The user-visible product is **Video2Knowledge**; `VideoToNo` appears only in protocol-compatibility positions (for example the `/api/health` `service` field) and in attribution.
- From `v1.0.0-beta.1` the project uses an **independent version line**: `1.0.0-beta.N` → `1.0.0-rc.N` → `1.0.0`. The transitional `v1.4.2-v2k.N` line always sorts below the independent line in update checks. `product_info.py` is the single source for the product name, version, environment-variable prefixes, and release metadata consumed by the launcher, backend, build script, and release workflow.
- The Windows portable artifact for this line is `Video2Knowledge-<version>-portable.exe`; `v1.0.0-beta.1` has passed its local and downloaded-release acceptance gates and is published as a GitHub Pre-release.
- `v1.0.0-beta.2` keeps the same task/API contracts while making templates, local Markdown destinations, optional Feishu publication, and export formats visible in the task flow. Its release evidence is recorded separately from the already accepted beta.1 artifact.

## Compatibility boundaries of the rebrand

The rename must not break existing integrations:

- **Service identity**: `/api/health` keeps returning the legacy `service: "VideoToNo"` alongside `product: "Video2Knowledge"` and `api_compat: 1`. The compat level is additive-only; it bumps only when an existing field's semantics break.
- **API**: endpoint paths, request shapes, and task manifest format are unchanged by the rebrand.
- **Environment variables**: new `VIDEO2KNOWLEDGE_*` names take priority; legacy `VIDEOTONOTES_*` names keep working (`WORKSPACE`, `BACKEND_URL`, `REJECTED_LLM_PARAMS`, `LLM_API_KEY`, and so on).
- **Browser preferences**: non-sensitive localStorage preferences move to `v2k_prefs`. On first launch the app copies legacy `vtn_prefs`, preserves that old key for rollback, and never migrates API keys into localStorage.
- **MCP / Agent Skill**: discovery recognizes both the new `product` field and the legacy `service` value; tool names, the SSE endpoint, and the Skill directory layout are unchanged.
- **Workspace**: the `workspace/` directory layout, credential files, and model cache locations are unchanged.

## Knowledge Studio UI principles

The redesigned workspace ("Knowledge Studio") follows [DESIGN.md](DESIGN.md) as the single design baseline: task-first flow (output type → template → destination → source → start), low-frequency model and integration settings collected into a slide-out panel, state conveyed by text and badges rather than color alone, local-trust copy that states where data goes, and restrained motion honoring `prefers-reduced-motion`. Six built-in templates and saved custom templates are visible before submission. Local Markdown always remains the primary artifact; Feishu is an opt-in additional publication. The brand mark is an original geometric logo generated reproducibly by repository scripts (`scripts/make_brand_assets.py`); no third-party icon sets or upstream-derived artwork are used. The rebrand does not change backend APIs, task semantics, or the element-ID contract guarded by `tests/test_frontend_hygiene.py`.

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

1. Four read-only built-in templates are available: General Structured Notes (default), Cornell Review Notes, Tutorial / How-to Notes, and Interview / Viewpoint Analysis.
2. A user can clone a built-in template, then create, edit, and delete custom templates stored by the backend.
3. A template contains a name, description, LLM organization instructions, and a deterministic Markdown layout.
4. Layouts accept only a documented placeholder allowlist and must contain exactly one `{{content}}` placeholder. They never execute Jinja, Python, JavaScript, shell, or other user code.
5. `summary_style` remains an independent generation-depth strategy. `note_template` controls organization and final layout.
6. Each generation produces one Markdown file. Changing the template reuses an existing transcript, calls the LLM again, creates a collision-safe new note, and preserves previous notes.
7. Local Markdown includes YAML Frontmatter for available title, source URL, platform, author, creation time, template, and transcript source. Missing values are omitted.
8. Each task records the selected template ID, version, and an immutable snapshot so later template edits do not rewrite task history.
9. LLM failure leaves the timestamped transcript available.
10. Focused tests and the complete `pytest` suite pass before one local milestone commit is created.

## Upstream capability and successor gaps

| Area | Current evidence | Successor status |
| --- | --- | --- |
| Subtitle preference and ASR fallback | `prefer_subtitles` defaults to true; platform subtitles and automatic captions are checked before local ASR; regression tests cover subtitle reuse and ASR paths. A frozen Windows build completed an offline local-media smoke through its isolated ASR child with the cached Whisper `small` model. A separately authorized short synthetic-SRT smoke also completed through DeepSeek `deepseek-flash` without entering download or ASR. | Source and packaged offline transcription paths are accepted for the first successor prerelease. The real-provider evidence is intentionally limited to one short DeepSeek note task and is not a general Provider guarantee. |
| Markdown and transcript artifacts | Upstream writes UTF-8 `notes.md`, `transcript.md`, and `transcript.json`, and exposes completed transcripts through API/MCP paths. | Upstream capability present. |
| Selected directory or Vault output | Note tasks accept an optional absolute final-note destination. Custom destinations receive only the final Markdown and referenced task attachments; leaving it empty preserves `workspace/notes`. Collision, Unicode-path, invalid-path, and credential-boundary tests cover the contract. | Successor customization implemented. A downloaded release asset completed the real chain from imported SRT through DeepSeek to one Markdown file in an isolated custom destination. |
| Personal Markdown template | Four immutable built-ins, backend-stored custom templates, safe deterministic layouts, task snapshots, transcript-reuse regeneration, and frontend management are covered by code and tests. | Successor customization implemented locally. |
| Credential safety | API keys use masked/encrypted local storage on Windows, are bound to endpoints, and errors are scrubbed before persistence. Temporary platform cookie files are deleted. | Covered by code and tests. In the limited DeepSeek smoke, a page-session Key was not saved, `llm_keys.json` was not created, and no key-shaped value or authorization field appeared in the task files, output note, or app log. |
| Media retention | Successful notes retain immediate owned-media cleanup. Failed/cancelled retry media is retained forever by default, with optional 1/7/30-day cleanup. Manifests, notes, transcripts, frames, unknown files and active reuse sources are preserved; uncertain deletion produces warnings. | Success-only cleanup and opt-in age cleanup implemented locally. |
| Same-name output | Default and custom destinations use exclusive creation, safe Unicode filenames, and `-2`, `-3`, and later suffixes. Controlled race tests cover notes and attachment directories without overwriting foreign content. | Covered by automated tests. |
| LLM failure preserves transcript | Transcript artifacts are written before the LLM step and remain readable for failed note tasks. | Covered by code and tests. |
| Unicode and Frontmatter | UTF-8 reads/writes, Chinese filenames, Unicode destination paths, URI-encoded attachment links, deterministic YAML Frontmatter, and YAML-sensitive Unicode escaping are tested. | Covered by automated tests. |
| Brand and workspace UI | Product metadata is centralized in `product_info.py`; the frontend implements the Knowledge Studio layout per `DESIGN.md` with the element-ID contract guarded by `tests/test_frontend_hygiene.py`; brand assets are generated reproducibly by repository scripts. | Brand baseline released in `v1.0.0-beta.1`; beta.2 adds task-flow discoverability for six templates, three local destination modes, optional Feishu publication and explicit export actions. |

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
12. `v1.0.0-beta.2` template and export discoverability: **implemented locally, release acceptance pending**. Six built-in templates and custom templates are selectable on the main page; default/custom/Obsidian Markdown destinations are explicit; Feishu remains an opt-in additional publication; export labels identify Markdown, SRT, HTML, JSON, plain text and PNG without changing request fields or task formats.

## Non-goals for the current phase

- Xiaoe-tech URL downloading or merchant OpenAPI integration;
- Feishu Wiki/docx import, overwrite or sync, permission management, and automatic login;
- automated cookie management;
- bypassing platform login, verification, or access controls;
- a complete Obsidian plugin;
- custom Agent or MCP product work;
- a new downloader or ASR framework;
- a large frontend or backend architecture rewrite;
- migration of the old Video2Knowledge Provider/Pipeline architecture;
- cleanup or archival of the old repository.
