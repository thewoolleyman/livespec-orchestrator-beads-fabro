---
proposal: the-preserved-tree-comment-names-the-needs-human-ref.md
decision: accept
revised_at: 2026-11-11T12:23:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratify as written. The livespec-preserved-tree comment named only work-in-progress refs, so a run that ended at needs_human with its tree safely on a needs-human ref read 'the run has no work-in-progress ref'. On 2026-11-11 that line was read as lost work repeatedly: bd-ib-6szexa, livespec-dev-tooling-ie7fas and overseer-fbt5hu (the last was regroomed while its preserve held +360 lines), plus two more misreadings by sandbox-commit-gate-ceiling and one by the dispatcher, per legacy-coordinator-agent. Every one of those refs was measured on origin with a non-empty merge-base diff. Naming the needs-human or failed-checkpoint preservation ref with its tip and diff size removes the trap. The empty-diff and unmeasurable-diff cases make an empty or unknown preserve explicit rather than silent. The recovery release rule that reads this comment keys on a work-in-progress ref or an undetermined preservation, and is unchanged. Decided by the factory-run-work-preservation plan seat under delegated decision mode, in the revise slot legacy-coordinator-agent assigned.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T12:17:39Z
verdict: NO BLOCKERS
proposal_stem: the-preserved-tree-comment-names-the-needs-human-ref
content_digest: 8b326117e1ea485f964bf11d91adcb8ec7ccd8f01be28a326f70adbfe735b481
