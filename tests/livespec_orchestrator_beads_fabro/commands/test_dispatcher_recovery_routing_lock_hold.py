"""A live ownership lock holds a released item that could otherwise be seeded.

Scenario 185's fifth scenario. The `contracts.md` section
"Factory-configurable ACP fallback priority" → "Recovery from the failed run's
preserved work" splits the resume's refusals in two and routes on the class: a
refusal is "*fallback-permitting* when its named remedy is a plain dispatch",
while "Every other refusal is *non-fallback*: the earlier run is live, the
item's dispatch-scoped ownership lock is held by a live process, or the pull
request is merged". And: "A non-fallback refusal takes precedence over every
fallback-permitting one".

WHY THE FIXTURE CARRIES EVERY INGREDIENT OF A `seeded` ROUTE. This case's whole
claim is about PRECEDENCE, so the route it must not take has to be available.
The forge names no pull request — the first arm of the resume's anchor ladder,
and a fallback-permitting refusal; origin carries the needs-human ref the dying
run pushed, so preserved work verifies; the factory answers and holds nothing
alive; and both of the reclaim's forge calls are scripted. A build that graded
the refusals as one undifferentiated set therefore completes a perfectly
well-formed `seeded` dispatch rather than erroring, which is the failure being
closed: a second run started against a branch whose lock says a first dispatch
still owns it.

WHY THE HOLD'S `measurements` LIST IS ASSERTED EMPTY. A hold has two causes and
the clause keeps them apart because their remedies differ in kind — a
measurement that could not be taken is retried automatically by the next pass,
while a non-fallback refusal names a remedy a human or another valve performs.
A build that reached the hold by failing to MEASURE something would satisfy
every other assertion here while telling an operator to wait for a read that
answered perfectly well.

WHY THE LOCK IS A REAL FILE RATHER THAN A STUBBED READER. The lock is read
through `live_dispatch_lock`, which is also what decides liveness, so a stubbed
reader would prove only that routing consults whatever it is handed. The file
is written for this process's own pid, which `os.kill(pid, 0)` genuinely
answers for. Only the `/proc` start-time comparison is stood down — it is the
one input a test cannot set, and standing it down is what lets the lock carry a
chosen AGE instead of the zero a just-written lock would report.

WHY `dispatch --item` IS DRIVEN IN THE SAME FILE. The clause gives the two
entry points one decision and two reports: "Under `loop` the hold is reported
as a deferred outcome... Under `dispatch --item` it is a precondition error
(exit `3`...) naming the item and the measurement or the non-fallback refusals
with their remedies, before any run exists". The targeted path reaches routing
through its own call site, so a hold wired into the drain alone leaves
`dispatch --item` claiming and launching the very item the drain refuses.
"""

from __future__ import annotations

import argparse
import json
import os
import time
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
    _dispatcher_dispatch_lock as dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_wave as loop_wave,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_run_commands as run_commands,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_run_launch as run_launch,
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
from returns.io import IOSuccess

_ITEM_ID = "bd-ib-qgcpoc"
_BRANCH = f"feat/{_ITEM_ID}"
_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_DISPATCH = "a7395318d0c945589105940e7936139f"
_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"
_PRESERVED_COMMIT = "216c811200000000000000000000000000000002"

# The wave-mate: no journaled history, so nothing released it and it is routed
# `fresh` without any remote measurement.
_FRESH_ID = "bd-ib-3snvbf"

# How old the lock reads. A round number so the rendered "Ns old" is exact, and
# large enough that a build rendering anything but the lock's own age cannot
# match it by accident.
_LOCK_AGE_SECONDS = 42.0

# Spelled as literals because this file's Red predates the module that exports
# them, and a Red's test bytes are fixed across its Red-to-Green pair.
_HELD_STAGE = "recovery-held"
_ROUTE_STAGE = "recovery-route"
_RECLAIM_STAGE_PREFIX = "publish-branch-reclaim"
_EXIT_PRECONDITION_ERROR = 3


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


