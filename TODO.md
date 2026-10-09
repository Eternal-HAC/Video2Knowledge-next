# Current TODO

This file holds only the active gap-verification queue. For every item: close it when upstream already satisfies the requirement; add a test when evidence is insufficient; change implementation only after the test demonstrates a gap.

1. [x] Selected directory or Obsidian Vault output
   - Closed by the optional absolute-path destination setting, preflight validation, final-note-only export, referenced-attachment copying, relative-link rewriting, and collision tests.
   - Leaving the setting empty keeps the existing `workspace/notes` behavior.
2. [x] Personal Markdown template
   - Closed locally by four read-only built-ins, backend-stored custom templates, safe deterministic layouts, immutable task snapshots, YAML Frontmatter, and transcript-reuse regeneration.
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

## Later roadmap

1. [x] Optional age-based cleanup of failed/cancelled-task media: implemented locally.
2. ~~On-demand real checks for YouTube, Bilibili, and Douyin.~~ Completed as a one-off real validation milestone (see PROJECT_STATUS.md): YouTube platform subtitles, Bilibili audio download plus local ASR, and Douyin login through local ASR all passed. Automated tests remain the durable evidence; live results are point-in-time and do not guarantee ongoing platform availability.
3. [x] Xiaoe-tech research: official permitted download/export followed by existing local import; no URL downloader. Other requested platforms and shop-authorized merchant OpenAPI remain separate future work.
4. Deferred Feishu/Obsidian work: native cloud image blocks, Wiki/docx import, overwrite or sync, permission management, automatic login.

## Next single execution task

After separate authorization, review feasibility and define acceptance criteria for native Feishu cloud image blocks, starting from the existing lark-cli publication path and mature capabilities. Limit that task to a read-only design review; implementation, login and cloud writes each require their applicable explicit authorization. Current Markdown plus optional ZIP publication remains available.
