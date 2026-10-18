"""A pull request that already anchored two resumes is seeded, not resumed a third time.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" lists the reached chain bound
among the fallback-permitting refusals — "the pull request already anchored two
resumes" — and then says what must happen next: "When resume is inapplicable
because no valid proof anchor exists, the head or Definition of Done changed, or
the resume-count bound is reached, the Dispatcher MUST autonomously use a plain
dispatch seeded from preserved work."

WHY THE BOUND IS THE ONE REFUSAL WORTH ITS OWN ROUTING MODULE. Its state is the
only fallback-permitting one that is INVISIBLE in the outside world: the forge
names an open pull request at exactly the anchored head, the pull request carries
the records, the factory holds nothing alive, origin carries the preserved ref —
every measurement a resume takes comes back clean, and the refusal comes from the
journal's own count of earlier resumes. So a build that dropped the count would
reach a perfectly well-formed THIRD resume here, and nothing in the forge, the
factory or origin would contradict it. The sibling `seeded` module reaches its
fallback through a MISSING pull request, which is the opposite shape: there, the
resume fails on the outside world and the count is never consulted.

WHY THE ABSENT THIRD RECORD IS ASSERTED AS WELL AS THE ROUTE. The two assertions
fail in different directions and neither implies the other. A build that routed
`seeded` while still journaling a `resume` record would leave the chain one
closer to a bound it had already reached — and the count is read from exactly
those records, so the next pass would see THREE and the fault would compound
silently while the item kept being seeded correctly. And a build that journaled
nothing while still resuming would route the item onto a tree with no attribution
link, which is the mirror failure: the acceptance pass reads that record to credit
an earlier run's proof.

The record count is read on the journal the pass WROTE, so "no third record" is a
measurement of this pass rather than an inference from the two the fixture seeded.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Import order is load-bearing; see `test_dispatcher_recovery_routing_resume.py`
# for the cycle this leading import breaks.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as _admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_launch as launch,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_routing as routing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    NEEDS_HUMAN_REF_PREFIX,
    SEED_REMOTE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    PRESERVED_WORK_VERIFIED,
    RECOVERY_ROUTE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_SEEDED,
    RecoverySeed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    RESUME_FETCH_REF_ARG,
    RESUME_HEAD_ARG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import RESUME_STAGE
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    gather_resume,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    resume_refusals,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ = _admission

_ITEM_ID = "bd-ib-kn7ktk"
_BRANCH = f"feat/{_ITEM_ID}"
_PR = 3401

# The three runs of the chain: the original dispatch and the two resumes of it.
# The newest is what the preserved ref belongs to and what the seed names.
_FIRST_RUN = "01M52R2WND7Y0000000000000A"
_SECOND_RUN = "01M52R2WND7Y0000000000000B"
_THIRD_RUN = "01M52R2WND7Y0000000000000C"

_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"
_PRESERVED_COMMIT = "216c811200000000000000000000000000000002"
_PRESERVED_REF = f"{NEEDS_HUMAN_REF_PREFIX}/{_THIRD_RUN}"

# The record the newest run published before dying, which is what makes the
# resume's anchor measurement succeed — so the refusal can only come from the
# count.
_PROOF_BODY = (
    f"Proof of Done — verified — run {_THIRD_RUN} — 2026-10-18T00:00:00Z\n"
    f"{PUBLISH_HEAD_LABEL}: {_PUBLISHED_HEAD}\n"
)


class _Shell:
    """A scripted seam; an unscripted argv FAILS rather than answering.

    A refusal rather than an empty success, because every claim here rests on the
    outside world answering CLEANLY: a seam that invented an empty reply would
    make "the resume was refused by the count" indistinguishable from "the resume
    was refused by a measurement that came back blank".
    """

    answers: ClassVar[dict[str, CommandResult]] = {}
    calls: ClassVar[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        _Shell.calls.append(joined)
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


def test_the_shell_seam_refuses_a_command_no_case_scripted() -> None:
    """The instrument's own control; see the sibling wave modules for the argument."""
    _Shell.answers = {}
    _Shell.calls = []

    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Shell().run(
            argv=["git", "ls-remote", "origin", "refs/heads/x"],
            cwd=Path("/repo"),
            timeout_seconds=1.0,
        )


