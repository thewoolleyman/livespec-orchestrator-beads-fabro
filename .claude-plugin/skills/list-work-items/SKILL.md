---
name: list-work-items
description: List work-items from the beads-backed work-items store. Required thin-transport surface per livespec/SPECIFICATION/contracts.md §"Thin-transport skills (3) — required machine query surface". Invoke as `/livespec-impl-beads:list-work-items [--filter <name>] [--with-gap-id <id>] [--json]`.
allowed-tools: Bash
---

# list-work-items

Thin-transport pass-through. All behavior lives in
`.claude-plugin/scripts/livespec_impl_beads/commands/list_work_items.py`.

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
  `/livespec-impl-beads:list-work-items --json` to enumerate the
  materialized state.
- The project-local Layer 3 loop driver inspects the queue.
