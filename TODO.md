# Current TODO

This file holds only the active gap-verification queue. For every item: close it when upstream already satisfies the requirement; add a test when evidence is insufficient; change implementation only after the test demonstrates a gap.

1. [ ] Selected directory or Obsidian Vault output
   - Current evidence: configurable workspace and `workspace/notes` archive only.
   - Needed: define a dedicated final-note destination that does not place task state or credentials in the Vault.
2. [ ] Personal Markdown template
   - Current evidence: three built-in summary styles and deterministic metadata, with no inspected personal-template contract.
3. [x] Subtitle-first and local-ASR fallback
   - Closed for gap verification by current code and tests. Final real-chain acceptance remains pending.
4. [x] Credential safety
   - Closed for gap verification by storage, masking, error-redaction, and temporary-cookie tests. Real-provider use remains authorization-gated.
5. [ ] Media and intermediate-file retention
   - Current evidence: large uploads may discard the original video, while ordinary task media is retained for reuse until task deletion.
6. [x] Same-name output protection
   - Closed for the current archive by collision-suffix tests. Reopen when a custom destination is implemented.
7. [x] Transcript availability after LLM failure
   - Closed by transcript persistence and failed-task retrieval tests.
8. [ ] Unicode and Frontmatter
   - Unicode UTF-8 output and Chinese filenames are covered. YAML Frontmatter is UNKNOWN.

## Next single execution task

Define the selected-directory/Vault output contract with focused failing tests, then implement the smallest destination setting that writes only final note artifacts to that destination, preserves collision-safe naming, and leaves task state and credentials in the workspace.
