"""The fail-closed cost gate still gates only successful runs with a run record.

Binds `SPECIFICATION/contracts.md` section "Fail-closed cost gate (keyed on
`--item` presence)" as the attempt-cost clause leaves it: "section 'Fail-closed
cost gate (keyed on `--item` presence)' remains authoritative", and Scenario
45's "A run that did not reach a successful terminal outcome is not gated /
Then that run yields no gate verdict".

TWO CONDITIONS, AND BOTH ARE ASSERTED AS NECESSARY RATHER THAN MERELY STATED. A
green outcome whose run the attribution cannot place in `fabro ps -a --json` is
journaled as a SKIPPED gate and refuses nothing -- deliberately fail-open,
because the cost of an unknown run is unknown -- while a non-green outcome
produces no record at all. Those two absences are different, and an
implementation that collapsed them would report a confirmed run with no cost as
a run nobody could find.

THE REFUSING CONTROL IS WHAT MAKES THE ABSENCES EVIDENCE. Every case here runs
`enforce` on an UNATTENDED drain, the one combination in which the gate
genuinely refuses, and the green-and-resolvable case refuses -- so each absence
is about the condition its case varies rather than about a gate that had
stopped deriving verdicts.

THE NON-GREEN STATUSES ARE THE REAL ONES THIS DISPATCHER PRODUCES, including
the provider-limit release the attempt-cost clause is about. A fixture inventing
a status would leave the one status that now carries a cost observation
untested.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import (
    COST_MODE_ENFORCE,
    gate_wave,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome import (
    PROVIDER_LIMIT_RELEASE_STATUS,
)

_ITEM = "bd-ib-gatescope"
_RUN = "01GATESCOPERUNOFANITEM"

_GATE_STAGE = "cost-gate"
_SKIPPED_STAGE = "cost-gate-skipped"


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)

    def of_stage(self, *, stage: str) -> list[dict[str, object]]:
        return [one for one in self.records if one.get("stage") == stage]


def _outcome(*, status: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_run_id=_RUN,
    )


def _ps_json(*, confirmed: bool) -> str:
    """This item's run record, or a listing that confirms no run of it.

    The absent case carries ANOTHER run rather than an empty array, because a
    factory serves every repository on its host and an empty listing is a
    weaker fixture than a populated one the attribution cannot place.
    """
    goal = f"Work-item: {_ITEM}" if confirmed else "Work-item: bd-ib-somebodyelse"
    return json.dumps([{"run_id": _RUN, "goal": goal, "total_usd_micros": None}])


def _gated(*, status: str, confirmed: bool, journal: _RecordingJournal) -> tuple[str, ...]:
    """The strictest posture: `enforce`, on an unattended drain."""
    return gate_wave(
        unattended=True,
        outcomes=(_outcome(status=status),),
        ps_json=_ps_json(confirmed=confirmed),
        journal=journal,
        environ={},
        cost_mode=COST_MODE_ENFORCE,
    )


def test_a_successful_run_with_a_confirmed_run_record_is_gated() -> None:
    """The control: both conditions met, so the gate derives its verdict."""
    journal = _RecordingJournal()

    refusals = _gated(status="green", confirmed=True, journal=journal)

    assert refusals == (_ITEM,)
    gated = journal.of_stage(stage=_GATE_STAGE)
    assert len(gated) == 1
    assert gated[0]["run_id"] == _RUN
    assert gated[0]["observable"] is False
    assert gated[0]["refuse"] is True
    assert journal.of_stage(stage=_SKIPPED_STAGE) == []


def test_a_successful_run_with_no_confirmed_run_record_is_skipped_fail_open() -> None:
    """The cost of a run nobody can find is unknown, so nothing is refused."""
    journal = _RecordingJournal()

    refusals = _gated(status="green", confirmed=False, journal=journal)

    assert refusals == ()
    assert journal.of_stage(stage=_GATE_STAGE) == []
    skipped = journal.of_stage(stage=_SKIPPED_STAGE)
    assert len(skipped) == 1
    assert skipped[0]["work_item_id"] == _ITEM


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(PROVIDER_LIMIT_RELEASE_STATUS, id="provider-limit-release"),
        pytest.param("failed", id="failed"),
        pytest.param("blocked", id="blocked"),
        pytest.param("cancelled", id="cancelled"),
        pytest.param("run-unobservable", id="run-unobservable"),
    ],
)
def test_a_run_that_did_not_succeed_yields_no_gate_verdict_at_all(status: str) -> None:
    """Not a skipped gate either: an unsuccessful run is outside the gate's scope.

    Driven with a CONFIRMED run record, which is what makes the case about the
    status: with the record absent as well, the same absence would be equally
    consistent with the skip arm above.
    """
    journal = _RecordingJournal()

    refusals = _gated(status=status, confirmed=True, journal=journal)

    assert refusals == ()
    assert journal.of_stage(stage=_GATE_STAGE) == []
    assert journal.of_stage(stage=_SKIPPED_STAGE) == []
    assert journal.records == []
