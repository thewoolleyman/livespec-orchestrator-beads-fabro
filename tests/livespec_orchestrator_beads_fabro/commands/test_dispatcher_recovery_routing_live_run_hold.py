"""A still-live earlier run holds a released item; it is never seeded around.

The third of the three non-fallback refusals the `contracts.md` section
"Factory-configurable ACP fallback priority" → "Recovery from the failed run's
preserved work" names in one sentence: "Every other refusal is *non-fallback*:
the earlier run is live, the item's dispatch-scoped ownership lock is held by a
live process, or the pull request is merged". Its two siblings are bound by
`test_dispatcher_recovery_routing_lock_hold.py` and
`..._merged_hold.py`; this is the arm with no Definition-of-Done assertion of
its own, and it is the one whose absence is most expensive.

WHY IT IS THE MOST EXPENSIVE OF THE THREE. The other two hold work that is
merely in the wrong state. This one holds work that is STILL MOVING. A released
item whose earlier run is alive and a released item whose earlier run has ended
present identically everywhere except this measurement — the ledger row is
`ready` in both cases, the publish branch is standing in both, and preserved
work verifies in both. Classifying the live-run refusal as fallback-permitting
therefore seeds a SECOND run against a branch the first is still pushing to,
and both runs then race `publish_draft` on one ref.

WHY THIS SITS BESIDE THE UNOBSERVABLE-FACTORY CASE RATHER THAN INSIDE IT.
`test_dispatcher_recovery_routing_unobservable.py` drives a factory that cannot
be ASKED, which routes `held` on the measurement. This drives a factory that
answers perfectly well and reports a live run, which routes `held` on the
refusal. The two produce the same row SHAPE and carry opposite remedies — the
first clears itself on the next pass, the second clears when the run ends or is
reconciled — so each asserts which of the record's two lists is populated.

WHY THE FIXTURE AGAIN SUPPLIES A COMPLETE `seeded` ROUTE, and the wave-mate
control: see the lock-hold module, whose argument is the same one.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Import order is load-bearing; see `test_dispatcher_recovery_routing_resume.py`.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_wave as loop_wave,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-qgcpoc"
_BRANCH = f"feat/{_ITEM_ID}"
_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_DISPATCH = "a7395318d0c945589105940e7936139f"
_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"
_PRESERVED_COMMIT = "216c811200000000000000000000000000000002"

# The status the factory reports for the earlier run. One of the non-terminal
# kinds, so the reading is a LIVE run rather than a finished one.
_LIVE_STATUS = "running"

# The wave-mate: no journaled history, so nothing released it.
_FRESH_ID = "bd-ib-3snvbf"

# Spelled as literals because this file's Red predates the module that exports
# them, and a Red's test bytes are fixed across its Red-to-Green pair.
_HELD_STAGE = "recovery-held"
_ROUTE_STAGE = "recovery-route"
_RECLAIM_STAGE_PREFIX = "publish-branch-reclaim"


class _Shell:
    """A scripted subprocess seam; an unscripted argv FAILS rather than answering."""

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
    """The instrument's own control; see the resume module for the argument."""
    _Shell.answers = {}
    _Shell.calls = []

    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Shell().run(
            argv=["git", "ls-remote", "origin", "refs/heads/x"],
            cwd=Path("/repo"),
            timeout_seconds=1.0,
        )


