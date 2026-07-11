"""Host-only routing predicate for the Dispatcher planning layer.

Mechanizes the explicit host-only routing marker so the Dispatcher can
refuse to sandbox a work-item that touches dispatcher self-machinery
(the proven 7us.6 hang class). Pure functions of the work-item; the
side-effecting routing decision lives in the engine.
"""

from __future__ import annotations

import re

from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "host_only_refusal_detail",
    "is_host_only_item",
]

# The explicit host-only routing marker (see `is_host_only_item`). A
# word-bounded `host-only` / `host_only` token: a leading boundary that is
# neither a word char nor a hyphen (so `ghosthost-only` is NOT a match), the
# token with either separator, and a trailing boundary that is neither a word
# char nor a hyphen (so `host-onlyish` is NOT a match).
_HOST_ONLY_MARKER_RE = re.compile(r"(?<![\w-])host[-_]only(?![\w-])", re.IGNORECASE)


def is_host_only_item(*, item: WorkItem) -> bool:
    """Recognise the explicit host-only routing marker on a work-item.

    Mechanizes the currently-manual routing rule (judgment-leaning OR
    touches dispatcher self-machinery -> host sub-agent; ddu rationale)
    AND prevents the proven 7us.6 hang class: a commit-hook
    self-machinery item mis-routed to a fabro sandbox once deadlocked the
    in-sandbox `git commit` (a 2.5h silent stall; work-item
    livespec-impl-beads-uvd). The Dispatcher reads this predicate BEFORE
    launching any fabro run and refuses to sandbox a host-only item.

    The marker is the EXPLICIT contract — a `host-only` / `host_only`
    token in the item's title or description — carried in the only
    field-space the `WorkItem` schema exposes without a cross-repo
    contracts.md change (the mapped beads record drops unrecognised
    labels). It is recognised exactly the way `item_sizing_warnings`
    recognises its `multi-part/multi-RGR` marker, but as a HARD refuse
    rather than a warn. The token is word-bounded so incidental prose
    like "the host is only sometimes ready" never trips the gate.
    """
    return _HOST_ONLY_MARKER_RE.search(f"{item.title}\n{item.description}") is not None


def host_only_refusal_detail(*, item_id: str) -> str:
    """Build the actionable refusal message for a sandboxed host-only item.

    Routed as DATA (the `host-only-refused` DispatchOutcome detail), so
    the orchestrator reads a clear instruction to HOST-ROUTE the item to
    a host sub-agent instead of retrying the sandbox — never a launched
    run, so the in-sandbox/in-hook `git commit` can never deadlock.
    """
    return (
        f"host-only refusal: work-item {item_id} carries the explicit host-only "
        "marker and MUST NOT be dispatched to a fabro sandbox (sandboxing "
        "dispatcher self-machinery once deadlocked the in-sandbox git commit — "
        "the 7us.6 hang class). Host-route it to a host sub-agent instead "
        "(the livespec-implementer dispatch path)."
    )
