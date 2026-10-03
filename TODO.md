# Current TODO

This file holds only the active gap-verification queue. For every item: close it when upstream already satisfies the requirement; add a test when evidence is insufficient; change implementation only after the test demonstrates a gap.

1. [x] Selected directory or Obsidian Vault output
   - Closed by the optional absolute-path destination setting, preflight validation, final-note-only export, referenced-attachment copying, relative-link rewriting, and collision tests.
   - Leaving the setting empty keeps the existing `workspace/notes` behavior.
2. [ ] Personal Markdown template
   - Current evidence: three built-in summary styles and deterministic metadata, with no inspected personal-template contract.
3. [x] Subtitle-first and local-ASR fallback
   - Closed for gap verification by current code and tests. Final real-chain acceptance remains pending.
4. [x] Credential safety
   - Closed for gap verification by storage, masking, error-redaction, and temporary-cookie tests. Real-provider use remains authorization-gated.
5. [ ] Media and intermediate-file retention
   - Current evidence: large uploads may discard the original video, while ordinary task media is retained for reuse until task deletion.
6. [x] Same-name output protection
   - Closed for both destinations by exclusive-create collision and controlled-race tests. Custom attachment directories are tied to each final note stem; failure cleanup uses verified file identity so existing or replacement foreign files are not overwritten or removed.
7. [x] Transcript availability after LLM failure
   - Closed by transcript persistence and failed-task retrieval tests.
8. [ ] Unicode and Frontmatter
   - Unicode UTF-8 output, Chinese filenames, and Unicode custom destination paths are covered. YAML Frontmatter is UNKNOWN.

## Next single execution task

Verify the personal Markdown template gap and define its smallest evidence-backed contract. Do not begin implementation until a focused test demonstrates the gap.
