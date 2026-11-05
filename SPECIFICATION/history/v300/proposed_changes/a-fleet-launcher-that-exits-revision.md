---
proposal: a-fleet-launcher-that-exits.md
decision: modify
revised_at: 2026-11-05T02:30:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:gmktec-factory-placement
---

## Decision and Rationale

Decided in delegated mode by claude:gmktec-factory-placement; legacy-coordinator-agent ACCEPTED this exact modification under its R301 delegated authority (not the maintainer's own answer) at 2026-11-05 ~02:31Z, content digest 29c6fec5. It generalizes §"Provisional fleet launch scripts" so a committed fleet-launch launcher accounts for every exit it makes before its run lists: a terminal line naming item, ticket number and cause; a still-ready item's ticket re-taken at the same number or reported in a ledger comment; a bounded ready-set retry; and a stall line for a dead-pid ticket. On 2026-11-04 twelve interim-launcher losses were silent because the EXIT trap deleted each ticket with no record; the committed scripts share that shape (bd-ib-rk7mbd, absorbing bd-ib-3mhh5r). It adds no admission authority: the retry re-asks the Dispatcher's own ready set, and a non-run exit never changes the item's status.

## Modifications

Two changes against the proposal text. First, the coordinator's R301 ruling on rule 2 (2026-11-05 ~01:15Z): the dropped-ticket comment duty applies to every signal exit, including a launcher stopped deliberately by the seat that runs the launchers, and for a signal exit the comment's cause MUST name the signal and MUST state that the exit was not a run ending; the clause, the harness paragraph and Scenario 312's TERM case carry it. Where a launcher cannot establish that a successor holds its ticket number, the intended reading is to always comment. Second, the scenario the proposal left as NN is numbered 312, the next free number, and the harness paragraph cites it. The heading-coverage TODO row for Scenario 312 (integration tier, owned by bd-ib-rk7mbd) and the regenerated debt register are co-edited in the revise commit. The independent review found NO BLOCKERS; its four non-blocking notes (resume TERM coverage sits in the harness paragraph, the loose 'yield wait that ends', the unnamed successor-detection method, per-reader stall reporting) need no change per the coordinator.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T02:28:30Z
verdict: NO BLOCKERS
proposal_stem: a-fleet-launcher-that-exits
content_digest: 29c6fec571d21fcd69d37bfd46cb04836327736a5224e44b7348fbd9f20864d1
