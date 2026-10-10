"""The committed ImplementWorkItem graph's engine-agnostic (Petri-era) properties.

Plan `fabro-currency` P4 (`bd-ib-hti4zf`). The factory is mid-migration from the
pinned Fabro 0.254 engine to the Petri-era build, and the parallel rollout needs
ONE graph that validates and runs on BOTH. Three semantic gaps were MEASURED on
the candidate `v0.378.0-nightly.0` on 2026-10-08 (research notes 007 and 008 of
`plan/fabro-currency/research`), and each one is a property of the committed
graph that this module pins:

- `context.internal.node_visit_count` edge conditions NEVER FIRE on the
  candidate. Probe p3 looped ZERO times: routing took the unconditional edge at
  visit 1. A loop guarded that way therefore does not loop at all on the
  candidate -- the Red would fall straight through to the exhaustion terminal --
  so every such guard has to go, and the bound has to be `max_visits`, which
  probe p3f showed fails the run deterministically after N firings.
- An `inputs.*` token inside an edge condition is an
  `attractor.condition.syntax` ERROR at load. Those three errors are the whole
  reason `validate_accepts_livespec_workflow_templated_acp_command` failed on
  the candidate in the Enemy Unit Test comparison.
- A script node prefers the run id from the Petri context source while retaining
  `FABRO_RUN_ID` as the pinned-engine fallback, so one graph preserves the tree
  on both engines during the parallel rollout.

WHAT THIS MODULE DOES NOT CLAIM. `fabro validate` accepted every ACP attribute
shape tried on the candidate, so graph VALIDITY is necessary and nowhere near
sufficient; validating the generated graph against both engine builds is a
host-captured assertion of this work-item, and the launch behaviour behind it was
settled by running agents, not by reading a graph. These cases pin the committed
TEXT's properties, which is the half a sandbox can check.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_allowance import (
    commit_timeout_seconds,
    per_attempt_overhead_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_execution_budget import (
    ExecutionBudget,
    execution_budget,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _PAYLOAD / "workflow.fabro"

# The pre-port graph, kept beside the ported one under its own name so a
# rollback is a file copy rather than a revert archaeology exercise.
_ROLLBACK = _PAYLOAD / "workflow.pre-petri.fabro"

# Every edge statement's `condition` attribute value, which is the ONLY place
# the two refused shapes matter. Anchored on an identifier followed by `->` so a
# `//` DOT comment containing an arrow -- of which this graph has several --
# can never be read as an edge.
_EDGE_RE = re.compile(
    r"(?m)^[ \t]*(?P<src>[A-Za-z_]\w*)[ \t]*->[ \t]*(?P<dst>[A-Za-z_]\w*)(?P<attrs>.*)$"
)
_CONDITION_RE = re.compile(r'condition[ \t]*=[ \t]*"(?P<value>[^"]*)"')

# The template opener written as a character class rather than as the literal
# pair, because the literal pair poisons ledger and goal rendering wherever this
# file's text is quoted (the fleet convention of livespec-dev-tooling-9yb4).
_OPENER_RE = re.compile(r"\{[{#%]")

_NODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]*(?P<name>\w+)[ \t]*\[(?P<body>[^\]]*)\]")

_VISIT_COUNT_FIELD = "node_visit_count"
_RUN_ID_SOURCE = 'stdin_source="context.internal.run_id"'


def _graph_text() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _conditions(*, text: str) -> dict[tuple[str, str], str]:
    """Each conditional edge as `(source, target) -> condition`, verbatim."""
    found: dict[tuple[str, str], str] = {}
    for edge in _EDGE_RE.finditer(text):
        condition = _CONDITION_RE.search(edge.group("attrs"))
        if condition is not None:
            found[edge.group("src"), edge.group("dst")] = condition.group("value")
    return found


def _node_bodies(*, text: str) -> dict[str, str]:
    """Each declared node's attribute body, by node name."""
    return {
        match.group("name"): match.group("body")
        for match in _NODE_BLOCK_RE.finditer(text)
        if match.group("name") != "graph"
    }


def test_no_edge_condition_references_a_workflow_input_token() -> None:
    """An `inputs.*` token in a condition is an `attractor.condition.syntax` error."""
    conditions = _conditions(text=_graph_text())
    assert conditions != {}
    offenders = {edge: value for edge, value in conditions.items() if _OPENER_RE.search(value)}
    assert offenders == {}


def test_no_edge_condition_reads_a_node_visit_count() -> None:
    """A visit-count guard never fires on the candidate, so a guarded loop never loops."""
    conditions = _conditions(text=_graph_text())
    offenders = {edge: value for edge, value in conditions.items() if _VISIT_COUNT_FIELD in value}
    assert offenders == {}