def _arm(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A world in which EVERY resume measurement comes back clean.

    The forge names one OPEN pull request at exactly the head the newest record
    declares, so no head has moved; that record is a factory `verified` one, so
    the anchor resolves; the factory board answers and holds nothing of this item
    alive; and origin carries the needs-human ref the dying run pushed. The only
    thing left that can refuse is the chain count.
    """
    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(
            exit_code=0,
            stdout=json.dumps([{"number": _PR, "state": "OPEN", "headRefOid": _PUBLISHED_HEAD}]),
            stderr="",
        ),
        f"gh pr view {_PR} --json comments": CommandResult(
            exit_code=0,
            stdout=json.dumps({"comments": [{"body": _PROOF_BODY, "url": "u"}]}),
            stderr="",
        ),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
        f"ls-remote {SEED_REMOTE} {NEEDS_HUMAN_REF_PREFIX}/": CommandResult(
            exit_code=0, stdout=f"{_PRESERVED_COMMIT}\t{_PRESERVED_REF}\n", stderr=""
        ),
    }
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A released item whose pull request has already been resumed twice",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _dispatch(*, dispatch_id: str, run: str) -> Sequence[dict[str, object]]:
    """One dispatch of the item, launched and released back to `ready`."""
    return (
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": dispatch_id,
            "workflow_name": "implement-work-item",
        },
        {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": run},
        {
            "stage": "stall-cancel-release",
            "work_item_id": _ITEM_ID,
            "status": "ready",
            "run_id": run,
        },
    )


def _resume_record(*, earlier_run: str) -> dict[str, object]:
    """One journaled resume of this pull request, naming the run it set out to finish."""
    return {
        "stage": RESUME_STAGE,
        "work_item_id": _ITEM_ID,
        "earlier_run_ids": [earlier_run],
        "pull_request": _PR,
        "head": _PUBLISHED_HEAD,
        "resumed_at": "proof_capture",
        "resumed_at_source": "latest-record",
    }


def _history() -> Sequence[dict[str, object]]:
    """The original dispatch plus TWO resumes of it, each released again.

    Written in the order a real chain accumulates: a dispatch, its release, the
    resume record the next pass journals BEFORE its run exists, that run, its
    release, and the same again. The newest row is a release, which is what leaves
    the item released for recovery.
    """
    return (
        *_dispatch(dispatch_id="d1", run=_FIRST_RUN),
        _resume_record(earlier_run=_FIRST_RUN),
        *_dispatch(dispatch_id="d2", run=_SECOND_RUN),
        _resume_record(earlier_run=_SECOND_RUN),
        *_dispatch(dispatch_id="d3", run=_THIRD_RUN),
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in _history()), encoding="utf-8"
    )
    return journal


def _rows(*, journal: JournalFile, stage: str) -> tuple[dict[str, Any], ...]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(record for record in written if record.get("stage") == stage)


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        workflow_name="implement-work-item",
        fabro_bin="/usr/local/bin/fabro",
    )


def _pins() -> launch.LaunchPins:
    """Pins that apply nothing, so the launch namespace carries only route state."""

    def _through(**kwargs: object) -> argparse.Namespace:
        pinned = kwargs["args"]
        assert isinstance(pinned, argparse.Namespace)
        return pinned

    return launch.LaunchPins(factory=_through, workflow=_through)


def test_a_pull_request_that_already_anchored_two_resumes_is_seeded_from_its_preserved_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole bound, read off one routing pass plus the launch it hands over to.

    The route is `seeded` from the preserved commit, the journal carries the two
    resume records it started with and no third, and the launch places the sandbox
    on that commit by way of the ref that carries it — at `start`, because a seed
    is not a resume and the unfinished nodes all have to run.
    """
    journal = _journal(tmp_path=tmp_path)
    _arm(monkeypatch=monkeypatch)

    routed = routing.route_recovery(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        candidates=[_work_item()],
        journal=journal,
    )
    route = routed.route_for(work_item_id=_ITEM_ID)
    assert route is not None
    launch.journal_recovery_route(route=route, journal=journal)
    launched = launch.recovery_launch_args(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        route=route,
        pins=_pins(),
    )

    assert route.route == ROUTE_SEEDED
    assert route.preserved_work == PRESERVED_WORK_VERIFIED
    assert route.seed == RecoverySeed(
        source_run_id=_THIRD_RUN,
        remote=SEED_REMOTE,
        commit_sha=_PRESERVED_COMMIT,
        preservation_ref=_PRESERVED_REF,
    )
    # Exactly the two the fixture seeded: no third resume was journaled, so the
    # count the next pass reads is still two rather than three.
    assert [record["earlier_run_ids"] for record in _rows(journal=journal, stage=RESUME_STAGE)] == [
        [_FIRST_RUN],
        [_SECOND_RUN],
    ]
    assert [record["route"] for record in _rows(journal=journal, stage=RECOVERY_ROUTE_STAGE)] == [
        ROUTE_SEEDED
    ]
    assert getattr(launched, RESUME_HEAD_ARG, None) == _PRESERVED_COMMIT
    assert getattr(launched, RESUME_FETCH_REF_ARG, None) == _PRESERVED_REF
    assert getattr(launched, "resume_entry_node", None) is None


def test_the_refusal_that_sent_this_item_to_the_fallback_is_the_chain_bound_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case above is only about the bound if the bound is what refused.

    Without this, a world that happened to refuse for some other reason — a head
    that did not match, an unreadable record list — would produce the identical
    `seeded` route and the identical absent third record, and the module would be
    asserting the right outcome for the wrong cause. The refusal list is produced
    by the SAME `gather_resume` and `resume_refusals` pair the routing pass grades
    its ladder on, against the same scripted world, so it is that pass's own
    reading rather than a second one assembled here.
    """
    journal = _journal(tmp_path=tmp_path)
    _arm(monkeypatch=monkeypatch)
    gather = gather_resume(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        item=_work_item(),
        journal_path=journal.path,
        runner=ShellCommandRunner(),
    )

    refusals = resume_refusals(observation=gather.observation)

    assert len(refusals) == 1
    assert "2 resumes" in refusals[0]
    assert _FIRST_RUN in refusals[0]
    assert _SECOND_RUN in refusals[0]
    # And the anchor the bound refused DID resolve, which is what makes this a
    # count refusal rather than a resume that had nothing to anchor on anyway.
    assert gather.anchor is not None
    assert gather.anchor.head == _PUBLISHED_HEAD
