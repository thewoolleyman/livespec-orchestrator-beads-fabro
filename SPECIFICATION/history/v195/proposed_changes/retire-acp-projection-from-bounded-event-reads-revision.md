---
proposal: retire-acp-projection-from-bounded-event-reads.md
decision: modify
revised_at: 2026-10-21T20:23:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:factory-configurable-model-fallback-priority
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session factory-configurable-model-fallback-priority (plan bd-ib-jxvgq5), which coordinator gitops-fleet-capacity-monitoring assigned this amendment as ruling R521 on 2026-10-21. The proposal is a conformance repair and departs from no design record: v127 (proposal dispatcher-level-model-fallback, 'Retire engine failover events and their projection', design record plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md) retired the agent.acp.failover projection, and v176 later named that retired reader as a caller of '### Bounded Fabro event reads' and mandated an acp-projection-exhausted record for it. Striking the reader restores the v127 ruling; the read-size, failed-read backoff and concurrency bounds on every remaining caller are unchanged, so bd-ib-2dlh7m keeps its scope minus the exhaustion assertion. The contradiction was blocking: bd-ib-qm6r1 (PR 3336), which deletes the retired projection code, was refused on both legs of its launch-time Definition-of-Done preflight (gate 20261021T200550Z-2517949) because its removal assertion conflicted with v176. The configured ratification reviewer, gpt-6-astra, in a separate read-only Codex session, returned NO BLOCKERS on the exact resulting bytes in round 1 (digest 42126dde5b9df25903816da79a72baf2e8eae3c7bcf868787aeda737bb76fbe7) and independently recomputed that digest.

## Modifications

Accepted as proposed with one placement change: the proposal's trailing prose rule that a journal reader MUST still parse already-written acp-projection records is folded into the new 'No projection reader' paragraph of contracts.md as its last sentence, naming both acp-projection-failure and acp-projection-exhausted records. Every other byte follows the proposal's diffs.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T20:23:18Z
verdict: NO BLOCKERS
proposal_stem: retire-acp-projection-from-bounded-event-reads
content_digest: 42126dde5b9df25903816da79a72baf2e8eae3c7bcf868787aeda737bb76fbe7
