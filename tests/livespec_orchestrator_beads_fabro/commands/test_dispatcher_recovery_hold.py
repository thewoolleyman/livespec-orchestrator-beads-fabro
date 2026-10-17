"""A held item is withheld from the valve, recorded once, and reported as deferred.

The `contracts.md` section "Factory-configurable ACP fallback priority" →
"Recovery from the failed run's preserved work": a `held` item "MUST NOT be
offered to the admission valve in that pass. It stays `ready`, the journal
carries one `recovery-held` record naming the item and the measurement that could
not be taken... and the next pass retries automatically. Under `loop` the hold is
reported as a deferred outcome on the same terms as a capacity deferral."

WHY THE PRESERVED-WORK READ IS THE MEASUREMENT USED HERE. It is the one
measurement only the fallback arm takes, so a case built on it exercises the hold
without also exercising the resume ladder's own measurements — which are graded
elsewhere. "An unreadable reference is not confirmed absence", so this read
failing is a hold rather than the `fresh` dispatch a confirmed absence permits.

WHY "WITHHELD FROM THE VALVE" IS ASSERTED ON THE VALVE'S OWN ARGUMENTS. The item
staying `ready` is not something this tier can observe in a ledger — the valve is
what writes `ready -> active`, and it is stood in. What it CAN observe is that the
valve was never offered the item, which is the mechanism rather than a proxy for
it: an item the valve never sees cannot be transitioned by it.

WHY THE DEFERRED OUTCOME'S STATUS AND STAGE ARE BOTH READ. The status is what the
verdict and the post-verdict alarm classify on, so a hold reported under any other
status turns an automatic retry into a drain that exits non-zero and pages
someone. The stage is what lets an operator tell a recovery hold from a full WIP
cap. One without the other is a reading that satisfies half the clause.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    RECOVERY_HELD_STAGE,
    recovery_held_record,
    recovery_held_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_HELD,
    RecoveryHold,
    RecoveryMeasurement,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    MEASUREMENT_PRESERVED_WORK,
    RecoveryRouting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-qgcpoc"
_BRANCH = f"feat/{_ITEM_ID}"
_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_DISPATCH = "a7395318d0c945589105940e7936139f"

# The second candidate: a first dispatch, routed `fresh` with no measurement. It
# is the control for every assertion below — a build that withheld the WHOLE
# selection from the valve, or reported every item deferred, would satisfy the
# held half exactly as well as a correct one does.
_FRESH_ID = "bd-ib-3snvbf"


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
    """The instrument's own control; see the resume module for the argument."""
    _Shell.answers = {}

    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Shell().run(
            argv=["git", "ls-remote", "origin", "refs/heads/x"],
            cwd=Path("/repo"),
            timeout_seconds=1.0,
        )


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="A released item whose preserved work cannot be read",
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
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH},
        {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH,
            "run_id": _RUN,
            "factory": "hp",
            "executing_stage": "proof_capture",
            "published_head": "f3f139b28469c7efaae32dcb897d73518edbaadd",
        },
        {"stage": "stall-cancel-release", "work_item_id": _ITEM_ID, "status": "ready"},
    )
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
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
    """One wave whose released candidate's preserved-work read cannot be taken."""
    journal = _journal(tmp_path=tmp_path)
    items = [_work_item(item_id=_ITEM_ID), _work_item(item_id=_FRESH_ID)]
    offered: list[str] = []
    launched: list[str] = []

    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
        # The one read that cannot be taken. Nothing below it in the preference
        # order is scripted, which the seam turns into a failure — so a build
        # that proceeded past an unreadable reference is caught rather than
        # quietly seeding from a lower-preference source.
        "ls-remote origin refs/heads/needs-human/": CommandResult(
            exit_code=128, stdout="", stderr="fatal: unable to access"
        ),
    }
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)
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
    monkeypatch.setattr(loop_wave, "post_admission_publish_branch_reclaim", lambda **_kwargs: None)

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


def test_an_unreadable_preserved_reference_holds_the_item_out_of_the_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The held item is never offered, never launched, and recorded exactly once.

    Its wave-mate is offered and launched in the same pass, which is what makes
    the hold per-item rather than a wave that stopped.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert wave.offered == [_FRESH_ID]
    assert wave.launched == [_FRESH_ID]
    held = _rows(journal=wave.journal, stage=RECOVERY_HELD_STAGE)
    assert [record["work_item_id"] for record in held] == [_ITEM_ID]
    assert held[0]["measurements"] == [MEASUREMENT_PRESERVED_WORK]
    assert "could not be established" in held[0]["details"][0]
    assert held[0]["refusals"] == []


def test_the_hold_is_reported_as_a_deferred_outcome_on_the_capacity_terms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The STATUS is the capacity one and the STAGE is this hold's own.

    The status is what the verdict and the alarm classify on, so a hold reported
    under any other one converts an automatic retry into a non-zero drain. The
    stage is what distinguishes a recovery hold from a full WIP cap for the
    operator reading the same line.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    deferred = [one for one in wave.outcomes if one.work_item_id == _ITEM_ID]
    assert [(one.status, one.stage) for one in deferred] == [
        ("capacity-deferred", RECOVERY_HELD_STAGE)
    ]
    assert MEASUREMENT_PRESERVED_WORK in str(deferred[0].detail)


def test_the_held_row_and_the_operator_refusal_name_the_same_reasons() -> None:
    """One renderer per surface, both reading one hold.

    Two renderers is how an operator comes to read a remedy the journal does not
    record. Both lists are asserted because the clause admits a hold caused by a
    measurement, by a non-fallback refusal, "or both".
    """
    hold = RecoveryHold(
        measurements=(RecoveryMeasurement(name="factory-run-liveness", detail="the factory"),),
        refusals=("wait for that dispatch to release it",),
    )

    record = recovery_held_record(work_item_id=_ITEM_ID, hold=hold)
    report = recovery_held_report(work_item_id=_ITEM_ID, hold=hold)

    assert record["measurements"] == ["factory-run-liveness"]
    assert record["details"] == ["the factory"]
    assert record["refusals"] == ["wait for that dispatch to release it"]
    assert "factory-run-liveness: the factory" in report
    assert "wait for that dispatch to release it" in report
    assert _ITEM_ID in report


def test_a_hold_route_carrying_no_hold_still_reports_rather_than_raising() -> None:
    """A defensive arm, and the reason it is not dead code.

    `RecoveryRoute.hold` is optional because three of the four routes have no
    hold, so the type admits a shape the routing step never constructs. The arm
    exists so that shape produces a reportable outcome instead of an
    `AttributeError` raised from inside the drain's own reporting — which would
    convert a held item into a crashed wave.
    """
    routing = RecoveryRouting(routes=(RecoveryRoute(work_item_id=_ITEM_ID, route=ROUTE_HELD),))

    assert [one.detail for one in routing.held_outcomes()] == ["recovery held"]
