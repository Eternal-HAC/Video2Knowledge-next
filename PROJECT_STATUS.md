# Project Status

Updated: 2026-10-04

## Current stage

`gap verification before customization`

The successor Fork is established and synchronized. The current task is to verify which product requirements are already satisfied by VideoToNo and customize only demonstrated gaps.

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

The following items remain open or partial:

- dedicated output to a selected normal directory or Obsidian Vault: partial;
- personal Markdown templates: gap;
- default cleanup of downloaded, uploaded, and intermediate media: partial;
- YAML Frontmatter behavior: UNKNOWN;
- successor-specific end-to-end acceptance of all six required chains: pending.

## Isolated evaluation evidence

Earlier isolated evaluation covered these real flows:

- YouTube platform subtitles;
- YouTube forced ASR;
- local-media ASR;
- public Bilibili input;
- DeepSeek-generated Markdown.

This is evaluation evidence for the adopted upstream baseline. It does not count as final acceptance of the successor, its destination behavior, personal templates, cleanup policy, or credential boundary.

## Current constraints

- No functionality changes have started after the Fork baseline.
- Real providers, media downloads, model downloads, platform login, cookies, and credentials require explicit user approval.
- Publication of each local commit requires separate user approval.
