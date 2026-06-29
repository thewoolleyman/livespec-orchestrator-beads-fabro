---
proposal: work-item-state-machine.md
decision: accept
revised_at: 2026-06-29T14:20:29Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: wism-l1a-beads-fabro
---

## Decision and Rationale

AUTO-RATIFY per the LOCKED fleet design (decisions 1-46; cross-repo design of record at livespec/plan/work-item-state-machine/research/). This is the L1a orchestrator slice: the beads 7-state custom-status encoding + 2-step append + rank/policy field homes (decisions 36/39), the new Dispatcher admission valve + per-repo WIP cap + post-merge acceptance H2 (decisions 7/9/10/22/26/33/34), list-work-items lane/lane_reason emission (decision 40), next rank ordering (decision 39), and the resolution of the two previously-open realization choices (needs-regroom -> backlog bounce, decision 32; groom is its own skill). Load-bearing behaviors are paired to Scenarios 22-28 (authoring discipline (i)); the one new contracts H2 + the seven new scenario H2s are co-registered in tests/heading-coverage.json in the same change. doctor-static and heading_coverage previewed green against the edited tree.

## Resulting Changes

- contracts.md
- scenarios.md
