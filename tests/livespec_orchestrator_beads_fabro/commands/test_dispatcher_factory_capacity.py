"""One overflow candidate's capacity: the two figures, and every unmeasured arm.

Scenario 203 is bound at the integration tier by
`tests/integration/test_factory_overflow_selection_scenario203.py`; these cases
cover what that tier cannot observe, which is every reading a FACTORY CANNOT
PRODUCE. A live server does not report a `max_concurrent_runs` below 1, and a
declared factory on a dispatch path always carries a server or a registry — so
the three arms below are reachable only by handing the reading in directly, and
each one decides whether a candidate is passed over or dispatched to.

WHY A CEILING BELOW 1 IS GRADED IN BOTH ACCESSORS. `free_slot` and `utilization`
answer different questions and a build can get one right and the other wrong: a
`free_slot` that admitted a zero ceiling would dispatch to a stopped scheduler,
while a `utilization` that divided by it would raise inside the ranking and take
the whole dispatch down with a `ZeroDivisionError` rather than a decision.

WHY THE UNDECLARED-SERVER ARM NAMES ITS OWN REASON. A factory that declares no
server and one whose registry did not resolve both leave `FactoryTarget.server`
at `None`, and the two have completely different remedies — edit the committed
entry, or render the host registry. The journal is the only place that
distinction survives, so the reason has to be the one the reading earned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_capacity import (
    UNREADABLE_SERVER_UNDECLARED,
    FactoryCapacity,
    read_factory_capacity,
)

_FACTORY = "hp"


def _capacity(*, run_count: int | None, ceiling: int | None) -> FactoryCapacity:
    """A measured reading, with `unreadable` None by construction."""
    return FactoryCapacity(
        factory=_FACTORY,
        run_count=run_count,
        max_concurrent_runs=ceiling,
        unreadable=None,
    )


def test_a_ceiling_below_one_is_no_free_slot_and_no_utilization() -> None:
    """A server that will start nothing has no room, and no ratio to rank by.

    The positive control is in the same case: an identical reading with a usable
    ceiling must be free and must rank, so neither assertion can pass against an
    accessor that refuses every reading.
    """
    for ceiling in (0, -1):
        stopped = _capacity(run_count=0, ceiling=ceiling)

        assert stopped.free_slot is False
        assert stopped.utilization is None
        assert stopped.ranking_key == 1.0

    usable = _capacity(run_count=0, ceiling=2)

    assert usable.free_slot is True
    assert usable.utilization == 0.0
    assert usable.ranking_key == 0.0


def test_an_unmeasured_figure_is_no_free_slot_and_no_utilization() -> None:
    """Either figure absent answers the same way, and never as a zero.

    Both halves are asserted because a build can carry one: a `free_slot` that
    read an absent count as zero would report an unreachable server as idle,
    which is the one reading that sends work to a factory nobody could measure.
    """
    unmeasured = (
        _capacity(run_count=None, ceiling=10),
        _capacity(run_count=0, ceiling=None),
        _capacity(run_count=None, ceiling=None),
    )

    assert [one.free_slot for one in unmeasured] == [False, False, False]
    assert [one.utilization for one in unmeasured] == [None, None, None]
    # And it ranks LAST rather than raising or winning: a `None` reaching the
    # comparison would take the dispatch down with a type error instead of a
    # decision, and a 0.0 would make the one candidate nobody could measure
    # beat every candidate that was measured.
    assert [one.ranking_key for one in unmeasured] == [1.0, 1.0, 1.0]


def test_a_candidate_declaring_no_server_is_unmeasured_naming_that_fault(
    tmp_path: Path,
) -> None:
    """A committed entry with no `server` is passed over before any read.

    The reason is asserted specifically rather than merely "unreadable", because
    an unresolvable REGISTRY leaves the same `None` server and sends the operator
    to a different file. The journal row is also asserted, since the fields are
    what an operator actually reads and a reading carrying the reason in a
    property nothing projects would be invisible there.
    """
    entry: dict[str, Any] = {_FACTORY: {"bin": "/factory/fabro"}}
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {"factories": entry}}}),
        encoding="utf-8",
    )

    reading = read_factory_capacity(repo=tmp_path, factory=_FACTORY)

    assert reading.unreadable == UNREADABLE_SERVER_UNDECLARED
    assert reading.free_slot is False
    assert dict(reading.journal_fields()) == {
        "factory": _FACTORY,
        "run_count": None,
        "max_concurrent_runs": None,
        "unreadable": UNREADABLE_SERVER_UNDECLARED,
    }
