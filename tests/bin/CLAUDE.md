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
- `test_bootstrap_unattended_marker_forwarding.py` — covers
  `_bootstrap._marker_forwarded_argv`, which splices `env
  LIVESPEC_PLAN_UNATTENDED=<value>` in after the credential wrapper's
  `--` separator so the overseer's unattended-resume marker survives
  the wrapper's `sudo` env rebuild. Its two end-to-end cases drive the
  real re-exec against a wrapper DOUBLE that `unset`s the marker, so a
  forwarding that only worked by environment inheritance fails them.
  Like the file below, the real modules are imported only inside that
  spawned child.
- `test_payload.py` — unit coverage for `_payload.py`, the
  payload-retention step `bootstrap()` runs before any packaged
  import: which plugin roots are harness-managed, that each
  invocation gets a payload no other invocation shares, that no
  pre-existing tree (including a symlink under the launcher's own
  holder prefix) is ever adopted as an executable payload, and how a
  release label degrades when the manifest cannot be read.
- `test_payload_retention_after_eviction.py` — the end-to-end
  counterpart of `test_payload.py`, and the regression guard for the
  `bd-ib-mtuqxb` host incident. It copies the real plugin root into a
  disposable fixture installation, launches a real child through the
  real `bootstrap()`, DELETES that installation once the launcher has
  finished, and only then releases the child to import the packaged
  drive and Dispatcher routes, read a packaged asset and spawn a
  `scripts/bin/` helper. No in-process `main()` can stand in: the
  question is what a second process sees after its own source tree is
  gone. Listed in `subprocess_spawn_allowlist`. Its bytes are FROZEN
  across its Red->Green pair — cover anything it leaves unexercised in
  the harness file below rather than editing it.
- `test_payload_retention_harness.py` — coverage for the frozen
  regression's own scaffolding, which this repo measures like any other
  `tests/` file: `_wait_for`'s early-child-exit and bounded-timeout
  arms, and the test body's `finally` reaping a wedged probe. It loads
  the frozen module BY PATH and drives those arms against real
  disposable children, so the frozen file never has to change. It
  asserts nothing about `_payload.py` — harness robustness, not product
  Red. Listed in `subprocess_spawn_allowlist`.
- `test_payload_concurrent_release_isolation.py` — two concurrent
  invocations launched from two distinguishable installs that carry
  the SAME manifest version, with the older install deleted between
  launch and use. Each must report its own marker from a packaged
  module (deferred code) and from the bundled workflow manifest (a
  packaged asset), which is what forces an invocation-private payload
  rather than one keyed by version text. Listed in
  `subprocess_spawn_allowlist`.
- `test_payload_provisioning_refusal.py` — drives the real packaged
  Dispatcher entry point against an incomplete source, and against a
  source whose copy breaks part-way, and observes that the refusal is
  actionable AND that nothing irreversible happened: `bd` and `fabro`
  are replaced on `PATH` by recorders that must never be called, the
  dispatch journal must not exist, and `TMPDIR` must be left empty so
  no partial payload survives for a later invocation to adopt. Listed
  in `subprocess_spawn_allowlist`.
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
