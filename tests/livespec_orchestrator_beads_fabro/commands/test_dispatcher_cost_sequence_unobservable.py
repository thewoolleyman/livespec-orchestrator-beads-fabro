"""One unobservable attempt darkens the whole sequence, and says so.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt": "If any included attempt has
unobservable cost, the sequence total MUST be unobservable; a known subtotal MAY
be displayed only when explicitly labeled incomplete."

THE DANGEROUS WRONG ANSWER IS THE SUBTOTAL, NOT ZERO. A sequence whose records
are mostly priced has a plausible number sitting in it, and reporting that
number as the total produces a figure SMALLER than the truth that reads exactly
like a complete observation -- which is the same reason an unpriceable
component poisons one run's whole total one module over. So every case below
asserts the TOTAL is absent and the subtotal is LABELLED, and the complete
sequence beside them is the control: without it, an implementation that
darkened every total would satisfy each unobservable case while reporting
nothing usable about any sequence at all.

BOTH TERMS OF THE SUM ARE EXERCISED, because the clause makes the final run one
term of one sum and an implementation can easily guard only the records. A
sequence whose releases are all priced and whose FINAL run is dark is exactly as
unobservable as the other way round, and a reader that reported its subtotal as
a total would be reporting the released attempts' spend as the whole cost of the
work.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ATTEMPT_COST_RELEASED_RUN,
    ATTEMPT_COST_STAGE,
    attempt_cost_identity,
)

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_dispatcher_cost_sequence"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

_ITEM = "bd-ib-dark"
_FACTORY = "hp"
_PRICED_RUN = "01PRICEDRELEASEDRUN"
_DARK_RUN = "01DARKRELEASEDRUN"

_PRICED_MICROS = 12_000
_FINAL_RUN_MICROS = 480_000

# The one label the clause permits a displayed subtotal to carry. Spelled as a
# literal here and bound to the module's exported name by the surface test
# below, because this file's Red predates that name and a top-level import of
# an absent name dies at collection -- which proves the name is absent, not
# that the behaviour is unimplemented.
_INCOMPLETE = "incomplete"


def _module() -> Any:
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")


def _row(*, run_id: str, usd_micros: int | None) -> dict[str, object]:
    return {
        "stage": ATTEMPT_COST_STAGE,
        "observation_id": attempt_cost_identity(
            source=ATTEMPT_COST_RELEASED_RUN,
            factory=_FACTORY,
            run_id=run_id,
            node_attempt="implement",
        ),
        "source": ATTEMPT_COST_RELEASED_RUN,
        "work_item_id": _ITEM,
        "factory": _FACTORY,
        "run_id": run_id,
        "node_attempt": "implement",
        "occurred_at": "2026-10-12T09:10:00Z",
        "attempts": [],
        "usd_micros": usd_micros,
        "cost_observable": usd_micros is not None,
    }


def _cost(*, rows: list[dict[str, object]], final_run_usd_micros: int | None) -> Any:
    module = _module()
    return module.sequence_cost(  # pyright: ignore[reportAttributeAccessIssue]
        observations=module.attempt_cost_observations(  # pyright: ignore[reportAttributeAccessIssue]
            records=tuple(rows), work_item_id=_ITEM
        ),
        final_run_usd_micros=final_run_usd_micros,
    )


def test_the_sequence_cost_reports_an_incomplete_label() -> None:
    """The label the clause names, and the field a displayed subtotal carries."""
    module = _module()
    assert hasattr(module, "SUBTOTAL_INCOMPLETE_LABEL"), dir(module)
    assert module.SUBTOTAL_INCOMPLETE_LABEL == _INCOMPLETE  # pyright: ignore[reportAttributeAccessIssue]
    cost = _cost(
        rows=[_row(run_id=_PRICED_RUN, usd_micros=_PRICED_MICROS)],
        final_run_usd_micros=_FINAL_RUN_MICROS,
    )
    assert hasattr(cost, "subtotal_label"), cost


def test_one_unobservable_attempt_makes_the_whole_sequence_total_unobservable() -> None:
    """The subtotal survives, labelled; the total does not survive at all."""
    cost = _cost(
        rows=[
            _row(run_id=_PRICED_RUN, usd_micros=_PRICED_MICROS),
            _row(run_id=_DARK_RUN, usd_micros=None),
        ],
        final_run_usd_micros=_FINAL_RUN_MICROS,
    )
    assert cost.usd_micros is None
    assert cost.subtotal_usd_micros == _PRICED_MICROS + _FINAL_RUN_MICROS
    assert cost.subtotal_label == _INCOMPLETE


def test_an_unobservable_final_run_darkens_the_sequence_too() -> None:
    """The final run is one term of the same sum, not a separately guarded one."""
    cost = _cost(
        rows=[_row(run_id=_PRICED_RUN, usd_micros=_PRICED_MICROS)],
        final_run_usd_micros=None,
    )
    assert cost.usd_micros is None
    assert cost.subtotal_usd_micros == _PRICED_MICROS
    assert cost.subtotal_label == _INCOMPLETE


def test_a_fully_observable_sequence_reports_its_total_and_no_label() -> None:
    """The control: a darkened-everything implementation must fail here."""
    cost = _cost(
        rows=[
            _row(run_id=_PRICED_RUN, usd_micros=_PRICED_MICROS),
            _row(run_id=_DARK_RUN, usd_micros=1),
        ],
        final_run_usd_micros=_FINAL_RUN_MICROS,
    )
    assert cost.usd_micros == _PRICED_MICROS + 1 + _FINAL_RUN_MICROS
    assert cost.subtotal_usd_micros == cost.usd_micros
    assert cost.subtotal_label is None


def test_a_measured_zero_is_observable_and_does_not_darken_the_sequence() -> None:
    """Zero is a MEASURED figure everywhere else in this tree, and here too."""
    cost = _cost(
        rows=[_row(run_id=_PRICED_RUN, usd_micros=0)], final_run_usd_micros=_FINAL_RUN_MICROS
    )
    assert cost.usd_micros == _FINAL_RUN_MICROS
    assert cost.subtotal_label is None
