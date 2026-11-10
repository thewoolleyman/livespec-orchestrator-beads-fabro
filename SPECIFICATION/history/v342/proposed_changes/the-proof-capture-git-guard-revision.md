---
proposal: the-proof-capture-git-guard.md
decision: modify
revised_at: 2026-11-10T23:41:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modify. The proposal is adopted with three refinements: (1) the launcher rules land as one paragraph placed directly after the proof_capture and review read-only rules in §"Self-contained plugin dispatch" (not as a bulleted list), ending with a pointer to Scenario 341; (2) the scenario's refused-push case splits its Then into the refusal line and an unchanged remote; (3) per the revise co-edit discipline the new heading carries a spec-first TODO coverage row and a matching debt-register row, both owned by bd-ib-7e6uzu. The rule generalizes the existing 'It MUST NOT modify the tree' sentence: commit was already scoped to the run's checkout (bbc4df37b), and push is now scoped the same way, admitting only a push into a local repository under the system temporary directory. No ratified clause states a contrary launcher rule, and the proof-only arm's read-only checkout is the protected checkout this rule keeps refused. This unblocks bd-ib-ffw4q3's four factory_captured assertions, whose surface is publish_draft run against a local fixture with a scratch bare origin.

## Modifications

Placed as one paragraph after the review read-only rule, before the proof-record finding paragraph; the scenario's checkout-refusal Then split into two lines; coverage TODO row and debt-register row added for the new heading, owned by bd-ib-7e6uzu.

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
reviewed_at: 2026-11-10T23:39:52Z
verdict: NO BLOCKERS
proposal_stem: the-proof-capture-git-guard
content_digest: cc7da105f3323c55869ac2523211cf169f00d74e4f818dcdc661db8692577a42
