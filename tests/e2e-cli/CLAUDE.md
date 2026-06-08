# tests/e2e-cli/

The CLI end-to-end harness wiring for livespec-impl-beads, per
`livespec/SPECIFICATION/contracts.md` §"CLI end-to-end harness contract".
This is the *top-of-pyramid*, user-surface tier whose sole interaction surface
is the `claude` CLI binary — a sibling to (not a superset of) the wrapper-chain
e2e tier; both coexist in CI.

The harness itself ships from `livespec-dev-tooling` (the single canonical
implementation, contract requirement 6) and is consumed here via the imported
`test_workflow_full_round_trip` entry point from
`livespec_dev_tooling.testing.cli_e2e` (dev-tooling >= v0.8.0). This directory
carries only the thin per-repo wiring:

- `test_cli_e2e_round_trip.py` — wraps the imported entry point, supplies the
  `HarnessConfig` (impl-plugin id, marketplace, enabled plugins, the
  `.claude-plugin/` install dir discovery walks, the fixtures root), and — for
  the **mock tier** (`LIVESPEC_E2E_HARNESS=mock`, the default, the tier that
  runs in `just check`) — injects a deterministic `CliRunner` that materializes
  each fixture's expected files. The one mocked boundary is the `claude -p`
  subprocess; discovery, fixture loading, the fail-closed time-bomb coverage
  gate, and the orchestration loop all run for real.
- `fixtures/<skill>/` — one directory per `/livespec-impl-beads:*` skill
  (contract requirement 4), each holding a `prompt.md` (text piped to
  `claude -p`) and an `expected_files.txt` (project-root-relative paths that
  MUST exist after the skill's turn; comment-only / absent means no file
  assertion, used by the thin read-only transports that emit JSON to stdout).
  Discovery walks the directory layout, not a manifest: directory present ==
  fixture exists. The `fixtures/` subtree is CLAUDE.md-exempt by convention.

The **time-bomb coverage gate** (contract requirement 5) is fail-closed: the
imported harness asserts `discovered_skills − fixtured_skills − exempt_skills`
is empty and raises `CoverageGateError` otherwise. Adding a new skill to the
plugin trips the gate until either a `fixtures/<skill>/` directory is added or
the skill is listed in the test's `_EXEMPT_SKILLS` table with a written
justification. No skill is exempt today.

The **real tier** (`LIVESPEC_E2E_HARNESS=real`) shells out to the actual
`claude` binary, requires `ANTHROPIC_API_KEY`, installs the upstream `livespec`
plugin paired in lockstep, and is NOT part of `just check` (the dedicated
`e2e-cli` CI job sets the selector explicitly).
