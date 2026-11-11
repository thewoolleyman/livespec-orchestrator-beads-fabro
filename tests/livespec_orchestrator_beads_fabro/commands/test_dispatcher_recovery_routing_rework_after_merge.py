"""A rework rejection that postdates a pull request's merge routes the rework.

`bd-ib-nkoyln`, measured on `bd-ib-5d5aue`: the original pull request merged, a
coordinator then rejected the item to rework because its host-captured assertion
measured over budget, the rework dispatch ended at needs-human with its tree
preserved — and routing answered `held` with "pull request is already merged, so
there is no unmerged publication left to finish", whose own remedy
(`reconcile-merged`) would have closed an unfinished rework.

WHY THE REJECTION'S TIMESTAMP IS COMPARED WITH THE MERGE'S. A merged pull request
on the item's publish branch means two different things: the item's work landed
and nothing is owed (hold; the remedy is the close-out), or the work landed and a
LATER rejection says it was not enough (route the rework). Only the order of the
two events tells them apart, so every case below fixes both instants and the two
control cases swap the order while holding everything else still.

WHY THE CONTROLS ARE LOAD-BEARING. A build that stopped holding merged pull
requests at all satisfies the rework case exactly as well as a correct one, so the
rejection-BEFORE-merge case and the NO-rejection case must stay held, on the same
fixture.

WHY BOTH REWORK ENTRIES ARE DRIVEN. The human `reject:<id>:rework` valve and the
AI-fail automatic rework disposition are the only two entries the rework contract
permits to mark an item, and they journal different shapes; a reading of one
leaves the other's items held.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import pytest

# Import order is load-bearing; see `test_dispatcher_recovery_routes.py`.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as _admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_routing as routing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ = _admission

_ITEM_ID = "bd-ib-5d5aue"
_BRANCH = f"feat/{_ITEM_ID}"
_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_DISPATCH = "a7395318d0c945589105940e7936139f"
_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"
_PRESERVED_COMMIT = "8246ef5b700000000000000000000000000000002"
_PULL_REQUEST = 4328
_MERGED_AT = "2026-11-03T12:00:00Z"
_REJECTED_AFTER = "2026-11-04T09:48:12Z"
_REJECTED_BEFORE = "2026-11-02T09:48:12Z"

_HUMAN_REWORK = {"stage": "human-valve-reject-rework", "actor": "operator"}
_AI_REWORK = {"stage": "auto-disposition", "disposition": "ai-fail-auto-rework"}


class _Shell:
    """A scripted subprocess seam; an unscripted argv FAILS rather than answering."""

    answers: ClassVar[dict[str, CommandResult]] = {}

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
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


def test_the_shell_seam_refuses_a_command_no_case_scripted() -> None:
    """The instrument's own control: an unscripted command fails instead of answering."""
    _Shell.answers = {}

    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Shell().run(
            argv=["git", "ls-remote", "origin", "refs/heads/x"],
            cwd=Path("/repo"),
            timeout_seconds=1.0,
        )


