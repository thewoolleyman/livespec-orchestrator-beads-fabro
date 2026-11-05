---
proposal: file-a-ledger-breakage-item.md
decision: modify
revised_at: 2026-11-05T03:33:35Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:ci-runtime-and-cost
---

## Decision and Rationale

Decided in delegated mode by claude:ci-runtime-and-cost. legacy-coordinator-agent pre-ruled ACCEPT of this proposal under ruling R301 on 2026-11-03 at about 06:45Z, conditional on a clean independent ratification review of the final bytes, and authorized this narrowed revise on 2026-11-05 at about 02:2xZ. The proposal adds a host-side breakage pass: a Dispatcher verb that turns each failed job of a watched scheduled workflow on the default branch into one ledger work item, deduplicated by workflow, job and head commit. That makes the 3-hourly root-uid workflow of bd-ib-xufdwx owned work rather than a red mark on the forge. It only files work and never gates a dispatch, so it does not conflict with the master-CI preflight rule in §"Dispatch preflight and post-merge step discipline". The implementation item is bd-ib-pgbr52, which carries assertion 2 of livespec-dev-tooling plan ci-runtime-and-cost (epic livespec-dev-tooling-ib3oe3).

## Modifications

One change against the proposal text, which the proposal itself prescribes: the scenario is numbered 313, not 302, because Scenarios 302 to 312 were taken while this proposal waited (v298 and v299 took 309 to 311, and v300 took 312). The contracts.md closing sentence names Scenario 313 to match. The heading-coverage TODO row for Scenario 313 (integration tier, owned by bd-ib-pgbr52) and its debt-register entry are co-edited in the revise commit. The independent review of the final bytes found NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T03:32:58Z
verdict: NO BLOCKERS
proposal_stem: file-a-ledger-breakage-item
content_digest: 0b7019fc3947c35b3b5e09563147bdc502b130ab846c8e9bb5606b656ab1f0b1
