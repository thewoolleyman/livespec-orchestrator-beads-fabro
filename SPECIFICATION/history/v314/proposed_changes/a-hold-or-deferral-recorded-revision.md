---
proposal: a-hold-or-deferral-recorded.md
decision: modify
revised_at: 2026-11-07T17:33:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent under R301 delegated authority on 2026-11-07: ACCEPT MODIFY on content digest 4982be92..., the seventh review round. This is the coordinator's decision, not the maintainer's. It accepted three departures from its fleet-scope order: records that only mean healthy work are not holds (measured: about 40 facts under the proposal's rule against 1 under this one, by the drafter's simulation over the live journal); admission-held and rework-capacity-deferred stay out because they are nested drain outcomes, revisited if ever written as stages; and a hold whose end writes no retiring record stands up to seven days as the clause's stated limit. It directed that the implementing item's Definition of Done make such a fact read as unverified, and test the claim-changed, dispatch-live and already-released exclusions. Independent sonnet review reported blockers on rounds 1 to 4 and 6 and NO BLOCKERS with notes on round 5, all applied, and reported NO BLOCKERS on these bytes in round 7. Scope: this repository's own journal only; launcher-hold is written by no launcher yet.

## Modifications

Compared with the proposal: excludes stranded-claim-hold with run-live, dispatch-live or claim-changed, sandbox-container-held with run-live, and the two release-held stages with already-released; drops admission-held and rework-capacity-deferred; replaces 'route, release, launch or terminal record' with a closed retiring list, where one retiring record retires every hold of its subject except that launcher-hold-lifted retires only a launcher-hold; defines a subject's hold as its newest record that is a named stage, not excluded, with no later same-stage exclusion and not retired; names reason and subject keys; gives launcher-hold a record shape and a lifted record; defines a live recovery-held, independent of the fact, for the idle-factory qualifier and the idle-slot audit, with an unreadable journal unobservable and reported as hygiene:journal-hold:unobservable; adds edits to the idle-slot audit, both determinism sentences and the ownership boundary. Scenario 324 has seventeen cases rather than nine.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T17:31:29Z
verdict: NO BLOCKERS
proposal_stem: a-hold-or-deferral-recorded
content_digest: 4982be922201f091b2fedecea18613973a37b10ee1dd7ca0fe6a4dcfcf1c1355
