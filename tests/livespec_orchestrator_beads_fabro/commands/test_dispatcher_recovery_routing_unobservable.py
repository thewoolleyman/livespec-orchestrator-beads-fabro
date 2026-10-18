"""A measurement that cannot be taken holds the item; it never seeds around it.

Scenario 185's fourth scenario. The `contracts.md` section
"Factory-configurable ACP fallback priority" → "Recovery from the failed run's
preserved work": "an unobservable or unreadable measurement at any step routes
`held`"; and "An unobservable forge or factory measurement requires an
automatically retried wait, not destructive reclaim."

WHY THE FACTORY MEASUREMENT IS THE ONE DRIVEN HERE. It is the measurement whose
failure is most plausibly mistaken for an answer: a factory that cannot be asked
and a factory holding nothing alive carry the SAME empty live-run set, and one
authorizes a recovery while the other forbids it. Driving the hold on this read
therefore exercises the distinction rather than a shape that could not be
confused.

WHY PRESERVED WORK IS DELIBERATELY AVAILABLE IN THIS FIXTURE. Origin DOES carry
a needs-human preservation ref, and the publish branch IS standing, and the
reclaim's own two forge calls ARE scripted. So every ingredient of a `seeded`
route is present and a build that fell through to it would succeed loudly — which
is exactly the failure this case exists to catch: a seed taken while the earlier
run's liveness was never established can start a second run against a branch the
first one is still pushing to.

WHY THE WAVE-MATE IS THE CONTROL. A build that withheld the whole selection from
the valve, or that journaled a hold for every candidate, would satisfy the held
half perfectly. The second item has no journaled history at all, so it is routed
`fresh` without any remote measurement, is offered, and launches in the same
pass.
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
_TERMINAL_COMMIT = "216c811200000000000000000000000000000002"

# The wave-mate: no journaled history, so nothing released it.
_FRESH_ID = "bd-ib-3snvbf"

# Spelled as literals because this file's Red predates the module that exports
# them, and a Red's test bytes are fixed across its Red-to-Green pair.
_HELD_STAGE = "recovery-held"
_ROUTE_STAGE = "recovery-route"
_MEASUREMENT_FACTORY_RUN_LIVENESS = "factory-run-liveness"
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
    """A world where only the FACTORY cannot be asked, and everything else can.

    The forge answers both of its reads. The factory board does not. Preserved
    work IS available and the publish branch IS standing, and both of the
    reclaim's forge calls are scripted — so a build that fell through to a
    `seeded` route would complete, which is what makes the hold a measurement
    rather than a crash in the right place.
    """
    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ps -a --json": CommandResult(exit_code=1, stdout="", stderr="dial tcp: refused"),
        "ls-remote origin refs/heads/needs-human/": CommandResult(
            exit_code=0,
            stdout=f"{_TERMINAL_COMMIT}\trefs/heads/needs-human/{_RUN}\n",
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
        title="A released item whose factory cannot be asked",
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
    """One wave whose released candidate's factory read cannot be taken."""
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


def test_an_unaskable_factory_holds_the_item_and_reclaims_nothing_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The item is never admitted, recorded once, and its branch is untouched.

    All four claims of the fourth scenario, off one wave. The hold is recorded
    EXACTLY once and names the measurement, so the next pass retries it rather
    than an operator having to find out which read failed; and the reclaim — whose
    every call was scripted and whose branch origin was carrying — never ran, so
    the dead run's publication is still there to recover from.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    # Not admitted in this pass, and nothing launched for it: the valve, which is
    # the only thing that writes `ready -> active`, was never offered it.
    assert wave.offered == [_FRESH_ID]
    assert wave.launched == [_FRESH_ID]
    held = _rows(journal=wave.journal, stage_prefix=_HELD_STAGE)
    assert [record["work_item_id"] for record in held] == [_ITEM_ID]
    assert held[0]["measurements"] == [_MEASUREMENT_FACTORY_RUN_LIVENESS]
    assert "could not" in str(held[0]["details"][0])
    # No route row either: a held item took no route.
    assert [
        record["work_item_id"] for record in _rows(journal=wave.journal, stage_prefix=_ROUTE_STAGE)
    ] == [_FRESH_ID]
    # And nothing on origin for the held item.
    assert _rows(journal=wave.journal, stage_prefix=_RECLAIM_STAGE_PREFIX) == ()
    assert [call for call in _Shell.calls if "gh api" in call] == []
    assert [call for call in _Shell.calls if f"ls-remote origin refs/heads/{_BRANCH}" in call] == []


def test_the_hold_rides_the_wave_report_as_a_deferred_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A drain that held a candidate reports it rather than silently losing it.

    "Under `loop` the hold is reported as a deferred outcome on the same terms as
    a capacity deferral" — so the status is the capacity one, which keeps the
    verdict and the post-verdict alarm treating an automatic retry as a
    non-defect.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert sorted((one.work_item_id, one.status) for one in wave.outcomes) == [
        (_FRESH_ID, "green"),
        (_ITEM_ID, "capacity-deferred"),
    ]
    held = next(one for one in wave.outcomes if one.work_item_id == _ITEM_ID)
    assert held.stage == _HELD_STAGE
    assert _MEASUREMENT_FACTORY_RUN_LIVENESS in str(held.detail)
