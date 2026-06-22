---
topic: rename-orchestrator-beads-fabro-refs
author: orchestrator-rename-4moata.4.15
created_at: 2026-06-22T01:25:36Z
---

## Proposal: Rename impl-beads plugin and repo references to orchestrator-beads-fabro

### Target specification files

- spec.md
- contracts.md
- constraints.md
- scenarios.md
- README.md

### Summary

Align the dogfooded specification prose with the orchestrator-rename wave: rename the retired name `livespec-impl-beads` to the current `livespec-orchestrator-beads-fabro` (repo/plugin/package, 33 chars) across the current spec files, with the connection-block value fields using the 25-char Beads tenant `livespec-orch-beads-fabro` to match the live `.livespec.jsonc` and Dolt's 32-char username limit.

### Motivation

The reference orchestrator was renamed family-wide (the `impl-` prefix dropped to `orchestrator-`): GitHub repository, local clone, Python package, plugin identity and the `/livespec-orchestrator-beads-fabro:*` skill namespace, configs, and CI. Because the repo/plugin name (`livespec-orchestrator-beads-fabro`, 33 chars) exceeds Dolt's 32-char SQL-username limit, the Beads tenant uses the abbreviated `livespec-orch-beads-fabro` (25 chars). The dogfooded SPECIFICATION prose still cites the retired `livespec-impl-beads` name. This is the spec-prose half of the rename wave (work-item 4moata.4.15).

### Proposed Changes

Rename `livespec-impl-beads` -> `livespec-orchestrator-beads-fabro` (33-char repo/plugin name) in the current spec files for all titles, the `/livespec-orchestrator-beads-fabro:` skill namespace, the `.livespec.jsonc` plugin-block keys, and prose. THREE context-specific exceptions: (1) the `connection` block's value fields in `contracts.md` (`tenant`, `prefix`, `database`, `server_user`) use the 25-char tenant `livespec-orch-beads-fabro`, matching the live config and Dolt's 32-char limit; (2) the three frozen work-item-ID citations `livespec-impl-beads-i3jiny` (scenarios.md, contracts.md x2) are preserved unchanged because work-item IDs are immutable; (3) the stale `socket` key in the `contracts.md` connection example is dropped, since the live config is TCP-only. Additionally, the realization-list names in `spec.md` are updated to the new `orchestrator-` convention (the real renamed `livespec-orchestrator-git-jsonl` plus the on-paper hypotheticals `livespec-orchestrator-{gitlab,gascity,darkfactory-kilroy}`) so the list reflects the current naming convention consistently. `SPECIFICATION/history/` snapshots are immutable and untouched; the H2 heading set is unchanged, so `tests/heading-coverage.json` needs no co-edit.
