---
name: drive
description: Execute one livespec-orchestrator-beads-fabro action-id: impl:<id> dispatch, approve/accept/reject valves, or set-admission/set-acceptance policy edits. Invoke as livespec-orchestrator-beads-fabro:drive.
---

# drive - Codex binding

Thin Codex operator binding for the shared Python CLI.

## Resolving the plugin root

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
python3 "$PLUGIN_ROOT/scripts/bin/drive.py" "$@"
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

## Launching a long-running action — use the detached gate runner

An `impl:<work-item-id>` dispatch is NOT a short command. One invocation spans the Fabro run, the pull request, the merge, the post-merge janitor, and acceptance, so it routinely outlives the agent turn that launched it.

**Do NOT launch it as an agent-harness background task.** Such a task can be killed mid post-merge: measured 2026-09-10, two `impl:` dispatches launched that way from one session died 37 ms apart at ~34m55s with the harness line `exited with code 144`, AFTER both their pull requests had merged. Both work-items were left `active` with no merge audit — merged work the ledger still showed as in flight. **A background task's death is NOT the dispatch's verdict**; the Fabro run and the merge can already have succeeded, and `drive` prints its result only on exit, so its `--json` log is empty either way.

Launch it through the detached gate runner instead. `gate-start` runs the command in its own session that survives the tool call and returns immediately with a run id; `gate-wait` blocks until that run is terminal and reports a durable `PASSED` / `FAILED` / `RUNNING` / `DIED_WITHOUT_VERDICT`:

```bash
run_id=$(mise exec -- just gate-start -- python3 "$PLUGIN_ROOT/scripts/bin/drive.py" --action impl:<work-item-id> --json)
mise exec -- just gate-wait "$run_id"
```

Prefix the gate command with whatever the invocation ordinarily needs (the governed project's `with-<project>-env.sh` credential wrapper, for instance) — `gate-start` runs the argv it is given, unchanged. `gate-wait` exits with the gate's own exit code (75 for `DIED_WITHOUT_VERDICT`, which is neither a pass nor a fail); killing the waiter does not touch the gate, so it is safe to background and safe to re-issue.

The `gate-*` recipes come from the livespec-dev-tooling worktree-discipline pack, imported optionally and installed by `just install-worktree-pack` (which `just bootstrap` runs). `Justfile does not contain recipe gate-start` therefore means the pack is not installed in that checkout — install it rather than falling back to a background task.

## Recovering a merged item left `active`

A merged item still sitting at `active` with no merge audit is the signature of a killed dispatch. The recovery is `dispatcher.py reconcile-merged`, driven per item — the `reconcile-runs.timer` does NOT close cleanly-merged work. It runs a fresh checkout plus baseline checks and routinely exceeds a foreground timeout, so launch it through `gate-start` for the same reason:

```bash
run_id=$(mise exec -- just gate-start -- python3 "$PLUGIN_ROOT/scripts/bin/dispatcher.py" reconcile-merged --repo <path> --item <work-item-id> --invoker <role:name>)
mise exec -- just gate-wait "$run_id"
```
