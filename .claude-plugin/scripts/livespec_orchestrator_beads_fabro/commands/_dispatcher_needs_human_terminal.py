"""Needs-human terminal-state rendering for the dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        DispatchOutcome,
    )

__all__: list[str] = [
    "needs_human_terminal_outcome",
]

_PRESERVED_SENTINEL = f"{NEEDS_HUMAN_MARKER}_PRESERVED: "


def needs_human_terminal_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    text: str,
) -> DispatchOutcome | None:
    """Map the `needs_human` terminal's sentinel onto the `blocked` outcome.

    The workflow's needs-human path no longer parks the run (plan
    ledger-is-the-only-gate; contracts.md "A factory run never awaits a
    human", v093): the terminal node preserves the tree on a run-scoped ref,
    prints `NEEDS_HUMAN_MARKER` and exits non-green. What the Dispatcher owes
    the ledger is unchanged — the item rests at `blocked / needs-human` and
    the dispatch reports exit code 4 — so the sentinel produces the very same
    `blocked` outcome the gate did, with a detail that names the ledger valve
    instead of a `fabro attach` that would find no run to attach to. It names a
    preservation ref only when the node reported a successful push; otherwise
    it names the dump pointer as the only preservation. The sentinel is read
    from BOTH the raw stderr and the structured detail, for the same reason the
    dead-implementer breaker does: neither channel is guaranteed to carry a
    node's own output.
    """
    if NEEDS_HUMAN_MARKER not in text:
        return None
    run_label = "unknown-run" if run_id is None else run_id
    marker_lines = (
        line.split(_PRESERVED_SENTINEL, 1)
        for line in text.splitlines()
        if _PRESERVED_SENTINEL in line
    )
    preserved_ref = next((parts[1].strip() for parts in marker_lines), None) or None
    preservation = (
        (
            "no run-scoped preservation ref was reported; the preserve-by-reference "
            "dump pointer is the only preservation"
        )
        if preserved_ref is None
        else (
            f"the tree was preserved on {preserved_ref} "
            "(see the preserve-by-reference pointer on the item for the dump digest)"
        )
    )
    rework_source = (
        "from the dump pointer or from scratch"
        if preserved_ref is None
        else "from the preserved ref or from scratch"
    )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"run {run_label} terminated at the needs_human node (needs-human); "
            f"{preservation}; no run is waiting — the decision lives in the "
            "ledger: answer with "
            f"`resolve-blocked:{plan.work_item_id}:ready` (re-dispatch, seeding rework "
            f"{rework_source}) or leave the item blocked"
        ),
        fabro_run_id=run_id,
    )
