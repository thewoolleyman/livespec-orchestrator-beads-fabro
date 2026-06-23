---
name: implement
description: Drive Red→Green for a single work-item. For gap-tied items, verify closure by re-running capture-impl-gaps in dry-run mode. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (5)". Invoke as `/livespec-orchestrator-beads-fabro:implement [<work-item-id>]`.
allowed-tools: Bash, Read, Grep, Glob, Edit, Write
---

# implement — Claude Code binding

This file is the thin Claude Code binding for the `implement` operation
of the **livespec-orchestrator-beads-fabro** plugin. The complete
harness-neutral driving prose — the disposition/consent flow, the
Red→Green driving steps, the gap-tied closure re-detection, the
`livespec_orchestrator_beads_fabro.*` package calls, and the
closure-record semantics — is the plugin's own artifact at
`${CLAUDE_PLUGIN_ROOT}/prose/implement.md`. Read that prose file in
full, then execute it end-to-end, binding its harness-neutral
vocabulary to this runtime per `## Runtime bindings` below.

```bash
cat "${CLAUDE_PLUGIN_ROOT}/prose/implement.md"
```

This binding adds NO operation behavior of its own; all orchestration
lives in the prose.

## Runtime bindings

- **`<plugin-root>`** — the live `${CLAUDE_PLUGIN_ROOT}` token in this
  Claude Code skill. Any `python3 "<plugin-root>/scripts/bin/<x>.py"`
  invocation in the prose runs via the Bash tool with
  `<plugin-root>` → `${CLAUDE_PLUGIN_ROOT}`.
- **"ask the user" / "confirm with the user" / "surface" / "narrate"** —
  conversational turns in this session (the AskUserQuestion tool or plain
  narration, as appropriate; ask one question at a time).
- **"read `<file>`"** — the Read tool. **"write `<file>`"** — the Write
  or Edit tool. **Python snippets** — run via the Bash tool against the
  bundled `livespec_orchestrator_beads_fabro` package (the wrappers
  self-bootstrap the import path).
- **"the `next` operation"** — the
  `/livespec-orchestrator-beads-fabro:next` skill in this plugin.
- **"the `capture-impl-gaps` / `capture-work-item` operation"** — the
  `/livespec-orchestrator-beads-fabro:capture-impl-gaps` and
  `/livespec-orchestrator-beads-fabro:capture-work-item` skills in this
  plugin.
