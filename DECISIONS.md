# Decisions

## 2026-10-04: Adopt VideoToNo as the successor foundation

Decision: Develop Video2Knowledge successor as a Fork of VideoToNo `v1.4.2` while preserving upstream history and MIT attribution.

Reason: VideoToNo already provides the download, subtitle, ASR, task, UI, LLM, and Markdown foundation required for the product goal.

Alternatives considered: Continue the independent rewrite; copy selected upstream files into the old repository.

Impact: Successor work starts from verified upstream behavior and carries only focused product differences.

Review condition: Revisit only if a required acceptance path cannot be achieved through a bounded change to the Fork.

## 2026-10-04: Migrate requirements and tests selectively

Decision: Reuse selected requirements, safety rules, and regression tests from the old Video2Knowledge when they remain relevant. Do not migrate its Provider/Pipeline architecture.

Reason: Proven requirements can prevent regressions, while moving the old architecture would duplicate mature upstream subsystems and increase maintenance cost.

Alternatives considered: Port the complete old architecture; ignore all previous work.

Impact: Each migrated item needs a current gap, a narrow acceptance criterion, and an upstream-compatible test.

Review condition: Revisit when a legacy test encodes a product requirement that cannot be expressed against the Fork without architectural change.

## 2026-10-04: Keep a minimal project document set

Decision: Maintain `AGENTS.md`, `PRD.md`, `PROJECT_STATUS.md`, `TODO.md`, and `DECISIONS.md` as the initial successor documentation set. Add another document only when a concrete maintenance need appears.

Reason: The project needs durable product state and decision boundaries without recreating the old repository's documentation burden.

Alternatives considered: Copy the old documentation tree; create roadmap, architecture, program-map, snapshot, and changelog files immediately.

Impact: Current work, product scope, status, and long-term decisions each have one clear home.

Review condition: Add a document only when existing files can no longer hold the required information without becoming ambiguous or difficult to maintain.

## 2026-10-04: Separate final-note export from task workspace

Decision: Add an optional request-level absolute note destination. When configured, export only the final Markdown and attachments referenced by that note. Keep manifests, transcripts, downloaded media, model caches, and credentials in the task workspace. Leave the setting empty to retain the upstream `workspace/notes` behavior.

Reason: A normal directory or Obsidian Vault needs portable final artifacts without receiving runtime state or sensitive files. Preserving the empty-setting path keeps upstream behavior compatible.

Alternatives considered: Move the entire task directory into the Vault; redefine the global workspace root; add a separate export subsystem or Obsidian plugin.

Impact: The frontend stores the optional path as a non-sensitive local preference. The backend validates it before media processing, uses exclusive collision-safe creation, copies only resolved in-task attachments, and reports custom-export failures instead of silently falling back.

Review condition: Revisit if personal templates, cleanup policy, or a future Obsidian integration requires a different artifact layout or persistent destination model.
