# Video2Knowledge Product Baseline

## User goal

Turn saved YouTube videos, Bilibili videos, and local media into Markdown that can be imported into Obsidian or another knowledge tool. The successor builds on VideoToNo and should add only the differences needed for this workflow.

## Main flow

```text
YouTube / Bilibili / local media
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
- a local audio or video file;
- optional provider configuration for note generation;
- an optional personal Markdown template;
- a selected normal directory or Obsidian Vault destination.

Outputs:

- a UTF-8 Markdown note with traceable source information;
- a timestamped transcript that remains available when note generation fails;
- optional local image attachments when screenshots are requested;
- no silently overwritten note and no unnecessary retained media by default.

## Required acceptance paths

1. YouTube with subtitles → Markdown.
2. YouTube without subtitles → local ASR → Markdown.
3. Public Bilibili URL → Markdown.
4. Local media → local ASR → Markdown.
5. DeepSeek → personal-template Markdown.
6. LLM failure → transcript remains available.

All six paths must also confirm the configured destination, collision-safe naming, credential safety, expected media cleanup, Unicode paths, and valid metadata output.

## Upstream capability and successor gaps

| Area | Current evidence | Successor status |
| --- | --- | --- |
| Subtitle preference and ASR fallback | `prefer_subtitles` defaults to true; platform subtitles and automatic captions are checked before local ASR; regression tests cover subtitle reuse and ASR paths. | Upstream capability present. Final successor end-to-end acceptance is pending. |
| Markdown and transcript artifacts | Upstream writes UTF-8 `notes.md`, `transcript.md`, and `transcript.json`, and exposes completed transcripts through API/MCP paths. | Upstream capability present. |
| Selected directory or Vault output | Note tasks accept an optional absolute final-note destination. Custom destinations receive only the final Markdown and referenced task attachments; leaving it empty preserves `workspace/notes`. Collision, Unicode-path, invalid-path, and credential-boundary tests cover the contract. | Successor customization implemented. Final real-chain acceptance is pending. |
| Personal Markdown template | The backend exposes three built-in summary styles and deterministic metadata formatting. No personal-template field or renderer is present in the inspected backend contract. | Gap. |
| Credential safety | API keys use masked/encrypted local storage on Windows, are bound to endpoints, and errors are scrubbed before persistence. Temporary platform cookie files are deleted. | Covered by code and tests; real-provider validation remains separately authorized. |
| Media retention | Large uploaded video may be replaced by extracted audio, and deleting a task removes its directory. Downloaded or uploaded task media otherwise remains available for reuse. | Partial. The desired default cleanup policy is not established. |
| Same-name output | Default and custom destinations use exclusive creation, safe Unicode filenames, and `-2`, `-3`, and later suffixes. Controlled race tests cover notes and attachment directories without overwriting foreign content. | Covered by automated tests. |
| LLM failure preserves transcript | Transcript artifacts are written before the LLM step and remain readable for failed note tasks. | Covered by code and tests. |
| Unicode and Frontmatter | UTF-8 reads/writes, Chinese filenames, Unicode destination paths, and URI-encoded attachment links are tested. Current note metadata is Markdown text, not verified YAML Frontmatter. | Unicode covered; Frontmatter is UNKNOWN and requires a product decision plus tests. |

## Non-goals for the current phase

- Xiaoe-tech support;
- automated cookie management;
- bypassing platform login, verification, or access controls;
- a complete Obsidian plugin;
- custom Agent or MCP product work;
- a new downloader or ASR framework;
- a large frontend or backend architecture rewrite;
- migration of the old Video2Knowledge Provider/Pipeline architecture;
- cleanup or archival of the old repository.
