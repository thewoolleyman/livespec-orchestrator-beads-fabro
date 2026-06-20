# tests/bin/

Tests for the shebang wrappers under `.claude-plugin/scripts/bin/`.

- `conftest.py` provides the `wrapper_runner` fixture: it
  `runpy.run_path()`'s a wrapper file with a `monkeypatch`-stubbed
  `_bootstrap` (so the runtime version check is a no-op) and a
  stubbed `livespec_impl_beads.<module>.main` (so the wrapper's
  plumbing is exercised without invoking the real command), then
  asserts the wrapper raises `SystemExit` with the expected exit
  code.
- `test_<cmd>.py` — one per wrapper (`detect_impl_gaps`,
  `list_work_items`, `next`, `orchestrator`). Each
  uses `wrapper_runner` to assert the wrapper threads `main()`'s
  return value into `raise SystemExit(...)`. Required for 100% line
  + branch coverage of the wrappers.
- `test_bootstrap.py` — covers `_bootstrap.bootstrap()`. Both
  branches of the `sys.version_info < (3, 10)` check are exercised
  via `monkeypatch.setattr(sys, "version_info", ...)`; the exit-127
  path is reached by monkeypatching rather than a coverage pragma
  (pragma exclusions on `bin/*.py` are forbidden).

Rules: keep these tests purely structural — they assert the
wrapper's no-logic supervisor shape and exit-code threading, never
the real command behavior (that is covered under
`tests/livespec_impl_beads/`). Do NOT import the real
`commands`/`migration` `main` into a wrapper test; always stub it.
