---
proposal: governing-heading-omission-advisory.md
decision: modify
revised_at: 2026-10-24T23:45:19Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance on coordinator gitops-fleet-capacity-monitoring's ruling of 2026-10-24 ~23:0xZ, made under the maintainer's stability-tier direction (epic livespec-dev-tooling-dfixhe). A reference-coverage finding becomes advisory when at least one named heading governs, because the spec-stated judgement names different governing headings for one unchanged subject; seven measured instances on 2026-10-24 made admission non-convergent. Modified, not accepted verbatim: the first independent ratification review (gpt-6-astra, codex session 01a17022-1eb2-77b3-957e-cc41fe0bd208) found that Scenario 141 and Scenario 174 kept unconditional omission refusals that would contradict the new rule, and that the node's advisory continuation and the recording of advisory findings had no scenario coverage. The modification resolves all three, and the second review returned NO BLOCKERS on the exact bytes. No design record is contradicted: the remedy wording of 'The spec-stated judgement is one shared component' is unchanged, and Scenario 206's refusal of a citation that governs nothing still holds. Ratifying review: gpt-6-astra codex session 01a1704d-0d86-7071-93e8-5e6b8f5a56b1 (read-only, separate process) returned NO BLOCKERS on these exact bytes. It was re-cut onto v209 after v208 and v209 landed first, with the change set byte-identical to the one that sessions 01a17025-ce11-7830-8dbb-3bf650bd70b2 and 01a17027-ab62-7e22-b024-edf2a6aa6e8f had already cleared.

## Modifications

(1) The contracts.md sentence now requires recording only of a host taking that records its verdict, and states that the node falls through to implement and the host takings admit the item, refusing no dispatch. (2) Scenario 141: 'A generic reference where a scenario exists is a gate finding' is narrowed to a non-scenario heading that governs none of the item's assertions, and a new scenario 'A governing generic reference where a scenario also governs is an advisory finding' is added. (3) Scenario 174: its pre-admission and pre-dispatch refusal scenarios are narrowed to a References line naming no governing heading, and a new scenario 'An item whose References line omits only some governing headings moves to ready with an advisory finding' is added. No `## ` heading changes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T23:45:06Z
verdict: NO BLOCKERS
proposal_stem: governing-heading-omission-advisory
content_digest: 56ca5c83740389adfe403b4abc17cd798ee6c86ae5e25c9c890d7c68c66ca8ad
