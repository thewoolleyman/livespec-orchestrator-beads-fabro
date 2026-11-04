---
proposal: terminal-claim-remedies-read-the-forge.md
decision: modify
revised_at: 2026-10-21T18:55:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds), adopting both proposals of the file: work-item bd-ib-mzyhn2 with the third assertions of bd-ib-l6rleb and bd-ib-ddu6wq (a resume refusal on an active item names a remedy that changes that item), and work-item bd-ib-dbmoeh (a capacity handoff for a claim with no recorded pull request reads the forge before advertising any status move). ACTIVE-LANE DECISION, the question the proposal flagged for this revise, decided under the decision-authority rules as coordinator record R499 directed: the terminal-claim recovery move out of active is CONSISTENT with the ratified state machine and is not a departure from the design record that "### Per-state operator verb vocabulary" cites (repo thewoolleyman/livespec-console-beads-fabro, plan/archive/console-happy-path-mvp/research/verb-vocabulary-brainstorm.md). Three reasons: drive's guarded move clause already guards only the target and never the source, so "observe only" for active contradicted a ratified clause; "Stranded claim release" hold 2 (attribution-pending) already requires its held entry for an active item to name the operator move valve as the remedy; and the design record kept an abort verb out of active because the run keeps going (its point 4), whereas this move is valid only once the run is terminal, while its point 3 (no bare moves INTO active) is untouched. Because the change asserts nothing the ratified texts and design record do not already support, no coordinator question was sent. The configured ratification reviewer, gpt-6-astra, in separate read-only sessions, independently confirmed all three reasons and returned NO BLOCKERS on the exact resulting bytes in round 4 (digest ac14a435059e13fa0a10ecfe9f347ee263eb4e72c737f4b57d82a68f694c8523) on master c709e6163 (spec v193), after rounds 1-3 found five blockers that are repaired in these bytes.

## Modifications

Beyond the filed text: (1) the not-ready resume refusal withholds every status move, naming the condition, while a live process holds the item's ownership lock or the lock cannot be read; names reconcile-merged only when that command's own preconditions hold, else the failing precondition; names move:<id>:ready only when the forge was read and reports no merged pull request; and names the failed read when the forge cannot be read. (2) Items carrying rework:pending or a merge-hold: label are excluded from the terminal-claim recovery and keep their own routes. (3) The closed-or-merged refusal bullet names reconcile-merged only when its preconditions hold. (4) Stranded claim release hold 8 (run-succeeded) names reconcile-merged only when its preconditions hold, the recovery move when the forge reports no merge, and the failed read otherwise. (5) The verb table's active row admits the terminal-claim recovery move with the same predicate, and the door-rules ready bullet names it as a third journaled door. (6) Scenario 221 gains the live-lock, merge-held and unreadable-forge cases and the no-live-lock premise on the others; Scenario 222 is as filed. Scenarios 221 and 222 gain coverage and debt entries owned by bd-ib-mzyhn2 and bd-ib-dbmoeh.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T18:49:13Z
verdict: NO BLOCKERS
proposal_stem: terminal-claim-remedies-read-the-forge
content_digest: ac14a435059e13fa0a10ecfe9f347ee263eb4e72c737f4b57d82a68f694c8523
