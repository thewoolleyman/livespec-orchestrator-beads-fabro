---
proposal: a-held-spec-change-tier.md
decision: modify
revised_at: 2026-11-03T18:33:56Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with modifications under delegated revise mode (coordinator legacy-coordinator-agent, R301; spec_governance.revise_decision_mode delegated) for bd-ib-6is4z7, plan spec-implementation-lockstep (epic bd-ib-ax3rds). A held spec-change-tier item only ever records the linked topic the Dispatcher derives from its title, so a proposal filed under any other stem leaves the hold unratifiable; the relink-spec-tier route lets the hold wait on the topic actually filed while ratification and a stated re-run judgement remain the only release. Three independent read-only sonnet reviews were run; the first two raised scenario-coverage blockers that the modifications resolve, and the third, over these exact bytes, found NO BLOCKERS. Its non-blocking notes are recorded for the implementing item rather than folded in: assert the appended tier record keeps the standing verdict, generalization target and clause provenance; a repeat relink replaces the current linked topic; relink deliberately carries no live-run refusal and writes no dispatch-journal entry on success.

## Modifications

(a) The relink-spec-tier refusal list defines a canonical topic stem as one /livespec:propose-change's topic canonicalization would not change, and adds a refusal for a topic with no pending proposal whose latest revision record carries decision reject, since a hold waiting on a rejected topic could never release. (b) Two scenarios are added to Scenario 206: a relink to an already ratified topic changes only the linked topic (no status change, no release, no other item touched; release only at the next intake or drain pass), and a relinked topic is carried forward by every later tier record. (c) The proposal's single refusal scenario is replaced by a Scenario Outline covering the four refusals, each writing no linked topic, status, ledger comment, tier record or dispatch-journal entry.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T18:33:55Z
verdict: NO BLOCKERS
proposal_stem: a-held-spec-change-tier
content_digest: 570786c0193f69c37f797cc6c4842c533b850f2ca972d575c06a03e42ed85bda
