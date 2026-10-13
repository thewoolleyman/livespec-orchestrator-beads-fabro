# tests/e2e/

Tests that drive a REAL external program this repository does not ship, and
that are therefore skipped wherever that program is absent. The directory is
omitted from coverage (`[tool.coverage.run] omit` in `pyproject.toml`) and is
still collected by the ordinary suite (`testpaths = ["tests"]`), so its tests
run on every host that has the program and are counted by no coverage gate.

That split is the point of the tier, not a convenience. CI carries none of
these programs, so a skip-guarded test body anywhere else is a line no CI leg
ran, and the per-file coverage gate would either fail on it or have to be
weakened for it. Put a test here only when the behaviour cannot be reached
without the external program; every branch of the PRODUCT code under test must
stay covered from the CI-runnable tier through controlled peers, so moving a
test here never removes coverage of shipped code.

- `test_session_wait_pane_live_herdr.py` — the Scenario 155 pane-wait proofs
  against a real isolated `herdr server`, plus the fixture's own
  readiness-diagnostic test. Skipped without the `herdr` binary. Its
  CI-runnable counterpart is
  `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_pane.py`.

Rules: create and clean up only servers, panes and sockets the test itself
owns; drop every inherited `HERDR_*` variable before launching a server, so a
run inside a herdr pane can never reach the operator's live server; and
disclose any controlled peer in its docstring.
