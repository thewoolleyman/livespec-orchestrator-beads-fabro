---
proposal: reconcile-merged-runs-owed-janitor.md
decision: accept
revised_at: 2026-10-22T06:49:45Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session fabro-currency (plan bd-ib-6tcjfx), which filed the proposal (PR 3489) for bd-ib-ssmioz under coordinator ruling R480 and ratifies it as a single-proposal pass under R202. It narrows the reconcile-merged acceptance arm: when an acceptance item's latest dispatch journaled that its post-merge janitor did not run, the valve runs that owed janitor against the merged default-branch tip under every guard and the ownership lock, then re-runs acceptance; a red owed janitor keeps the item in acceptance; missing janitor evidence refuses; an item whose janitor ran keeps the acceptance-only behaviour. Measured on openbrain ob-5qlusq (openbrain#20) on 2026-10-21. It departs from no design record. Two presentation adjustments versus the proposal text: Scenario 237's heading sits outside the gherkin fence (house format), and, at the reviewer's round-1 blocker, Scenario 136's hand-driven reconcile-merged scenario gains the Given 'its latest dispatch journaled a green post-merge janitor' so it cannot contradict the new owed-janitor arm. The configured ratification reviewer, gpt-6-astra, in a separate read-only Codex session, returned NO BLOCKERS in round 2 on the exact resulting bytes (digest a5842be8352c30a7cbdb8ff37716eb4af1c4d291c36163cf61e14dd822ac06e9) on master after v198 and independently recomputed that digest.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T06:48:39Z
verdict: NO BLOCKERS
proposal_stem: reconcile-merged-runs-owed-janitor
content_digest: a5842be8352c30a7cbdb8ff37716eb4af1c4d291c36163cf61e14dd822ac06e9