def _arm(*, monkeypatch: pytest.MonkeyPatch, repo: Path) -> None:
    """A world where a `seeded` route is fully available and the lock forbids it."""
    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
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
    _write_live_lock(repo=repo)
    # The ONE input a test cannot set. `None` is what this helper genuinely
    # answers wherever `/proc` cannot be read, and it is what lets the lock
    # below carry an age instead of reading as written-this-instant.
    monkeypatch.setattr(dispatch_lock, "process_started_at_epoch", lambda **_kwargs: None)


def _write_live_lock(*, repo: Path) -> None:
    """This item's dispatch lock, owned by a live pid and `_LOCK_AGE_SECONDS` old."""
    path = dispatch_lock.dispatch_lock_path(repo=repo, work_item_id=_ITEM_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "work_item_id": _ITEM_ID,
                "pid": os.getpid(),
                "started_at_epoch": time.time() - _LOCK_AGE_SECONDS,
                "dispatch_id": _DISPATCH,
            }
        ),
        encoding="utf-8",
    )


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="A released item whose dispatch lock is held by a live process",
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


def _args(*, repo: Path, journal: JournalFile, item: str | None) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        item=item,
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
    """One wave over the locked released candidate and an unreleased wave-mate."""
    journal = _journal(tmp_path=tmp_path)
    items = [_work_item(item_id=_ITEM_ID), _work_item(item_id=_FRESH_ID)]
    offered: list[str] = []
    launched: list[str] = []

    _arm(monkeypatch=monkeypatch, repo=tmp_path)
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
        args=_args(repo=tmp_path, journal=journal, item=None),
        repo=tmp_path,
        items=items,
        selected_candidates=items,
        journal=journal,
        janitor=None,
        rework=ReworkPass(scope_ids=frozenset()),
    )
    return _Wave(journal=journal, offered=offered, launched=launched, outcomes=outcomes)


@dataclass(kw_only=True)
class _Targeted:
    exit_code: int
    claimed_and_launched: list[str]


