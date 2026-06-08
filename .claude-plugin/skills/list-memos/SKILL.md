---
name: list-memos
description: List memos from the beads-backed memos store. Required thin-transport surface per livespec/SPECIFICATION/contracts.md §"Thin-transport skills (3) — required machine query surface". Invoke as `/livespec-impl-beads:list-memos [--filter <name>] [--json]`.
allowed-tools: Bash
---

# list-memos

This is a thin-transport skill — a pass-through over a Python CLI per
livespec-impl-beads/SPECIFICATION/constraints.md §"Skill orchestration
constraints". Do NOT add orchestration logic here; every behavior lives in
`.claude-plugin/scripts/livespec_impl_beads/commands/list_memos.py`.

## Invocation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/list_memos.py" "$@"
```

Forwards all arguments to the wrapper. Supported flags:

- `--filter=<all|untriaged|dispositioned>` (default `all`)
- `--json` — emit JSON array of memo materialized views
- `--memos-path <path>` — override the default `memos.jsonl` location

## When to use

- User asks "what memos do we have pending?" or similar.
- Doctor's memo-hygiene invariant invokes
  `/livespec-impl-beads:list-memos --filter=untriaged --json` to
  count untriaged memos.
- Other skills (notably `process-memos`) iterate over the result.
