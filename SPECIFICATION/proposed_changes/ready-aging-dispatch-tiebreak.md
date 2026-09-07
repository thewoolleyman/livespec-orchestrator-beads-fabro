---
topic: ready-aging-dispatch-tiebreak
author: claude-opus (control-plane-accounts-and-dispatch-policy)
created_at: 2026-09-07T04:21:24Z
---

## Proposal: Ready-aging tiebreak in the dispatch ready ordering

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend the ranking-authority clause so the ready ordering breaks EQUAL-RANK ties by ready-age: a ready item that has waited past `dispatcher.ready_aging_threshold_hours` is ordered ahead of newer equal-rank items, while `rank` remains the primary key and `next` and the Dispatcher still compose one identical ordering. Reuses the existing 24h threshold and the durable `ready_since` instant, and adds a scenario binding the tiebreak. The aging SURFACING (the `hygiene:ready-aging` fact) already exists; this adds only the ordering behavior.

### Motivation

b5 leg 4 of plan control-plane-accounts-and-dispatch-policy (epic bd-ib-rh3iyd, child bd-ib-rh3iyd.2). It transfers the deprecated foreman starvation rule (livespec-overseer overseer-7ranbh, closed; overseer-5ugiuj.5 cites this id by name). Prior-art check: the criterion to surface an aged ready item with its age is already shipped as the `hygiene:ready-aging:<repo>` fact (contracts.md 'Ready-work aging', Scenario 84, _needs_attention_ready_aging.py); the genuinely net-new part is the ORDERING tiebreak, which the current ranking-authority clause forbids by declaring `(rank, id)` the sole ordering authority. The age input (`ready_dwell_instants` from the durable `ready_since` beads metadata) and the bound (`dispatcher.ready_aging_threshold_hours`, default 24) already exist and are reused unchanged.

### Proposed Changes

Amend `SPECIFICATION/contracts.md` and add a scenario to `SPECIFICATION/scenarios.md`.

**contracts.md — amend the ranking-authority clause** (the clause currently stating the ready ranking IS `ready_sort_key` = `(rank, id)` and is the sole ordering authority that `next` and the Dispatcher compose).

The ready ordering MUST continue to use `rank` as its primary ordering key. Among ready items of EQUAL rank, the ordering MUST break ties by ascending ready-age once an item has been ready longer than `dispatcher.ready_aging_threshold_hours`: such an aged item MUST be ordered ahead of newer equal-rank items, and equal-rank items that have NOT yet passed the bound MUST retain the deterministic `id` lexicographic tiebreak. This is a TIEBREAK strictly WITHIN a rank tier; it MUST NOT promote any item across rank tiers, so a higher-`rank` item is never overtaken by a lower-`rank` aged item.

`next` and the Dispatcher MUST compose ONE identical aging-aware ready ordering and MUST NOT diverge; the aging-aware key MUST be applied at every point either surface orders ready work. The ready-age MUST be measured from the durable, clone-independent instant of the item's latest transition into `ready` (the same `ready_since` source the aging surfacing already reads), and MUST NOT be read from a machine-local dispatch journal. An item whose ready instant is unknowable MUST retain the `id` tiebreak and MUST NOT receive any age-based ordering advantage. The bound MUST reuse the existing `dispatcher.ready_aging_threshold_hours` setting; this change adds NO new config key and NO per-item override.

**scenarios.md — add a new `## Scenario` binding the tiebreak.**

Add a scenario asserting: given two ready items of equal `rank` where one has been ready past `dispatcher.ready_aging_threshold_hours` and the other has not, when `next` ranks the candidates and when the Dispatcher composes its drain order, then the aged item MUST be ordered ahead of the newer equal-rank item and the two surfaces MUST agree; given an equal-rank pair where neither has passed the bound, the `id` lexicographic tiebreak MUST hold; and given an aged item whose ready instant is unknowable, it MUST retain the `id` tiebreak with no age advantage. A higher-`rank` item MUST remain ahead of a lower-`rank` aged item. The revise that ratifies this scenario MUST update `tests/heading-coverage.json` in the same commit so the new scenario heading is bound to its exercising tests.
