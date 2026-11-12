---
proposal: the-dispatcher-s-watch-still.md
decision: modify
revised_at: 2026-11-12T04:20:46Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (dispatcher-run-watch-cost plan session)
---

## Decision and Rationale

Modified, then ratified. A bound run's watchdog poll reads the run's status and stage list by its id in one request. The stage list becomes a progress source of the same kind as the event stream, for the open command node and for node completions. A poll whose status and stage list are unchanged issues no other read from the factory. Events are read only at a stage boundary, on the poll that observes a terminal state or a run coming to need a human, and once before any stall cancel or not-progressing budget grading. A failed pre-decision events read defers that decision, and the hard ceiling still bounds the run. Scenario 173 gains seven cases with its heading unchanged. Measured on the dev VPS: 7.18 CPU-s per live run per minute before, and 3.61 after the released incremental read (bd-ib-u6llci), against the plan's 0.72 target. legacy-coordinator-agent (72dc4e8c) graded the proposal PASS-WITH-FIXES, ruled to keep the pre-decision events read, and the fixes are in the merged proposal (PR #4993). The independent ratification review found no blocker and noted one literal conflict, fixed below; the re-review of the final bytes returned NO BLOCKERS. No design record is cited by the paragraphs involved, and the decision resolves no conflict between ratified statements: the modification removes a conflict the proposal as written would have introduced. bd-ib-22j24v implements it; tests/heading-coverage.json's Scenario 173 row gains a sentence naming bd-ib-22j24v as owning the tests for the seven new cases.

## Modifications

One wording change, from the independent review: as proposed, the unchanged-poll sentence allowed an events read only under clause (d), while clauses (b) and (c) required one whenever the run IS terminal or NEEDS a human, so a needs-human state persisting across unchanged polls made the two MUSTs conflict. Now: "unless clause (b), (c) or (d) below applies", and "(b) the run reached a terminal state since that previous poll; (c) the run came to need a human since that previous poll;". The Scenario 173 case "A terminal run or a run needing a human triggers an incremental events read" takes the matching Given "a dispatch whose bound run reached a terminal state or came to need a human since the previous poll". The end-of-run readers are separate callers and are unaffected. Every other edit is applied verbatim.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T04:20:44Z
verdict: NO BLOCKERS
proposal_stem: the-dispatcher-s-watch-still
content_digest: ff56b582c0e623862ec1503a4cc6b9c4f8bc8e3c6278b615ee168e0d2cdb4801
