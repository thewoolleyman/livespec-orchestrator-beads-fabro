"""The `non_converged` terminal names the cap that actually fired (work-item `bd-ib-iy4cd4`).

Run `01M5YH9P9REX` for `bd-ib-yzk2h2` (petri, 2026-10-27) ended at `recapture_route`
with `LIVESPEC_RECAPTURE_EXHAUSTED`, and `non_converged` then printed its one fixed
line, "janitor fix-loop cap hit without converging; routing back to the Dispatcher
for needs-regroom". The janitor had succeeded. The real fault was a proof record
whose steps kept failing the record grammar, which a proof-capture rider repairs,
so the misnamed cause sent a recoverable item to the maintainer groom valve.

The node's script bytes decide which cause line is printed, so they are EXECUTED
here in a throwaway clone, taken through `parse_dot_graph` rather than retyped.
The recapture arm is reached the way the run reaches it, through the counter the
`recapture_route` node itself writes, never through a hand-seeded file alone.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_RECAPTURE_MARKER = "LIVESPEC_RECAPTURE_EXHAUSTED"
_FINDING = "[BLOCKING] (proof-record) step 2 runs a helper the record never creates"

# A stand-in for the forge client. `pr list` answers a pull request number and
# `pr view` answers what the node's own filter would have printed for the review
# records, so the node's shell flow is what is under test; the filter itself is
# jq and is exercised against real review-record bodies by the forge.
_GH_STUB = """#!/bin/sh
case "$1 $2" in
    "pr list") echo 4242 ;;
    "pr view") printf '%s\\n' "$LIVESPEC_TEST_RECORD_FINDINGS" ;;
    *) exit 1 ;;
esac
"""

_GH_FAILING_STUB = """#!/bin/sh
exit 1
"""


def _script(*, node: str) -> str:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[node]["script"]


def _clone(*, tmp_path: Path) -> Path:
    repo = tmp_path / "clone"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    return repo


def _stub_bin(*, tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "bin"
    directory.mkdir(exist_ok=True)
    gh = directory / "gh"
    _ = gh.write_text(body, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return directory


def _run(
    *, node: str, repo: Path, stub_bin: Path | None = None
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["LIVESPEC_PUBLISH_BRANCH"] = "feat/bd-ib-iy4cd4"
    environment["LIVESPEC_TEST_RECORD_FINDINGS"] = _FINDING
    if stub_bin is not None:
        environment["PATH"] = f"{stub_bin}{os.pathsep}{environment['PATH']}"
    return subprocess.run(
        ["sh", "-c", _script(node=node)],
        cwd=repo,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _exhaust_recapture(*, repo: Path) -> None:
    """Take three recapture verdicts through the route node, which counts its own entries."""
    results = [_run(node="recapture_route", repo=repo) for _ in range(3)]
    assert [one.returncode for one in results] == [0, 0, 1], [one.stderr for one in results]


def test_a_run_ended_by_recapture_exhaustion_names_the_recapture_cap_and_the_findings(
    tmp_path: Path,
) -> None:
    """Assertion 1: the cause line names the recapture cap and the recurring findings."""
    repo = _clone(tmp_path=tmp_path)
    _exhaust_recapture(repo=repo)

    result = _run(
        node="non_converged",
        repo=repo,
        stub_bin=_stub_bin(tmp_path=tmp_path, body=_GH_STUB),
    )

    assert result.returncode == 1, result.stderr
    assert f"{_RECAPTURE_MARKER}:" in result.stderr
    assert "recapture cap" in result.stderr
    assert _FINDING in result.stderr


def test_a_run_ended_by_recapture_exhaustion_does_not_claim_the_janitor_cap_was_hit(
    tmp_path: Path,
) -> None:
    """Assertion 1, negative half: neither the janitor wording nor its routing survives."""
    repo = _clone(tmp_path=tmp_path)
    _exhaust_recapture(repo=repo)

    result = _run(
        node="non_converged",
        repo=repo,
        stub_bin=_stub_bin(tmp_path=tmp_path, body=_GH_STUB),
    )

    assert "janitor" not in result.stderr
    assert NON_CONVERGED_MARKER not in result.stderr
    assert "needs-regroom" not in result.stderr


def test_unreadable_review_records_still_name_the_cap_and_say_no_finding_was_read(
    tmp_path: Path,
) -> None:
    """The cause line is owed whether or not the forge answers."""
    repo = _clone(tmp_path=tmp_path)
    _exhaust_recapture(repo=repo)

    result = _run(
        node="non_converged",
        repo=repo,
        stub_bin=_stub_bin(tmp_path=tmp_path, body=_GH_FAILING_STUB),
    )

    assert result.returncode == 1, result.stderr
    assert f"{_RECAPTURE_MARKER}:" in result.stderr
    assert "recapture cap" in result.stderr
    assert "none could be read" in result.stderr


def test_a_janitor_cap_ending_still_reports_the_janitor_cap_and_needs_regroom(
    tmp_path: Path,
) -> None:
    """Assertion 3: with no exhausted recapture the line is exactly the existing one."""
    repo = _clone(tmp_path=tmp_path)

    result = _run(node="non_converged", repo=repo)

    assert result.returncode == 1, result.stderr
    assert f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit without converging" in result.stderr
    assert "needs-regroom" in result.stderr
    assert _RECAPTURE_MARKER not in result.stderr


def test_two_recapture_laps_alone_do_not_change_the_janitor_cap_line(tmp_path: Path) -> None:
    """Assertion 3: a run that recaptured below the cap and then hit the janitor cap."""
    repo = _clone(tmp_path=tmp_path)
    results = [_run(node="recapture_route", repo=repo) for _ in range(2)]
    assert [one.returncode for one in results] == [0, 0]

    result = _run(node="non_converged", repo=repo)

    assert f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit" in result.stderr
    assert _RECAPTURE_MARKER not in result.stderr
