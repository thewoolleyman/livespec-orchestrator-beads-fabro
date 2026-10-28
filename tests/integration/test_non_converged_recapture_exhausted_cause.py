"""The `non_converged` terminal names WHICH cap fired, not always the janitor's.

Work-item `bd-ib-iy4cd4`. Run `01M5YH9P9REX` ended on `LIVESPEC_RECAPTURE_EXHAUSTED`
at `recapture_route@3`, and `non_converged@1` then printed the fixed
"janitor fix-loop cap hit" line, which the Dispatcher read as a janitor
non-convergence and bounced to `backlog` for `needs-regroom`. The real fault was a
proof record that kept failing review, which a proof-capture rider can repair.

Both scripts are EXECUTED, in a throwaway clone with a stand-in `gh`, because the
property is a sequence: `recapture_route` has to leave a trace that `non_converged`
reads, and a substring assertion on either script cannot show that the trace
crosses the node boundary.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_ROUTE = "recapture_route"
_TERMINAL = "non_converged"
_RECURRING = "- [BLOCKING] (proof-record) step 2 runs a helper no step creates"
_ONE_OFF = "- [BLOCKING] (proof-record) the head named is stale"

_STAND_IN_GH = f"""#!/bin/sh
case "$1 $2" in
  "pr list") echo 7 ;;
  "pr view")
    printf '%s\\n' '{_RECURRING}' '{_ONE_OFF}' '{_RECURRING}'
    ;;
esac
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


def _stand_in_bin(*, tmp_path: Path) -> Path:
    directory = tmp_path / "bin"
    directory.mkdir(exist_ok=True)
    gh = directory / "gh"
    _ = gh.write_text(_STAND_IN_GH, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return directory


def _run(*, node: str, repo: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PATH"] = f"{_stand_in_bin(tmp_path=tmp_path)}:{environment['PATH']}"
    environment["LIVESPEC_PUBLISH_BRANCH"] = "feat/bd-ib-iy4cd4"
    return subprocess.run(
        ["sh", "-c", _script(node=node)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _exhaust_recapture(*, repo: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    third = None
    for _ in range(3):
        third = _run(node=_ROUTE, repo=repo, tmp_path=tmp_path)
    assert third is not None
    assert third.returncode != 0, third.stdout
    return third


def test_recapture_exhaustion_is_named_by_the_terminal_with_the_recurring_findings(
    tmp_path: Path,
) -> None:
    """Assertion 1: the cause line names the recapture cap and what kept recurring."""
    repo = _clone(tmp_path=tmp_path)
    _ = _exhaust_recapture(repo=repo, tmp_path=tmp_path)

    terminal = _run(node=_TERMINAL, repo=repo, tmp_path=tmp_path)

    assert terminal.returncode != 0
    assert "LIVESPEC_RECAPTURE_EXHAUSTED" in terminal.stderr
    assert _RECURRING in terminal.stderr
    assert _ONE_OFF not in terminal.stderr
    assert "janitor fix-loop cap" not in terminal.stderr
    assert "LIVESPEC_NON_CONVERGED" not in terminal.stderr


def test_a_janitor_cap_exit_still_reports_the_janitor_cap(tmp_path: Path) -> None:
    """Assertion 3: with no recapture exhaustion recorded, the fixed line is unchanged."""
    repo = _clone(tmp_path=tmp_path)

    terminal = _run(node=_TERMINAL, repo=repo, tmp_path=tmp_path)

    assert terminal.returncode != 0
    assert "LIVESPEC_NON_CONVERGED: janitor fix-loop cap hit" in terminal.stderr
    assert "needs-regroom" in terminal.stderr
    assert "LIVESPEC_RECAPTURE_EXHAUSTED" not in terminal.stderr
