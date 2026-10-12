---
proposal: dispatcher-level-model-fallback.md
decision: modify
revised_at: 2026-10-12T09:16:02Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies the maintainer's 2026-10-12 decision that ordered model fallback moves from the Fabro engine (cross-candidate fallback inside one node visit via acp.fallback_chain, which the Petri engine rejects) to the Dispatcher, with the stated priority of preventing stalls and avoiding needless delegation to a human, recoverable lost work being acceptable. The independent ratification reviewer (OpenAI Codex gpt-6-astra, read-only, the repo's configured ratification_reviewer_model) first returned ACCEPT-WITH-CHANGES with eleven required changes; the maintainer's plan session accepted all eleven, so the decision is modify: every proposal finding is applied as modified by those changes, and the same reviewer confirmed the exact final bytes NO BLOCKERS. The departed-from design record is v112's engine-side same-visit fallback (its one-node-visit, shared-deadline, partial-write hand-off, failover-event projection and stop-picking clauses), deliberately retired because it cannot be met on the Petri engine; the investigation behind the decision is committed at plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md, and every citation of it and of its D1-D13/E1-E8 findings in the archived proposal now resolves to that path.

## Modifications

The eleven proposal findings are applied as modified by the reviewer's eleven required changes:
1. Host-wide holds: the optional dispatcher.hold_peer_repositories peer-journal list and its fail-open hygiene fact are removed. Availability evidence is discoverable host-wide from factory-native run records of every factory declared under dispatcher.factories; each recorded attempt identifies factory, repository, run, node attempt, candidate entitlement, occurrence time and typed outcome; observations, confirmations and operator clearances are factory-native records so retirement is reconstructible after a repository-local journal is removed; journals are audit references only; an unreadable source is unavailable, never an empty hold set. constraints.md 'No off-substrate persistence' gains the factory-native evidence exception (no hold sidecar; tenant DB authority over work-item state unchanged). The 'at most one provider-limit attempt' claim is dropped.
2. Conservative admission: every ACP node potentially reachable in the submitted graph must have an eligible candidate before submission; a conditional node is never rendered with a held candidate (the proposal's earliest-expiry rule is removed). The predicate ('admission-required') is applied to the opening paragraph, admission valve and eligibility, rework preconditions, provider spend containment, idle-factory and wait attention, and Scenarios 60, 85, 120, 121, 127 and 128.
3. Per-node selection uses the reviewer's eligibility rule; availability confirmation requires a successfully completed ACP prompt turn with the candidate's pinned adapter version, model, effort and projected credential identity (host-side only when equivalent and durably observable through the same source, otherwise a minimal factory run); confirmation satisfies only the expired observations it names; non-eligible probe failures skip without a hold; no-eligible-candidate waits retry after dispatcher.credential_reprobe_interval_seconds; probes are bounded by dispatcher.availability_probe_timeout_seconds (default 120); scheduled waits survive restart, never busy-loop, and clearance makes them immediately reevaluable.
4. Provider-limit release is idempotent and replayable keyed by factory, run and failing node attempt; the released failure is the unrecovered failure responsible for the terminal disposition; unreadable failure evidence is surfaced and retried, never a non-match or a needs-human decision.
5. Recovery: resume preconditions are evaluated before stale publish-branch reclaim and the Dispatcher invokes resume itself when they pass; otherwise a plain dispatch seeded from preserved work (seed record names source run, remote, immutable SHA and preservation reference; preference order terminal preserved tree, then published head or preserved-publish ref; preservation verified before deletion; unreadable is not confirmed absence). The resume section's plain-dispatch and impl:<id> statements and the reclaim section's operator-choice sentence are qualified for this exception.
6. Detection: attribution comes from the executed candidate identity; structured fields parsed as fields; both Codex spellings recognized; a Claude rate_limit kind alone is not quota exhaustion; provider-limit-release covers every eligible availability cause while the typed provider-usage-limit flag stays specific to usage or spend ceilings; identity-less legacy adapters keep the legacy observation and release to ready.
7. Cost: the fail-closed cost gate's opening and its first coverage bullet are rewritten (gate applies only to successful confirmed runs; failed-run and probe cost observation is independent); the cost-gate scenario's result uses the reviewer's three lines; sequence accounting adds stable identities, count-once, unobservable totals with labeled incomplete subtotals, and no full double-charging of a shared probe.
8. config_options: the permanence carve-out sentence uses the reviewer's replacement; the selected candidate's config_options travel through a supported single-node mechanism independent of acp.fallback_chain, a missing or unreadable required capability refuses before claim, and a dispatch with no selected protocol-configured candidate needs no capability.
9. Warning observation: reconciliation replays selection-to-execution idempotently; unreadable node outcomes are unavailable, retried, never clear a warning and never create a needs-human decision; existing versioned holds, retirement and fallback audit records remain readable.
10. Scenarios: Scenario 127 is rewritten with the reviewer's admission fixture and non-match lines and new sub-scenarios for a held conditional node, a timed-out probe, restart replay of release, a third resume falling back to preserved-tree plain dispatch, an unreadable availability source, and journal removal; Scenario 65 gains the Claude usage-limit and Codex 'usage limit exceeded' message forms, key-order/whitespace and shared-message attribution controls, and a rate_limit-without-sentence control; Scenario 60 replaces the peer-list sub-scenario with a host-wide factory-native one and adds the restart clause to the scheduled-wait sub-scenario.
11. Citations: the investigation report is committed at plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md and the archived proposal's eleven motivation citations, its abbreviated fabro-currency research references (001, 002 row 23, 003, 007 probe p6) and its measured counts now resolve to committed paths.
Optional suggestion applied as a consistency fix: 'permanent' is defined in the permanence section as unsuitable for immediate retry within the current allowance window, not unavailable forever. The availability-release rename was not applied.
Heading coverage: Scenario 127's coverage row is re-keyed to the renamed heading. The ratified shrink-only debt register refuses a TODO for a renamed heading, so the row is bound to the surviving integration test of the release-floor case with a reason naming the owed Dispatcher-level journey test and its owner bd-ib-jxvgq5.

## Resulting Changes

- constraints.md
- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-12T09:15:42Z
verdict: NO BLOCKERS
proposal_stem: dispatcher-level-model-fallback
content_digest: 851ddbaf9bf327d614a735fb466367e23589cfebe3ccb582182abc1a1e9d432b
