---
name: next
description: Rank the most-ripe impl-side action from the beads-backed work-items store (read-only, deterministic). Invoked as livespec-orchestrator-beads-fabro:next.
---

# next — Codex binding

Thin Codex binding for the `next` operation of the
**livespec-orchestrator-beads-fabro** plugin. The behavior lives in the
plugin's reference wrapper `scripts/bin/next.py`; this binding only
resolves the plugin root and dispatches to it. Pure read-only
pass-through — it never mutates the store and never prompts the user.

## Resolving the plugin root (`$PLUGIN_ROOT`)

Codex does NOT textually substitute a plugin-root token into SKILL
prose, so resolve it explicitly, once, in this order:

1. If `LIVESPEC_ORCH_PLUGIN_ROOT` is set and non-empty, use it
   (explicit override for nonstandard dev setups).
2. Else if `./.claude-plugin/scripts/bin` exists under the cwd AND
   `./.claude-plugin` validates as this orchestrator plugin checkout
   (matching plugin manifest name), use `$(pwd)/.claude-plugin`.
3. Else resolve the installed plugin's `source.path` from
   `codex plugin list --json -m livespec-orchestrator-beads-fabro`
   (the install flattens `./.claude-plugin`, so that path carries
   `scripts/` directly).

```bash
PLUGIN_ROOT="$LIVESPEC_ORCH_PLUGIN_ROOT"
if [ -z "$PLUGIN_ROOT" ] && [ -d "./.claude-plugin/scripts/bin" ]; then
  CANDIDATE_PLUGIN_ROOT="$(pwd)/.claude-plugin"
  if [ -f "$CANDIDATE_PLUGIN_ROOT/plugin.json" ] && python3 - "$CANDIDATE_PLUGIN_ROOT/plugin.json" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    sys.exit(1)
sys.exit(0 if data.get("name") == "livespec-orchestrator-beads-fabro" else 1)
PY
  then
    PLUGIN_ROOT="$CANDIDATE_PLUGIN_ROOT"
  fi
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

If resolution fails, STOP and surface those install instructions rather
than improvising paths.

## Invocation

```bash
python3 "$PLUGIN_ROOT/scripts/bin/next.py" "$@"
```

Supported flags mirror the wrapper: `--limit <count>`,
`--offset <count>`, `--json`, `--work-items-path <path>`,
`--project-root <path>`.

## Output

Surface the wrapper's stdout JSON verbatim — the ranked `candidates[]`
envelope with `pagination`. Empty `candidates[]` IS the no-work signal.
Do NOT re-interpret, re-summarize, or mutate any state; the ranking is
deterministic and read-only by contract.
