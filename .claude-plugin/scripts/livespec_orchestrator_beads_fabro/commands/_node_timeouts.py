"""Per-node timeout policy for the `implement-work-item` phase graph.

Split out of `_config` for the same reason `_codex_model_tiers` is: the
policy -- the 30-minute default, the worst-case visit map the Dispatcher's
subprocess ceiling is derived from, and the record that justifies both --
belongs next to its own resolver rather than inside the general
connection-resolution module.

WHY THE TIMEOUTS ARE CONFIGURATION AT ALL. There was never a 20-minute
limit anywhere in this repo: the "sub-20-minute turn" rule was the
empirical wall-clock proxy for a Codex implement turn's context reaching
`model_auto_compact_token_limit`, at which point Codex called a dead remote
compaction endpoint with no local fallback. Moving the implementer off
Codex removes that failure class, which leaves the NODE TIMEOUT as the only
ceiling on a turn -- and a ceiling that is the only one had better be a
decision rather than a literal nobody revisits.

WHY 1800 SECONDS, and what it costs. The 30-minute default is the
maintainer's ruling (2026-08-26 commission, item C) and it is a DELIBERATE
REDUCTION: it lowers `implement` from the previously shipped 14400 seconds
and `janitor` / `fix` / `review_fix` from 3600, against recorded legitimate
turns near 120 minutes. A repository whose items need longer turns raises
them through `dispatcher.node_timeouts`; the reduction is recorded as
deliberate in `SPECIFICATION/contracts.md` section "ACP node timeouts".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

__all__: list[str] = [
    "DEFAULT_FABRO_TIMEOUT_SECONDS",
    "DEFAULT_NODE_TIMEOUT_SECONDS",
    "DEFAULT_STALL_TIMEOUT_SECONDS",
    "REPOSITORY_LAYER",
    "WORKFLOW_DEFAULT_LAYER",
    "NodeTimeouts",
    "default_node_timeouts",
    "derive_fabro_timeout_seconds",
    "node_timeouts_from_block",
    "node_timeouts_journal_record",
]

_NODE_TIMEOUTS_KEY = "node_timeouts"
_STALL_TIMEOUT_KEY = "stall_timeout_seconds"

DEFAULT_NODE_TIMEOUT_SECONDS = 1800
DEFAULT_STALL_TIMEOUT_SECONDS = 7200

# The supplying-layer names the dispatch record carries per node, so a reader
# can tell a repository override from the built-in default without
# re-deriving it.
REPOSITORY_LAYER = "repository"
WORKFLOW_DEFAULT_LAYER = "default"

# The graph's worst-case path, expressed as the visit budget each node can
# actually consume in one run -- read off `workflow.fabro`: `implement` and
# `pr` carry `max_retries=1` (two attempts each), the janitor fix loop is
# bounded by the `< 3` visit guard on the janitor's own visit count (three
# janitor visits, two fix attempts), and the review loop is bounded by the
# default `review_fix_visit_cap` of four review visits with three
# disposition / review_fix rounds under it.
#
# The two SCRIPT breakers on the main path -- `implementation_diff` after
# `implement` and `verify_pr` after `pr` -- each carry the budget of the
# retryable node they guard, because either can be reached once per attempt
# of it. They are cheap in practice (one `git` call apiece) and budgeting
# them at the guarded node's count is what keeps the ceiling ABOVE the
# graph rather than level with an optimistic reading of it.
#
# The three TERMINAL sentinel nodes (`dead_implementer`, `abandon`,
# `non_converged`) are deliberately absent: each ENDS the run, so they are
# mutually exclusive with one another and with the tail of the main path,
# and summing all three would bill a worst case no run can reach. They still
# resolve their timeouts from configuration like every other node; they just
# do not contribute to the ceiling.
_WORST_CASE_VISITS: Mapping[str, int] = {
    "implement": 2,
    "implementation_diff": 2,
    "janitor": 3,
    "fix": 2,
    "review": 4,
    "disposition": 3,
    "review_fix": 3,
    "pr": 2,
    "verify_pr": 2,
}

# Sandbox-provisioning slack on top of the derived worst case. Carried over
# from the hand-computed constant this derivation replaces, which budgeted
# the same one hour of slack above its own 50400-second graph sum.
_CEILING_MARGIN_SECONDS = 3600.0


@dataclass(frozen=True, kw_only=True)
class NodeTimeouts:
    """Node timeouts resolved for one dispatch, with their supplying layers.

    `configured` holds ONLY the nodes the dispatch target's
    `dispatcher.node_timeouts` table names; every other node resolves to
    `DEFAULT_NODE_TIMEOUT_SECONDS`. Keeping the configured set separate from
    the resolved value is what lets the dispatch record name the supplying
    layer per node instead of reporting one indistinguishable number.
    """

    configured: Mapping[str, int]
    stall_seconds: int
    stall_layer: str

    def seconds_for(self, *, node: str) -> int:
        """The resolved timeout in seconds for `node`."""
        return self.configured.get(node, DEFAULT_NODE_TIMEOUT_SECONDS)

    def layer_for(self, *, node: str) -> str:
        """Which layer supplied `node`'s timeout."""
        return REPOSITORY_LAYER if node in self.configured else WORKFLOW_DEFAULT_LAYER


