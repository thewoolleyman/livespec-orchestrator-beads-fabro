---
proposal: a-live-run-whose-dispatcher.md
decision: modify
revised_at: 2026-11-12T01:52:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (dispatcher-run-watch-cost plan session)
---

## Decision and Rationale

Modified, then ratified. A dispatch's own watch is today the only thing that applies the whole-run wall budget, so a run whose re-attach supervision gave up is held as run-live by reconciliation on every pass and never cancelled; on 2026-11-11 bd-ib-p6ammc's run 01M75SD00Z90 and livespec-dev-tooling-symfx2's run 01M760HYV9CE each held a gmktec slot past 21,600 s this way. The new reconciliation duty "Live-run wall budget" applies the watchdog's whole-run wall budget, progress grading, hard ceiling, export-then-terminate disposition and held arm to a non-terminal run whose ownership lock no live process holds, and on the periodic pass for every dispatching repository it reaches; an unmeasured budget never cancels and an unreadable export is held. Hold 5 run-live is narrowed and no other hold changes. Scenario 349 exercises the duty and was still free at cut time. legacy-coordinator-agent (599f41e5) graded the proposal PASS and ruled this revise cut on merge. The independent ratification review found one blocker, fixed below, and re-reviewed the final bytes as NO BLOCKERS. No design record is cited by the paragraphs involved, and the decision resolves no conflict between ratified statements: the modification removes a conflict the proposal as written would have introduced. bd-ib-ag633q implements it. tests/heading-coverage.json and tests/heading-coverage-debt.json gain TODO and debt rows for Scenario 349, owned by bd-ib-ag633q, in the revise commit.

## Modifications

Two changes to contracts.md beyond the proposal. (1) Blocker from the independent review: the reconciliation clause's "Status changes" bullet closes the list of item status changes a reconciliation surface makes, and that list is what exempts them from the rule of the section "A factory run never awaits a human" that reconciling or terminating a run MUST NOT change the item's status. The new duty rests an item at blocked / needs-human, which was on neither. The bullet now reads: "The absent-run release, the run-absent-repeated rest, the terminal-run completions, and the blocked / needs-human rest of a 'Live-run wall budget' disposition are the only item status changes any reconciliation surface makes." The rest of that bullet is unchanged, so its carve-out covers the new rest. (2) Clarification of effect order, adding no behaviour: after "The reconciliation pass stands in for the watchdog poll." the new bullet gains "The budget disposition is a recovery effect, so 'Recovery is exclusive on its host and convergent' governs it: its export and its cancel precede the journal record, and its blocked / needs-human rest is the status transition written last." The proposal's bullet, the hold-5 narrowing and Scenario 349 are otherwise applied verbatim.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T01:52:06Z
verdict: NO BLOCKERS
proposal_stem: a-live-run-whose-dispatcher
content_digest: 15c69ab8675bac6b947aa904888225e470164e0307002edd4093562fb2e49f02