def _arm(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A world whose only resume refusal is that the earlier run has not ended.

    The factory ANSWERS — which is what separates this from the unobservable
    case — and names the item's own earlier run at a non-terminal status. The
    forge names no pull request, the resume's first anchor refusal and a
    fallback-permitting one; origin carries the preservation ref, so preserved
    work verifies; and both of the reclaim's forge calls are scripted, so a
    build that fell through to `seeded` would complete rather than erroring.
    """
    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ps -a --json": CommandResult(
            exit_code=0,
            stdout=json.dumps([{"run_id": _RUN, "status": _LIVE_STATUS}]),
            stderr="",
        ),
        "inspect": CommandResult(
            exit_code=0,
            stdout=json.dumps([{"run_id": _RUN, "status": _LIVE_STATUS}]),
            stderr="",
        ),
        "ls-remote origin refs/heads/needs-human/": CommandResult(
            exit_code=0,
            stdout=f"{_PRESERVED_COMMIT}\trefs/heads/needs-human/{_RUN}\n",
            stderr="",
        ),
        f"ls-remote origin refs/heads/{_BRANCH}": CommandResult(
            exit_code=0, stdout=f"{_PUBLISHED_HEAD}\trefs/heads/{_BRANCH}\n", stderr=""
        ),
        "gh api --method POST": CommandResult(exit_code=0, stdout="", stderr=""),
        "gh api --method DELETE": CommandResult(exit_code=0, stdout="", stderr=""),
    }
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="A released item whose earlier run has not ended",
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


def _journal(*, tmp_path: Path) -> JournalFile:
    """A journal whose newest dispatch of the item ended in a first-stall release."""
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    records: Sequence[dict[str, object]] = (
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH,
            "workflow_name": "implement-work-item",
        },
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


def _rows(*, journal: JournalFile, stage_prefix: str) -> tuple[dict[str, Any], ...]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(record for record in written if str(record.get("stage")).startswith(stage_prefix))


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        item=None,
        items=None,
        budget=2,
        parallel=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


@dataclass(kw_only=True)
class _Wave:
    journal: JournalFile
    offered: list[str]
    launched: list[str]
    outcomes: list[DispatchOutcome]


def _drive_wave(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Wave:
    """One wave over the still-running released candidate and a wave-mate."""
    journal = _journal(tmp_path=tmp_path)
    items = [_work_item(item_id=_ITEM_ID), _work_item(item_id=_FRESH_ID)]
    offered: list[str] = []
    launched: list[str] = []

    _arm(monkeypatch=monkeypatch)
    monkeypatch.setattr(loop_wave, "await_usable_credential", lambda **_kwargs: None)
    monkeypatch.setattr(loop_wave, "resolve_acp_preflight", lambda **_kwargs: None)

    def _admit(**kwargs: Any) -> admission.Admission:
        candidates: list[WorkItem] = kwargs["candidates"]
        offered.extend(one.id for one in candidates)
        return admission.Admission(admitted=list(candidates), deferred=[], refused=[])

    monkeypatch.setattr(loop_wave, "admit_and_select", _admit)
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"]
    )

    def _launch(**kwargs: Any) -> DispatchOutcome:
        item_id = str(kwargs["item"].id)
        launched.append(item_id)
        return DispatchOutcome(
            work_item_id=item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="merged",
        )

    monkeypatch.setattr(loop_wave, "dispatch_one", _launch)
    outcomes = loop_wave.dispatch_loop_wave(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        items=items,
        selected_candidates=items,
        journal=journal,
        janitor=None,
        rework=ReworkPass(scope_ids=frozenset()),
    )
    return _Wave(journal=journal, offered=offered, launched=launched, outcomes=outcomes)


def test_a_still_live_earlier_run_holds_the_item_rather_than_seeding_a_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Held on the REFUSAL, naming the run and its status, with nothing reclaimed.

    The refusal list is asserted populated and the measurement list empty, which
    is what tells this hold apart from the unobservable-factory one: that hold
    clears itself on the next pass, while this one clears when the run ends or
    is reconciled, and the row shape alone cannot say which an operator is
    looking at.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert wave.offered == [_FRESH_ID]
    assert wave.launched == [_FRESH_ID]
    assert [
        (record["work_item_id"], record["route"])
        for record in _rows(journal=wave.journal, stage_prefix=_ROUTE_STAGE)
    ] == [(_FRESH_ID, "fresh")]
    held = _rows(journal=wave.journal, stage_prefix=_HELD_STAGE)
    assert [record["work_item_id"] for record in held] == [_ITEM_ID]
    # The factory ANSWERED, so no measurement is named; the hold is the refusal.
    assert held[0]["measurements"] == []
    assert held[0]["details"] == []
    refusals = [str(one) for one in held[0]["refusals"]]
    assert len(refusals) == 1
    assert "still live on its factory" in refusals[0]
    assert f"{_RUN} ({_LIVE_STATUS})" in refusals[0]
    assert "reconcile-runs" in refusals[0]
    # Nothing on origin: the branch the live run is pushing to is left alone.
    assert _rows(journal=wave.journal, stage_prefix=_RECLAIM_STAGE_PREFIX) == ()
    assert [call for call in _Shell.calls if "gh api" in call] == []


def test_the_live_run_hold_rides_the_wave_report_as_a_deferred_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain reports the hold, naming the run an operator has to wait on."""
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert sorted((one.work_item_id, one.status) for one in wave.outcomes) == [
        (_FRESH_ID, "green"),
        (_ITEM_ID, "capacity-deferred"),
    ]
    held = next(one for one in wave.outcomes if one.work_item_id == _ITEM_ID)
    assert held.stage == _HELD_STAGE
    assert _RUN in str(held.detail)
