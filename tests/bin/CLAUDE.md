# tests/bin/

Tests for the shebang wrappers under `.claude-plugin/scripts/bin/`.

- `conftest.py` provides the `wrapper_runner` fixture: it
  `runpy.run_path()`'s a wrapper file with a `monkeypatch`-stubbed
  `_bootstrap` (so the runtime version check is a no-op) and a
  stubbed `livespec_orchestrator_beads_fabro.<module>.main` (so the wrapper's
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
- `test_host_side_self_contained_import.py` — the end-to-end
  counterpart of `test_bootstrap.py`: it spawns a `-S` (no-site)
  subprocess that runs the real bootstrap and imports the host-side
  dispatcher surface, asserting the path the bootstrap builds
  (`scripts/` + `scripts/_vendor/`, no site-packages) resolves every
  import. It guards plugin self-containment from the flattened cache —
  an unvendored host-side dependency (e.g. `typing_extensions`) trips
  it. The real modules are imported only inside the isolated
  subprocess, never in-process, so the structural rule below holds.

Rules: keep these tests purely structural — they assert the
wrapper's no-logic supervisor shape and exit-code threading, never
the real command behavior (that is covered under
`tests/livespec_orchestrator_beads_fabro/`). Do NOT import the real
`commands`/`migration` `main` into a wrapper test; always stub it.
(`test_host_side_self_contained_import.py` is the one exception that
imports real modules — but only inside an isolated `-S` subprocess,
to verify import *resolution* from the vendored tree, not behavior.)
