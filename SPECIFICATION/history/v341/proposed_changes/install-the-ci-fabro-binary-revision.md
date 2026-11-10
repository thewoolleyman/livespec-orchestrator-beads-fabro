---
proposal: install-the-ci-fabro-binary.md
decision: accept
revised_at: 2026-11-10T09:56:22Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept. CI's factory-graph gate (check-fabro-graph-validity) validates with the pinned upstream fabro-sh/fabro release, outside the factory's carrier-build scope, and its installer now installs the static Linux asset for the runner's own architecture (x86_64 or aarch64), verified against the sha256 that release publishes, refusing any other architecture by name and installing nothing. The pinned release already publishes the aarch64 asset and its checksum, so no build is needed, and this lifts the repository's exclusion from the arm64 CI overflow. The clause joins Fabro runtime constraints as its last bullet and Scenario 340 states the behaviour, taking the next free number as the proposal directs. Per the revise co-edit discipline the new heading carries a spec-first TODO coverage row and a matching debt-register row, both owned by work item bd-ib-jjmywv. Its scenarios.md carries the merge-hold edits of the decision before it, because resulting files apply in decision order.

## Resulting Changes

- constraints.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T09:55:57Z
verdict: NO BLOCKERS
proposal_stem: install-the-ci-fabro-binary
content_digest: 1aa04a21989292a3d35f2560402ac0f701bc8b88f38c37b67cc21e52075461a2
