---
name: orchestrate
description: Compose spec-side next and impl-side next, present operator-selectable actions, and dispatch selected factory-safe impl work through Dispatcher/Fabro. Invoke as `/livespec-orchestrator-beads-fabro:orchestrate plan --repo <path> --json` or `/livespec-orchestrator-beads-fabro:orchestrate run --repo <path> --action <action-id> --json`.
allowed-tools: Bash
---

# orchestrate

Thin operator binding over the shared Python CLI:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/orchestrate.py" "$@"
```

## Commands

- `plan --repo <path> [--json]` — run spec-side `next` and impl-side
  `next`, then emit selectable action records. This is read-only.
- `run --repo <path> --action <action-id> [--json]` — run one selected
  action. `impl:<work-item-id>` dispatches through Dispatcher/Fabro in
  `shadow` mode with `budget=1` and `parallel=1`. `spec:<action>:<n>`
  returns a human handoff such as `/livespec:revise --spec-target
  SPECIFICATION/`; it never mutates spec state directly.

## Operator Flow

1. Invoke `plan --repo <path> --json`.
2. Present the returned `actions[]` to the user.
3. Invoke `run --repo <path> --action <id> --json` only for the action
   the user selected.
4. Summarize `status`, Dispatcher exit code, PR/run fields present in
   `dispatcher.stdout_json`, and any human handoff.

This skill does not create work-items and does not duplicate ranking
logic from either `next` surface.
