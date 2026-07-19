# tests/hooks_plugin/

Mirrors `.claude-plugin/hooks/` one-to-one: every non-exempt `.py` hook module there
has its paired `test_<module>.py` here (`check-tests-mirror-pairing`, wired via
the `.claude-plugin/hooks` -> `tests/hooks_plugin` entry in `pyproject.toml`'s
`mirror_pairings`).

Conventions specific to this tree:

- `.claude-plugin/hooks/` is NOT an importable package — Claude Code executes each
  hook as a standalone script. Load the module under test by file location
  (`importlib.util.spec_from_file_location`), the same idiom
  `tests/test_fleet_pat_dispatch_surface_helpers.py` uses. `_REPO_ROOT` is
  `Path(__file__).resolve().parents[2]` from this depth.
- Hook `.sh` wrappers are NEVER spawned from a test
  (`check-tests-no-subprocess-spawn`). That is precisely why each hook keeps
  its logic in a pure, importable `.py` module and leaves the `.sh` a thin
  `exec python3 ...` wrapper: the `.sh` carries no behavior worth testing.
- Drive each `main()` in-process — `monkeypatch` for `sys.stdin` / env vars,
  `tmp_path` for filesystem fixtures, `capsys` for the stdout/stderr contract,
  and `pytest.raises(SystemExit)` for hooks that exit rather than return.
- Every hook is FAIL-OPEN: malformed input, a missing target, or an unexpected
  shape must pass through silently rather than block or raise. Each module's
  tests must cover that arm explicitly — a hook that crashes can wedge every
  Bash call or every session start.
