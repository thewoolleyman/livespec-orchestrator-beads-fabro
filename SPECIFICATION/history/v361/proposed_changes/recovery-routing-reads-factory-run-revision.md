---
proposal: recovery-routing-reads-factory-run.md
decision: modify
revised_at: 2026-11-12T19:14:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:factory-run-work-preservation-revise
---

## Decision and Rationale

The proposal closes a real gap measured on 2026-11-12: no clause said which credential a Dispatcher factory read uses, so a tenant whose credential_wrapper seals its child's environment (dropping every FABRO_ variable) made every factory liveness read unobservable and held its recovery routes for good, although the factory reported the run ended. The new paragraph in contracts.md §"Dispatcher policy settings" fixes this. Factory reads authenticate with the Dispatcher's own factory credential from the default family wrapper, ledger IO stays under the tenant's declared wrapper, no FABRO_ value is passed into that wrapper's child, and a withheld tenant variable can no longer cause an unobservable read. Three new Scenario 182 scenarios exercise it. Placement is correct (this orchestrator's Dispatcher realization belongs in its own contracts.md), every cross-reference resolves, and no H2 heading changes. One sentence needed modification. The independent reviewer found that the original MAY sentence, which let the Dispatcher take a read in the outer default-family-wrapper environment it was launched under, cannot be exercised by a Dispatcher running inside a sealed tenant wrapper's child, which is exactly the case the paragraph exists for, because that child cannot see the outer environment. That made the MAY contradict the preceding MUST. The modified text removes the contradiction.

## Modifications

1. contracts.md: the sentence 'Because §"Provisional fleet launch scripts" runs a tenant wrapper nested inside the default family wrapper, the Dispatcher MAY take such a read in the outer default-family-wrapper environment it was launched under, and need not invoke the default family wrapper again for each read.' is replaced by: 'A Dispatcher whose own process environment carries the factory variables the default family wrapper injects, because it was not started inside a tenant wrapper's child, MAY take such a read in that environment, and need not invoke the default family wrapper again for each read. A Dispatcher running inside a tenant wrapper's child MUST NOT take such a read from its own process environment, even though §"Provisional fleet launch scripts" nests that tenant wrapper inside the default family wrapper, because a sealed tenant wrapper withholds that outer environment from its child; it MUST invoke the default family wrapper for the read.' The new paragraph is hard-wrapped at 79 columns to match its neighbours. 2. scenarios.md, the first new scenario: the Then step's 'in a default-family-wrapper environment and not in the tenant wrapper's child environment' becomes 'through the default family wrapper invoked for that read, and not from the tenant wrapper's child environment'. 3. scenarios.md, the second new scenario: the When step becomes 'When recovery routing grades the item and reads that earlier run's liveness', so the scenario's pass condition names the factory read as occurring. Everything else lands exactly as proposed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T19:12:04Z
verdict: NO BLOCKERS
proposal_stem: recovery-routing-reads-factory-run
content_digest: 7028eb76fddd4e5664bc2102e88afc532c6218e5856cf2998707473ae863fd4c
