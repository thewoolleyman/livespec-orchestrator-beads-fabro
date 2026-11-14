---
proposal: impl-dispatch-launches-its-dispatcher.md
decision: modify
revised_at: 2026-11-13T20:13:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Coordinator grade PASS WITH ONE FIX on livespec-orchestrator-beads-fabro#5191 (legacy-coordinator-agent, 2026-11-13); the fix is applied in 9e0d4e022. VPS overload prevention, priority 1. Per-run dispatcher loops were an uncapped memory consumer in the 2026-11-13 dev VPS exhaustion (13 loops, up to 2.53G peak each). livespec-dev-tooling#4543 provisions factory-dispatch.slice and the per-loop bound; this clause makes the single fleet launch path, drive impl:, use them, and leaves a host without them unchanged. It unblocks bd-ib-szbxu7, which was refused at the spec tier (unratified-topic). No design record is contradicted.

## Modifications

1. The proposal's three plain H2 scenarios (371, 372, 373) are folded into ONE `## Scenario 371 — An impl dispatch launches its loop inside the host's dispatch memory slice when the host provides one`. It holds a fenced gherkin Feature with three Scenarios (scoped launch, unscoped when a condition is missing, fallback when the scoped launch fails), matching the repository's scenario format, so one heading-coverage row is owed instead of three. 2. On the independent reviewer's blocker, the undefined `drive record` is replaced by a named surface. Every impl: launch appends one dispatch-journal record with top-level stage `dispatch-launch-scope`, carrying work_item_id, launch (scoped|unscoped), scope_unit for a scoped launch, and detail for a fallback; the drive JSON output carries the same launch value. The stage is neither a hold nor a retiring stage of the journal-hold paragraph, so no hold's currency changes. 3. On the reviewer's note, the fallback applies only when the scoped launch failed before any loop process started, and it MUST NOT start a second loop; the gherkin fallback case says exactly one loop starts. 4. The heading-coverage TODO row names the integration tier and work_item bd-ib-szbxu7; the debt register is regenerated (one added row). Independent read-only sonnet re-review of these exact bytes: NO BLOCKERS at 2026-11-13T20:07:02Z.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T20:07:02Z
verdict: NO BLOCKERS
proposal_stem: impl-dispatch-launches-its-dispatcher
content_digest: a090c63408c77355be072ed9b355ba158fc7e121e9485756ac223bdbf6cf99a0
