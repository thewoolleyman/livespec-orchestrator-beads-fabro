---
name: capture-spec-drift
description: Detect impl→spec drift heuristically (LLM-driven) and hand off each finding to /livespec:propose-change with user consent. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (5)". Invoke as `/livespec-orchestrator-beads-fabro:capture-spec-drift`.
allowed-tools: Bash, Read, Grep, Glob, Write
---

# capture-spec-drift — Claude Code binding

This file is the thin Claude Code binding for the `capture-spec-drift`
operation of the **livespec-orchestrator-beads-fabro** plugin. The
complete harness-neutral driving prose — the Spec Reader baseline load,
the impl-tree survey, the per-finding consent, and the cross-boundary
propose-change handoff — is the plugin's own artifact at
`${CLAUDE_PLUGIN_ROOT}/prose/capture-spec-drift.md`. Read that prose file
in full, then execute it end-to-end, binding its harness-neutral
vocabulary to this runtime per `## Runtime bindings` below.

```bash
cat "${CLAUDE_PLUGIN_ROOT}/prose/capture-spec-drift.md"
```

This binding adds NO operation behavior of its own; all orchestration
lives in the prose.

## Runtime bindings

- **"the propose-change operation"** — the
  `/livespec:propose-change` skill (the cross-boundary handoff to
  livespec core). The prose's
  `the propose-change operation --spec-target … --topic … --body …`
  invocation maps to
  `/livespec:propose-change --spec-target … --topic … --body …`.
- **"ask the user" / "confirm with the user" / "surface" / "narrate"** —
  conversational turns in this session (the AskUserQuestion tool or plain
  narration, as appropriate; ask one question at a time).
- **"read `<file>`"** — the Read tool. **Python snippets** (e.g. the Spec
  Reader `read_current_specification` call) — run via the Bash tool
  against the bundled `livespec_orchestrator_beads_fabro` package (the
  wrappers self-bootstrap the import path).
- **"the `capture-impl-gaps` operation"** — the
  `/livespec-orchestrator-beads-fabro:capture-impl-gaps` skill in this
  plugin.
