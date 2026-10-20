---
proposal: bounded-fabro-events-reads.md
decision: modify
revised_at: 2026-10-20T18:48:57Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fabro-currency (session d8087064)
---

## Decision and Rationale

Accepted with modification under this repository's delegated revise_decision_mode, by session fabro-currency (d8087064), at the request of fleet coordinator gitops-fleet-capacity-monitoring (R330(2) filing, then R202 after the R265 preflight refused bd-ib-2dlh7m for want of a governing clause). The subsection bounds every Dispatcher fabro events read in size, retries and concurrency, after petri measured unstreamed reads returning 0 bytes after 240 s on a 390-minute gmktec run while reconcile-runs replayed unresolved projection failures every pass. The bounds are fixed values rather than dispatcher.* keys, because Dispatcher policy settings makes every key per-item overridable except wip_cap and these are not per-item properties. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 2. The Step 3.5 stale-branch precondition was skipped with --skip-stale-branch-check: its findings are other sessions' unlanded spec branches, none of which touches the new subsection or Scenario 227.

## Modifications

Round 1 of the ratification review found that Scenario 227 did not exercise every new MUST. Its Gherkin block was replaced verbatim with the reviewer's: bounded later reads for each caller (outline), preserved progress instant and open command node across bounded samples, a completion clearing carried state, sample cost independent of total event count, failed reads of each kind (timeout, non-zero exit, zero bytes) journaled with every field and treated as unobservable, the 60-second floor, doubling and reset, durable exhaustion after five failures that a new run does not inherit, one read per run per reconcile pass, and the cross-process per-factory concurrency cap. The contract subsection is unchanged from the proposal. Scenario 227 is the next free number; 224-226 are reserved by open PR 3405.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T18:48:25Z
verdict: NO BLOCKERS
proposal_stem: bounded-fabro-events-reads
content_digest: 69d0144bb9ecacb28afbbef323a378e529c7127d0c187e4c0bb225f3ca62e75d