def _drive_targeted(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Targeted:
    """`dispatch --item` over the same locked candidate, with routing live.

    Every seam AROUND routing is stood in, including the shared pre-dispatch
    wall: routing sits strictly after it, so a wall refusal answering first
    would return the same exit code for a different reason. The two seams whose
    entry IS the claim and the run are logged rather than merely neutralized —
    `admit_and_select` writes `ready -> active`, and `dispatch_one` creates the
    factory run — because "before any run exists" is a claim about them, and
    they are stood in where the targeted path reaches them, which is its own
    admit-and-launch module rather than the command module.
    """
    journal = _journal(tmp_path=tmp_path)
    item = _work_item(item_id=_ITEM_ID)
    log: list[str] = []

    _arm(monkeypatch=monkeypatch, repo=tmp_path)
    monkeypatch.setattr(run_commands, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(run_commands, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(run_commands, "prepare", lambda **_kwargs: ([item], journal))
    monkeypatch.setattr(run_commands, "ready_items", lambda **_kwargs: [item])
    monkeypatch.setattr(run_commands, "pre_dispatch_wall_exit", lambda **_kwargs: None)
    monkeypatch.setattr(
        run_commands, "apply_factory_size_dispatch_entry", lambda **_kwargs: IOSuccess(())
    )
    monkeypatch.setattr(
        run_commands,
        "dispatch_tail_exit",
        lambda **_kwargs: log.append("reported a verdict") or 0,
    )
    monkeypatch.setattr(
        run_launch,
        "admit_and_select",
        lambda **_kwargs: log.append("claimed the row")
        or admission.Admission(admitted=[item], deferred=[], refused=[]),
    )
    monkeypatch.setattr(
        run_launch,
        "dispatch_one",
        lambda **_kwargs: log.append("created a run")
        or DispatchOutcome(
            work_item_id=item.id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="stood in",
        ),
    )
    monkeypatch.setattr(run_launch, "post_admission_publish_branch_reclaim", lambda **_kwargs: None)
    monkeypatch.setattr(
        run_launch, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(
        run_launch, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"]
    )
    exit_code = run_commands.run_dispatch_command(
        args=_args(repo=tmp_path, journal=journal, item=_ITEM_ID)
    )
    return _Targeted(exit_code=exit_code, claimed_and_launched=log)


def test_a_live_ownership_lock_holds_a_released_item_that_has_preserved_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route is `held`, not `seeded`, and the hold names the lock itself.

    The three claims the fifth scenario makes of the routing pass, off one wave.
    The hold's REASON is asserted to be a refusal rather than a measurement,
    which is what separates "the lock forbade the fallback" from "something
    could not be read" — two holds with the same row shape and opposite
    remedies.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    # Not admitted in this pass and nothing launched for it: the valve, which is
    # the only thing that writes `ready -> active`, was never offered it.
    assert wave.offered == [_FRESH_ID]
    assert wave.launched == [_FRESH_ID]
    # Held took no route at all — and specifically not the `seeded` one every
    # ingredient of which this fixture supplies.
    assert [
        (record["work_item_id"], record["route"])
        for record in _rows(journal=wave.journal, stage_prefix=_ROUTE_STAGE)
    ] == [(_FRESH_ID, "fresh")]
    held = _rows(journal=wave.journal, stage_prefix=_HELD_STAGE)
    assert [record["work_item_id"] for record in held] == [_ITEM_ID]
    # Every read answered, so this hold is a refusal and names no measurement.
    assert held[0]["measurements"] == []
    assert held[0]["details"] == []
    refusals = [str(one) for one in held[0]["refusals"]]
    assert len(refusals) == 1
    assert "dispatch-scoped ownership lock" in refusals[0]
    assert f"{_LOCK_AGE_SECONDS:.0f}s old" in refusals[0]
    assert "wait for that dispatch to release it" in refusals[0]
    assert "fabro ps" in refusals[0]
    # And nothing on origin for the held item: no reclaim row, and neither of
    # the reclaim's own forge calls, both of which this fixture scripted.
    assert _rows(journal=wave.journal, stage_prefix=_RECLAIM_STAGE_PREFIX) == ()
    assert [call for call in _Shell.calls if "gh api" in call] == []


def test_the_lock_hold_rides_the_wave_report_as_a_deferred_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A drain that held a candidate reports it rather than silently losing it.

    The STATUS is the capacity one, which keeps the verdict and the
    post-verdict alarm treating the hold as a non-defect; the STAGE is the
    hold's own, which is what lets an operator tell the two apart. The detail
    carries the refusal, so the drain's report and the journal row say the same
    thing about the same lock.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert sorted((one.work_item_id, one.status) for one in wave.outcomes) == [
        (_FRESH_ID, "green"),
        (_ITEM_ID, "capacity-deferred"),
    ]
    held = next(one for one in wave.outcomes if one.work_item_id == _ITEM_ID)
    assert held.stage == _HELD_STAGE
    assert "dispatch-scoped ownership lock" in str(held.detail)


def test_dispatch_item_exits_three_naming_the_lock_before_any_run_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The targeted path refuses with the precondition code and names the lock.

    The log is asserted EMPTY rather than merely lacking the run: a build that
    claimed the row and then refused would leave the item `active` with no
    factory run, which is the stranded shape a pre-claim refusal exists to
    retire.
    """
    targeted = _drive_targeted(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert targeted.exit_code == _EXIT_PRECONDITION_ERROR
    assert targeted.claimed_and_launched == []
    err = capsys.readouterr().err
    assert _ITEM_ID in err
    assert "dispatch-scoped ownership lock" in err
    assert f"{_LOCK_AGE_SECONDS:.0f}s old" in err
    assert "wait for that dispatch to release it" in err
    assert "fabro ps" in err
    assert [call for call in _Shell.calls if "gh api" in call] == []
