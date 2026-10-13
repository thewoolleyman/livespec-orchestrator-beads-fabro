# tests/

The pytest suite. Mirrors `.claude-plugin/scripts/bin/` and
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/` one-to-one:
`tests/bin/` covers the shebang wrappers; `tests/
livespec_orchestrator_beads_fabro/` mirrors the package's directory shape
(top-level `test_<module>.py` for top-level package modules,
subdirectories for subpackages).

Conventions:

- pytest is the test framework. Run the suite + coverage via
  `mise exec -- just check-coverage` (the canonical pytest-running
  aggregate target); the full gate is `mise exec -- just check`.
- 100% line + branch coverage is REQUIRED (inherited from
  `SPECIFICATION/constraints.md` §"Inherited from livespec").
  Pragma exclusions on wrappers are forbidden — cover branches by
  monkeypatching instead.
- Hypothesis property-based tests are required on pure modules
  (`check-pbt-coverage-pure-modules`).
- Every directory under `tests/` (except `fixtures/` subtrees and
  `__pycache__/`) carries a `CLAUDE.md` — enforced by the shared
  `claude_md_coverage` check.
- Data files (e.g. `tests/heading-coverage.json`, the
  heading-coverage registry consumed by the shared
  `heading_coverage` check) live at `tests/<file>` directly;
  subdirectories cover code under test.
- `tests/plan_resume_checkout.py` is the ONE derivation of the checkout
  the plan-resume fixtures name in their typed `required_result`
  (imported as `from tests.plan_resume_checkout import ...` from both
  `tests/integration/` and `tests/livespec_orchestrator_beads_fabro/`).
  A fixture naming this repository LITERALLY resolves only in a checkout
  whose DIRECTORY is named after the repository, so it passed from the
  primary clone and failed from every worktree and from the Dispatcher's
  post-merge janitor checkout. Read that module's docstring before
  adding a plan-resume fixture; `tests/
  test_plan_resume_checkout_identity.py` is the guard that keeps the
  three existing fixtures on it.
- Tests use `tmp_path` for filesystem fixtures, `monkeypatch` to
  stub `os.environ` and the runtime version check, and `capsys` to
  capture stdout/stderr. Happy-path tests that exercise a
  `Path.cwd()` default MUST `monkeypatch.chdir(tmp_path)` to avoid
  polluting the repo.
