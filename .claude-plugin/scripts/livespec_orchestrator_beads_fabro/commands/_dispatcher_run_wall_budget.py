"""The whole-run wall budget one dispatch resolved, and the layer that supplied it.

`SPECIFICATION/contracts.md` section "ACP node timeouts" -> "Whole-run wall
budget key" governs `dispatcher.run_wall_budget_seconds`: a positive integer of
seconds bounding how long ONE run may hold a factory slot, resolved through
three layers, most specific last -- the built-in default of 21600 seconds, the
dispatch target's `.livespec.jsonc`, then a per-dispatch
`--run-wall-budget-seconds` argument -- with the resolved figure and its
supplying layer journaled on the dispatch record.

WHY THE BUDGET IS CONFIGURATION AND NOT A LITERAL, and why it is a DIFFERENT
number from the stall window beside it. The watchdog's stall window bounds a
run that has gone SILENT; this bounds a run that is working perfectly and will
still end at `needs_human` hours from now. Measured 2026-10-13 on hp's fleet
server over 45 finished `ImplementWorkItem` runs: the nine that succeeded used
20.4 of about 120 slot-hours at a 99-minute median wall time, while the runs
that parked at `needs_human` after `implement`, `pr`, `proof_capture` or `fix`
each held a slot for 200-390 minutes first -- two to four times that median.
A run that is going to need a human is far cheaper the earlier it parks, and
nothing in the stall window can bound it, because such a run is emitting
events throughout.

THE DEFAULT IS A CEILING AND NOT A TARGET. 21600 seconds is six hours, which
is wide enough that no legitimate run measured in that window reaches it; a
repository that wants to fail faster lowers it, and one whose items genuinely
need longer raises it. What the default must never be is BELOW a node timeout
resolved for the same dispatch, which is why `node_timeout_conflict` exists one
function down: such a budget would cancel that node's legitimate turn, so it is
refused before any run exists rather than discovered by watching one die.

THE LAYER RIDES WITH THE VALUE for the reason `StallWindow.layer` does. A
budget of 21600 seconds is the fleet default on one target and a deliberate
repository override on another, and only the layer separates them -- so only
the layer says whether raising the key would have saved a cancelled run or
whether it had already been raised.

THE COERCION IS THE NODE TIMEOUTS' OWN. All three keys of that clause are "a
positive integer of seconds", so `positive_int_seconds` is imported rather than
re-written: a second coercion is a second place for the `bool`-is-an-`int` trap
to be forgotten, and `true` in a config file resolving to a one-second budget
is a value that both passes a naive validation and cancels every run.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
    positive_int_seconds,
)

__all__: list[str] = [
    "DEFAULT_RUN_WALL_BUDGET",
    "DEFAULT_RUN_WALL_BUDGET_SECONDS",
    "PER_DISPATCH_ARGUMENT_LAYER",
    "RUN_WALL_BUDGET_ARGUMENT",
    "RUN_WALL_BUDGET_KEY",
    "RunWallBudget",
    "node_timeout_conflict",
    "run_wall_budget_from_block",
    "run_wall_budget_journal_record",
]

_RUN_WALL_BUDGET_BLOCK_KEY = "run_wall_budget_seconds"

# The key and the argument as an operator spells them, so every refusal below
# names the surface that has to be edited rather than paraphrasing it.
RUN_WALL_BUDGET_KEY = f"dispatcher.{_RUN_WALL_BUDGET_BLOCK_KEY}"
RUN_WALL_BUDGET_ARGUMENT = "--run-wall-budget-seconds"

DEFAULT_RUN_WALL_BUDGET_SECONDS = 21600

# The third layer's name. The other two are the node timeouts' own layer names,
# imported rather than restated so a record carrying a budget layer and a
# record carrying a node-timeout layer use one vocabulary.
PER_DISPATCH_ARGUMENT_LAYER = "per-dispatch argument"


@dataclass(frozen=True, kw_only=True)
class RunWallBudget:
    """One dispatch's whole-run wall budget, and which layer supplied it.

    `seconds` is a float because the watchdog compares it against a measured
    wall-clock span, while every configured value is an integer count of
    seconds; converting once here keeps the comparison off a mixed-type
    expression, exactly as `StallWindow` does.
    """

    seconds: float
    layer: str


# The fully-defaulted budget: what a dispatch target declaring nothing, invoked
# with no argument, resolves to. A VALUE as well as a resolution so a caller
# that needs one in a signature or a dataclass default does not have to carry
# None and make every reader branch on an absence with a perfectly good answer.
DEFAULT_RUN_WALL_BUDGET = RunWallBudget(
    seconds=float(DEFAULT_RUN_WALL_BUDGET_SECONDS),
    layer=WORKFLOW_DEFAULT_LAYER,
)


def run_wall_budget_from_block(
    *,
    block: dict[str, Any],
    argument: str | None = None,
) -> RunWallBudget | str:
    """Resolve the budget from a dispatcher config block and argument, or refuse.

    Returns the resolution, or an actionable refusal message NAMING THE SURFACE
    at fault -- the committed key or the argument. The caller routes that
    message as a failed dispatch BEFORE any Fabro run exists, which is the
    whole point of validating here: a mistyped budget is a config typo, and the
    honest place to discover one is the dispatch that would otherwise have run
    under a number nobody chose.

    THE COMMITTED KEY IS GRADED EVEN WHEN THE ARGUMENT WOULD WIN, and the order
    is deliberate. The argument decides the RESOLUTION, but a mistyped
    committed key is a fault in the repository's own configuration whichever
    way this one dispatch was invoked -- and an argument that masked it would
    make the typo discoverable only on the next dispatch that passed none.

    The ARGUMENT arrives as the text an operator typed rather than as a coerced
    integer, so a non-integer refuses HERE naming the argument rather than as
    an argparse usage error naming a type. A value that is not a run of digits
    -- `-60`, `90.5`, the empty string, a word -- is therefore refused by the
    same arm that refuses `0`.
    """
    configured = _configured_budget(block=block)
    if isinstance(configured, str) or argument is None:
        return configured
    return _argument_budget(argument=argument)


def run_wall_budget_journal_record(*, budget: RunWallBudget) -> dict[str, object]:
    """Project the resolved budget for the dispatch record.

    One nested object rather than two sibling keys, so a reader joining the
    figure to its layer cannot pick up one from a record that carried the
    other -- the same shape `node_timeouts_journal_record` gives the stall
    timeout beside it.
    """
    return {"run_wall_budget": {"seconds": budget.seconds, "layer": budget.layer}}


def node_timeout_conflict(*, budget: RunWallBudget, nodes: Mapping[str, int]) -> str | None:
    """Refuse a budget smaller than a node timeout the same dispatch resolved.

    `nodes` is what each node's `timeout` attribute ACTUALLY received in the
    rendered graph, keyed by node name, so the conflict is measured against the
    values the run will execute under rather than against a re-derivation of
    them. A node the graph declares with no timeout attribute is absent from
    that mapping and cannot conflict, which is correct: it carries no bound for
    the budget to undercut.

    EQUALITY PASSES. A budget equal to the longest node is not smaller than it,
    and the clause refuses only a budget that IS smaller -- the same strictness
    the budget's own exceeded test applies one layer up.

    THE LONGEST OFFENDING NODE IS THE ONE NAMED, because it is the binding
    constraint: a refusal naming any shorter offender sends an operator to
    raise the budget to a figure the longest node would still exceed. A tie
    resolves to the alphabetically-first node, because the population is walked
    in sorted order rather than in whatever order the mapping yields -- a
    refusal that named a different node on two identical dispatches would read
    as two different faults.

    The budget renders as an integer because every resolved budget IS one: both
    resolution arms build from `positive_int_seconds`, so the float on
    `RunWallBudget` is a comparison convenience and never a fractional value.
    """
    offending = [
        (node, seconds) for node, seconds in sorted(nodes.items()) if seconds > budget.seconds
    ]
    if not offending:
        return None
    node, seconds = max(offending, key=lambda pair: pair[1])
    return (
        f"{RUN_WALL_BUDGET_KEY} is {int(budget.seconds)} seconds (layer: {budget.layer}), "
        f"which is smaller than dispatcher.node_timeouts.{node} at {seconds} seconds; "
        f"such a budget would cancel that node's legitimate turn, so the dispatch is "
        f"refused before any run exists"
    )


def _configured_budget(*, block: dict[str, Any]) -> RunWallBudget | str:
    """The budget the dispatch target's committed configuration supplies."""
    raw: object = block.get(_RUN_WALL_BUDGET_BLOCK_KEY)
    if raw is None:
        return DEFAULT_RUN_WALL_BUDGET
    seconds = positive_int_seconds(value=raw)
    if seconds is None:
        return f"{RUN_WALL_BUDGET_KEY} must be a positive integer of seconds; got {raw!r}"
    return RunWallBudget(seconds=float(seconds), layer=REPOSITORY_LAYER)


def _argument_budget(*, argument: str) -> RunWallBudget | str:
    """The budget this one dispatch's argument supplies."""
    seconds = positive_int_seconds(value=int(argument) if argument.isdigit() else None)
    if seconds is None:
        return (
            f"{RUN_WALL_BUDGET_ARGUMENT} must be a positive integer of seconds; "
            f"got {argument!r}"
        )
    return RunWallBudget(seconds=float(seconds), layer=PER_DISPATCH_ARGUMENT_LAYER)
