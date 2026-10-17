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
    """Every `script` attribute written in the graph's CANONICAL one-line shape.

    An independent LOWER BOUND on `_script_attributes`, deliberately read a
    different way: a count derived from the scanner would agree with itself
    however much the scanner dropped. It is a lower bound and not the census,
    because it shares the line-shape restriction the first revision of this
    refusal had -- a multi-line script, or `script = "..."` with spaces, is
    invisible to it -- and that shared restriction is how two readings once
    agreed on a scan that missed every non-canonical layout.
    """
    return [
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()).startswith(_SCRIPT_ATTRIBUTE_PREFIX)
        and stripped.endswith('"')
    ]


_DOT_WORD_RE = re.compile(r"[A-Za-z_][\w.]*")
_SCRIPT_KEY = "script"


def _skip_blank(*, text: str, at: int) -> int:
    while at < len(text) and text[at] in " \t\r\n":
        at += 1
    return at


def _dot_string(*, text: str, start: int) -> tuple[str, int]:
    """The raw body of the DOT string opened at `start`, and the index after it.

    Escapes stay UNDECODED: a backslash only shields the character after it from
    closing the string. A string may span lines and may hold a bare `]`.
    """
    at = start + 1
    while at < len(text):
        if text[at] == "\\":
            at += 2
        elif text[at] == '"':
            return text[start + 1 : at], at + 1
        else:
            at += 1
    raise AssertionError(f"unterminated DOT string opened at offset {start}")


def _script_attributes(*, text: str) -> list[tuple[str, str]]:
    """Every `script` attribute in the graph as `(owner, raw value)`, in file order.

    Read off the raw text rather than through `parse_dot_graph`, which models the
    PINNED reader and drops the backslash from every escape it meets: a decoded
    script cannot carry the pattern the refusal below is about, so a scan over
    the parsed graph would report clean for every graph ever written.

    QUOTE-AWARE AND LAYOUT-FREE, and that is the second revision's whole point.
    The first revision attributed scripts by line shape, so `script = "..."`,
    a quoted `"script"` key, a script spanning lines, or a bare `]` inside one
    all fell out of the scan silently while the refusal still passed. This walk
    skips comments, tracks attribute lists by `[`/`]` OUTSIDE strings only, and
    reads each `script` key's value to its unescaped closing quote. The owner is
    the last bare word before the list opened, which is the node for a node
    statement. A script value that is not a quoted string cannot be scanned, so
    it fails here, naming its owner, rather than being skipped.
    """
    found: list[tuple[str, str]] = []
    owner = ""
    last_word = ""
    depth = 0
    at = 0
    while at < len(text):
        skipped = _skip_comment(text=text, at=at)
        if skipped != at:
            at = skipped
            continue
        if text[at] in "[]":
            opens = text[at] == "["
            depth += 1 if opens else -1
            owner = last_word if opens else owner
            at += 1
            continue
        token, at = _dot_token(text=text, at=at)
        if depth == 0:
            last_word = token if token is not None else last_word
            continue
        if token != _SCRIPT_KEY:
            continue
        read = _script_value(text=text, at=at, owner=owner)
        if read is not None:
            value, at = read
            found.append((owner, value))
    return found


def _skip_comment(*, text: str, at: int) -> int:
    """The index after a DOT comment opening at `at`, or `at` when none opens there."""
    if text.startswith("//", at):
        newline = text.find("\n", at)
        return len(text) if newline < 0 else newline
    if text.startswith("/*", at):
        end = text.find("*/", at + 2)
        assert end >= 0, f"unterminated block comment at offset {at}"
        return end + 2
    return at


def _dot_token(*, text: str, at: int) -> tuple[str | None, int]:
    """One DOT token: a string's raw body or a bare word, or `None` for punctuation."""
    if text[at] == '"':
        return _dot_string(text=text, start=at)
    word = _DOT_WORD_RE.match(text, at)
    if word is not None:
        return word.group(), word.end()
    return None, at + 1


