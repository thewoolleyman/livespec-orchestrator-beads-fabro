---
name: list-work-items
description: List work-items from the beads-backed work-items store (read-only thin transport). Invoked as livespec-orchestrator-beads-fabro:list-work-items.
---

# list-work-items — Codex binding

Thin Codex binding for `list-work-items`. The behavior lives in the
plugin's reference wrapper `scripts/bin/list_work_items.py`; this
binding only resolves the plugin root and dispatches. Read-only
pass-through — it never mutates the store.

## Resolving the plugin root (`$PLUGIN_ROOT`)

Codex does NOT textually substitute a plugin-root token into SKILL
prose, so resolve it explicitly, once, in this order:

1. If `LIVESPEC_ORCH_PLUGIN_ROOT` is set and non-empty, use it.
2. Else if `./.claude-plugin/scripts/bin` exists under the cwd
   (dogfood / dev checkout), use `$(pwd)/.claude-plugin`.
3. Else resolve the installed plugin's `source.path` from
   `codex plugin list --json -m livespec-orchestrator-beads-fabro`.

```bash
PLUGIN_ROOT="$LIVESPEC_ORCH_PLUGIN_ROOT"
if [ -z "$PLUGIN_ROOT" ] && [ -d "./.claude-plugin/scripts/bin" ]; then
  PLUGIN_ROOT="$(pwd)/.claude-plugin"
fi
if [ -z "$PLUGIN_ROOT" ]; then
  PLUGIN_ROOT="$(codex plugin list --json -m livespec-orchestrator-beads-fabro 2>/dev/null | python3 -c 'import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for plugin in data.get("installed", []):
    if plugin.get("pluginId") == "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro":
        sys.stdout.write(plugin.get("source", {}).get("path", ""))
        break' 2>/dev/null || true)"
fi
if [ -z "$PLUGIN_ROOT" ] || [ ! -d "$PLUGIN_ROOT/scripts/bin" ]; then
  echo "livespec-orchestrator-beads-fabro plugin root not found. Install it first:" >&2
  echo "  codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro" >&2
  echo "  codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro" >&2
  exit 1
fi
```

If resolution fails, STOP and surface those install instructions.

## Invocation

```bash
python3 "$PLUGIN_ROOT/scripts/bin/list_work_items.py" "$@"
```

Supported flags mirror the wrapper:
`--filter=<all|gap-tied|freeform|blocked|ready|closed>` (default `all`),
`--with-gap-id <id>`, `--json`, `--work-items-path <path>`.

## Output

Surface the wrapper's stdout verbatim — the JSON array of materialized
work-item views when `--json` is passed. Do NOT re-interpret or mutate
any state.
