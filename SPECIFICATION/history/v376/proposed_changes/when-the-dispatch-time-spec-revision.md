---
proposal: when-the-dispatch-time-spec.md
decision: accept
revised_at: 2026-11-14T12:31:19Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Releases bd-ib-ubcqgo's spec-change-tier hold: a stale hold whose dispatch-time classification did not run is re-judged once or held naming the stale record, and no outage releases a held item. Measured cause: priority-1 bd-ib-cwuxfi refused at 2026-11-14T02:41:56Z on a v357 tier record while master was v373. Ratified under delegated decision in factory-run-yield's orchestrator revise slot (cut after v375 on legacy-coordinator-agent's queue, relayed by throughput-plans-coordinator); an independent read-only sonnet review reported NO BLOCKERS on these exact bytes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T12:31:12Z
verdict: NO BLOCKERS
proposal_stem: when-the-dispatch-time-spec
content_digest: a97c0aea59950c0a89d1c26e7ff73ffd5d77ef7442a16202eeb731d2f70e313f
