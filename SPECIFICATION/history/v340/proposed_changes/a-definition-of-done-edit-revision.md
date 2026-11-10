---
proposal: a-definition-of-done-edit.md
decision: accept
revised_at: 2026-11-10T03:08:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept. Proof mode states how an assertion is proved, not what the item asks for, so the spec-change tier decision's input, the asked-for behaviour statement, is rendered without the Definition of Done's proof-mode partition (the Host-captured and Human-attested sub-headings, their Reason lines, and bullet order). A partition-only edit then leaves the input unchanged and the recorded tier decision is reused under the existing reuse rule, while any real behaviour edit still forces a new judgement. This is the narrowest change that stops the measured re-roll on livespec-dev-tooling-thhgeg (tier none at v173, spec-change partial at v174 after a word-for-word proof-mode move). Governing-heading verdicts keep their own input. Three scenarios join Scenario 206; no H2 heading is added. Work item bd-ib-ajtmgf.

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
reviewed_at: 2026-11-10T03:07:13Z
verdict: NO BLOCKERS
proposal_stem: a-definition-of-done-edit
content_digest: 50f600c2c441a83c33e098cb94d6f5991d593a1aaf8e83196e83c821117d2441
