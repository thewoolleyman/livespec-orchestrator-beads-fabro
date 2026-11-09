---
proposal: a-goal-carries-a-bounded-rider-set.md
decision: modify
revised_at: 2026-11-09T23:15:32Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:publish-draft-green-work-loss
---

## Decision and Rationale

Accepted in substance under delegated decision mode, at v338, the slot legacy-coordinator-agent ordered after gmktec-factory-placement's v337 (#4787). Carrier bd-ib-y6tcni. Every non-receipt ledger comment entered the rendered goal and the Definition-of-Done judgement subject forever, so a long-lived item became unjudgeable: bd-ib-uq2ocd carried 88 comments (1,628,501 characters) and every host taking ended at the 100,000-token input bound. Proposal 1 bounds the carried rider set to riders appended since the item's last dispatch claim plus standing and stage-scoped riders, and states the left-out count in the goal. Proposal 3 names the input bound as a cannot-run cause, requires the did-not-run record to state the subject size, and lists such an item as an unpreflightable hygiene fact. Proposal 2 is kept only as the each-rider-once invariant: its motivation is stale, because bd-ib-tzvtgc's fix e47abc38d (released in v0.311.1) already removed the judgement subject from the shared goal, but the invariant guards against a regression. The coordinator (legacy-coordinator-agent, session 5779d475) concurred with these dispositions. An LLM doctor pass on the first cut found two contradictions and several gaps. The cut was undone, the text repaired (see Modifications), and a fresh independent read-only sonnet review found one further blocker (a pre-dispatch scenario asserting an item stays ready although its dispatch proceeds), fixed by retargeting it to the pre-admission route; the re-review then found NO BLOCKERS on the exact bytes. Deferred, not part of this revise: the repository preflight's fallback-versus-independent chain drift (pre-existing); whether a claim released before its first ACP node moves the bound; the dod_gate subject file also carrying riders; naming the ledger-listing command; and whether a standing rider may also be stage-scoped.

## Modifications

(1) Proposal 2 is reduced to a no-duplication invariant in the GOAL bullet: "A rendered goal MUST NOT carry any carried rider's text more than once, whichever section of the goal carries it, and the subject digest MUST be computed over the subject as this paragraph defines it, unchanged by how the node receives the subject." Its clause about including the judgement subject in the node's goal is dropped because e47abc38d (v0.311.1) took the subject out of the shared goal; its scenario is retargeted to the implement stage's goal and a no-stage rider. (2) Proposal 3's cause-list replacement is applied at the two hard-wrapped occurrences inside "Judged before admission" and "Judged again before dispatch" only; the autonomy-tier bullet's identical phrase concerns the tier classification and is unchanged. (3) Proposal 1's not-carried-digest sentence sits in the GOAL bullet after the replaced operator-rider sentence. (4) Doctor-finding repairs: the pre-existing sentence that a repository preflight's chain is outside the input bound now says the preflight is not ended mid-run but a candidate reporting input at or above the bound has returned no verdict with the bound as cause, so it no longer contradicts the TAKING paragraph; every input-bound did-not-run record states the subject size and carried rider count and the unpreflightable fact reads both from the most recent such record; a partially bound-ended taking is not unpreflightable; the fact clears on any later verdict, reused or fresh, or a non-bound did-not-run; the rider definition in "Work-item riders are scoped to the stages they name" now covers every non-receipt comment and renders only carried riders; the new paragraph names the three receipt classes directly; the left-out line counts only non-carried riders, never receipts, and is outside the GOAL component of every subject; the GOAL bullet's "excludes ... and except" grammar is repaired. (5) Scenarios: the digest-reuse scenario's Given takes D after claim T; added an identical left-out line across a dispatch's stages, the did-not-run record's rider count, and a pre-admission bound-ended item routed unchanged and listed as unpreflightable; "1 ledger comment" became "1 rider". No H2 heading changes, so tests/heading-coverage.json is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T23:15:31Z
verdict: NO BLOCKERS
proposal_stem: a-goal-carries-a-bounded-rider-set
content_digest: 59b668b9be44708009d8bb308b074e7e0accc75e94a15a809875a45bd1803205
