"""Integration-tier acceptance for SPECIFICATION/scenarios.md "Scenario 17 —
orchestrate operator-surface defaults".

Drives the `orchestrate` CLI through its public `main()` entry point and
asserts the three operator-surface defaults the scenario pins, end to end
through argv parsing, repo resolution, and output rendering:

- A bare `orchestrate` invocation (no subcommand) runs the read-only plan
  flow and does NOT error on the missing subcommand — it never raises
  `SystemExit(2)`.
- An omitted `--repo` resolves the target repo to the current working
  directory's repo; an explicit `--repo <path>` overrides it; an
  unresolvable path surfaces a precondition error (exit 3) naming the path.
- Console output is human-readable Markdown by default; `--json` is the
  machine opt-in and renders the same payload as JSON.

The spec-side and impl-side `next` surfaces are driven through the CLI's
public `runner` seam (the same seam the explicit-form callers use) so the
acceptance is hermetic: it exercises the operator surface without a live
Beads/Dolt or spec backend, which the operator-surface defaults are a
property of regardless.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.orchestrate import CommandRun, main


class _Runner:
    """A CommandRunner double returning canned spec/impl `next` JSON."""

    def __init__(self, *, results: list[CommandRun]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


def _ok(payload: object) -> CommandRun:
    return CommandRun(argv=("cmd",), returncode=0, stdout=json.dumps(payload), stderr="")


def _plan_runner() -> _Runner:
    """A runner that yields one spec candidate and one impl candidate."""
    return _Runner(
        results=[
            _ok(
                {
                    "candidates": [
                        {
                            "action": "revise",
                            "urgency": "high",
                            "reason": "pending proposal",
                            "target": "proposed_changes/a.md",
                        }
                    ]
                }
            ),
            _ok(
                {
                    "candidates": [
                        {
                            "action": "implement",
                            "work_item_ref": "bd-ib-123",
                            "urgency": "medium",
                            "reason": "ready item",
                        }
                    ]
                }
            ),
        ]
    )


def test_bare_orchestrate_runs_the_plan_walkthrough_without_erroring(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: a bare orchestrate invocation walks the operator through the choices."""
    monkeypatch.chdir(tmp_path)
    runner = _plan_runner()

    exit_code = main([], runner=runner)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "spec:revise:0" in out
    assert "impl:bd-ib-123" in out


def test_bare_orchestrate_does_not_raise_system_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """And it does NOT argparse-exit-2 on the missing subcommand."""
    monkeypatch.chdir(tmp_path)
    runner = _plan_runner()

    # A missing subcommand must NOT raise the argparse usage error.
    exit_code = main([], runner=runner)

    assert exit_code == 0
    _ = capsys.readouterr()


def test_omitted_repo_resolves_to_the_current_working_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: an omitted --repo resolves to the current working directory's repo."""
    monkeypatch.chdir(tmp_path)
    runner = _plan_runner()

    exit_code = main(["plan"], runner=runner)

    assert exit_code == 0
    out = capsys.readouterr().out
    # The plan header names the resolved repo — the cwd, not a passed path.
    assert str(tmp_path) in out


def test_explicit_repo_overrides_the_cwd_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """And an explicit --repo <path> still overrides the cwd default when supplied."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    override = tmp_path / "override"
    override.mkdir()
    monkeypatch.chdir(cwd)
    runner = _plan_runner()

    exit_code = main(["plan", "--repo", str(override)], runner=runner)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert str(override) in out
    assert str(cwd) not in out


def test_unresolvable_repo_is_a_precondition_error_naming_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """And an unresolvable --repo path surfaces a precondition error (exit 3)."""
    missing = tmp_path / "does-not-exist"

    exit_code = main(["plan", "--repo", str(missing)])

    assert exit_code == 3
    assert str(missing) in capsys.readouterr().err


def test_console_output_is_markdown_by_default_and_not_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: console output is Markdown by default and JSON only with --json."""
    monkeypatch.chdir(tmp_path)
    runner = _plan_runner()

    exit_code = main(["plan"], runner=runner)

    assert exit_code == 0
    out = capsys.readouterr().out
    # Human-readable Markdown: a leading heading and bullet list, NOT JSON.
    assert out.lstrip().startswith("#")
    with pytest.raises(json.JSONDecodeError):
        _ = json.loads(out)


def test_json_opt_in_renders_the_same_payload_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """And passing --json renders the same payload as machine-readable JSON."""
    monkeypatch.chdir(tmp_path)
    runner = _plan_runner()

    exit_code = main(["plan", "--json"], runner=runner)

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert [action["id"] for action in parsed["actions"]] == [
        "spec:revise:0",
        "impl:bd-ib-123",
    ]
