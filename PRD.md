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
```

## MVP inputs and outputs

Inputs:

- a public YouTube URL;
- a public Bilibili URL;
- a public Douyin single-video URL or share link;
- a local audio or video file;
- optional provider configuration for note generation;
- an optional personal Markdown template;
- a selected normal directory or Obsidian Vault destination.

Outputs:

- a UTF-8 Markdown note with traceable source information;
- a timestamped transcript that remains available when note generation fails;
- optional local image attachments when screenshots are requested;
- no silently overwritten note and no unnecessary retained media by default.

## Platform support contract

- **Focused support:** YouTube, Bilibili, Douyin, and local media use the existing subtitle-first and local-ASR pipeline. Platform-specific behavior requires focused automated regression coverage and actionable errors. Known login, verification, membership, region, and upstream-interface limits must be documented.
- **Generic compatibility:** Other HTTP or HTTPS video URLs supported by the installed `yt-dlp` version may use the generic pipeline on a best-effort basis. They do not receive platform-specific guarantees.
- **Pending adaptation:** A platform that cannot use the generic pipeline is researched separately. Reuse a mature lawful implementation when available, then add the smallest platform-specific behavior and tests justified by demand.

Focused support does not promise that every public video remains reachable, does not require every platform to repeat global destination and Unicode tests, and does not require live network tests for every release. Real-media checks are used when first adapting a platform, investigating a breakage, or preparing a relevant release, subject to the repository's approval boundaries. The project never bypasses DRM, payment, login, verification, or other access controls.

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
| Media retention | Large uploaded video may be replaced by extracted audio, and deleting a task removes its directory. Downloaded or uploaded task media otherwise remains available for reuse. | Partial. The desired default cleanup policy is not established. |
| Same-name output | Default and custom destinations use exclusive creation, safe Unicode filenames, and `-2`, `-3`, and later suffixes. Controlled race tests cover notes and attachment directories without overwriting foreign content. | Covered by automated tests. |
| LLM failure preserves transcript | Transcript artifacts are written before the LLM step and remain readable for failed note tasks. | Covered by code and tests. |
| Unicode and Frontmatter | UTF-8 reads/writes, Chinese filenames, Unicode destination paths, URI-encoded attachment links, deterministic YAML Frontmatter, and YAML-sensitive Unicode escaping are tested. | Covered by automated tests. |

## Ordered successor roadmap

1. Fork baseline, attribution, and configurable Markdown destination: complete locally.
2. Note template system: complete locally.
3. Media retention policy: next milestone. First inspect and test the current lifecycle, then after successful note generation keep Markdown, transcript, and referenced screenshots while deleting downloaded or uploaded source media and extracted audio; retain retry material on failure, then add optional age-based cleanup later.
4. Obsidian detection and Vault experience, followed by opt-in Feishu CLI Markdown upload. A screenshot note also uploads a Markdown-plus-attachments ZIP until native cloud image blocks are implemented.
5. On-demand real checks and repairs for YouTube, Bilibili, and Douyin.
6. Separate research and adaptation for Xiaoe-tech and other requested platforms.

## Non-goals for the current phase

- Xiaoe-tech support;
- Feishu upload and Obsidian application detection;
- automatic media cleanup;
- automated cookie management;
- bypassing platform login, verification, or access controls;
- a complete Obsidian plugin;
- custom Agent or MCP product work;
- a new downloader or ASR framework;
- a large frontend or backend architecture rewrite;
- migration of the old Video2Knowledge Provider/Pipeline architecture;
- cleanup or archival of the old repository.
