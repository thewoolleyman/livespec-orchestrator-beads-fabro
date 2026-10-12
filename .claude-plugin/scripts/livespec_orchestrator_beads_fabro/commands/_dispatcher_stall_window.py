"""The host-side stall watchdog's window, and the layer that supplied it.

`SPECIFICATION/contracts.md` section "ACP node timeouts" governs BOTH the
phase graph's per-node timeouts AND the run's stall watchdog, and it governs
them through the SAME layers: the workflow's own declared defaults, then the
dispatch target's `.livespec.jsonc` `dispatcher.stall_timeout_seconds`. This
module is where that one resolution becomes the HOST-side watchdog's window.

WHAT IT REPLACES, and why the replacement is the whole point of the module.
The watchdog used to resolve its own window from an environment variable with
a private 1500-second default, so the graph and the host backstop were
budgeted by two unrelated numbers and the configured key governed only one of
them. On legacy hp run 01M4QGDETRJ3 (2026-10-12) that cost a run roughly four
hours of unpublished work: the host cancelled it at 1529.9 quiet seconds
against its 1500-second window while the graph it was executing carried
`stall_timeout="7200s"`, and a single implement tool call measured on another
run the same day ran 20 minutes emitting no events at all. A window shorter
than an ordinary quiet stretch is not a backstop; it is a reaper.

TWO ENTRY POINTS, for two kinds of caller, and the difference is
load-bearing rather than a convenience.

`stall_window_from_timeouts` PROJECTS a resolution the dispatch has already
taken and journaled. That is the launcher's route, through `DispatchPlan`, for
the reason every other integration point rides the plan: the `fabro run`
subprocess ceiling is DERIVED from the same `stall_seconds`
(`_node_timeouts.derive_fabro_timeout_seconds`), so a watchdog that re-read the
file for itself could budget its window against one reading while the ceiling
that must outlive it was budgeted against another — and nothing in either
record would show the disagreement.

`resolve_stall_window` is for a caller holding no plan: the post-run surfaces
that report WHICH cap a non-convergence bounce tripped and what it observed.
It reads the dispatch target's committed configuration itself, and it FAILS
SOFT onto the default in BOTH of its arms — an unreadable file and a refused
value. Every caller it has runs after the run's verdict is already final, so a
refusal raised there would turn a mistyped key into a crash inside an
escalation write; the honest place to refuse a mistyped key is the
dispatch-time validation `_dispatcher_payload.prepare_workflow_payload`
already performs, naming the key, before any run exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_node_timeouts
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_STALL_TIMEOUT_SECONDS,
    WORKFLOW_DEFAULT_LAYER,
    NodeTimeouts,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

__all__: list[str] = [
    "DEFAULT_STALL_WINDOW",
    "StallWindow",
    "resolve_stall_window",
    "stall_window_from_timeouts",
]


@dataclass(frozen=True, kw_only=True)
class StallWindow:
    """The watchdog's quiet-window interval, and which layer supplied it.

    `seconds` is a float because the watchdog compares it against a measured
    wall-clock span, while the configured key is an integer count of seconds;
    converting once here keeps the comparison off a mixed-type expression.
    `layer` is one of `_node_timeouts`' layer names, carried beside the value
    rather than re-derived, because a record naming the number alone cannot
    tell a repository override from the built-in default — and that is the
    first question asked of any cancellation.
    """

    seconds: float
    layer: str


# The fully-defaulted window: what a dispatch target declaring nothing
# resolves to. Derived from the node-timeout policy's own constant rather than
# restated, so the host watchdog and the graph's `stall_timeout` cannot drift
# apart the way they already did once.
DEFAULT_STALL_WINDOW = StallWindow(
    seconds=float(DEFAULT_STALL_TIMEOUT_SECONDS),
    layer=WORKFLOW_DEFAULT_LAYER,
)


def stall_window_from_timeouts(*, timeouts: NodeTimeouts) -> StallWindow:
    """Project an already-resolved node-timeout set as the host stall window."""
    return StallWindow(seconds=float(timeouts.stall_seconds), layer=timeouts.stall_layer)


def resolve_stall_window(*, cwd: Path) -> StallWindow:
    """Resolve the host stall window from `cwd`'s committed configuration.

    Fail-soft onto `DEFAULT_STALL_WINDOW` on both of the two ways the read can
    fail — an unreadable `.livespec.jsonc`, and a value the node-timeout
    validator refuses — per the module docstring: every caller is a post-run
    reporting surface, and the refusal belongs at dispatch time instead.
    """
    timeouts = attempt(
        action=lambda: resolve_node_timeouts(cwd=cwd),
        exceptions=(LivespecConfigUnreadableError,),
    )
    if isinstance(timeouts, AttemptFailure | str):
        return DEFAULT_STALL_WINDOW
    return stall_window_from_timeouts(timeouts=timeouts)
