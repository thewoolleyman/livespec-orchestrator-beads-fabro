# .claude/hooks/

Repo-local hook entry points that run around Claude/plugin setup and local
footgun guards.

Rules:

- Preserve hook process contracts: exit codes and stdout/stderr are part of the
  operator surface.
- Keep host mutation explicit, bounded, and reversible where the hook changes
  files or plugin cache state.
- Do not add product logic here; shared behavior belongs under
  `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/`.
- Do not print secrets.

