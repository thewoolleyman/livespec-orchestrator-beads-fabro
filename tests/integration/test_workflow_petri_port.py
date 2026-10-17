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
- A script node reads the run id from the context source the engine supplies,
  `stdin_source="context.internal.run_id"`, rather than from `FABRO_RUN_ID`,
  which the pinned engine exports to HOOKS only and never to script nodes.

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

# The scripted publication stages (v121) and the cycle they open. `pr_refresh`
# reconciles the publish branch with the authoritative default and its
# postcondition breaker routes a CHANGED head back to `proof_capture`, so the
# refresh loop re-enters capture, review and replay -- which is why those three
# nodes' derived visit counts move even though neither their attributes nor
# their own edges changed.
_PUBLICATION_STAGES_ADDED = {"pr_refresh", "pr_refresh_head"}
_PUBLICATION_STAGES = _PUBLICATION_STAGES_ADDED | {"pr", "verify_pr"}
_REFRESH_LOOP = _PUBLICATION_STAGES_ADDED | {"proof_capture", "review", "proof_verify"}

# The refresh-repair classifier (v134), kept as its own constant rather than
# folded into the port-era set above. The subject of this module is the PORT, so
# "which nodes the port added" has to stay the port's own answer; a later
# addition merged into that set would make a future port regression read as part
# of the v134 route. The nodes it moves are the fix loop's, which is every node
# the repair round re-earns.
_REFRESH_REPAIR_ADDED = {"refresh_repair"}

# The refresh-route decision node (v145; work-item bd-ib-3hpdvm), kept as its own
# constant for the reason the refresh-repair set above gives: the subject of this
# module is the PORT, so a later addition merged into the port's own set would
# make a future port regression read as part of this route. The nodes it moves
# are the publication stages' and the proof loop's, because the route re-enters
# `pr_refresh` and a changed head re-earns the trio.
_PR_ROUTE_ADDED = {"pr_route"}
_REFRESH_REPAIR_LOOP = _REFRESH_REPAIR_ADDED | {
    "fix",
    "janitor",
    "publish_draft",
    "proof_capture",
    "review",
    "disposition",
    "review_fix",
    "proof_verify",
    "non_converged",
    "needs_human",
}

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

# A node's attribute body, read LINE-ORIENTED rather than by a `[^\]]*` body
# pattern. That pattern ended a body at the first `]` ANYWHERE after the
# opener, and a `]` is not rare inside a node script: it closes a shell
# character class. `publish_draft` and `needs_human` each carry `*[!0-9]*`, so
# each body truncated mid-script, each one's `script="` line lost the quote that
# would have closed it, and both nodes fell out of the attribution entirely --
# silently, because the remaining ten nodes still produced a plausible
# non-empty scan. A graph carrying this work-item's own defect inside
# `publish_draft` therefore read CLEAN through the refusal written to forbid it.
#
# A block body is every line between a bare `name [` opener and the `]` that
# sits alone on its own line. That closer cannot occur inside an attribute,
# because this graph writes one attribute per line and a DOT attribute string
# holds no bare newline -- which is the property the old pattern needed and did
# not have. The single-line `name [...]` form (`start` and `exit`) is a separate
# pattern rather than a widening of this one, so neither shape's reading depends
# on the other's.
_NODE_BLOCK_RE = re.compile(
    r"(?m)^[ \t]*(?P<name>\w+)[ \t]*\[[ \t]*\n(?P<body>(?:.*\n)*?)[ \t]*\]$"
)
_INLINE_NODE_RE = re.compile(r"(?m)^[ \t]*(?P<name>\w+)[ \t]*\[(?P<body>[^\n\]]*)\][ \t]*$")

_VISIT_COUNT_FIELD = "node_visit_count"
_RUN_ID_SOURCE = 'stdin_source="context.internal.run_id"'

# How the shipped graph declares a node's script: one attribute, on one line,
# opened by this prefix and closed by the quote that ends the line.
_SCRIPT_ATTRIBUTE_PREFIX = 'script="'

