---
name: needs-attention
description: Compose spec, implementation, human-valve, plan-thread, and hygiene gather primitives into a Markdown attention list. Invoke as `/livespec-orchestrator-beads-fabro:needs-attention [--project-root <path>]`.
allowed-tools: Bash
---

# needs-attention

Thin binding over
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/needs_attention.py`.

## Invocation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/needs_attention.py" "$@"
```

Supported flags:

- `--project-root <path>` — target repo root, default current directory
- `--repo-name <name>` — override the repo name carried in source refs
- `--work-items-path <path>` — pass-through work-item store override

Default output is Markdown for operator reading. Use the wrapper directly with
`--json` for the machine envelope.
