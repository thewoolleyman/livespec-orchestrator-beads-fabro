---
proposal: oom-kill-named-on-stalled-outcome.md
decision: modify
revised_at: 2026-10-21T10:37:56Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 12). Work-item bd-ib-7rnipp: dod_gate refused it twice on gmktec (runs 01M57RNA8HTV and 01M57SD4NT46) because no ratified clause stated the OOM vocabulary its Definition of Done names; its second assertion (no backlog bounce, no non-convergence observation) was already stated by 'Not non-convergence' and Scenario 172. Modifications beyond the filed proposal: the clause names the watchdog-stall-cancel record rather than a generic journal record, adds the ledger comment of whichever stall disposition applies, forbids inferring an OOM kill the factory does not report, and Scenario 234 gains a third case for that negative. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes. An earlier launch of the same review was discarded unread because a shell-quoting fault corrupted its prompt. Its two non-blocking suggestions (an explicit 'On a stalled-no-progress cancel' opener, and asserting unobservable on all three surfaces in the missing-limit scenario) were not adopted, because changing the bytes would need another review round. Scenario 234 gains coverage and debt entries owned by bd-ib-7rnipp. The stale-branch precondition ran unskipped unless the revise record below says otherwise.

## Modifications

contracts.md: a new paragraph '**An OOM kill is named.**' in section 'Dispatcher progress watchdog', immediately after the 'Not non-convergence' paragraph, requiring the watchdog-stall-cancel record, the dispatch result and the applicable stall disposition's ledger comment to name the OOM kill, the run id and the factory-reported container memory limit, recording an unreported limit as unobservable, forbidding an inferred OOM kill, and keeping the outcome stalled-no-progress for every rule of the section. scenarios.md: Scenario 234, 'A stalled run whose sandbox was OOM-killed names the kill and the memory limit', with three scenarios: a reported kill with a limit, a reported kill without a limit, and no reported kill.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T10:36:58Z
verdict: NO BLOCKERS
proposal_stem: oom-kill-named-on-stalled-outcome
content_digest: 784fd7f47f9dde794c5224080f96a28b656d88431399b20bb8a9812c1b3fdc5e
