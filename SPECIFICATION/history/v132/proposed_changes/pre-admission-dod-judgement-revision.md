---
proposal: pre-admission-dod-judgement.md
decision: modify
revised_at: 2026-10-13T10:44:14Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the maintainer's standing direction to drive plan hp-factory-failure-follow-ups (bd-ib-qieqc6) to completion: plan assertion 2 requires a references or authoring defect to be held out of ready, which the ratified clause forbade, and bd-ib-7f66ar's dod_gate verdict on run 01M4T6VPNZ90 prescribed this spec-change route. The wall's own advisory classification is unchanged; the gate's judgement now also runs before admission, which satisfies the clause's own rationale that only the gate can judge such findings.

## Modifications

Two modifications. (1) Placement: the new 'Judged before admission' paragraph is inserted after the clause's closing sentence ('Scenario 140 in scenarios.md exercises this clause.') rather than mid-paragraph after the ADVISORY sentence, so the existing paragraph stays whole; its reference to the ready-item advisory hygiene fact therefore reads 'above' instead of 'below'. (2) Consistency, raised by the ratification review: the dod_gate clause's sentence 'the semantic half runs only in the node' is amended to say the semantic half MUST run in the node on every run and MUST also run once before admission per the new paragraph, and that the earlier judgement never removes or replaces the node. The scenario is numbered 174 because master took Scenario 173 for unrelated work before this pass merged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-13T10:43:59Z
verdict: NO BLOCKERS
proposal_stem: pre-admission-dod-judgement
content_digest: 9bbbd08524fe267d2347fb1e8e38d5c2089c838e842aa694ff2b3318ebad621e