def _script_value(*, text: str, at: int, owner: str) -> tuple[str, int] | None:
    """The value of the `script` key ending at `at`, or `None` when no `=` follows it."""
    equals = _skip_blank(text=text, at=at)
    if equals >= len(text) or text[equals] != "=":
        return None
    opener = _skip_blank(text=text, at=equals + 1)
    assert (
        opener < len(text) and text[opener] == '"'
    ), f"node {owner!r} declares a script that is not a quoted DOT string, so it cannot be scanned"
    return _dot_string(text=text, start=opener)


def _raw_node_scripts(*, text: str) -> dict[str, str]:
    """Each node's `script` value as the FILE carries it, escapes UNDECODED."""
    return dict(_script_attributes(text=text))


def _quoting_offenders(*, text: str) -> dict[str, int]:
    """Each node whose script carries a backslash-escaped single quote, and how many.

    Summed over the attribute LIST rather than the by-node mapping, so a node
    declaring a second script cannot hide the first one's offence.
    """
    offenders: dict[str, int] = {}
    for owner, script in _script_attributes(text=text):
        count = script.count(_ESCAPED_SINGLE_QUOTE)
        if count:
            offenders[owner] = offenders.get(owner, 0) + count
    return offenders


# Non-canonical script layouts, each carrying ONE escaped-quote pair. Every one
# passed the first revision of the refusal silently; each is now a mutant
# control. Written with the escape as a placeholder so the source of THIS file
# carries no backslash-quote pair of its own.
_PROBE_NODE = "layout_probe"
_LAYOUT_MUTANTS = (
    f'{_PROBE_NODE} [script = "echo Q.bad.Q"]',
    f'{_PROBE_NODE} ["script"="echo Q.bad.Q"]',
    f'{_PROBE_NODE} [\n    script="echo first;\n echo Q.bad.Q;\n echo last"\n]',
    f'{_PROBE_NODE} [\n    script="case $x in\n]\n esac; echo Q.bad.Q"\n]',
)


def _with_probe_node(*, text: str, declaration: str) -> str:
    """The graph with one extra node declared just before its closing brace."""
    closer = text.rstrip().rfind("}")
    assert closer > 0
    body = declaration.replace("Q.", _ESCAPED_SINGLE_QUOTE).replace(".Q", _ESCAPED_SINGLE_QUOTE)
    return f"{text[:closer]}    {body}\n{text[closer:]}"


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
    answer can establish. When this case was first authored the body pattern
    truncated each body at its first shell character class, so `publish_draft`
    and `needs_human` were outside the scan and ten scripts of twelve passed for
    twelve. Its first repair then read scripts by LINE SHAPE, and so did the
    count meant to check it, so the two agreed while `script = "..."`, a quoted
    key, and any multi-line script were all invisible to both. The scan is now a
    quote-aware walk with no layout assumption; the canonical-line reading
    remains only as a lower bound, and the layout mutants below are what show
    the walk's reach.

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
    attributes = _script_attributes(text=text)
    scripts = _raw_node_scripts(text=text)
    declared = _declared_script_lines(text=text)
    assert declared != []
    # One script per node, so the by-node mapping collapsed nothing.
    assert len(scripts) == len(attributes), [owner for owner, _ in attributes]
    # The canonical-line reading is a LOWER BOUND: every script it sees, the
    # scanner must see too, so the scanner cannot have dropped one that the
    # file's ordinary layout declares.
    assert {line[len(_SCRIPT_ATTRIBUTE_PREFIX) : -1] for line in declared} <= set(scripts.values())

    committed = _quoting_offenders(text=text)

    # THE LAYOUT MUTANTS are the controls the second review asked for: each is a
    # script shape the canonical-line reading cannot see, so only a scanner that
    # is genuinely layout-free can name the offending node.
    for declaration in _LAYOUT_MUTANTS:
        mutated = _quoting_offenders(text=_with_probe_node(text=text, declaration=declaration))
        assert mutated.get(_PROBE_NODE) == 2, (declaration, mutated)

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
