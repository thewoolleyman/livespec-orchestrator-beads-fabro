---
name: capture-work-item
description: Freeform direct filing of an impl-side work item (bugs, refactors, tactical tasks). Filed records carry `origin: freeform` and `gap_id: null`. Invoked as livespec-orchestrator-beads-fabro:capture-work-item.
---

# capture-work-item — Codex binding

Thin Codex binding for the `capture-work-item` operation of the
**livespec-orchestrator-beads-fabro** plugin. The complete
harness-neutral driving prose — the consent flow, the multi-step
dialogue, the `livespec_orchestrator_beads_fabro.*` package calls, and
the intake Definition-of-Ready semantics — is the plugin's own artifact
at `$PLUGIN_ROOT/prose/capture-work-item.md`. FIRST resolve
`$PLUGIN_ROOT` (next section), THEN read that prose file in full, then
execute it end-to-end, binding its harness-neutral vocabulary to this
runtime per `## Runtime bindings` below. This binding adds NO operation
behavior of its own.

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
than improvising paths. Then read the prose:

```bash
cat "$PLUGIN_ROOT/prose/capture-work-item.md"
```

## Runtime bindings

- **`<plugin-root>`** — the resolved `$PLUGIN_ROOT` above. Any
  `python3 "<plugin-root>/scripts/bin/<x>.py"` invocation in the prose
  runs via the shell tool with `<plugin-root>` → `$PLUGIN_ROOT`.
- **"ask the user" / "confirm with the user" / "surface" / "narrate"** —
  conversational narration in this session (ask one question at a time).
- **"read `<file>`"** — reading the file directly. **"write `<file>`"** —
  writing the file directly. **Python snippets** — run via the shell tool
  against the bundled `livespec_orchestrator_beads_fabro` package (the
  wrappers self-bootstrap the import path).
- **"the `capture-impl-gaps` / `implement` / `groom` operation"** — the
  `capture-impl-gaps`, `implement`, and `groom` skills in this plugin
  (invoke them by name).
