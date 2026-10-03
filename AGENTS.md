# AGENTS.md

## Project identity

This repository is the Video2Knowledge successor Fork, derived from VideoToNo `v1.4.2` at commit `0b1df7fe6db3035f94603d58b6f6ab0028083c0f`. Preserve the upstream Git history, MIT License, copyright notice, and attribution in `UPSTREAM.md`.

## Development principles

1. Inspect the current upstream-derived implementation and tests before proposing a change.
2. Reuse an upstream capability when it already meets the requirement.
3. Add or strengthen a test when evidence is missing.
4. Change implementation only after a relevant test demonstrates the gap.
5. Keep successor differences small, reviewable, and independently verifiable.
6. Do not migrate the old Video2Knowledge Provider/Pipeline architecture.
7. Do not reimplement download, ASR, task management, or other mature upstream subsystems without evidence that the existing subsystem cannot meet the requirement.

## Lightweight workflow

`Inspect → Reuse → Test → Minimal Change → Verify → Local Commit → User-approved Push`

- Inspect code, tests, Git state, and the relevant project documents.
- Reuse current behavior when it satisfies the acceptance criteria.
- Run the smallest relevant test first, followed by the required regression suite.
- Keep each local commit focused on one verified slice.
- Push, tag, release, or create a PR only after explicit user approval.

## Safety and authorization

Explicit user approval is required before:

- installing or upgrading dependencies;
- contacting a real LLM provider or using an API credential;
- downloading media or ASR models;
- logging in to a platform or using cookies or saved credentials;
- pushing commits, creating or updating tags, publishing releases, or creating PRs.

Never place credentials in Git, logs, generated Markdown, task manifests, tests, or project documents. Do not start unrelated feature work while completing a bounded task.
