---
proposal: the-spec-change-hold-is.md
decision: modify
revised_at: 2026-11-11T09:07:25Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modify. Adopted: an item classified bug, chore or non_functional is spec-change tier whenever the spec-stated judgement reports its asked-for behaviour partial or unstated, exactly as a feature is, so the judgement is always taken; and classify-tier re-judges an item whose latest tier record's behaviour digest or spec identity no longer matches, instead of always reporting its first record. This aligns classify-tier with the ratified verdict-reuse rule (a verdict is reused only while its input and spec identity are both unchanged). Two live cases motivated it: bd-ib-p6ammc was classified bug and routed ready at tier none although its behaviour was unstated, and retyping plus classify-tier changed nothing. Implemented by bd-ib-t2rg6x (legacy-coordinator-agent ruling, 2026-11-11), in plan publish-draft-green-work-loss (epic bd-ib-acrr56).

## Modifications

The every-classification judgement and the no '(not taken)' rule are stated normatively in the replaced autonomy-tier sentence with a Scenario 344 pointer; the behaviour digest is defined inline and the spec identity is tied to the spec-change tier decision's identity in Effective acceptance criteria, and a record carrying no digest is re-judged; Scenario 206 is narrowed so only a bug or chore restoring stated behaviour keeps its leeway; Scenario 267's appends-nothing case is conditioned on an unchanged digest and spec identity; Scenario 344 is appended with a spec-first TODO coverage row and a sorted debt-register row owned by bd-ib-t2rg6x.

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
reviewed_at: 2026-11-11T09:07:19Z
verdict: NO BLOCKERS
proposal_stem: the-spec-change-hold-is
content_digest: 33c5857055aa996cd20f74eb3dc61bf97c9fdcc0425b07f065aecefde3a9edbe
