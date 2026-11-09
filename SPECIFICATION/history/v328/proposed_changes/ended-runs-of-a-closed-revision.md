---
proposal: ended-runs-of-a-closed.md
decision: modify
revised_at: 2026-11-09T04:00:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by the kubernetes-sandbox-backend plan session (epic bd-ib-nmuyjc, model claude-opus-5-5) under the repository's delegated revise decision mode, on legacy-coordinator-agent's grant (session 546979bb, 2026-11-09 ~03:5xZ: 'your v328 claim for --only-topic ended-runs-of-a-closed is GRANTED, as a slot swap'; host-judgement-spend-journal-final-usage moves to v329). MODIFY on content digest 58809af3. Basis: coordinator ruling R493 (2026-11-08) set fleet scope and one fleet-wide periodic pass for collecting closed items' ended-run sandboxes. The bd-ib-u5facl host measurement (2026-11-08 ~20:30Z) found the only periodic collector, reconcile-runs.timer, collecting only this repository's runs, and 55 never-collected workspaces of closed items (about 48 GB on gmktec-xubuntu and poweredge-xubuntu). Work-item bd-ib-q4xgcp rests at spec-change on this topic. The modification makes the journal duty total: as filed, a refusal for a run whose work-item cannot be resolved had to name 'the item status the pass read', which no pass can read, so the proposal's own run G step could not be satisfied. An independent read-only sonnet reviewer (claude-sonnet-5-5) reported NO BLOCKERS on these exact bytes at 2026-11-09T03:59:09Z. It recomputed the digest itself, confirmed both departures, and checked that the paragraph composes with retention, provider-only deletion, deletion pacing and deferral, the stop rule and idempotence. Its non-blocking notes, for the implementing carrier bd-ib-q4xgcp: a refusal for a run unresolvable in every ledger still names 'the dispatching repository', which the run's recorded provenance is expected to supply; whether retention at `blocked` counts as a 'refusal' is undefined (the scenario asserts no journal for run F); and 'periodic pass on a dispatching host' and 'dispatching repository' are used without a definition. No H2 heading changes, so tests/heading-coverage.json needs no co-edit.

## Modifications

(1) The journal sentence of the new contracts.md paragraph ends 'the item status the pass read, or that no status could be read.' The proposal stopped at 'the pass read'. (2) The new Scenario 281 case's final step is split into two: run E's collection names the closed status it read, and run G's refusal names that no status could be read. Every other word of the proposal's paragraph and scenario is kept, at the positions the proposal names: after the paragraph beginning 'Once the run's work-item is closed', and at the end of Scenario 281's gherkin block after 'Deletions against a busy factory are paced host-wide'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T03:59:09Z
verdict: NO BLOCKERS
proposal_stem: ended-runs-of-a-closed
content_digest: 58809af3372ff86205437e514e27bc9f614efeefbb901b419f86ea2976f87f35
