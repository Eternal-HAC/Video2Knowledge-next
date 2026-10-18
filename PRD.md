# Video2Knowledge Product Baseline

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
| Subtitle preference and ASR fallback | `prefer_subtitles` defaults to true; platform subtitles and automatic captions are checked before local ASR; regression tests cover subtitle reuse and ASR paths. | Upstream capability present. Final successor end-to-end acceptance is pending. |
| Markdown and transcript artifacts | Upstream writes UTF-8 `notes.md`, `transcript.md`, and `transcript.json`, and exposes completed transcripts through API/MCP paths. | Upstream capability present. |
| Selected directory or Vault output | Note tasks accept an optional absolute final-note destination. Custom destinations receive only the final Markdown and referenced task attachments; leaving it empty preserves `workspace/notes`. Collision, Unicode-path, invalid-path, and credential-boundary tests cover the contract. | Successor customization implemented. Final real-chain acceptance is pending. |
| Personal Markdown template | Four immutable built-ins, backend-stored custom templates, safe deterministic layouts, task snapshots, transcript-reuse regeneration, and frontend management are covered by code and tests. | Successor customization implemented locally. |
| Credential safety | API keys use masked/encrypted local storage on Windows, are bound to endpoints, and errors are scrubbed before persistence. Temporary platform cookie files are deleted. | Covered by code and tests; real-provider validation remains separately authorized. |
| Media retention | Successful notes retain immediate owned-media cleanup. Failed/cancelled retry media is retained forever by default, with optional 1/7/30-day cleanup. Manifests, notes, transcripts, frames, unknown files and active reuse sources are preserved; uncertain deletion produces warnings. | Success-only cleanup and opt-in age cleanup implemented locally. |
| Same-name output | Default and custom destinations use exclusive creation, safe Unicode filenames, and `-2`, `-3`, and later suffixes. Controlled race tests cover notes and attachment directories without overwriting foreign content. | Covered by automated tests. |
| LLM failure preserves transcript | Transcript artifacts are written before the LLM step and remain readable for failed note tasks. | Covered by code and tests. |
| Unicode and Frontmatter | UTF-8 reads/writes, Chinese filenames, Unicode destination paths, URI-encoded attachment links, deterministic YAML Frontmatter, and YAML-sensitive Unicode escaping are tested. | Covered by automated tests. |

## Ordered successor roadmap

1. Fork baseline, attribution, and configurable Markdown destination: complete locally.
2. Note template system: complete locally.
3. Media retention policy: complete locally, including optional 1/7/30-day failed/cancelled media cleanup.
4. Obsidian detection and Vault experience, followed by opt-in Feishu publication: complete locally. Feishu publication now creates an online docx with native in-body image blocks for referenced screenshots; no cloud Markdown file or ZIP is created.
5. One-off real validation for YouTube, Bilibili, and Douyin: complete; this does not guarantee permanent availability.
6. Xiaoe-tech research and local import guidance: complete. Other platform or merchant integrations require separate authorization.
7. Subtitle-file import and SRT export: ported from upstream `662f56b`; complete locally.

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
