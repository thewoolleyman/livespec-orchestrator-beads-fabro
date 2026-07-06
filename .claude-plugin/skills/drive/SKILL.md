---
name: drive
description: Execute one livespec-orchestrator-beads-fabro action-id: impl:<id> dispatch, approve/accept/reject valves, or set-admission/set-acceptance policy edits. Invoke as `/livespec-orchestrator-beads-fabro:drive --action <action-id> [--repo <path>] [--json]`.
allowed-tools: Bash
---

# drive

Thin operator binding over the shared Python CLI:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/drive.py" "$@"
```

## Command

`--action <action-id> [--repo <path>] [--json]` executes exactly one action-id. `--repo` defaults to the current working directory. `--json` emits the machine-readable result; Markdown is the default human output.

Accepted action ids:

- `impl:<work-item-id>` dispatches the selected implementation work-item through Dispatcher/Fabro in `shadow` mode with `budget=1`, `parallel=1`, and `--item <work-item-id>`.
- `approve:<work-item-id>` moves an effective-manual `pending-approval` item to `ready`.
- `accept:<work-item-id>` moves an `acceptance` item to `done`.
- `reject:<work-item-id>:rework` moves an `acceptance` item back to `active`.
- `reject:<work-item-id>:regroom` reverts the recorded merge SHA, then moves an `acceptance` item to `backlog`.
- `set-admission:<work-item-id>:auto|manual` updates admission policy without changing status.
- `set-acceptance:<work-item-id>:ai-only|human-only|ai-then-human` updates acceptance policy without changing status.

`drive` does not plan, rank, compose spec-side and impl-side `next`, present an interactive walkthrough, execute spec-side indexed action ids, or create work-items. Spec lifecycle actions remain human handoffs outside this executor.
