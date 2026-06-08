"""CLI end-to-end harness wiring for livespec-impl-beads (mock tier).

Per `livespec/SPECIFICATION/contracts.md` §"CLI end-to-end harness contract"
(requirement 6 — single canonical implementation in `livespec-dev-tooling`;
requirement 7 — consumer obligations), this repo consumes the imported
`test_workflow_full_round_trip` entry point from
`livespec_dev_tooling.testing.cli_e2e` (shipped at dev-tooling v0.8.0) and
wires it into its own pytest collection against this plugin's per-skill
fixtures under `tests/e2e-cli/fixtures/`.

This is the **mock tier** (`LIVESPEC_E2E_HARNESS=mock`, the default): real
install-shape setup, real structural skill discovery over the on-disk
`.claude-plugin/` tree, the real fail-closed time-bomb coverage gate, and the
real per-skill orchestration loop all run — the ONLY mocked boundary is the
`claude -p` subprocess itself (the `CliRunner` seam), supplied here as a
deterministic injected runner that materializes each fixture's expected files.
The `real` tier (`LIVESPEC_E2E_HARNESS=real`) shells out to the actual
`claude` binary, requires `ANTHROPIC_API_KEY`, installs the upstream
`livespec` plugin paired in lockstep, and is NOT part of `just check`.

The plugin slash-command prefix (`livespec-impl-beads`) and the skill set
are discovered structurally from `<plugin>/plugin.json` `name` + the
`skills/*/SKILL.md` layout — there is no parallel manifest (contract
requirement 3). Every discovered skill MUST carry a fixture or the coverage
gate fails the run; no skill is exempt (`EXEMPT_SKILLS` is empty).
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.testing import cli_e2e
from livespec_dev_tooling.testing.cli_e2e import CliResult, FixturedSkill, HarnessConfig

# The canonical entry point is named `test_workflow_full_round_trip` (fixed by
# the contract's consumer import path). Importing that bare `test_*` name into
# a pytest module would make pytest try to COLLECT it as a test with a missing
# `config` fixture — so it is aliased here under a non-`test_`-prefixed name
# and invoked explicitly from the wrapper test below.
run_full_round_trip = cli_e2e.test_workflow_full_round_trip

__all__: list[str] = []


# Repo-root-relative anchors: this file lives at
# `<repo>/tests/e2e-cli/test_cli_e2e_round_trip.py`, so the repo root is three
# parents up. The installed-plugin location discovery walks is this repo's own
# `.claude-plugin/` tree (its `plugin.json` + `skills/*/SKILL.md`); the
# fixtures root is the sibling `fixtures/` directory next to this file.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_DIR = _REPO_ROOT / ".claude-plugin"
_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"

# No skill is exempt: every discovered impl-beads skill MUST carry a
# fixture (contract requirement 5). An empty exempt table keeps the time-bomb
# coverage gate fully armed — adding a new skill to the plugin trips it until a
# fixture directory lands here.
_EXEMPT_SKILLS: frozenset[str] = frozenset()


class _MaterializingCliRunner:
    """The injected `claude -p` seam — the one mocked boundary (mock tier).

    A real `claude -p <prompt>` run of each skill's slash command would create
    that skill's output artifacts; this deterministic stand-in reads each
    fixture's declared `expected_files` and materializes exactly those paths
    under the run's `cwd` (the tmp `project_root`), then returns a successful
    `CliResult`. Everything else in the harness — discovery, fixture loading,
    the coverage gate, the orchestration loop — runs for real against on-disk
    trees. The per-skill expected-file map is built from the loaded fixtures so
    the stand-in stays in lockstep with the fixture set with no duplication.
    """

    def __init__(self, *, expected_by_prompt: dict[str, tuple[str, ...]]) -> None:
        self._expected_by_prompt = expected_by_prompt

    def run(
        self,
        *,
        prompt: str,
        home: Path,
        cwd: Path,
        resume_session_id: str | None,
    ) -> CliResult:
        # `home` is part of the `CliRunner` protocol signature (the real runner
        # sets `HOME=home` for the `claude` subprocess) but the mock tier never
        # shells out, so the tmp HOME is unused here; bind it to satisfy the
        # unused-argument lint (ARG002) without dropping the protocol parameter.
        _ = home
        # The runner materializes each fixture's declared expected files. Under
        # the beads substrate EVERY skill writes to the per-repo tenant DB
        # rather than a project-root file, so every fixture's expected-file
        # tuple is empty and this loop body never runs (the round-trip's
        # success signal is the exit-0 below). The loop is retained verbatim
        # so this runner stays a faithful generic CliRunner — a future
        # file-declaring fixture would exercise it — hence the pragma rather
        # than deleting the body.
        for rel in self._expected_by_prompt.get(prompt, ()):  # pragma: no cover
            target = cwd / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            _ = target.write_text("materialized by the mock-tier runner\n", encoding="utf-8")
        return CliResult(exit_code=0, stdout="", stderr="", session_id=resume_session_id)


def _expected_by_prompt(*, fixtures: dict[str, FixturedSkill]) -> dict[str, tuple[str, ...]]:
    """Map each fixture's prompt text → its declared expected-file tuple."""
    return {fixture.prompt: fixture.expected_files for fixture in fixtures.values()}


def _config() -> HarnessConfig:
    return HarnessConfig(
        impl_plugin_id="livespec-impl-beads",
        marketplace="thewoolleyman/livespec-impl-beads",
        enabled_plugins=(
            "livespec@livespec",
            "livespec-impl-beads@livespec-impl-beads",
        ),
        plugin_install_dirs=(_PLUGIN_DIR,),
        fixtures_root=_FIXTURES_ROOT,
        exempt_skills=_EXEMPT_SKILLS,
    )


def test_cli_e2e_round_trip_against_impl_beads(*, tmp_path: Path) -> None:
    """Drive the imported harness against this plugin's own fixtures (mock tier).

    Asserts the full discovery → coverage-gate → per-skill orchestration loop
    passes: every `/livespec-impl-beads:*` skill discovered structurally
    from `.claude-plugin/` carries a fixture under `tests/e2e-cli/fixtures/`,
    and each skill's mock round-trip materializes its declared expected files
    and exits 0. `run_full_round_trip` raises `CoverageGateError` (fail-closed)
    on a fixture gap and `WorkflowFailedError` on any failing step, so a green
    run proves both the coverage gate is satisfied and every step round-trips.
    """
    config = _config()
    fixtures = cli_e2e.discover_fixtures(fixtures_root=config.fixtures_root)
    runner = _MaterializingCliRunner(expected_by_prompt=_expected_by_prompt(fixtures=fixtures))
    result = run_full_round_trip(
        config=config,
        home=tmp_path / "home",
        project_root=tmp_path / "project",
        injected_runner=runner,
    )
    # The discovered skill set is exactly the fixtured skill set (the coverage
    # gate enforces no gaps); the round-trip passed every step.
    assert set(result.discovered_skills) == set(result.fixtured_skills)
    assert result.passed is True
    # Every discovered skill was driven (none silently skipped) — `next` is one
    # of the thin-transport skills and MUST appear among the run steps.
    driven = {step.skill for step in result.steps}
    assert driven == set(result.discovered_skills)
    assert "next" in driven
