"""Tests for WHERE the post-merge janitor's check suite runs, and how it reads.

The venue's behaviour THROUGH the post-merge flow lives in
`test_dispatcher_engine_janitor.py`; this module covers the readings that flow
cannot produce -- a gate whose output carries no readable state, one that
narrates before it decides, and a janitor checkout whose HEAD does not resolve.
"""

import json
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_check_venue import (
    cluster_janitor_red,
    gate_tree_hash,
)

_CHECKOUT = Path("/tmp/janitor-x-1")


def _ran(*, stderr: str) -> CommandResult:
    """A gate client invocation that refused, carrying whatever it printed.

    `exit_code` is 1 in every case here because the client's own contract makes
    it 0 only on a passed gate whose green token was written -- and none of
    these readings is that.
    """
    return CommandResult(exit_code=1, stdout="", stderr=stderr)


def test_cluster_gate_verdict_is_read_past_lines_that_carry_no_state() -> None:
    """A progress line the client printed first must not shadow its verdict.

    The client logs one verdict line today, so this is the property that keeps
    the reading correct if it ever narrates first: the state is taken from the
    last line that carries one, not from the first line that parses.
    """
    narration = json.dumps({"event": "submitting the gate Job", "job": "gate-repo-0ff1ce"})
    verdict = json.dumps({"event": "delegated gate passed", "state": "PASSED"})

    red = cluster_janitor_red(
        result=_ran(stderr=f"not json at all\n{narration}\n{verdict}"), checkout=_CHECKOUT
    )

    assert red is None


def test_cluster_gate_output_carrying_no_readable_state_is_red() -> None:
    """Fail-closed: an output nothing can be read out of decides nothing.

    A gate client that could not start at all -- an absent tool runner, an
    absent package -- prints no state, and the one thing the post-merge gate
    must never do is read that as green. BOTH unreadable shapes are here: a
    line that is not JSON, and a well-formed JSON line that names no state,
    which is what a client logging something other than a verdict produces.
    """
    structured = json.dumps({"event": "delegated gate errored", "error": "no module named any"})

    red = cluster_janitor_red(
        result=_ran(stderr=f"Traceback (most recent call last):\n{structured}"),
        checkout=_CHECKOUT,
    )

    assert red is not None
    assert str(_CHECKOUT) in red


def test_submitted_tree_reading_that_could_not_be_taken_is_an_absence(tmp_path: Path) -> None:
    """A checkout whose HEAD does not resolve yields `None`, not a plausible-looking value.

    Run against REAL git through the production runner, because the behaviour
    under test is git's own: asked to resolve a revision it cannot, `git
    rev-parse` ECHOES the revision it was given onto standard output and exits
    128. So the reading declines by writing nothing rather than by failing to
    write, and an `or None` guard over a bare `rev-parse` can never fire -- the
    row would carry the literal `HEAD^{tree}` where the field's whole promise is
    an absence. A canned runner could assert nothing here: it would report
    whatever shape this module chose to hand it.

    The checkout is a `git init` with no commit, which is the state this field is
    read in when the janitor checkout could not be provisioned -- and the row's
    tree hash is exactly what an operator reads to find, or rule out, the gate
    Job for that tree, so a non-hex string there sends them looking for a Job
    whose name cannot exist.

    The POSITIVE CONTROL is the same reading one commit later, through the same
    runner against the same checkout. Without it, `None` is equally consistent
    with a build that answers `None` for every checkout, and the assertion would
    hold against a function that reads nothing at all.
    """
    checkout = tmp_path / "janitor-co"
    checkout.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=str(checkout), check=True)
    runner = ShellCommandRunner()

    unresolvable = gate_tree_hash(runner=runner, checkout=checkout)

    _ = (checkout / "merged.txt").write_text("the merged tree\n", encoding="utf-8")
    _ = subprocess.run(["git", "add", "merged.txt"], cwd=str(checkout), check=True)
    _ = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Janitor Fixture",
            "-c",
            "user.email=janitor@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "the merged default-branch tip",
        ],
        cwd=str(checkout),
        check=True,
    )
    resolvable = gate_tree_hash(runner=runner, checkout=checkout)

    assert unresolvable is None
    assert resolvable is not None
    assert len(resolvable) == 40
