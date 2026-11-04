# .claude-plugin/hooks/

Plugin-bundled Claude Code hooks that ship to consuming projects when this
orchestrator plugin is installed.

Rules:

- Preserve SessionStart fail-open behavior: a missing marker, missing plugin
  cache, unreadable file, or unexpected per-file error must not abort a session.
- Keep Claude-only SessionStart hooks inert under native Codex: short-circuit on
  `CODEX_THREAD_ID` before expanding `CLAUDE_PLUGIN_ROOT` or invoking a script.
- `session_wait_stop.py` is the Claude Stop hook: it runs the shared
  `session_wait.py check`, blocks a stop ONCE when that reports findings
  (never again once `stop_hook_active` is set), and reports a check that could
  not run as unavailable rather than healthy. It is Claude-only: Codex and pi
  invoke `check` explicitly from their guidance.
- Resolve the consuming project through `CLAUDE_PROJECT_DIR`; `__file__` points
  at the plugin cache after distribution and must not be treated as the adopter
  repo.
- Keep non-listed adopters as silent no-ops unless `LIVESPEC_CODEX_FULL_ACCESS`
  explicitly opts them in.
- Keep each Python hook mirrored under `tests/hooks_plugin/` with 100% line and
  branch coverage, and do not spawn subprocesses from tests.
- Do not print secrets.
