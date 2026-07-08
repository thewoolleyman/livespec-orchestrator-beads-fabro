---
name: needs-attention
description: Compose the repo attention primitives into a Markdown or JSON attention list. Invoked as livespec-orchestrator-beads-fabro:needs-attention.
---

# needs-attention — Codex binding

Thin Codex binding for `needs-attention`. The behavior lives in the
plugin's reference wrapper `scripts/bin/needs_attention.py`; this
binding only resolves the plugin root and dispatches. The default output
is Markdown for operator reading; `--json` emits the machine envelope.

## Resolving the plugin root (`$PLUGIN_ROOT`)

Codex does NOT textually substitute a plugin-root token into SKILL
prose, so resolve it explicitly, once, in this order:

1. If `LIVESPEC_ORCH_PLUGIN_ROOT` is set and non-empty, use it.
2. Else if `./.claude-plugin/scripts/bin` exists under the cwd AND
   `./.claude-plugin` validates as this orchestrator plugin checkout
   (matching plugin manifest name), use `$(pwd)/.claude-plugin`.
3. Else use the newest valid installed cache root under
   `$HOME/.codex/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/<version>`.
4. Else resolve the installed plugin's `source.path` from
   `codex plugin list --json -m livespec-orchestrator-beads-fabro` using a
   robust executable lookup (`command -v codex`, `$HOME/.local/bin/codex`,
   then `$HOME/.bun/bin/codex`)..

```bash
PLUGIN_ROOT="${LIVESPEC_ORCH_PLUGIN_ROOT:-}"
PLUGIN_ROOT_DIAGNOSTICS=""
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
  CODEX_CACHE_PARENT="$HOME/.codex/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro"
  if [ -d "$CODEX_CACHE_PARENT" ]; then
    CANDIDATE_PLUGIN_ROOT="$(find "$CODEX_CACHE_PARENT" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)"
    if [ -n "$CANDIDATE_PLUGIN_ROOT" ] && [ -d "$CANDIDATE_PLUGIN_ROOT/scripts/bin" ]; then
      PLUGIN_ROOT="$CANDIDATE_PLUGIN_ROOT"
    else
      PLUGIN_ROOT_DIAGNOSTICS="$PLUGIN_ROOT_DIAGNOSTICS
cache root not found: no valid version under $CODEX_CACHE_PARENT"
    fi
  else
    PLUGIN_ROOT_DIAGNOSTICS="$PLUGIN_ROOT_DIAGNOSTICS
cache root not found: $CODEX_CACHE_PARENT"
  fi
fi
if [ -z "$PLUGIN_ROOT" ]; then
  CODEX_BIN=""
  CODEX_TRIED="command -v codex, $HOME/.local/bin/codex, $HOME/.bun/bin/codex"
  if command -v codex >/dev/null 2>&1; then
    CODEX_BIN="$(command -v codex)"
  elif [ -x "$HOME/.local/bin/codex" ]; then
    CODEX_BIN="$HOME/.local/bin/codex"
  elif [ -x "$HOME/.bun/bin/codex" ]; then
    CODEX_BIN="$HOME/.bun/bin/codex"
  else
    PLUGIN_ROOT_DIAGNOSTICS="$PLUGIN_ROOT_DIAGNOSTICS
codex executable not found; tried: $CODEX_TRIED"
  fi
  if [ -n "$CODEX_BIN" ]; then
    PLUGIN_ROOT="$("$CODEX_BIN" plugin list --json -m livespec-orchestrator-beads-fabro 2>/tmp/livespec-orchestrator-beads-fabro-codex-plugin-list.err | python3 -c 'import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for plugin in data.get("installed", []):
    if plugin.get("pluginId") == "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro":
        sys.stdout.write(plugin.get("source", {}).get("path", ""))
        break' 2>/dev/null || true)"
    if [ -z "$PLUGIN_ROOT" ]; then
      PLUGIN_ROOT_DIAGNOSTICS="$PLUGIN_ROOT_DIAGNOSTICS
plugin not installed according to: $CODEX_BIN plugin list --json -m livespec-orchestrator-beads-fabro"
      if [ -s /tmp/livespec-orchestrator-beads-fabro-codex-plugin-list.err ]; then
        PLUGIN_ROOT_DIAGNOSTICS="$PLUGIN_ROOT_DIAGNOSTICS
codex plugin list stderr: $(cat /tmp/livespec-orchestrator-beads-fabro-codex-plugin-list.err)"
      fi
    fi
  fi
fi
if [ -z "$PLUGIN_ROOT" ] || [ ! -d "$PLUGIN_ROOT/scripts/bin" ]; then
  echo "livespec-orchestrator-beads-fabro plugin root not found." >&2
  if [ -n "$PLUGIN_ROOT_DIAGNOSTICS" ]; then
    printf "%b\n" "$PLUGIN_ROOT_DIAGNOSTICS" >&2
  fi
  echo "Install it first:" >&2
  echo "  codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro" >&2
  echo "  codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro" >&2
  exit 1
fi
```

If resolution fails, STOP and surface those install instructions.

## Invocation

```bash
python3 "$PLUGIN_ROOT/scripts/bin/needs_attention.py" "$@"
```

Supported flags mirror the wrapper: `--project-root <path>`, `--repo-name <name>`,
`--work-items-path <path>`, `--skip-hygiene`, and `--json`.

## Output

Surface the wrapper's stdout verbatim — Markdown by default, or the
`{"attention": [...]}` JSON envelope when `--json` is passed. Do NOT
execute any handoff automatically.
