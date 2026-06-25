---
name: plan
description: Open or resume a durable, multi-session planning thread in `plan/<topic>/` (reasoning + a self-sufficient handoff), anchor a ledger epic, route matured pieces to the spec lifecycle or the ledger, and archive on close. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (6)"; the Orchestrator-Plane realization of the Planning Lane. Invoke bare as `/livespec-orchestrator-beads-fabro:plan` to create or resume interactively, or `/livespec-orchestrator-beads-fabro:plan <slug>` to resume an existing thread strictly.
allowed-tools: Bash, Read, Grep, Glob, Write
---

# plan — Claude Code binding

This file is the thin Claude Code binding for the `plan` operation of
the **livespec-orchestrator-beads-fabro** plugin. The complete
harness-neutral driving prose — the planning-thread create/resume
dialogue, the reasoning-capture and handoff-refresh writes, the
matured-piece routing, the handoff self-sufficiency gate, the
archive-on-close transition, and the `livespec_orchestrator_beads_fabro.*`
package calls — is the plugin's own artifact at
`${CLAUDE_PLUGIN_ROOT}/prose/plan.md`. Read that prose file in full,
then execute it end-to-end, binding its harness-neutral vocabulary to
this runtime per `## Runtime bindings` below.

```bash
cat "${CLAUDE_PLUGIN_ROOT}/prose/plan.md"
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
- **"read `<file>`"** — the Read tool. **"write `<file>`"** — the Write
  tool. **Enumerate `plan/` directories** — the Glob tool.
  **Python snippets** and **`git` checks** — run via the Bash tool
  against the bundled `livespec_orchestrator_beads_fabro` package (the
  wrappers self-bootstrap the import path).
- **"fresh-context reader" (the cold-open readiness test)** — the
  Task/Agent sub-agent facility when this runtime exposes one to skills
  (launch a reader that opens ONLY the handoff and its read-first
  chain); otherwise a deliberately cleared re-read via the Read tool
  that consults only those paths and ignores conversational context.
- **"the `list-work-items` / `next` operation"** — the
  `/livespec-orchestrator-beads-fabro:list-work-items` and
  `/livespec-orchestrator-beads-fabro:next` skills in this plugin (the
  read-only status surface).
- **"the `capture-work-item` operation"** — the
  `/livespec-orchestrator-beads-fabro:capture-work-item` skill in this
  plugin (the epic-anchor and child-work-item filing seam).
- **"the `propose-change` operation"** — the cross-boundary
  `/livespec:propose-change` skill of the **livespec** plugin (the
  matured-to-spec handoff target).
