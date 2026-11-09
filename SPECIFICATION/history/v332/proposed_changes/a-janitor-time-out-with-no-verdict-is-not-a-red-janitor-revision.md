---
proposal: a-janitor-time-out-with-no-verdict-is-not-a-red-janitor.md
decision: accept
revised_at: 2026-11-09T15:26:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:sandbox-commit-gate-ceiling
---

## Decision and Rationale

Accepted as proposed. legacy-coordinator-agent decided the shape under R301 (2026-11-09 about 14:2xZ): a janitor visit that its node timeout ends with no check-suite verdict is not a red janitor for Scenario 138 and the contracts.md red-janitor sentence; it gets exactly one further janitor visit on the same head with no agent turn between; a second no-verdict visit ends at needs_human with the tree preserved and a cause naming both time-outs; a janitor with a failing verdict still enters fix unchanged. The proposal's one refinement under that ruling, that the re-janitor spends no fix-loop round, keeps a transient load spike from shortening the budget a real failure needs. Measured on four 2026-11-09 runs (fkd4ve 01M6ZFGPXDAE, cbcdrp 01M6ZSE3750Z, ch44wn 01M6ZXG272V3, hap62u 01M6ZY2GDWFP): each janitor timed out at 4800 s, then a fix turn with no failed target re-ran the full suite and was cut at 3600 s. The independent read-only sonnet review found no blockers. Its non-blocking notes go to the implementation carrier bd-ib-kclvlo: the janitor node's visit limit (max_visits) must admit the extra re-janitor visit, as Refresh-repair accounting states for fix; 'fix-loop round' reads as the existing 'fix round'; a time-out during the pre-aggregate refresh also counts as no verdict, which is intended. No `## ` heading changes, so tests/heading-coverage.json needs no co-edit. Carrier: bd-ib-kclvlo (plan bd-ib-qy5wol).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T15:25:50Z
verdict: NO BLOCKERS
proposal_stem: a-janitor-time-out-with-no-verdict-is-not-a-red-janitor
content_digest: bbc50fa112df8e3b0bfe0ef429bca6086b4c59f7fe689134581eef433c53b304
