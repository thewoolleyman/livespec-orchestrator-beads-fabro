---
name: list-work-items
description: List work-items from the beads-backed work-items store. Required thin-transport surface per livespec/SPECIFICATION/contracts.md. Invoke as `/livespec-orchestrator-beads-fabro:list-work-items [--filter <name>] [--with-gap-id <id>] [--json]`.
allowed-tools: Bash
---

# list-work-items

Thin-transport pass-through. All behavior lives in
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/list_work_items.py`.

## Invocation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/list_work_items.py" "$@"
```

Supported flags:

- `--filter=<all|gap-tied|freeform|blocked|ready|closed>` (default `all`)
- `--with-gap-id <id>` — exact gap_id match (combinable with --filter)
- `--json` — emit JSON array of work-item materialized views
- `--work-items-path <path>` — override the default `work-items.jsonl`
  location

## When to use

- User asks "what work-items are open / ready / blocked?"
- Doctor's four work-item structural invariants invoke
  `/livespec-orchestrator-beads-fabro:list-work-items --json` to enumerate the
  materialized state.
- The Dispatcher polls this surface when selecting which ready work-item to dispatch next.
