---
proposal: a-failed-fix-or-review.md
decision: accept
revised_at: 2026-11-11T13:00:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (sandbox-commit-gate-ceiling plan session)
---

## Decision and Rationale

Accepted as proposed. A failed open-Red Green amend currently leaves no observable cause: on 2026-11-11 the settles of runs 01M74ZKKRG5E (4zjjx4), 01M7533N2NHT (d2qm5d) and 01M750PMP0ND (n4kj4y) each recorded only {state: failed}, while the commit runner's composed cause died with the sandbox. The new contracts.md paragraph requires fix_commit_settle and review_fix_commit_settle to record a failed commit run's identity, exit status, failed targets (or 'failed targets: none'), hook ran/passed state, Git's refusal line and its final output lines, read from the run's own records. It also requires the open-Red re-entry brief to carry the failed targets and final lines. Scenario 179 gains two scenarios exercising both halves. The change adds to the commit-leg paragraph and is consistent with the full-recorded-output rule in 'An implement turn that ends incomplete does not succeed' and with the open-Red re-entry route in 'A fix turn grades each tree once'. It changes no commit-run state and no route. The two scenarios are appended at the end of Scenario 179's gherkin block, which is after 'A second commit does not start while one is running' as the proposal places them. No H2 heading changes, so tests/heading-coverage.json is unchanged. The independent reviewer's non-blocking notes (state explicitly that failed target names come from the full recorded output; add 'failed targets: none' and fix-stage scenarios; widen the first scenario's name) are left for a later proposal; none changes what this text requires. This gives bd-ib-wotls4 the clause and scenario its Definition of Done references.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T12:59:50Z
verdict: NO BLOCKERS
proposal_stem: a-failed-fix-or-review
content_digest: 7fa2abc04ae02039f1581e6a4f41abd8575a53e04970de65ce45662fc43396c7
