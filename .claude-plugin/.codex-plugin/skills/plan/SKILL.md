---
name: plan
description: Open or resume a durable plan and carry authorized work through child disposition, independent completeness review, a verified plan Proof of Done with required attestations, and archive. Use released-build proof where applicable. Invoked as livespec-orchestrator-beads-fabro:plan (bare to create or resume interactively; with a slug to resume strictly).
---

# plan — Codex binding

Thin Codex binding for the `plan` operation of the
**livespec-orchestrator-beads-fabro** plugin. The complete
harness-neutral driving prose — the planning-thread create/resume
dialogue, write-once research and epic-anchor creation, ledger-held
handoff comment writes, scope-event recording, matured-piece routing,
archive gates, and the `livespec_orchestrator_beads_fabro.*`
package calls — is the plugin's own artifact at
`$PLUGIN_ROOT/prose/plan.md`. FIRST resolve `$PLUGIN_ROOT` (next
section), THEN read that prose file in full, then execute it
end-to-end, binding its harness-neutral vocabulary to this runtime per
`## Runtime bindings` below. This binding adds NO operation behavior of
its own.

## Resolving the plugin root (`$PLUGIN_ROOT`)

Codex does NOT textually substitute a plugin-root token into SKILL
prose, so resolve it explicitly, once, in this order:

1. If `LIVESPEC_ORCH_PLUGIN_ROOT` is set and non-empty, use it
   (explicit override for nonstandard dev setups).
2. Else if `./.claude-plugin/scripts/bin` exists under the cwd AND
   `./.claude-plugin` validates as this orchestrator plugin checkout
   (matching plugin manifest name), use `$(pwd)/.claude-plugin`.
3. Else use the newest valid installed cache root under
   `$HOME/.codex/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/<version>`.
4. Else resolve the installed plugin's `source.path` from
   `codex plugin list --json -m livespec-orchestrator-beads-fabro` using a
   robust executable lookup (`command -v codex`, `$HOME/.local/bin/codex`,
   then `$HOME/.bun/bin/codex`).
   (the install flattens `./.claude-plugin`, so that path carries
   `scripts/` directly).

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

If resolution fails, STOP and surface those install instructions rather
than improvising paths. Otherwise read all three bounded ranges in order.
A truncation notice is an incomplete read even when a range command exits
successfully; retrieve that range again before acting.

```bash
PLAN_PROSE="$PLUGIN_ROOT/prose/plan.md"
wc -l "$PLAN_PROSE"
sed -n '1,160p' "$PLAN_PROSE"
sed -n '161,320p' "$PLAN_PROSE"
sed -n '321,480p' "$PLAN_PROSE"
```

## Runtime bindings

- **`<plugin-root>`** — the resolved `$PLUGIN_ROOT` above. Any
  `python3 "<plugin-root>/scripts/bin/<x>.py"` invocation in the prose
  runs via the shell tool with `<plugin-root>` → `$PLUGIN_ROOT`.
- **"ask the user" / "confirm with the user" / "surface" / "narrate" /
  "present the draft to the maintainer"** — conversational narration in
  this session (ask one question at a time).
- **"read `<file>`"** — reading the file directly. **"write `<file>`"** —
  writing the file directly. **Enumerate `plan/` directories** — a
  directory listing. **Python snippets** and **`git` checks** — run via
  the shell tool against the bundled
  `livespec_orchestrator_beads_fabro` package (the wrappers
  self-bootstrap the import path).
- **"append a handoff" / "read the timeline" / "record a scoping
  event" / "archive the thread"** — call the package primitives in
  `livespec_orchestrator_beads_fabro.commands.plan` from a Python
  snippet, using the project root and resolved store config.
- **"the `list-work-items` / `next` operation"** — the `list-work-items`
  and `next` skills in this plugin (the read-only status surface;
  invoke them by name).
- **"the `capture-work-item` operation"** — the `capture-work-item`
  skill in this plugin (the epic-anchor and child-work-item filing
  seam; invoke it by name).
- **"the `propose-change` operation"** — the cross-boundary
  `propose-change` skill of the **livespec** plugin (the
  matured-to-spec handoff target; invoke it by name).
- **"drive a typed next action"** — preserve the shared prose's six-kind mapping unchanged: `impl`, `spec-op`, `proof`,
  `review`, `archive`, and `await` use their named sibling operation or package primitive; result reconciliation and any
  recorded continuation ruling decide whether this runtime acts or presents the picker.