def default_node_timeouts() -> NodeTimeouts:
    """The fully-defaulted resolution: every node 1800s, the watchdog 7200s."""
    return NodeTimeouts(
        configured={},
        stall_seconds=DEFAULT_STALL_TIMEOUT_SECONDS,
        stall_layer=WORKFLOW_DEFAULT_LAYER,
    )


def node_timeouts_from_block(*, block: dict[str, Any]) -> NodeTimeouts | str:
    """Resolve node timeouts from a dispatcher config block, or refuse.

    Reads `dispatcher.node_timeouts` (a table of node name to positive
    integer seconds) and `dispatcher.stall_timeout_seconds`. Returns the
    resolution, or an actionable refusal message NAMING THE KEY when a value
    is non-positive or not an integer -- the caller routes that message as a
    failed dispatch BEFORE any Fabro run exists, so a mistyped timeout is
    never discovered by watching a node run without one.

    There is deliberately NO environment override, matching
    `_codex_model_tiers`: the timeouts are steady-state policy read once per
    dispatch, and an env seam would let an ad-hoc shell re-budget the whole
    factory with nothing in the committed record to show for it.
    """
    table_raw = block.get(_NODE_TIMEOUTS_KEY)
    if table_raw is not None and not isinstance(table_raw, dict):
        return (
            f"dispatcher.{_NODE_TIMEOUTS_KEY} must be a table of node name to "
            f"positive integer seconds; got {table_raw!r}"
        )
    table = cast("dict[str, Any]", table_raw) if isinstance(table_raw, dict) else {}
    configured: dict[str, int] = {}
    for node in sorted(table):
        seconds = _positive_int(value=table[node])
        if seconds is None:
            return (
                f"dispatcher.{_NODE_TIMEOUTS_KEY}.{node} must be a positive "
                f"integer of seconds; got {table[node]!r}"
            )
        configured[node] = seconds
    return _with_stall(block=block, configured=configured)


def derive_fabro_timeout_seconds(*, timeouts: NodeTimeouts) -> float:
    """Derive the `fabro run` subprocess ceiling from the resolved graph.

    The ceiling must outlive whichever of the two run-level bounds fires
    last: the graph's worst-case wall clock (every node at its resolved
    timeout, taken at its worst-case visit count) and the stall watchdog,
    which cancels a silent run at `stall_seconds`. A subprocess budget below
    the graph's own ceiling kills the CLI mid-run while the server-side
    engine keeps executing the graph, so the margin sits ON TOP of the max
    rather than being folded into it.
    """
    worst_case = sum(
        timeouts.seconds_for(node=node) * visits for node, visits in _WORST_CASE_VISITS.items()
    )
    return float(max(worst_case, timeouts.stall_seconds)) + _CEILING_MARGIN_SECONDS


def node_timeouts_journal_record(
    *,
    timeouts: NodeTimeouts,
    nodes: Mapping[str, int],
) -> dict[str, object]:
    """Project the resolved timeouts for the dispatch record.

    `nodes` is what the payload's workflow graph actually received, keyed by
    node name, so the record reports the RENDERED values rather than a
    re-derivation of them. Each entry names the layer that supplied it.
    """
    return {
        "node_timeouts": {
            node: {"seconds": seconds, "layer": timeouts.layer_for(node=node)}
            for node, seconds in sorted(nodes.items())
        },
        "stall_timeout": {
            "seconds": timeouts.stall_seconds,
            "layer": timeouts.stall_layer,
        },
        "fabro_timeout_seconds": derive_fabro_timeout_seconds(timeouts=timeouts),
    }


def _with_stall(*, block: dict[str, Any], configured: dict[str, int]) -> NodeTimeouts | str:
    stall_raw = block.get(_STALL_TIMEOUT_KEY)
    if stall_raw is None:
        return NodeTimeouts(
            configured=configured,
            stall_seconds=DEFAULT_STALL_TIMEOUT_SECONDS,
            stall_layer=WORKFLOW_DEFAULT_LAYER,
        )
    stall_seconds = _positive_int(value=stall_raw)
    if stall_seconds is None:
        return (
            f"dispatcher.{_STALL_TIMEOUT_KEY} must be a positive integer of "
            f"seconds; got {stall_raw!r}"
        )
    return NodeTimeouts(
        configured=configured,
        stall_seconds=stall_seconds,
        stall_layer=REPOSITORY_LAYER,
    )


def _positive_int(*, value: object) -> int | None:
    """The value as a positive int, or None when it is neither.

    `bool` is excluded explicitly: it is an `int` subclass in Python, so
    `true` in a config file would otherwise resolve to a one-second timeout
    -- a value that both passes validation and destroys every dispatch.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


# Derived, never hand-written: the ceiling a fully-defaulted resolution
# implies. It is the fallback for a `DispatchPlan` built without an explicit
# ceiling (the hermetic tests and any caller that resolves no config), so
# even that path follows the graph rather than a literal.
DEFAULT_FABRO_TIMEOUT_SECONDS = derive_fabro_timeout_seconds(timeouts=default_node_timeouts())
