# Handoff - local-memory cleanup

## Purpose

This thread records the `livespec-orchestrator-beads-fabro` disposition for the
Claude local-memory records inventoried by the livespec-owned
`plan/cloud-local-memory-cleanup/` thread on 2026-07-13. The source records were
host-local harness memory, not committed repo `.claude/` files.

## Source Inventory

Source store:
`/home/ubuntu/.claude/projects/-data-projects-livespec-orchestrator-beads-fabro/memory/`

Inventory artifact:
`livespec/plan/cloud-local-memory-cleanup/research/2026-07-13-inventory-classification.md`

Migration owner: `bd-ib-jz62h3`

| Source file | Inventory SHA-256 prefix | Classification | Disposition |
|---|---|---|---|
| `MEMORY.md` | `e2e250f524d9` | `index` | Dropped as harness-local index metadata. It carried no durable guidance by itself; no repo content is needed. |
| `wism-l1a-rollout-state.md` | `17f8b35c3786` | `project-runbook` | Archived into the repo-owned work-item-state-machine record. Durable destination: `plan/archive/work-item-state-machine/handoff.md` section `Local-Memory Migration Provenance`, with the current rollout state already recorded in that handoff and `plan/archive/work-item-state-machine/l2-tenant-migration.md`. |

## Result

No spec follow-up is required for this repo: the work-item-state-machine
contracts and scenarios already live in `SPECIFICATION/`, and the source memory
record described rollout state rather than new normative behavior.

No ledger follow-up is required for this repo: the L1a epic `bd-ib-vvrxcb`, its
seven child slices, the release slice, and the L2 tenant migration state are
already recorded in the repo-owned archived plan thread. The family-level
cleanup follow-up that may quarantine or delete the host-local memory file
remains outside this repo and should run only after this migration lands.
