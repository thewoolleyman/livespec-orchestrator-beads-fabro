"""A hook-over-limit ending is named on the ledger, and its work is preserved.

Binds the LAST two clauses of `SPECIFICATION/scenarios.md` Scenario 177's
over-limit-push sub-scenario -- "the needs-human cause recorded on the item
names hook-over-limit, publish_draft and the push operation" and "the run's work
is preserved before it terminates" -- together with Scenario 103's "the run
preserves its work by reference before terminating", for ``bd-ib-xi63mq``.

WHY THE TWO CLAUSES SHARE A CASE. They are one promise read at two surfaces: the
ending has to be ATTRIBUTABLE on a record that outlives the run, and the tree
has to still EXIST when somebody acts on that record. A cause naming an event
whose work was discarded sends an operator to triage a tree that is gone, and a
preserved tree nobody can attribute is a ref with no reason beside it. Neither
half is worth much alone, which is why they are asserted against the same route.

THE CAUSE RECORD IS APPEND-ONLY, which is why the naming is asserted literally
rather than by shape. `bd comments` offers add and list with no edit and no
delete, so a record that failed to name the classification cannot be repaired
afterwards -- the assertion has to be on the words an operator will search for.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit import (
    HOOK_OVER_LIMIT_JOURNAL_STAGE,
    hook_over_limit_from_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_SENTINEL_LINE = (
    "LIVESPEC_HOOK_OVER_LIMIT: node=publish_draft operation=push "
    "limit_seconds=3600 hook_elapsed_ms=3477219"
)


def _outcome(*, kind: str | None, with_event: bool) -> DispatchOutcome:
    event = hook_over_limit_from_text(text=_SENTINEL_LINE) if with_event else None
    return DispatchOutcome(
        work_item_id="bd-ib-xi63mq",
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="publish_draft failed",
        fabro_run_id="01M4XKJE3GZKJ739SRE9VTRDX2",
        fabro_failure_cause="stage publish_draft failed",
        fabro_failure_category="deterministic",
        needs_human_kind=kind,
        needs_human_stages=("publish_draft",),
        hook_over_limit=event,
    )


def test_the_cause_recorded_on_the_item_names_the_event_the_node_and_the_push() -> None:
    """Scenario 177: the stop is not presented as an agent's decision."""
    body = needs_human_cause_body(outcome=_outcome(kind=STAGE_FAILURE, with_event=True))

    assert NEEDS_HUMAN_CAUSE_MARKER in body
    assert HOOK_OVER_LIMIT_JOURNAL_STAGE in body
    assert "publish_draft" in body
    assert "push" in body
    assert "3600s limit" in body
    assert "3477219ms" in body
    # The record must not read as a pending question, which is the misreading
    # the whole classification exists to prevent.
    assert "no agent asked anything" in body


def test_an_ending_with_no_such_event_names_none(tmp_path: Path) -> None:
    """A recovered or absent event is not named as a later ending's cause.

    The negative control for the clause "a recovered event MUST NOT be named as
    the cause of a later needs-human ending that has a different cause". A
    writer that rendered the classification whenever the field happened to be
    populated would pass the positive case above and break this one.
    """
    _ = tmp_path
    body = needs_human_cause_body(outcome=_outcome(kind=STAGE_FAILURE, with_event=False))

    assert NEEDS_HUMAN_CAUSE_MARKER in body
    assert HOOK_OVER_LIMIT_JOURNAL_STAGE not in body


def test_an_agent_request_ending_is_not_reattributed_to_a_hook() -> None:
    """An agent that DID ask keeps its own ending, event field or not.

    `_attribution` renders only under a stage failure, so an outcome carrying
    both an agent's request and a stale event must still report the request.
    Asserted because the event field rides on every outcome now, and the cheap
    coding -- render it wherever it is set -- would silently convert a genuine
    question into a hook report.
    """
    body = needs_human_cause_body(outcome=_outcome(kind=AGENT_REQUEST, with_event=True))

    assert HOOK_OVER_LIMIT_JOURNAL_STAGE not in body
    assert "an agent asked a question" in body


def test_the_over_limit_push_routes_to_the_terminal_that_preserves_the_tree() -> None:
    """Scenario 177 + 103: the failing push reaches needs_human, which preserves.

    The script's over-limit arm exits NON-ZERO under its own sentinel, and the
    graph's own edges are what turn that exit into a preserved tree. Both halves
    are read off the committed graph, because an exit code with no edge behind
    it preserves nothing and an edge no arm can reach is never taken.

    The route is TWO edges rather than one since v134's refresh repair
    (`bd-ib-5guqmt`): `publish_draft` now fails into the `refresh_repair`
    classifier, which reads the refresh-repair brief and routes to `fix` only
    when a stage WROTE one. The over-limit arm writes none -- it exits before
    `livespec_refresh_repair` is reachable -- so the classifier's own onward
    edge is what carries it to the preserving terminal. Both edges are asserted,
    because `publish_draft -> refresh_repair` alone would be satisfied by a
    classifier with no route out.
    """
    graph = _WORKFLOW.read_text(encoding="utf-8")

    assert re.search(
        r'publish_draft -> refresh_repair \[label="Blocked", condition="outcome=failed"\]', graph
    ), "publish_draft has no failure edge to the refresh-repair classifier"
    assert re.search(
        r"refresh_repair -> needs_human", graph
    ), "the refresh-repair classifier has no onward edge to the preserving terminal"
    # The terminal preserves by reference and says so on its own output, which
    # is the sentinel `_dispatcher_needs_human_detail` reads to report that a
    # ref was pushed.
    assert "LIVESPEC_NEEDS_HUMAN_PRESERVED" in graph
    # And the arm that reaches that edge: the bounded push returns non-zero
    # after naming the event, rather than falling through to proof capture.
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_OVER_LIMIT" in graph