# The pattern the structural refusal below exists for: a backslash in front of a
# single quote inside a node script. A DOT attribute string escapes a double
# quote and a backslash and NOTHING else, so this sequence is not an escape --
# the pinned reader drops the backslash by accident while a Petri-era reader
# hands it to the shell, where a backslashed quote is a LITERAL quote character.
_ESCAPED_SINGLE_QUOTE = "\\'"


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
    """Each declared node's attribute body, by node name, in BOTH declared shapes."""
    found = {
        match.group("name"): match.group("body")
        for pattern in (_INLINE_NODE_RE, _NODE_BLOCK_RE)
        for match in pattern.finditer(text)
    }
    return {name: body for name, body in found.items() if name != "graph"}


def _declared_script_lines(*, text: str) -> list[str]:
    """Every `script` attribute line in the FILE, attributed to no node at all.

    The completeness control for the attribution above, and deliberately a
    SECOND reading rather than a re-use of the first: a count derived from
    `_node_bodies` would agree with itself however much that walk dropped, which
    is exactly how the truncated body pattern reported a clean scan over ten of
    this graph's twelve scripts.
    """
    return [
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()).startswith(_SCRIPT_ATTRIBUTE_PREFIX)
        and stripped.endswith('"')
    ]


def _raw_node_scripts(*, text: str) -> dict[str, str]:
    """Each declared node's `script` value as the FILE carries it, escapes UNDECODED.

    Read off the raw text rather than through `parse_dot_graph`, which models the
    PINNED reader and drops the backslash from every escape it meets: a decoded
    script cannot carry the pattern the refusal below is about, so a scan over
    the parsed graph would report clean for every graph ever written.
    """
    found: dict[str, str] = {}
    for name, body in _node_bodies(text=text).items():
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(_SCRIPT_ATTRIBUTE_PREFIX) and stripped.endswith('"'):
                found[name] = stripped[len(_SCRIPT_ATTRIBUTE_PREFIX) : -1]
    return found


def _quoting_offenders(*, text: str) -> dict[str, int]:
    """Each node whose script carries a backslash-escaped single quote, and how many."""
    return {
        name: script.count(_ESCAPED_SINGLE_QUOTE)
        for name, script in _raw_node_scripts(text=text).items()
        if _ESCAPED_SINGLE_QUOTE in script
    }