def _arm(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A world whose pull request merged and whose rework run preserved a tree."""
    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(
            exit_code=0,
            stdout=json.dumps(
                [
                    {
                        "number": _PULL_REQUEST,
                        "state": "MERGED",
                        "headRefOid": _PUBLISHED_HEAD,
                        "mergedAt": _MERGED_AT,
                    }
                ]
            ),
            stderr="",
        ),
        f"gh pr view {_PULL_REQUEST} --json comments": CommandResult(
            exit_code=0, stdout=json.dumps({"comments": []}), stderr=""
        ),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ls-remote origin refs/heads/needs-human/": CommandResult(
            exit_code=0,
            stdout=f"{_PRESERVED_COMMIT}\trefs/heads/needs-human/{_RUN}\n",
            stderr="",
        ),
        f"ls-remote origin refs/heads/{_BRANCH}": CommandResult(
            exit_code=0, stdout=f"{_PUBLISHED_HEAD}\trefs/heads/{_BRANCH}\n", stderr=""
        ),
        f"{_PRESERVED_COMMIT}^{{tree}}": CommandResult(
            exit_code=0, stdout=f"{'1' * 40}\n", stderr=""
        ),
        f"{_PUBLISHED_HEAD}^{{tree}}": CommandResult(
            exit_code=0, stdout=f"{'2' * 40}\n", stderr=""
        ),
    }
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A released item rejected to rework after its pull request merged",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path, rejections: Sequence[dict[str, object]]) -> JournalFile:
    """The rejections, then a rework dispatch that ended at needs-human."""
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    records: Sequence[dict[str, object]] = (
        *rejections,
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH},
        {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH,
            "run_id": _RUN,
            "factory": "hp",
            "executing_stage": "proof_capture",
            "published_head": _PUBLISHED_HEAD,
        },
        {"stage": "stall-cancel-release", "work_item_id": _ITEM_ID, "status": "ready"},
    )
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _route(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rejections: Sequence[dict[str, object]]
) -> tuple[routing.RecoveryRouting, JournalFile]:
    journal = _journal(tmp_path=tmp_path, rejections=rejections)
    _arm(monkeypatch=monkeypatch)
    args = argparse.Namespace(
        repo=str(tmp_path),
        journal=str(journal.path),
        workflow_name="implement-work-item",
        fabro_bin="/usr/local/bin/fabro",
    )
    routed = routing.route_recovery(
        args=args, repo=tmp_path, candidates=[_work_item()], journal=journal
    )
    return routed, journal


def _rejection(*, shape: dict[str, str], at: str) -> dict[str, object]:
    return {**shape, "work_item_id": _ITEM_ID, "at": at}


@pytest.mark.parametrize("shape", [_HUMAN_REWORK, _AI_REWORK])
def test_a_rework_rejection_after_the_merge_routes_the_rework_seeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: dict[str, str]
) -> None:
    """The route is `seeded` from the newest needs-human tree, never `held`."""
    routed, _journal_file = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        rejections=[_rejection(shape=shape, at=_REJECTED_AFTER)],
    )

    route = routed.route_for(work_item_id=_ITEM_ID)
    assert route is not None
    assert route.route == "seeded"
    assert route.hold is None
    assert route.seed is not None
    assert route.seed.commit_sha == _PRESERVED_COMMIT
    assert routed.held_report(work_item_id=_ITEM_ID) is None


def test_a_rework_rejection_after_the_merge_with_no_preserved_tree_routes_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no needs-human tree and no other source, the rework starts fresh."""
    journal = _journal(
        tmp_path=tmp_path, rejections=[_rejection(shape=_HUMAN_REWORK, at=_REJECTED_AFTER)]
    )
    _arm(monkeypatch=monkeypatch)
    _Shell.answers["ls-remote origin refs/heads/needs-human/"] = CommandResult(
        exit_code=0, stdout="", stderr=""
    )
    _Shell.answers[f"ls-remote origin refs/heads/{_BRANCH}"] = CommandResult(
        exit_code=0, stdout="", stderr=""
    )
    _Shell.answers["ls-remote origin refs/livespec/"] = CommandResult(
        exit_code=0, stdout="", stderr=""
    )
    args = argparse.Namespace(
        repo=str(tmp_path),
        journal=str(journal.path),
        workflow_name="implement-work-item",
        fabro_bin="/usr/local/bin/fabro",
    )

    routed = routing.route_recovery(
        args=args, repo=tmp_path, candidates=[_work_item()], journal=journal
    )

    route = routed.route_for(work_item_id=_ITEM_ID)
    assert route is not None
    assert route.route == "fresh"
    assert routed.held_report(work_item_id=_ITEM_ID) is None


@pytest.mark.parametrize(
    "rejections",
    [
        [],
        [_rejection(shape=_HUMAN_REWORK, at=_REJECTED_BEFORE)],
        [_rejection(shape=_AI_REWORK, at=_REJECTED_BEFORE)],
        [{"stage": "human-valve-reject-rework", "work_item_id": _ITEM_ID}],
        [{"stage": "human-valve-reject-rework", "work_item_id": _ITEM_ID, "at": "not-a-time"}],
        [_rejection(shape=_HUMAN_REWORK, at=_REJECTED_AFTER) | {"work_item_id": "bd-ib-other"}],
    ],
    ids=[
        "no-rejection",
        "human-rejection-before-merge",
        "ai-rejection-before-merge",
        "rejection-without-timestamp",
        "rejection-with-unparseable-timestamp",
        "another-items-rejection",
    ],
)
def test_a_merge_no_rejection_postdates_still_holds_with_the_close_out_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rejections: list[dict[str, object]]
) -> None:
    """Without a rejection after the merge the item is held, remedy intact."""
    routed, _journal_file = _route(
        tmp_path=tmp_path, monkeypatch=monkeypatch, rejections=rejections
    )

    route = routed.route_for(work_item_id=_ITEM_ID)
    assert route is not None
    assert route.route == "held"
    report = routed.held_report(work_item_id=_ITEM_ID)
    assert report is not None
    assert f"pull request #{_PULL_REQUEST} is already merged" in report
    assert f"reconcile-merged --item {_ITEM_ID}" in report
