---
proposal: rename-orchestrator-beads-fabro-refs.md
decision: accept
revised_at: 2026-06-22T01:25:37Z
author_human: E2E Test <e2e-test@example.com>
author_llm: orchestrator-rename-4moata.4.15
---

## Decision and Rationale

Spec-prose half of the orchestrator-rename wave for impl-beads. Renames livespec-impl-beads -> livespec-orchestrator-beads-fabro (the 33-char repo/plugin/package name) across titles, the /livespec-orchestrator-beads-fabro: namespace, plugin-block keys, and prose. EXCEPTIONS: the connection-block value fields (tenant/prefix/database/server_user) use livespec-orch-beads-fabro (25-char) to match the live .livespec.jsonc and Dolt's 32-char username limit; the three frozen work-item-ID citations (livespec-impl-beads-i3jiny) are preserved unchanged. Also: the stale connection-example `socket` key is dropped (the live config is TCP-only), and the realization-list names in spec.md are updated to the new orchestrator- convention (the real renamed git-jsonl plus the three on-paper hypotheticals gitlab/gascity/darkfactory-kilroy, for list consistency). Immutable history snapshots untouched; H2 heading set unchanged.

## Resulting Changes

- spec.md
- constraints.md
- scenarios.md
- README.md
- contracts.md