def test_no_node_script_carries_a_backslash_escaped_single_quote() -> None:
    """The structural refusal that closes the Petri-era quoting family for good.

    Work-item bd-ib-be5r7o. Four spans of this one pattern reached master, and
    each was found by a production failure rather than by a gate:
    `bd-ib-m4cspa` fixed the fifth and missed these four, because nothing
    mechanical was looking. The pattern is invisible to every gate this
    repository already runs -- `check-fabro-graph-validity` hands the graph to
    `fabro validate`, which accepts it either way, since the graph is perfectly
    VALID and it is the SHELL that is handed a literal quote character.

    WHAT EACH SPAN COST, which is why the refusal is blanket rather than
    per-construct: a `--jq` operand becomes a program beginning with a quote
    token, so the read fails closed (fatal on the arming guard in front of every
    rewrite, and silent on the merge-detection path, where the run loses the sha
    of the merge it produced); a `printf` format becomes a quote-wrapped literal
    whose `\\n` is a bare `n`, so a state file holds a value a later visit cannot
    compare as a number and a durable reason file holds its cause punctuated by
    stray quotes with no line ending. Different constructs, one cause.

    THE SCOPE CONTROL RUNS FIRST, because the refusal's claim is about EVERY
    node script and an instrument's reach is the half of that claim no clean
    answer can establish. Every `script` attribute line in the file is counted
    by a reading that attributes nothing, and the attribution must account for
    all of them: when this case was first authored the body pattern truncated
    each body at its first shell character class, so `publish_draft` and
    `needs_human` were outside the scan and ten scripts of twelve passed for
    twelve.

    THE MUTANT CONTROLS RUN NEXT. A scan that reports an absence for a living
    has to be shown capable of returning a HIT before its clean answer means
    anything: a prefix that stopped matching, a body pattern that stopped
    reaching a node, or a scan taken over the PARSED graph (where the pattern
    cannot survive at all) would each report exactly what a clean graph reports.
    Each mutant is made from the committed graph's own text rather than
    hand-authored, so neither can rot into something the scan would miss for an
    unrelated reason, and each finding is asserted to NAME its node, since an
    offender a failure does not name sends a reader through a
    ten-thousand-character attribute by hand. Counts are asserted RELATIVE to
    the committed graph's own, so a control states what its mutation ADDED
    rather than restating what the graph happens to carry.

    THE TWO MUTANTS ARE NOT REDUNDANT, and the second is why this case was
    revised. `pr` was inside the original scan's reach, so a mutant in it could
    only ever show the instrument FUNCTIONS -- never that it is POINTED at the
    whole graph. `publish_draft` is the node that reach excluded, and its
    mutation is seeded in the `--jq` read of the pull-request number, the one
    span of this family's own shape that node carries. A mutant only in the
    reachable node is the exact control that passed while the blind spot stood.
    """
    text = _graph_text()
    scripts = _raw_node_scripts(text=text)
    declared = _declared_script_lines(text=text)
    assert declared != []
    # The COUNT says the attribution dropped none of them -- and it also reports
    # an attribution that collapsed two nodes onto one script, which a set
    # comparison alone would call equal. The VALUES say each script the scan
    # holds is one the file really declares, so the count cannot be met by
    # inventing entries.
    assert len(scripts) == len(declared), sorted(scripts)
    assert set(scripts.values()) == {line[len(_SCRIPT_ATTRIBUTE_PREFIX) : -1] for line in declared}

    committed = _quoting_offenders(text=text)

    # Each replacement is bounded to ONE occurrence, so a control's arithmetic
    # states a fixed addition of two quotes rather than however many reads its
    # node happens to carry today -- `pr` carries this needle twice already, on
    # one line, and a later visit may add more.
    for node, needle in (
        ("pr", "--jq '.mergeCommit.oid'"),
        ("publish_draft", "--jq '.[0].number'"),
    ):
        assert node in scripts, sorted(scripts)
        wrapped = needle.replace("'", _ESCAPED_SINGLE_QUOTE)
        mutant = text.replace(needle, wrapped, 1)
        assert mutant != text
        mutated = _quoting_offenders(text=mutant)
        assert node in mutated, (node, sorted(mutated))
        assert mutated[node] == committed.get(node, 0) + 2

    assert committed == {}


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
    """`FABRO_RUN_ID` is exported to hooks only; the Petri-era source is the context."""
    body = _node_bodies(text=_graph_text())["needs_human"]
    assert _RUN_ID_SOURCE in body
    assert "FABRO_RUN_ID" not in body


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

    PARITY IS NOW ATTRIBUTED RATHER THAN EXACT, and that change is stated here
    rather than absorbed. v121 replaced the ACP `pr` turn with the command stages
    `pr_refresh` and `pr_refresh_head`, which open a NEW cycle back through
    capture, review and replay, so the ported graph's allowance is genuinely
    LARGER than the pre-port one -- claiming equality would now require either a
    graph that does not carry the refresh or a derivation that does not see it.
    What the case asserts instead is that the whole difference is ATTRIBUTABLE:
    the two new stages are the only nodes added, nothing was dropped, and every
    node whose visit or attempt count moved is either a publication stage or a
    member of the refresh loop. An unrelated node's budget moving still fails,
    which is the regression this case exists to catch.
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

    # The two new stages plus the v134 refresh-repair classifier are the ONLY
    # nodes added, and nothing was dropped: a node the ported graph lost would be
    # an executable path missing from a figure still presented as an allowance.
    assert (
        set(ported.node_visits) - set(pre_port.node_visits)
        == _PUBLICATION_STAGES_ADDED | _REFRESH_REPAIR_ADDED | _PR_ROUTE_ADDED
    )
    assert set(pre_port.node_visits) - set(ported.node_visits) == set()

    # The visit TABLE, not just its sum: two different tables can total the same
    # seconds, and it is the per-node figure the credential deadline and the
    # fabro-run subprocess ceiling are both derived from. Every node whose count
    # moved must be one the scripted publication reaches.
    moved = {
        node
        for node in set(ported.node_visits) | set(pre_port.node_visits)
        if (ported.node_visits.get(node), ported.node_attempts.get(node))
        != (pre_port.node_visits.get(node), pre_port.node_attempts.get(node))
    }
    reachable = _PUBLICATION_STAGES | _REFRESH_LOOP | _REFRESH_REPAIR_LOOP | _PR_ROUTE_ADDED
    assert moved <= reachable, sorted(moved - reachable)
    # And the direction is the honest one: the graph grew, so the allowance grew.
    # Asserted rather than left implicit, because an allowance that SHRANK after
    # nodes were added would mean the derivation stopped seeing one of them.
    assert ported.seconds > pre_port.seconds
