"""The one journal record a wall-budget cancel writes (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "A budget cancel MUST journal one
`run-wall-budget-exceeded` record and MUST NOT journal a
`watchdog-stall-cancel` record. The `run-wall-budget-exceeded` record MUST
carry every field the cancel record above requires, under the same rules for
the stage and for the pull request and published head (including stating that
the head could not be read when it cannot), plus the elapsed slot-holding
seconds, the budget, the layer that supplied the budget, and the
preserve-by-reference pointer."

"Every field the cancel record above requires" is why the identifying half has
ONE renderer shared with `watchdog-stall-cancel`: two renderers of one field
set would drift, and the drift would be invisible -- both records would stay
well-formed while a reader joining them reported one cancel class as carrying
less than the other.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stall_cancel_record,
    _node_timeouts,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RUN_RECORD_SOURCE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
    UNREADABLE_PUBLISHED_HEAD,
    stall_cancel_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    StallPublication,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records"
_BUDGET = RunWallBudget(seconds=21600.0, layer=REPOSITORY_LAYER)
_POINTER = "comment-9173"


def _module_path() -> Path:
    """Where the budget records module lives, beside the budget it reports on."""
    return Path(str(_node_timeouts.__file__)).with_name("_dispatcher_run_wall_budget_records.py")


def _records() -> Any:
    """The records module, imported inside a test body rather than at top."""
    assert _module_path().is_file(), f"{_module_path()} does not exist"
    return importlib.import_module(_MODULE)


def _shared_fields() -> Any:
    """The identifying half's shared renderer, read inside a test body.

    Read off the module rather than imported at top so the Red commit fails on
    a genuine assertion rather than at collection.
    """
    module = _dispatcher_stall_cancel_record
    name = "watchdog_cancel_fields"
    assert hasattr(module, name), f"{module.__name__} declares no {name}"
    return module.watchdog_cancel_fields


def _exceeded(
    *,
    records: Any,
    publication: StallPublication | None = None,
    executing_stage: str | None = "implement",
) -> dict[str, object]:
    return records.run_wall_budget_exceeded_record(
        work_item_id="bd-ib-sdxfsn",
        dispatch_id="dispatch-01",
        run_id="01RUN",
        factory="hp",
        executing_stage=executing_stage,
        publication=publication,
        elapsed_seconds=25200.5,
        budget=_BUDGET,
        start_source=RUN_RECORD_SOURCE,
        preserved_pointer=_POINTER,
    )


def test_the_record_names_the_dispatch_the_run_and_the_budget() -> None:
    """One record carries every field the clause enumerates."""
    records = _records()
    record = _exceeded(records=records)
    assert record["stage"] == records.RUN_WALL_BUDGET_EXCEEDED_STAGE
    assert records.RUN_WALL_BUDGET_EXCEEDED_STAGE == "run-wall-budget-exceeded"
    assert record["work_item_id"] == "bd-ib-sdxfsn"
    assert record["dispatch_id"] == "dispatch-01"
    assert record["run_id"] == "01RUN"
    assert record["factory"] == "hp"
    assert record["executing_stage"] == "implement"
    assert record["elapsed_seconds"] == 25200.5
    assert record["budget_seconds"] == 21600.0
    assert record["budget_layer"] == REPOSITORY_LAYER
    assert record["preserved_pointer"] == _POINTER
    # Which route dated the clock, because a recorded instant is the factory's
    # own account while a first-poll instant is this host's observation.
    assert record["budget_start_source"] == RUN_RECORD_SOURCE


def test_the_record_is_not_a_stall_cancel_record() -> None:
    """A budget cancel is its own stage, never the stall cancel's.

    A SEPARATE stage rather than a field on the stall row, because the two are
    different dispositions: a reader filtering for "was this run cancelled as
    stalled" must not match the row that says it was cancelled on its budget.
    """
    records = _records()
    assert records.RUN_WALL_BUDGET_EXCEEDED_STAGE != STALL_CANCEL_STAGE
    assert _exceeded(records=records)["stage"] != STALL_CANCEL_STAGE


def test_both_cancel_records_render_their_identifying_half_from_one_renderer() -> None:
    """Every identifying field of the stall record appears on the budget record.

    Asserted as a SET relation rather than field by field, so a field added to
    the shared renderer later cannot reach one record and miss the other.
    """
    records = _records()
    shared = _shared_fields()(
        work_item_id="bd-ib-sdxfsn",
        dispatch_id="dispatch-01",
        run_id="01RUN",
        factory="hp",
        executing_stage="implement",
        publication=None,
    )
    assert "stage" not in shared
    stall = stall_cancel_record(
        work_item_id="bd-ib-sdxfsn",
        dispatch_id="dispatch-01",
        run_id="01RUN",
        factory="hp",
        executing_stage="implement",
        publication=None,
    )
    assert stall == {"stage": STALL_CANCEL_STAGE, **shared}
    budget_record = _exceeded(records=records)
    assert set(shared) <= set(budget_record)
    for key, value in shared.items():
        assert budget_record[key] == value


def test_a_published_run_names_its_pull_request_and_head() -> None:
    """The record names what the last completed publish_draft pushed."""
    records = _records()
    record = _exceeded(
        records=records,
        publication=StallPublication(pull_request=2714, published_head="a" * 40),
    )
    assert record["pull_request"] == 2714
    assert record["published_head"] == "a" * 40
    assert record["published_head_unreadable"] is None


def test_an_unreadable_published_head_is_stated_in_words() -> None:
    """A publication whose head could not be read says so, under one rule.

    The statement is the stall record's own, because the clause binds the
    budget record to "the same rules ... for the pull request and published
    head": two statements would let one cancel class advise a plain dispatch
    -- which reclaims and deletes the publish branch -- where the other did
    not.
    """
    records = _records()
    record = _exceeded(
        records=records,
        publication=StallPublication(pull_request=2714, published_head=None),
    )
    assert record["published_head"] is None
    assert record["published_head_unreadable"] == UNREADABLE_PUBLISHED_HEAD


def test_an_unpublished_run_writes_every_key_as_a_null() -> None:
    """Nulls rather than omissions, so an absent key cannot read as this run.

    An omitted key is exactly what a record from a build predating this
    renderer looks like, so a reader could not tell "this run published
    nothing" from "this build was never asked".
    """
    records = _records()
    record = _exceeded(records=records, publication=None, executing_stage=None)
    assert record["pull_request"] is None
    assert record["published_head"] is None
    assert record["published_head_unreadable"] is None
    assert record["executing_stage"] is None
