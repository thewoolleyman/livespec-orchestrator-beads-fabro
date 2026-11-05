---
proposal: factory-run-work-preserved-on-progress.md
decision: modify
revised_at: 2026-11-05T14:01:26Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The maintainer accepted this proposal on 2026-11-05 ("agreed", recorded as scope event frwp-ruling-decisions-accepted-2026-11-05 on plan epic bd-ib-nckst7), together with its three open design decisions: capture at the end of the three commit-settle command steps plus needs_human, a failed preservation push never failing the run, and plan assertions 1, 3 and 5 re-worded to the accepted one-node-visit loss bound. All four proposals land as written. The only change is mechanical: v304 already took Scenario numbers 314-316, so the four new scenarios are numbered 317-320.

## Modifications

Scenario numbers renumbered 314->317, 315->318, 316->319, 317->320 in the scenario headings and in each 'Scenario NNN in scenarios.md exercises this paragraph' sentence, because v304 (a-committed-fleet-launcher-screens) already took Scenarios 314-316. Cut as v306 after v305 (fix-review-fix-single-runner-wait-then-settle) merged first. The `\"` quote escapes inside the proposal's credential-clause replacement are written as plain quotes. No other wording change.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T14:00:41Z
verdict: NO BLOCKERS
proposal_stem: factory-run-work-preserved-on-progress
content_digest: d2dea5d3ac34d33bd9cba3ca006c1aad9228c26f0fc064e622726a220fdc8d2f
