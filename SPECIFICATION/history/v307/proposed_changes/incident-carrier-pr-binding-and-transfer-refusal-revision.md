---
proposal: incident-carrier-pr-binding-and-transfer-refusal.md
decision: accept
revised_at: 2026-11-05T14:52:34Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:legacy-coordinator-agent-revise-lane
---

## Decision and Rationale

Accepted as written in delegated mode. legacy-coordinator-agent ruled under R301 on 2026-11-05 to ACCEPT this proposal as written, recorded on bd-ib-dzbwaq. It carries the two non-blocking notes from v302's independent ratification review. First, the older ## Expedited incident lifecycle sentence requiring each attempt to bind its 'carrier PR' is qualified to bind the carrier identity, including its real PR once the carrier is pr-bound, per ### Carrier identity before and after PR creation, so a branch-reserved or head-published attempt is not read as violating the binding rule for lacking a PR number. Second, the factory-transfer refusal in ### Factory transfer and recovery of the initial operation gets a dedicated scenario inside the existing incident-authority gherkin block. The text keeps 'a named capability refusal' exactly as written; a literal refusal name for factory transfer is left to a later proposal. No ## heading is added or removed, so heading coverage is unchanged. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T14:52:06Z
verdict: NO BLOCKERS
proposal_stem: incident-carrier-pr-binding-and-transfer-refusal
content_digest: 61f484ca06cce5fdaf90f8cdc9027c8ca00086335819e87ba11985b142b6149a
