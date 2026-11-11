---
proposal: recapture-exhausted-holds.md
decision: modify
revised_at: 2026-11-11T09:04:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modify. Adopted: an item whose latest run ended at the non_converged terminal because its recapture bound was reached (LIVESPEC_RECAPTURE_EXHAUSTED) is released for recovery but routed held, never fresh and never resume or seeded automatically, with a recovery-held record naming the refusal recapture-exhausted, the preserved implementation and the explicit resume --item route at proof_capture with a proof rider. This closes a gap the ratified release clause left open: it releases every non_converged ending, yet the implementation excluded recapture-exhausted endings from the release (adadc0c42), so bd-ib-qshcwc's finished implementation on #4841 read route fresh and would have been re-implemented. A blind resume is refused because a proof that exhausted its recapture bound loops if re-captured without a rider (legacy-coordinator-agent ruling, 2026-11-11). Implemented by bd-ib-p6ammc, in plan publish-draft-green-work-loss (epic bd-ib-acrr56).

## Modifications

The marker is defined inline as the cause line the non_converged terminal records, and the recapture bound is cited at its own section (Self-contained plugin dispatch -> Definition-of-Done and Proof-of-Done stages); the no-rework-cap-budget and explicit resume --item precondition statements are folded into the inserted paragraph, which ends with a pointer to Scenarios 342 and 343; Scenario 343 gains a 'No preserved work observed' case; spec-first TODO coverage rows and sorted debt-register rows are added for both new headings, owned by bd-ib-p6ammc.

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
reviewed_at: 2026-11-11T09:04:18Z
verdict: NO BLOCKERS
proposal_stem: recapture-exhausted-holds
content_digest: 591c8b9d39b4383d971f418ab82fa7878cb9fccb9268dabae7e0540d5326ae64
