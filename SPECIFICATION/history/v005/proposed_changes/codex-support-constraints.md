---
topic: codex-support-constraints
author: codex-gpt-5
created_at: 2026-06-19T17:50:10Z
---

## Proposal: Codex adapter and hook support constraints

### Target specification files

- SPECIFICATION/constraints.md

### Summary

State how Codex support applies to the beads implementation plugin without copying Claude-specific skill bodies or assuming Claude-only hooks run under Codex.

### Motivation

The family-wide Codex audit found that impl-plugin specs mention AGENTS.md/Codex for persistent-knowledge loading, but do not state the required Codex adapter boundary, Dolt/beads substrate expectations, or hook/manual-verification requirements.

### Proposed Changes

In `SPECIFICATION/constraints.md`, add a bullet under the existing `## Skill orchestration constraints` section. The text should state that Codex support is required as a first-class agent-runtime consideration, that Codex adapters must be thin runtime bindings over the same wrapper CLIs / beads tenant semantics / consent rules rather than copies of Claude SKILL.md bodies, that thin-transport behavior remains zero-orchestration, that Claude-only hooks are not assumed to run under Codex, and that any Codex adapter or hook replacement must be manually verified before support is claimed.
