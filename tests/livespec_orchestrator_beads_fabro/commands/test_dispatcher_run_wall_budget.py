"""Tests for the whole-run wall budget's resolution and refusals (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "ACP node timeouts" ->  "Whole-run wall
budget key" governs `dispatcher.run_wall_budget_seconds`: a positive integer of
seconds resolving through three layers, most specific last -- the built-in
default of 21600, the dispatch target's `.livespec.jsonc`, then a per-dispatch
`--run-wall-budget-seconds` argument -- with the resolved value and the layer
that supplied it journaled on the dispatch record.

The module import sits INSIDE each test body (the new-module pattern this
repo's decomposition slices use) so the Red commit fails on a genuine
assertion -- the module file's absence -- rather than at collection.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _node_timeouts
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget"


def _module_path() -> Path:
    """Where the budget module lives, beside the node-timeout policy it extends."""
    return Path(str(_node_timeouts.__file__)).with_name("_dispatcher_run_wall_budget.py")


def _budget_module() -> Any:
    """The budget module, imported inside a test body rather than at top.

    The existence assertion LEADS the import so that every test here fails on
    a genuine assertion at Red rather than at collection.
    """
    assert _module_path().is_file(), f"{_module_path()} does not exist"
    return importlib.import_module(_MODULE)


def test_an_unconfigured_budget_resolves_to_the_built_in_default() -> None:
    """A target declaring nothing resolves 21600 seconds from the default layer."""
    module = _budget_module()
    assert module.DEFAULT_RUN_WALL_BUDGET_SECONDS == 21600
    budget = module.run_wall_budget_from_block(block={})
    assert budget.seconds == 21600.0
    assert budget.layer == WORKFLOW_DEFAULT_LAYER
    assert budget == module.DEFAULT_RUN_WALL_BUDGET


def test_the_journal_record_names_the_resolved_budget_and_its_layer() -> None:
    """The dispatch record carries the figure AND the layer that supplied it.

    The layer is the FIRST question asked of a budget cancel, for the reason
    the stall window's own layer is recorded beside it: 21600 seconds is the
    fleet default on one target and a deliberate repository override on
    another, and only the layer separates them.
    """
    module = _budget_module()
    record = module.run_wall_budget_journal_record(
        budget=module.run_wall_budget_from_block(block={})
    )
    assert record == {"run_wall_budget": {"seconds": 21600.0, "layer": WORKFLOW_DEFAULT_LAYER}}


def test_a_configured_budget_resolves_from_the_repository_layer() -> None:
    """The dispatch target's own `.livespec.jsonc` outranks the built-in default."""
    module = _budget_module()
    budget = module.run_wall_budget_from_block(block={"run_wall_budget_seconds": 25200})
    assert budget.seconds == 25200.0
    assert budget.layer == REPOSITORY_LAYER
    assert module.run_wall_budget_journal_record(budget=budget) == {
        "run_wall_budget": {"seconds": 25200.0, "layer": REPOSITORY_LAYER}
    }


def test_the_per_dispatch_argument_outranks_the_repository_layer() -> None:
    """The most specific layer wins, and the record names it by that name."""
    module = _budget_module()
    budget = module.run_wall_budget_from_block(
        block={"run_wall_budget_seconds": 25200}, argument="28800"
    )
    assert budget.seconds == 28800.0
    assert budget.layer == module.PER_DISPATCH_ARGUMENT_LAYER
    assert module.PER_DISPATCH_ARGUMENT_LAYER == "per-dispatch argument"


def test_the_argument_layer_applies_with_no_configured_value() -> None:
    """An argument on a target declaring nothing still outranks the default."""
    module = _budget_module()
    budget = module.run_wall_budget_from_block(block={}, argument="28800")
    assert budget.seconds == 28800.0
    assert budget.layer == module.PER_DISPATCH_ARGUMENT_LAYER


@pytest.mark.parametrize("value", [0, -60, 90.5, True])
def test_an_invalid_configured_budget_is_refused_naming_the_key(value: object) -> None:
    """A non-positive or non-integer committed value refuses, naming the key.

    `True` is in the set because `bool` is an `int` subclass in Python, so a
    config file carrying `true` would otherwise resolve to a one-second budget
    -- a value that both passes a naive validation and cancels every run.
    """
    module = _budget_module()
    refusal = module.run_wall_budget_from_block(block={"run_wall_budget_seconds": value})
    assert isinstance(refusal, str)
    assert module.RUN_WALL_BUDGET_KEY in refusal
    assert repr(value) in refusal


@pytest.mark.parametrize("argument", ["0", "-60", "90.5", "", "many"])
def test_an_invalid_argument_is_refused_naming_the_argument(argument: str) -> None:
    """A non-positive or non-integer argument refuses, naming the argument."""
    module = _budget_module()
    refusal = module.run_wall_budget_from_block(block={}, argument=argument)
    assert isinstance(refusal, str)
    assert module.RUN_WALL_BUDGET_ARGUMENT in refusal
    assert repr(argument) in refusal


def test_a_broken_committed_key_is_refused_even_when_an_argument_would_win() -> None:
    """The committed typo is reported rather than masked by the argument.

    The argument wins the RESOLUTION, but a mistyped committed key is still a
    fault in the repository's own configuration, and the dispatch that would
    have run past it is the honest place to discover one.
    """
    module = _budget_module()
    refusal = module.run_wall_budget_from_block(
        block={"run_wall_budget_seconds": 0}, argument="28800"
    )
    assert isinstance(refusal, str)
    assert module.RUN_WALL_BUDGET_KEY in refusal


def test_the_positive_seconds_coercion_is_shared_with_the_node_timeouts() -> None:
    """One coercion serves all three keys of the same contracts section.

    The budget, the per-node timeouts and the stall window are all "a positive
    integer of seconds" in the same clause, so a second coercion here would be
    a second place for the `bool` subclass trap to be forgotten.
    """
    _ = _budget_module()
    coerce = cast("Any", _node_timeouts.positive_int_seconds)
    assert coerce(value=1800) == 1800
    assert coerce(value=0) is None
    assert coerce(value=True) is None
    assert coerce(value="1800") is None
