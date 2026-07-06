---
name: list-plan-threads
description: List unarchived plan threads from the repo's plan/ thread store. Required thin-transport surface per livespec-orchestrator-beads-fabro/SPECIFICATION/contracts.md. Invoke as `/livespec-orchestrator-beads-fabro:list-plan-threads [--json] [--project-root <path>]`.
allowed-tools: Bash
---

# list-plan-threads

Thin-transport pass-through. All behavior lives in
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/list_plan_threads.py`.

## Invocation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/list_plan_threads.py" "$@"
```

Supported flags:

- `--json` — emit `{"plan_threads": ["<topic>", ...]}`
- `--project-root <path>` — override the repo root whose `plan/` store is enumerated

## When to use

- The needs-attention surface needs the current unarchived plan-thread topics.
- A caller needs a read-only inventory of direct child directories under `plan/`, excluding `plan/archive/`.
