---
name: groom
description: Regroom an oversized or non-converging `needs-regroom` work-item into ready, dependency-layered slices. Read-only drafting conversation — the maintainer OWNS the cut and the acceptance; the front-end drafts and files NOTHING until approval. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Skills — augmented versus new" (the one new maintainer surface). Invoke as `/livespec-orchestrator-beads-fabro:groom <work-item-id>`.
allowed-tools: Bash, Read, Grep, Glob
---

# groom — Claude Code binding

This file is the thin Claude Code binding for the `groom` operation of
the **livespec-orchestrator-beads-fabro** plugin. The complete
harness-neutral driving prose — the read-only grooming-context load,
the agent-drafts / human-approves decomposition dialogue, the
approved-slice filing and regroom-out transition, the spec-change
routing, and the `livespec_orchestrator_beads_fabro.*` package calls —
is the plugin's own artifact at `${CLAUDE_PLUGIN_ROOT}/prose/groom.md`.
Read that prose file in full, then execute it end-to-end, binding its
harness-neutral vocabulary to this runtime per `## Runtime bindings`
below.

```bash
cat "${CLAUDE_PLUGIN_ROOT}/prose/groom.md"
```

This binding adds NO operation behavior of its own; all orchestration
lives in the prose.

## Runtime bindings

- **`<plugin-root>`** — the live `${CLAUDE_PLUGIN_ROOT}` token in this
  Claude Code skill. Any `python3 "<plugin-root>/scripts/bin/<x>.py"`
  invocation in the prose runs via the Bash tool with
  `<plugin-root>` → `${CLAUDE_PLUGIN_ROOT}`.
- **"ask the user" / "confirm with the user" / "surface" / "narrate" /
  "present the draft to the maintainer"** — conversational turns in this
  session (the AskUserQuestion tool or plain narration, as appropriate;
  ask one question at a time).
- **"read `<file>`"** — the Read tool. **Python snippets** — run via the
  Bash tool against the bundled `livespec_orchestrator_beads_fabro`
  package (the wrappers self-bootstrap the import path).
- **"the `list-work-items` operation"** — the
  `/livespec-orchestrator-beads-fabro:list-work-items` skill in this
  plugin.
- **"the `propose-change` operation"** — the cross-boundary
  `/livespec:propose-change` skill of the **livespec** plugin (the
  spec-change handoff target).
- **"the `capture-work-item` / `capture-impl-gaps` / `capture-spec-drift`
  operation"** — the
  `/livespec-orchestrator-beads-fabro:capture-work-item`,
  `/livespec-orchestrator-beads-fabro:capture-impl-gaps`, and
  `/livespec-orchestrator-beads-fabro:capture-spec-drift` skills in this
  plugin.
