---
name: orchestrate
description: Compose spec-side and impl-side next, present operator-selectable actions, and dispatch the selected factory-safe impl work through Dispatcher/Fabro. Invoked as livespec-orchestrator-beads-fabro:orchestrate.
---

# orchestrate — Codex binding

Thin Codex operator binding for `orchestrate`. The behavior — composing
spec-side `next` and impl-side `next`, rendering selectable actions, and
dispatching a selected action — lives in the plugin's reference wrapper
`scripts/bin/orchestrate.py`. The operator-surface defaults (bare
walkthrough, optional `--repo`, Markdown-by-default) are properties of
the CLI itself, so this binding inherits them unchanged.

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
python3 "$PLUGIN_ROOT/scripts/bin/orchestrate.py" "$@"
```

Subcommands mirror the wrapper:

- `plan [--repo <path>] [--json]` — read-only; emits selectable action
  records. Bare `orchestrate` (no subcommand) runs the same `plan` flow.
- `run [--repo <path>] --action <action-id> [--json]` — run ONE selected
  action. `impl:<work-item-id>` dispatches through Dispatcher/Fabro;
  `spec:<action>:<n>` returns a human handoff and never mutates spec
  state directly.

## Operator flow + consent

1. Run bare `orchestrate` (or `plan`) to render the `actions[]`.
2. Present the actions to the operator.
3. Invoke `run --action <id>` ONLY for the action the operator selected
   — a `run` dispatch is the mutating step and requires that explicit
   operator selection as its consent. Never auto-`run` an action.
4. Summarize `status`, the Dispatcher exit code, any PR/run fields in
   `dispatcher.stdout_json`, and any human handoff. Machine callers
   SHOULD pass `--repo` and `--json` for a fully-specified invocation.

This binding adds no ranking or selection logic of its own.
