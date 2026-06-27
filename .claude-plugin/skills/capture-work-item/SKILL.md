---
name: capture-work-item
description: Freeform direct filing of an impl-side work item (bugs, refactors, tactical tasks). Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md. Filed records carry `origin: freeform` and `gap_id: null`. Invoke as `/livespec-orchestrator-beads-fabro:capture-work-item`.
allowed-tools: Bash, Read, Grep, Write
---

# capture-work-item — Claude Code binding

This file is the thin Claude Code binding for the `capture-work-item`
operation of the **livespec-orchestrator-beads-fabro** plugin. The
complete harness-neutral driving prose — the consent flow, the
multi-step dialogue, the `livespec_orchestrator_beads_fabro.*` package
calls, and the intake Definition-of-Ready semantics — is the plugin's
own artifact at `${CLAUDE_PLUGIN_ROOT}/prose/capture-work-item.md`. Read
that prose file in full, then execute it end-to-end, binding its
harness-neutral vocabulary to this runtime per `## Runtime bindings`
below.

```bash
cat "${CLAUDE_PLUGIN_ROOT}/prose/capture-work-item.md"
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
  tool. **Python snippets** — run via the Bash tool against the bundled
  `livespec_orchestrator_beads_fabro` package (the wrappers self-bootstrap
  the import path).
- **"the `capture-impl-gaps` / `implement` / `groom` operation"** — the
  `/livespec-orchestrator-beads-fabro:capture-impl-gaps`,
  `/livespec-orchestrator-beads-fabro:implement`, and
  `/livespec-orchestrator-beads-fabro:groom` skills in this plugin.
