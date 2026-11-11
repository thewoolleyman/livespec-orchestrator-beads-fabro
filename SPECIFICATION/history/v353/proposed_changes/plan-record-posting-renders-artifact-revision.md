---
proposal: plan-record-posting-renders-artifact.md
decision: accept
revised_at: 2026-11-11T13:41:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept as filed. v350 (df7f359b5, #4938) made an `artifact paths:` line part of a plan Proof of Done record's build identity in a component-declaring repository and requires every plan record to be rendered by one posting primitive, yet left that primitive's payload field unstated. The dispatcher's spec-stated judgement therefore read carrier bd-ib-qpibvm as partial at drive (2026-11-11T12:31:53Z, generalization target ## Planning Lane realization), and legacy-coordinator-agent ruled a split: bd-ib-qpibvm keeps the five stated assertions (now dispatched) and this proposal states the sixth for carrier bd-ib-sjxs4f, whose linked spec-change topic equals this proposal's topic. The text adds three MUSTs to the posting-primitive sentence group (accept an optional build artifact_paths array, render it in order or render no line when absent, refuse a malformed value naming the field and post nothing), and one unnumbered scenario covers each. The anchor sentence is unchanged on master through v352. Spec-first TODO coverage and debt rows are owned by bd-ib-sjxs4f. Case: homelab plan secret-writer-stored-key-alias (epic homelab/hl-bvycoc).

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
reviewed_at: 2026-11-11T13:41:44Z
verdict: NO BLOCKERS
proposal_stem: plan-record-posting-renders-artifact
content_digest: 54f8836b0af0f17bd372442d87921715e6f218587ff13626db536441c8d737c7
