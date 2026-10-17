---
proposal: janitor-inherits-no-routing-variables.md
decision: modify
revised_at: 2026-10-17T10:58:40Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Ratifies the janitor-environment rule that bd-ib-fd26sc implements, at the maintainer's 2026-10-17 direction to fix the root cause of janitor strands on env-routed dispatches. The cause was measured: LIVESPEC_FABRO_FACTORY and LIVESPEC_INVOKER each fail a test that passes without them, and a clean-shell check of the same checkout passes all 93 targets. The clause sits beside the venue clause, which governs only WHERE the janitor runs; this one governs WHAT ENVIRONMENT its check run receives.

## Modifications

Scenario 189 was revised after ratification review round 1 (gpt-6-astra, BLOCKERS). The first sub-scenario's premise is now 'a merged item whose check aggregate passes at the janitor venue when run without those variables', and its outcome is 'the janitor reports the aggregate's own passing verdict', not an unconditional 'reports green'. This preserves genuine failures under Scenarios 145 and 167. The sub-scenario title now reads 'gets the janitor verdict its merge earns'. The third sub-scenario's Given now reads 'none of the dispatcher's routing or attribution variables', to match the clause's future-variable requirement. The tests/heading-coverage.json entry lands as a same-PR hand edit outside the spec target, as v149 did.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-17T10:58:16Z
verdict: NO BLOCKERS
proposal_stem: janitor-inherits-no-routing-variables
content_digest: 2aa41b02071173a1c9bb36dbd97b6047dbe57978864183995df711c729fcdcd8
