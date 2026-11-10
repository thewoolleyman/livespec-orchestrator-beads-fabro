---
proposal: orchestrator-currency-surfaces-push-agents.md
decision: accept
revised_at: 2026-11-10T00:44:09Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed, in delegated mode. This re-cuts v326 (livespec-orchestrator-beads-fabro#4691, accepted and ratified on 2026-11-08), which closed unmerged only because CI's check-doctor-static dropped the external_references allowlist for the unreadable livespec-dev-tooling clone. livespec-bpzy (livespec#3152, merged 2026-11-10T00:35:43Z) fixes that doctor defect, and this pass runs only once livespec 0.47.2 is pinned in this repository's CI. Delegated decider: the gmktec-factory-placement plan seat (livespec-dev-tooling-me5aqz), which filed the proposal. It takes this slot at priority 1 because the #4749 canary chain is on expedited-incident-response-flag's critical path (legacy-coordinator-agent ruling, 2026-11-10 ~00:2xZ), and publish-draft-green-work-loss handed it over after v338 (52d7b90f3). Carrier: bd-ib-rfhnqf. v326's diff was three-way-applied cleanly onto post-v338 master. It composes with v337's release-channel paragraph: both rest on the session-reconcile hold of livespec-dev-tooling-7upzav. The commit also adds the livespec-dev-tooling external_references entry for contracts.md §"Orchestrator build adoption", as v326 did. An independent read-only sonnet reviewer recomputed the digest and found NO BLOCKERS at 2026-11-10T00:42:40Z, with no HIGH finding in its live-state doctor walk. Its MEDIUM finding is the implementation gap bd-ib-rfhnqf exists to close: `_needs_attention_currency_staleness.py`, `_dispatcher_staleness_gate.py`, `_dispatcher_minimum_release_floor.py` and `_dispatcher_registered_install_currency.py` still name `claude plugin update`, and `_needs_attention_release_adoption.py` raises high urgency for a behind clone. It also noted that v337 writes the adopt step as `<tag>` while live livespec-dev-tooling takes `<build>`; that is not contradictory, and the dev-tooling tag form (a-canary-clone-adopts-a) is pending.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T00:42:40Z
verdict: NO BLOCKERS
proposal_stem: orchestrator-currency-surfaces-push-agents
content_digest: f6bbf9afb095cca08d590f0063bbab92b2340f68356151d2ea3564346dbbd489
