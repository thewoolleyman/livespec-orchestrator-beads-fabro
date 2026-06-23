---
name: capture-impl-gaps
description: Detect spec→impl gaps by invoking the sibling detect-impl-gaps thin-transport skill, then file gap-tied work-items into the beads-backed store with per-gap user consent. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (5)". Invoke as `/livespec-orchestrator-beads-fabro:capture-impl-gaps`.
allowed-tools: Bash, Read, Grep, Glob, Write
---

# capture-impl-gaps — Claude Code binding

This file is the thin Claude Code binding for the `capture-impl-gaps`
operation of the **livespec-orchestrator-beads-fabro** plugin. The
complete harness-neutral driving prose — the `detect-impl-gaps`
invocation flow, the per-rule classification, the per-gap consent +
filing, and the intake Definition-of-Ready semantics — is the plugin's
own artifact at `${CLAUDE_PLUGIN_ROOT}/prose/capture-impl-gaps.md`. Read
that prose file in full, then execute it end-to-end, binding its
harness-neutral vocabulary to this runtime per `## Runtime bindings`
below.

```bash
cat "${CLAUDE_PLUGIN_ROOT}/prose/capture-impl-gaps.md"
```

This binding adds NO operation behavior of its own; all orchestration
lives in the prose.

## Runtime bindings

- **`<plugin-root>`** — the live `${CLAUDE_PLUGIN_ROOT}` token in this
  Claude Code skill. The prose's
  `python3 "<plugin-root>/scripts/bin/detect_impl_gaps.py"` invocations
  run via the Bash tool with `<plugin-root>` → `${CLAUDE_PLUGIN_ROOT}`.
- **"the `detect-impl-gaps` operation"** — the
  `/livespec-orchestrator-beads-fabro:detect-impl-gaps` thin-transport
  skill in this plugin (invoked here directly through its wrapper script
  per the `<plugin-root>` binding above).
- **"ask the user" / "confirm with the user" / "surface" / "narrate"** —
  conversational turns in this session (the AskUserQuestion tool or plain
  narration, as appropriate; ask one question at a time).
- **"read `<file>`"** — the Read tool. **"write `<file>`"** — the Write
  tool. **Python snippets** — run via the Bash tool against the bundled
  `livespec_orchestrator_beads_fabro` package (the wrappers self-bootstrap
  the import path).
- **"the `implement` / `capture-spec-drift` / `groom` operation"** — the
  `/livespec-orchestrator-beads-fabro:implement`,
  `/livespec-orchestrator-beads-fabro:capture-spec-drift`, and
  `/livespec-orchestrator-beads-fabro:groom` skills in this plugin.
