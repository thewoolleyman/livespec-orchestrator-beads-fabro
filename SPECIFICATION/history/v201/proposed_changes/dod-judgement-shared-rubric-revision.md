---
proposal: dod-judgement-shared-rubric.md
decision: modify
revised_at: 2026-10-22T09:07:58Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted with three mechanical modifications under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session fabro-currency (plan bd-ib-6tcjfx). The session filed the proposal (PR 3497) for bd-ib-gob6gl under coordinator rulings R588 and R589 and ratifies it as a single-proposal pass. Every taking of the Definition-of-Done judgement (repository preflight, pre-admission, pre-dispatch and the in-run dod_gate node) grades one rubric, the dod_gate prompt file of the executing build, over one subject. The subject is the rendered goal without the Dispatcher's judgement receipts, the referenced heading bodies, a spec identity and the grading set. The committed dispatcher.sandbox_capabilities array becomes the one grading set, and the published image file is compared with it as a journaled configuration mismatch. Verdict reuse and drain exclusion are keyed on the subject and rubric digests. The spec-stated component's reuse is keyed on its input, which includes riders, and on the spec identity. Judgement and sandbox seed share one resolved commit. The References-coverage rule (governing scenarios plus the governing contract H2) is written as a semantic judgement, never a host-wall check. The node still runs on every run, and a node refusal of a subject that pre-dispatch admitted on identical digests is journaled as dod-judgement-disagreement. It departs from no design record: the node's every-run duty is retained verbatim, and the earlier Sandbox capabilities precedence is amended explicitly in the same pass, with Scenario 139's body restated. Measured motivation: four preflight-PASS / in-run-refusal pairs on 2026-10-22 (u5j5f6, 7oec4d, 4cipbr; 7kvh2d flipped within one judge). The configured ratification reviewer, gpt-6-astra, in a separate read-only Codex session, returned NO BLOCKERS on round 3 of the proposal text and NO BLOCKERS on the exact resulting bytes (digest 74215a566afaea1916bfd546c9a05b1665786d791ea2679712e55057682778b5), which it recomputed independently.

## Modifications

(a) Scenario 139's H2 heading is kept verbatim rather than renamed as the proposal asked, because the shrink-only heading-coverage debt register refuses a change that removes an existing heading; only its gherkin body is restated. (b) In "The spec-stated judgement is one shared component", "named in the two paragraphs that follow" becomes "named in the \"Judged before admission\" and \"Judged again before dispatch\" paragraphs below", because "One rubric, one subject" is inserted between them. The sentence after the replaced reuse rule is capitalised ("A new revision ..."). (c) A blank line precedes the four-component bullet list of "One rubric, one subject". The co-edited tests/heading-coverage.json and tests/heading-coverage-debt.json gain Scenario 239 rows owned by bd-ib-gob6gl.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T09:07:37Z
verdict: NO BLOCKERS
proposal_stem: dod-judgement-shared-rubric
content_digest: 74215a566afaea1916bfd546c9a05b1665786d791ea2679712e55057682778b5
