# Project Status

Updated: 2026-10-04

## Current stage

`note template milestone complete locally`

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

The following items remain open or partial:

- default cleanup of downloaded, uploaded, and intermediate media: partial;
- Obsidian detection and Feishu upload: later milestone.

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

- full automated suite: `379 passed, 1 skipped`;
- JavaScript syntax check and `git diff --check`: passed;
- local browser smoke check: built-ins loaded; custom create and edit worked; clone form preserved all fields; transcript-only mode hid template controls and note mode restored them; a stale stored template ID fell back to the default after successful template loading;
- the temporary smoke-test template file was removed after verification;
- the independent architect review's four required fixes were applied. The separate code-reviewer lane did not return a verdict because its execution quota was interrupted, so there is no claim of two-lane formal review approval.

## Next milestone

Media and intermediate-file retention. The first task is read-only lifecycle inspection followed by focused tests. Implementation begins only after those tests demonstrate a gap against the approved success/failure retention policy.

## Current constraints

- Successor functionality changes so far are configurable final-note export and the safe note-template system.
- Custom destinations receive only the final Markdown and attachments referenced by that note. Task manifests, transcripts, downloaded media, model cache, and credentials remain in the workspace.
- Relative paths, ordinary files, and unavailable destinations are rejected before media processing with stable validation errors.
- Default and custom destinations use exclusive file creation. Controlled race and hard-link tests verify that concurrent foreign content is neither overwritten nor deleted.
- Failed-write cleanup compares the opened file's `fstat` identity with a non-following path `stat`; replaced paths and platforms without a reliable identity are retained instead of risking deletion of foreign content.
- Exported attachment link segments are URI-encoded and resolve back to Unicode and reserved-character filenames.
- The source-boundary implementation rejects attachments that resolve outside the task directory. Its Windows symbolic-link test is skipped when the host does not grant symbolic-link creation permission.
- Real providers, media downloads, model downloads, platform login, cookies, and credentials require explicit user approval.
- Publication of each local commit requires separate user approval.
