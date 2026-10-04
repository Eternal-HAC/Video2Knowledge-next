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
5. [ ] Media and intermediate-file retention
   - Current evidence: large uploads may discard the original video, while ordinary task media is retained for reuse until task deletion.
   - Scheduled after the template milestone. Successful note tasks keep Markdown, transcript, and referenced screenshots but delete source media and extracted audio; failed tasks retain retry material.
6. [x] Same-name output protection
   - Closed for both destinations by exclusive-create collision and controlled-race tests. Custom attachment directories are tied to each final note stem; failure cleanup uses verified file identity so existing or replacement foreign files are not overwritten or removed.
7. [x] Transcript availability after LLM failure
   - Closed by transcript persistence and failed-task retrieval tests.
8. [x] YAML Frontmatter
   - Unicode UTF-8 output, Chinese filenames, and Unicode custom destination paths are covered.
   - Closed by deterministic YAML Frontmatter that omits unavailable values and safely escapes YAML-sensitive Unicode code points.

## Later roadmap

1. Media retention and optional age-based cleanup.
2. Obsidian detection and Vault experience; opt-in Feishu CLI Markdown upload plus a screenshot attachment ZIP.
3. On-demand real checks for YouTube, Bilibili, and Douyin.
4. Separate research and adaptation for Xiaoe-tech and other requested platforms.

## Next single execution task

Inspect the existing media and intermediate-file lifecycle, then add focused tests that demonstrate the gap against the approved retention policy. Do not change cleanup behavior until those tests establish the gap, and do not start Feishu or new-platform work in this milestone.
