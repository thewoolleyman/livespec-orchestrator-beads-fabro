---
name: detect-impl-gaps
description: Detect spec→impl gaps mechanically via the Spec Reader and emit the gap-id set (read-only thin transport). Invoked as livespec-orchestrator-beads-fabro:detect-impl-gaps.
---

# detect-impl-gaps — Codex binding

Thin Codex binding for `detect-impl-gaps`. The behavior lives in the
plugin's reference wrapper `scripts/bin/detect_impl_gaps.py`; this
binding only resolves the plugin root and dispatches. Pure read-only
pass-through — it never mutates the store and never prompts the user.
The gap-id derivation is a deterministic function of spec text.

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
python3 "$PLUGIN_ROOT/scripts/bin/detect_impl_gaps.py" "$@"
```

Supported flags mirror the wrapper: `--spec-target <path>`,
`--project-root <path>`, `--json` (emits `{"gap_ids": [...]}`),
`--since-version <vN>`. Invalid `--since-version` exits `2` (usage) or
`3` (missing version directory); surface the wrapper's error verbatim
and abort.

## Output

Surface the wrapper's stdout verbatim. Do NOT re-interpret, file
work-items, or modify the spec — this skill only detects and reports.