def test_the_janitor_fix_loop_routes_on_outcome_and_is_bounded_by_max_visits() -> None:
    """Outcome routing works on both engines; `max_visits` is what bounds the loop."""
    text = _graph_text()
    conditions = _conditions(text=text)
    assert conditions["janitor", "fix"] == "outcome!=succeeded"
    assert conditions["janitor", "publish_draft"] == "outcome=succeeded"
    assert ("fix", "janitor") in {
        (edge.group("src"), edge.group("dst")) for edge in _EDGE_RE.finditer(text)
    }
    assert "max_visits=" in _node_bodies(text=text)["fix"]


def test_the_review_fix_loop_routes_on_preferred_label_and_is_bounded_by_max_visits() -> None:
    """The three review-cap conditions are gone; the loop's bound is on its nodes."""
    text = _graph_text()
    conditions = _conditions(text=text)
    assert conditions["review", "disposition"] == "preferred_label=fix"
    assert conditions["review", "proof_verify"] == "preferred_label=approve"
    bodies = _node_bodies(text=text)
    assert "max_visits=" in bodies["review_fix"]
    assert "max_visits=" in bodies["disposition"]


def test_the_needs_human_script_reads_the_run_id_from_the_engine_context() -> None:
    """The Petri context is authoritative and the pinned-engine env is its fallback."""
    body = _node_bodies(text=_graph_text())["needs_human"]
    assert _RUN_ID_SOURCE in body
    assert 'environment_run_id=\\"${FABRO_RUN_ID:-}\\"' in body
    assert 'run_id=\\"$environment_run_id\\"' in body


def test_the_pre_port_graph_is_kept_as_a_separately_named_rollback_file() -> None:
    """A rollback is a file copy, and it is NOT the file the generator writes."""
    assert _ROLLBACK.is_file()
    rollback = _ROLLBACK.read_text(encoding="utf-8")
    assert rollback != _graph_text()
    # The pre-port graph is the one carrying what the port removed, which is what
    # makes it a rollback rather than a stale duplicate.
    assert _VISIT_COUNT_FIELD in rollback
    assert "FABRO_RUN_ID" in rollback


def test_the_generator_writes_only_the_implement_work_item_graph() -> None:
    """The rollback file is inert: the run config names one graph and it is not this."""
    committed = (_PAYLOAD / "workflow.toml").read_text(encoding="utf-8")
    assert 'graph = "workflow.fabro"' in committed
    assert _ROLLBACK.name not in committed


def test_the_ported_graph_derives_the_same_execution_budget_as_the_pre_port_one() -> None:
    """The port changes HOW the loop budget is expressed, not how large it is.

    THIS IS THE CASE THAT GUARDS THE FACTORY. `_dispatcher_execution_budget`
    reads a loop's bound off `max_visits` once the edge guards are gone, and
    `_dispatcher_credential_requirement` sizes a REQUIRED CREDENTIAL LIFETIME
    from the result. Leaving the retired `max_visits=10` backstops in place while
    removing the guards they stood behind raised the derived allowance from 177
    hours to 391 — a lifetime no real Codex credential carries — so the credential
    gate would have refused every Codex-projecting dispatch while every
    graph-shape assertion above stayed green.

    The control is the ROLLBACK FILE rather than a figure written here: a literal
    would keep agreeing with itself every time this repository's configuration
    moved the node timeouts underneath it, and the claim is parity with the
    pre-port graph, not equality with a number.
    """
    toml = (_PAYLOAD / "workflow.toml").read_text(encoding="utf-8")
    timeouts = resolve_node_timeouts(cwd=_REPO_ROOT)
    assert not isinstance(timeouts, str), timeouts
    commit_timeout = commit_timeout_seconds(committed_text=toml)
    assert not isinstance(commit_timeout, str), commit_timeout
    overhead = per_attempt_overhead_seconds(commit_timeout_seconds=commit_timeout)
    inputs = {
        name: int(value.strip())
        for name, value in workflow_declared_inputs(committed_text=toml).items()
        if value.strip().isdigit()
    }

    def budget(*, text: str) -> ExecutionBudget:
        derived = execution_budget(
            graph_text=text,
            timeouts=timeouts,
            per_attempt_overhead_seconds=overhead,
            graph_inputs=inputs,
        )
        assert not isinstance(derived, str), derived
        return derived

    ported = budget(text=_graph_text())
    pre_port = budget(text=_ROLLBACK.read_text(encoding="utf-8"))

    assert ported.seconds == pre_port.seconds
    # The visit TABLE too, not just its sum: two different tables can total the
    # same seconds, and it is the per-node figure the credential deadline and the
    # fabro-run subprocess ceiling are both derived from.
    assert ported.node_visits == pre_port.node_visits
