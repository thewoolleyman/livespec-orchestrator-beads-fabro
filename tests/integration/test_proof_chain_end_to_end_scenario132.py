"""Scenario 132 END TO END: capture, review, replay, merge and pointer in ONE run.

Binds `SPECIFICATION/scenarios.md` "Scenario 132 — A factory-captured proof is
captured on a draft pull request, reviewed, replayed and published" as one
journey, and the `SPECIFICATION/contracts.md` clauses it realizes:
the Definition-of-Done-and-Proof-of-Done stages clause, for the positions and
routing of `publish_draft`, `proof_capture`, `review`, `proof_verify` and `pr`;
and the Proof-of-Done-record clause, for the append-only record comments and the
post-merge pointer.

WHY THIS MODULE EXISTS BESIDE FOUR THAT ALREADY BIND THE HEADING. The capture
half (`test_workflow_proof_capture_scenario132`), the replay half
(`test_workflow_proof_verify_scenario132`) and the host half
(`test_proof_of_done_acceptance_scenarios132_133`,
`test_needs_attention_proof_facts`) each assert their own leg against COMMITTED
GRAPH AND PROMPT PAYLOADS, or against one host primitive handed a canned record
body. Not one of them connects the two: every host-side case to date fed the
acceptance pass a record the TEST wrote, so "the pass graded the record the run
published" was true by construction and could not have failed. This module
closes that: ONE driven run publishes the records, and the REAL Dispatcher
completion path reads back exactly those bytes through the same forge double.

WHAT IS REAL AND WHAT STANDS IN. The route is the COMMITTED graph's own: the
drive reads the graph off the plan's MATERIALIZED run config — the file this
dispatch would have handed Fabro — and follows that file's edges and edge
CONDITIONS, so no node order is written down here. `dispatcher.main(argv=
["dispatch", ...])`, the plan build, `run_acceptance_pass`, the proof-evidence
leg, the disposition, the pointer write and every ledger write are production
code over the real store/client seam. Two seams are stood in: `run_dispatch`, so
no sandbox launches — replaced by the graph drive itself — and the acceptance
pass's `CommandRunner`, which IS the forge double, so the pull request the drive
published onto is the pull request the pass reads.

WHY THE RECORD BODIES ARE THE REAL ONES. Both are read VERBATIM from
`fixtures/proof_records/pull-request-2538-comments.json`, the committed
`gh pr view --json comments` payload of the first factory_captured dispatch that
ever ran this chain live (item `bd-ib-mxqrr4`, merged 2026-10-01). The item's
Definition of Done is BUILT from that record's own assertion headings and the
run id is read off its own header, so nothing in this module transcribes either:
a synthetic record stamped with whatever identifier the test also fed the pass is
exactly how a reader that could never match a real record looked correct for
weeks (`test_proof_record_dispatch_id_attribution` records that measurement).

WHY THE POINTER LINKS THE CAPTURED RECORD THROUGH THE PULL REQUEST AND NOT BY A
SECOND URL. The pointer clause fixes the section's contents as a CLOSED set —
the pull request number, the latest `verified` record's link, its run id,
timestamp and verdict, plus the host and human links when the item owes those
legs — and says outright that the section "MUST NOT copy proof content". A
`Captured record:` bullet would therefore be a conformance defect, not an
improvement. What the pointer carries is the pair that RESOLVES both records:
the pull request, and the run that published on it. So the pointer's reach is
asserted by resolving that pair against the forge and finding both records, with
a pull request the forge does not hold as the control that the resolution can
return the other answer.

WHY THE MERGED DIFF SHARES NO VOCABULARY WITH ANY ASSERTION. The proof-evidence
clause forbids merged-diff vocabulary matching for an assertion carrying a proof
mode, so a PASS taken off the diff would be a defect — and a diff that HAPPENS to
carry the assertion's words makes a PASS ambiguous about which leg produced it.
The overlap is therefore COMPUTED and asserted empty, over a term set that is a
deliberate SUPERSET of the production matcher's (every lowercase word of four
characters or more, with no stop-word subtraction), because a superset finding
nothing is the conservative direction.

WHY THE DRIVE REFUSES RATHER THAN GUESSES. A walker that silently mis-routes is
the "instrument that cannot return a hit" failure in its purest form: it would
report a green journey through a route the graph does not describe. So the
condition evaluator carries a CLOSED vocabulary — three context terms, four
operators, the two workflow inputs the graph interpolates — and raises on
anything else, on a node whose every edge is conditional with none matching
(the `all_conditional_edges` defect that took the factory down twice), and on a
graph that does not terminate. One case drives every condition the committed
graph declares through that evaluator, so the drive is known to understand the
WHOLE graph rather than only the clauses this journey happens to reach.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion, _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import (
    GREEN_TERMINAL_SHAPE,
    parse_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    AcceptancePassResult,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    PROOF_RECORD_EVIDENCE_LEG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    PROOF_OF_DONE_POINTER_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer_write import (
    PROOF_POINTER_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_COMMITTED_CONFIG = _BUNDLE / "workflow.toml"
_COMMITTED_GRAPH_TEXT = (_BUNDLE / "workflow.fabro").read_text(encoding="utf-8")
_RECORDS_FIXTURE = Path(__file__).parent / "fixtures/proof_records/pull-request-2538-comments.json"

_START = "start"
_PUBLISH_DRAFT = "publish_draft"
_PROOF_CAPTURE = "proof_capture"
_REVIEW = "review"
_DISPOSITION = "disposition"
_PROOF_VERIFY = "proof_verify"
_PR = "pr"
# The five positions the Definition of Done names, in the order it names them.
# Asserted as a SUBSEQUENCE of the route actually walked rather than as the route
# itself, so the claim stays about these nodes while the exact route (which the
# case also pins) is free to carry the loop the reviewer asked for.
_REQUIRED_POSITIONS = (_PUBLISH_DRAFT, _PROOF_CAPTURE, _REVIEW, _PROOF_VERIFY, _PR)

_SUCCEEDED = "succeeded"
_FAILED = "failed"
_LABEL_FIX = "fix"
_LABEL_APPROVE = "approve"
_LABEL_ALL_REJECTED = "all_rejected"

# The closed context vocabulary the committed graph's conditions read.
_OUTCOME_TERM = "outcome"
_PREFERRED_LABEL_TERM = "preferred_label"
_VISIT_COUNT_TERM = "context.internal.node_visit_count"
# The two workflow inputs the graph interpolates into a condition. Their VALUES
# come off the dispatch plan, never off a literal here: the review-fix cap is a
# repository dial, and a copy of today's number drifts the moment it moves.
_CAP_INPUT = "review_fix_visit_cap"
_MERGE_ON_CAP_INPUT = "merge_on_review_cap_outcome"
# Longest-first so `!=` is never read as `=` with a stray `!` on its left, and
# `>=` is never read as a bare `>`.
_OPERATORS = ("!=", ">=", "=", "<")
_CLAUSE_SEPARATOR = "&&"
_INPUT_REFERENCE = re.compile(r"\{\{\s*inputs\.(?P<name>\w+)\s*\}\}")
# A bare literal: the only term shape that is neither a context read nor an
# input reference. Anchored whole, so `context.internal.attempt` and an
# unresolved `{{ inputs.unknown }}` both fall through to the refusal.
_LITERAL = re.compile(r"\w+")
# An edge line and, when it carries one, its attribute block. The source name is
# `^`-anchored and must be followed directly by the arrow, so a `//` comment line
# describing an edge cannot match; the case below cross-checks the whole set
# against the production graph reader.
_EDGE_LINE = re.compile(
    r"(?m)^[ \t]*(?P<source>\w+)[ \t]*->[ \t]*(?P<target>\w+)[ \t]*(?:\[(?P<attrs>[^\]]*)\])?[ \t]*$"
)
_CONDITION_ATTRIBUTE = re.compile(r'condition="(?P<condition>[^"]*)"')
_GRAPH_KEY = re.compile(r'(?m)^graph = "(?P<path>[^"]+)"')
_ASSERTION_HEADING = re.compile(r"(?m)^## Assertion \d+ — (?P<text>.+)$")
_SIGNIFICANT_TERM = re.compile(r"[a-z0-9_]{4,}")
# A generous bound on the reserved workflow's longest honest route. The journey
# below walks eighteen nodes; anything near this many is a graph that does not
# terminate, which the drive reports rather than hanging on.
_STEP_BOUND = 64

_PULL_REQUEST_NUMBER = 2538
_PULL_REQUEST_URL = "https://example.test/thewoolleyman/livespec-orchestrator-beads-fabro/pull/"
_FIRST_COMMENT_ID = 5940546142
# The real merge sha of the pull request the committed record payload came from.
_MERGE_SHA = "77067d88"

# A diff that is READABLE — the pass must not park for an unobservable one — and
# that shares no significant term with any assertion, asserted rather than
# eyeballed in the journey case.
_MERGED_DIFF = (
    "diff --git a/zephyr/pebble.py b/zephyr/pebble.py\n"
    "--- a/zephyr/pebble.py\n"
    "+++ b/zephyr/pebble.py\n"
    '-    return "quiet"\n'
    '+    return "quieter"\n'
)
# An assertion no record names and the diff cannot evidence either, so the only
# honest answer for it is UNEVIDENCED. It is the control for "the pass graded
# from the record": a reader answering True for everything cannot pass with it in
# the section.
_UNRECORDED_ASSERTION = "The pointer section names the pull request that carries both records."
_TAMPERED_BODY = "Proof of Done — captured — run tampered — 2026-10-01T21:02:22Z\n"

_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)


class _DriveRefusedError(Exception):
    """The drive met graph syntax or a graph shape it will not route through.

    An exception rather than a return value on purpose: every caller is a step
    of one walk, and a refusal that rode the return channel would have to be
    distinguished from a node name by every one of them. The point of refusing
    at all is that a drive which cannot route honestly must not report a
    journey.
    """


@dataclass(frozen=True, kw_only=True)
class _Edge:
    """One committed edge: where it goes, and the condition guarding it."""

    source: str
    target: str
    condition: str | None


@dataclass(frozen=True, kw_only=True)
class _State:
    """What one node visit reported, as the edge conditions read it."""

    outcome: str
    preferred_label: str | None
    visit: int


@dataclass(frozen=True, kw_only=True)
class _Comment:
    """One published pull-request comment, by link and body."""

    url: str
    body: str


def _record_header(*, body: str) -> tuple[str, str, str]:
    """One record comment's (verdict, run identifier, timestamp), from its first line.

    Read with a test-local split rather than through the production record
    parser deliberately. The claim under test is that the records the drive
    published are the records the Dispatcher graded and pointed at, and
    resolving them with the same reader the Dispatcher used would make the two
    agree by construction — concurrence is not independence when the method is
    shared.
    """
    fields = [part.strip() for part in body.splitlines()[0].split("—")]
    return fields[1], fields[2].removeprefix("run "), fields[3]


def _fixture_comments() -> tuple[_Comment, ...]:
    payload = json.loads(_RECORDS_FIXTURE.read_text(encoding="utf-8"))
    return tuple(
        _Comment(url=str(one["url"]), body=str(one["body"])) for one in payload["comments"]
    )


def _fixture_body(*, verdict: str) -> str:
    """The committed payload's record body carrying one verdict, verbatim."""
    return next(
        one.body for one in _fixture_comments() if _record_header(body=one.body)[0] == verdict
    )


_CAPTURED_RECORD = _fixture_body(verdict=VERDICT_CAPTURED)
_VERIFIED_RECORD = _fixture_body(verdict=VERDICT_VERIFIED)
_RUN_ID = _record_header(body=_VERIFIED_RECORD)[1]
_VERIFIED_TIMESTAMP = _record_header(body=_VERIFIED_RECORD)[2]
# The item's assertions ARE the published record's own assertion headings, so the
# Definition of Done and the proof cannot drift apart in this fixture.
_ASSERTIONS = tuple(match.group("text") for match in _ASSERTION_HEADING.finditer(_VERIFIED_RECORD))


def _terms(*, text: str) -> set[str]:
    """Every lowercase term of four characters or more — a SUPERSET of the matcher's.

    The production matcher subtracts a stop-word list from this set, so a term
    here that is absent from the diff is certainly absent from the production
    terms too. Over-counting is the conservative direction for an assertion
    that the overlap is EMPTY.
    """
    return set(_SIGNIFICANT_TERM.findall(text.lower()))


def _definition_of_done(*, assertions: Sequence[str]) -> str:
    bullets = "\n".join(f"- {text}" for text in assertions)
    return (
        "Repoint the aggregate at the justfile's own target list.\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        f"{bullets}\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
    )


@dataclass(kw_only=True)
class _Forge:
    """A hermetic forge: one draft pull request and its APPEND-ONLY comments.

    It is BOTH halves of the end-to-end leg — the surface the driven nodes
    publish onto, and the `CommandRunner` the acceptance pass reads through — so
    the records the pass grades are necessarily the records the run published.

    `timeline` is a snapshot of the comment list taken at every node visit.
    Append-only is a property of the whole run rather than of one comment, and a
    single end-state read cannot see a body that was rewritten and then
    rewritten back.
    """

    number: int | None = None
    head: str | None = None
    draft: bool = True
    merge_sha: str | None = None
    comments: list[_Comment] = field(default_factory=list)
    timeline: list[tuple[_Comment, ...]] = field(default_factory=list)
    argvs: list[list[str]] = field(default_factory=list)

    def open_draft(self, *, head: str) -> int:
        """Open a DRAFT pull request for `head`, or return the one already open.

        The idempotence the contract requires of `publish_draft`: every accepted
        fix round re-enters a green janitor, so this runs again each time, and a
        second pull request would leave the capture and the review on different
        ones.
        """
        if self.number is None:
            self.number = _PULL_REQUEST_NUMBER
            self.head = head
        return self.number

    def post_comment(self, *, body: str) -> str:
        """APPEND one new comment and return its link."""
        comment = _Comment(
            url=f"{_PULL_REQUEST_URL}{self.number}"
            f"#issuecomment-{_FIRST_COMMENT_ID + len(self.comments)}",
            body=body,
        )
        self.comments.append(comment)
        return comment.url

    def rewrite_comment(self, *, index: int, body: str) -> None:
        """EDIT a published comment — the mutation the record clause forbids.

        It exists so the append-only instrument has a positive failure case. No
        driven node reaches it; the control case calls it directly, because an
        instrument that has never reported a violation is not known to be able
        to.
        """
        self.comments[index] = replace(self.comments[index], body=body)

    def mark_ready_and_merge(self) -> None:
        """What the `pr` node does: ready the standing draft, then it merges."""
        self.draft = False
        self.merge_sha = _MERGE_SHA

    def snapshot(self) -> None:
        self.timeline.append(tuple(self.comments))

    def records_on(self, *, number: int, run_id: str) -> tuple[str, ...]:
        """The verdicts of every record one run published on one pull request.

        This is the resolution the pointer makes possible, and it is why the
        pointer reaches the captured record without linking it: the pointer
        names a pull request and a run, and that pair addresses every record
        the run published there.
        """
        if self.number != number:
            return ()
        return tuple(
            verdict
            for verdict, identity, _ in (_record_header(body=one.body) for one in self.comments)
            if identity == run_id
        )

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        if "comments" in argv:
            payload = json.dumps(
                {"comments": [{"url": one.url, "body": one.body} for one in self.comments]}
            )
            return CommandResult(exit_code=0, stdout=payload, stderr="")
        return CommandResult(exit_code=0, stdout=_MERGED_DIFF, stderr="")


def _edges(*, text: str) -> tuple[_Edge, ...]:
    """Every declared edge, in declaration order, with its condition."""
    return tuple(
        _Edge(
            source=match.group("source"),
            target=match.group("target"),
            condition=_condition_of(attrs=match.group("attrs")),
        )
        for match in _EDGE_LINE.finditer(text)
    )


def _condition_of(*, attrs: str | None) -> str | None:
    if attrs is None:
        return None
    found = _CONDITION_ATTRIBUTE.search(attrs)
    return None if found is None else found.group("condition")


def _resolve(*, term: str, state: _State, inputs: dict[str, str]) -> str:
    """One side of a comparison, as a string, or a refusal.

    An unknown input reference survives substitution as its own `{{ … }}` text,
    which is not a literal, so it lands on the refusal with everything else the
    drive does not model.
    """
    resolved = _INPUT_REFERENCE.sub(
        lambda match: inputs.get(match.group("name"), match.group(0)), term
    ).strip()
    if resolved == _OUTCOME_TERM:
        return state.outcome
    if resolved == _PREFERRED_LABEL_TERM:
        return "" if state.preferred_label is None else state.preferred_label
    if resolved == _VISIT_COUNT_TERM:
        return str(state.visit)
    if _LITERAL.fullmatch(resolved) is not None:
        return resolved
    raise _DriveRefusedError(f"no term this drive resolves: {term!r}")


def _compare(*, operator: str, left: str, right: str) -> bool:
    if operator == "=":
        return left == right
    if operator == "!=":
        return left != right
    if operator == ">=":
        return int(left) >= int(right)
    return int(left) < int(right)


def _clause_holds(*, clause: str, state: _State, inputs: dict[str, str]) -> bool:
    for operator in _OPERATORS:
        left, separator, right = clause.partition(operator)
        if separator == "":
            continue
        return _compare(
            operator=operator,
            left=_resolve(term=left, state=state, inputs=inputs),
            right=_resolve(term=right, state=state, inputs=inputs),
        )
    raise _DriveRefusedError(f"no operator this drive evaluates: {clause!r}")


def _condition_holds(*, condition: str, state: _State, inputs: dict[str, str]) -> bool:
    return all(
        _clause_holds(clause=clause, state=state, inputs=inputs)
        for clause in condition.split(_CLAUSE_SEPARATOR)
    )


def _next_node(*, outgoing: Sequence[_Edge], state: _State, inputs: dict[str, str]) -> str:
    """The successor the graph's own routing picks for one node's report.

    Conditional edges outrank the unconditional fallthrough, in declaration
    order, which is the routing the pinned engine applies and the reason every
    inserted node leaves its ordinary route unconditional. A node with no
    unconditional route and nothing matching is the `all_conditional_edges`
    shape the engine rejects outright, so the drive refuses rather than
    inventing a successor.
    """
    for edge in outgoing:
        if edge.condition is not None and _condition_holds(
            condition=edge.condition, state=state, inputs=inputs
        ):
            return edge.target
    for edge in outgoing:
        if edge.condition is None:
            return edge.target
    raise _DriveRefusedError(f"no edge routes {state!r} onward from an all-conditional node")


def _walk(
    *,
    edges: Sequence[_Edge],
    inputs: dict[str, str],
    act: Callable[..., tuple[str, str | None]],
) -> tuple[list[str], str]:
    """Follow the graph from `start`, acting at each visit; return the route and terminal.

    A node with no outgoing edge IS the terminal — the graph's four terminals are
    exactly its sink nodes — so termination is read off the graph rather than off
    a node-name list written here.
    """
    visited: list[str] = []
    counts: dict[str, int] = {}
    node = _START
    for _ in range(_STEP_BOUND):
        visited.append(node)
        counts[node] = counts.get(node, 0) + 1
        outgoing = [edge for edge in edges if edge.source == node]
        if not outgoing:
            return visited, node
        outcome, label = act(node=node, visit=counts[node])
        node = _next_node(
            outgoing=outgoing,
            state=_State(outcome=outcome, preferred_label=label, visit=counts[node]),
            inputs=inputs,
        )
    raise _DriveRefusedError(f"no terminal reached within {_STEP_BOUND} steps")


def _always_succeeded(*, node: str, visit: int) -> tuple[str, str | None]:
    _ = node, visit
    return _SUCCEEDED, None


def _sandbox(*, forge: _Forge, branch: str) -> Callable[..., tuple[str, str | None]]:
    """What each node of the reserved workflow does to the forge, and what it reports.

    This is the whole of the sandbox's behaviour, and it is deliberately the
    minimum each node's contract names: `publish_draft` pushes and opens the
    draft, `proof_capture` publishes its record, `review` asks for one fix round
    and then approves, `proof_verify` publishes the verified record and routes
    on `approve`, `pr` readies the standing draft and it merges. The ONE fix
    round is not decoration: it is what makes `publish_draft`'s idempotence and
    the append-only rule load-bearing, since both are claims about a SECOND
    entry, and it drives the reviewer's own disposition loop out of the
    committed graph rather than around it.
    """

    def _act(*, node: str, visit: int) -> tuple[str, str | None]:
        if node == _PUBLISH_DRAFT:
            _ = forge.open_draft(head=branch)
        elif node == _PROOF_CAPTURE:
            _ = forge.post_comment(body=_CAPTURED_RECORD)
        elif node == _PROOF_VERIFY:
            _ = forge.post_comment(body=_VERIFIED_RECORD)
        elif node == _PR:
            forge.mark_ready_and_merge()
        forge.snapshot()
        if node == _REVIEW:
            return _SUCCEEDED, (_LABEL_FIX if visit == 1 else _LABEL_APPROVE)
        if node == _DISPOSITION:
            return _SUCCEEDED, _LABEL_FIX
        if node == _PROOF_VERIFY:
            return _SUCCEEDED, _LABEL_APPROVE
        return _SUCCEEDED, None

    return _act


def _append_only_violations(*, timeline: Sequence[tuple[_Comment, ...]]) -> list[str]:
    """Each adjacent snapshot pair where the later one is not the earlier one PLUS.

    One rule covers both ways append-only can break: a later snapshot must start
    with the earlier one link-for-link and byte-for-byte, which fails if a
    published comment was rewritten and fails if one disappeared.
    """
    return [
        f"snapshot {index} does not extend snapshot {index - 1}"
        for index, (before, after) in enumerate(pairwise(timeline), start=1)
        if after[: len(before)] != before
    ]


@dataclass(kw_only=True)
class _Run:
    """What one driven run of the committed graph resolved and produced."""

    forge: _Forge
    branch: str = ""
    graph: Path = Path()
    edges: tuple[_Edge, ...] = ()
    inputs: dict[str, str] = field(default_factory=dict)
    visited: list[str] = field(default_factory=list)
    terminal: str = ""


@dataclass(frozen=True, kw_only=True)
class _Journey:
    """One finished dispatch: its exit code, its journal, its repo and its run."""

    exit_code: int
    records: list[dict[str, object]]
    repo: Path
    run: _Run


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    scratch = tmp_path_factory.mktemp("fabro-proof-chain")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_self_update.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-proofchain",
        type="task",
        status="pending-approval",
        title="Repoint the aggregate at the justfile's own target list",
        description=_definition_of_done(assertions=_ASSERTIONS),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _graph_path(*, config: Path) -> Path:
    """The graph THIS dispatch resolved, read off its materialized run config.

    The overlay carries the committed config with its graph path absolutized, so
    this is the file the dispatch would have handed Fabro — not a path this
    module picked, which is the difference between driving the dispatch's own
    graph and driving one that merely resembles it.
    """
    found = _GRAPH_KEY.search(config.read_text(encoding="utf-8"))
    assert found is not None, config
    return Path(found.group("path"))


def _driving_run_dispatch(*, run: _Run) -> Callable[..., DispatchOutcome]:
    """Stand in for the factory launch by DRIVING the graph the dispatch resolved."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        run.branch = plan.branch
        run.graph = _graph_path(config=plan.workflow_toml)
        run.edges = _edges(text=run.graph.read_text(encoding="utf-8"))
        run.inputs = {
            _CAP_INPUT: str(plan.review_fix_visit_cap),
            _MERGE_ON_CAP_INPUT: plan.merge_on_review_cap_outcome,
        }
        run.visited, run.terminal = _walk(
            edges=run.edges,
            inputs=run.inputs,
            act=_sandbox(forge=run.forge, branch=plan.branch),
        )
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=run.forge.number,
            merge_sha=run.forge.merge_sha,
            detail="merged",
            fabro_run_id=_RUN_ID,
        )

    return _run_dispatch


def _acceptance_pass_over(*, runner: _Forge) -> Callable[..., AcceptancePassResult]:
    """The REAL acceptance pass, with the forge double as its command seam."""

    def _call(
        *,
        repo: Path,
        item: WorkItem,
        outcome: DispatchOutcome,
        raw_labels: Sequence[str] = (),
        journal_path: Path | None = None,
    ) -> AcceptancePassResult:
        return run_acceptance_pass(
            repo=repo,
            item=item,
            outcome=outcome,
            runner=runner,
            raw_labels=raw_labels,
            journal_path=journal_path,
        )

    return _call


def _drive(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, item: WorkItem) -> _Journey:
    """One dispatch of one item, with the graph drive standing in for the sandbox."""
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=item)
    run = _Run(forge=_Forge())
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _driving_run_dispatch(run=run))
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        _acceptance_pass_over(runner=run.forge),
        raising=False,
    )
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(_COMMITTED_CONFIG.resolve()),
        ]
    )
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return _Journey(
        exit_code=exit_code,
        records=[json.loads(line) for line in text.splitlines() if line.strip()],
        repo=repo,
        run=run,
    )


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _record(*, records: list[dict[str, object]], stage: str) -> dict[str, object]:
    return next(one for one in records if one.get("stage") == stage)


def _proof_assertions(*, records: list[dict[str, object]]) -> list[dict[str, object]]:
    proof = _record(records=records, stage="acceptance-ai-pass")["proof"]
    assert isinstance(proof, dict)
    graded = proof["assertions"]
    assert isinstance(graded, list)
    return [one for one in graded if isinstance(one, dict)]


def _pointer_section(*, description: str) -> list[str]:
    _, _, pointer = description.partition(f"## {PROOF_OF_DONE_POINTER_TITLE}")
    return pointer.splitlines()


def _pointer_fields(*, section: Sequence[str]) -> dict[str, str]:
    """The pointer's bullets as label → value, read off the written bytes."""
    return {
        label: value
        for label, _, value in (
            line.removeprefix("- ").partition(": ") for line in section if line.startswith("- ")
        )
    }


def _subsequence(*, route: Sequence[str], wanted: Sequence[str]) -> bool:
    remaining = iter(route)
    return all(any(node == step for node in remaining) for step in wanted)


def _assert_drove_the_committed_graph(*, run: _Run) -> None:
    """The route taken is the COMMITTED graph's own, and it is the whole route.

    The materialized copy the dispatch resolved differs from the bundle only in
    the per-node timeouts the Dispatcher projects into it, so the ROUTING is
    asserted identical rather than the bytes. The edge set is cross-checked
    against the PRODUCTION graph reader too, which is what rules out a reader
    here that silently dropped an edge — a route never offered an alternative
    looks exactly like a route that rejected it.

    The sequence is pinned EXACTLY rather than checked for the five positions
    the Definition of Done names: a graph that reached `pr` without a capture
    would then fail rather than merely omit a node. The named positions are
    asserted as a subsequence beside it, with a deliberately impossible order as
    the control that the subsequence reader can return False.

    The terminal is checked against the graph's own `Msquare` declaration rather
    than against the name `exit`, because "the run finished GREEN" is a claim
    about the terminal's kind and a renamed terminal must not pass.
    """
    assert run.edges == _edges(text=_COMMITTED_GRAPH_TEXT)
    graph = parse_workflow_graph(text=_COMMITTED_GRAPH_TEXT)
    assert tuple((edge.source, edge.target) for edge in run.edges) == graph.edges
    assert run.inputs[_CAP_INPUT].isdigit()
    # One reviewer-requested fix round, so `publish_draft` and `proof_capture`
    # are each entered twice — that second entry is what makes the idempotence
    # and append-only claims load-bearing.
    assert run.visited == [
        _START,
        "dod_gate",
        "implement",
        "implementation_diff",
        "janitor",
        _PUBLISH_DRAFT,
        _PROOF_CAPTURE,
        _REVIEW,
        _DISPOSITION,
        "review_fix",
        "janitor",
        _PUBLISH_DRAFT,
        _PROOF_CAPTURE,
        _REVIEW,
        _PROOF_VERIFY,
        _PR,
        "verify_pr",
        "exit",
    ]
    assert _subsequence(route=run.visited, wanted=_REQUIRED_POSITIONS)
    assert not _subsequence(route=run.visited, wanted=(_PR, _PUBLISH_DRAFT))
    assert run.terminal in graph.with_shape(shape=GREEN_TERMINAL_SHAPE)


def _assert_three_append_only_records_on_one_draft(*, run: _Run, item: WorkItem) -> None:
    """ONE draft pull request on the plan's own publish branch, readied and merged.

    The second `publish_draft` entry opened no second pull request, which is the
    idempotence the contract requires of a node a green janitor re-enters; the
    three records are the two captures and the replay, each a distinct comment
    link; and the append-only check is clean across a snapshot taken at every
    node visit, so a body rewritten and rewritten back could not hide in the end
    state. The sibling case proves that check can report a violation.
    """
    forge = run.forge
    assert run.branch == f"feat/{item.id}"
    assert (forge.number, forge.head, forge.draft) == (_PULL_REQUEST_NUMBER, run.branch, False)
    assert [_record_header(body=one.body)[0] for one in forge.comments] == [
        VERDICT_CAPTURED,
        VERDICT_CAPTURED,
        VERDICT_VERIFIED,
    ]
    assert len({one.url for one in forge.comments}) == len(forge.comments)
    assert _append_only_violations(timeline=forge.timeline) == []
    assert len(forge.timeline) == len(run.visited) - 1


def _assert_graded_from_the_verified_record(*, journey: _Journey) -> None:
    """Every assertion graded off the VERIFIED record the run published, not the diff.

    Each assertion's own journal projection is read, so "from the record" is
    per-assertion rather than a property of the pass as a whole: the evidence
    leg is the proof-record leg and the record cited is the comment the driven
    `proof_verify` node appended. The diff the pass ALSO read is asserted to
    share no significant term with any assertion, so even a build that applied
    merged-diff vocabulary matching — which the clause forbids for an assertion
    carrying a proof mode — could not have produced this PASS.

    Both forge reads are asserted to have happened, because "the pass graded the
    record" is a claim about a read, and a pass that graded nothing would exit 0
    just as happily.
    """
    forge = journey.run.forge
    verified_url = forge.comments[-1].url
    assert journey.exit_code == 0
    ai_pass = _record(records=journey.records, stage="acceptance-ai-pass")
    assert (ai_pass["verdict"], ai_pass["absent_evidence"]) == ("PASS", [])
    graded = _proof_assertions(records=journey.records)
    assert [one["text"] for one in graded] == list(_ASSERTIONS)
    assert [one["evidence_leg"] for one in graded] == [PROOF_RECORD_EVIDENCE_LEG] * len(_ASSERTIONS)
    assert [one["record_comment"] for one in graded] == [verified_url] * len(_ASSERTIONS)
    assert [one["evidenced"] for one in graded] == [True] * len(_ASSERTIONS)
    assert (
        _terms(text=_MERGED_DIFF) & set().union(*(_terms(text=one) for one in _ASSERTIONS)) == set()
    )
    assert ["gh", "pr", "view", str(forge.number), "--json", "comments"] in forge.argvs
    assert ["gh", "pr", "diff", str(forge.number), "--patch"] in forge.argvs


def _assert_pointer_reaches_both_records(*, journey: _Journey, item: WorkItem) -> None:
    """The pointer, after a byte-identical Definition of Done, reaching both records.

    Three separate claims, none redundant. The Definition of Done is compared
    BYTE FOR BYTE by slicing at the pointer heading, because a build that
    rewrote the section while appending would satisfy a containment check just
    as well. The pointer's bullets are compared LINE BY LINE against the closed
    field set the clause fixes, and the record's own proof vocabulary is asserted
    ABSENT, which is the "MUST NOT copy proof content" half.

    Then the reach: the pull request and run the pointer NAMES — read off the
    written bytes, not off the forge — are resolved against the forge and must
    return both the captured and the verified record. A pull request the forge
    does not hold is the control that the resolution can return the other
    answer; without it, finding both records is equally consistent with a reader
    that returns everything it holds.
    """
    forge = journey.run.forge
    verified_url = forge.comments[-1].url
    description = _stored()[item.id].description
    head, _, _ = description.partition(f"## {PROOF_OF_DONE_POINTER_TITLE}")
    assert head.rstrip("\n") == _definition_of_done(assertions=_ASSERTIONS).rstrip("\n")
    section = _pointer_section(description=description)
    assert section[1:] == [
        "",
        f"- Pull request: #{forge.number}",
        f"- Verified record: {verified_url}",
        f"- Run: {_RUN_ID}",
        f"- Timestamp: {_VERIFIED_TIMESTAMP}",
        f"- Verdict: {VERDICT_VERIFIED}",
    ]
    assert "Reproduced:" not in description
    assert "Proof mode:" not in description
    fields = _pointer_fields(section=section)
    pointed = int(fields["Pull request"].removeprefix("#"))
    assert forge.records_on(number=pointed, run_id=fields["Run"]) == (
        VERDICT_CAPTURED,
        VERDICT_CAPTURED,
        VERDICT_VERIFIED,
    )
    assert forge.records_on(number=pointed + 1, run_id=fields["Run"]) == ()
    assert _record(records=journey.records, stage=PROOF_POINTER_STAGE)["record_comment"] == (
        verified_url
    )


def test_the_committed_graph_drives_capture_review_replay_merge_and_the_pointer_in_one_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 132, whole: the capture chain and the host pointer in ONE journey.

    ONE case rather than six, because every mechanism it touches already passed
    in isolation and the claim under test is that they COMPOSE. Split apart,
    each half passes against a build that loses the record somewhere between the
    run and the pointer: no case would carry the same bytes through the publish
    seam, the forge read, the grading and the description write.

    Each assertion is chosen to be unable to pass for the wrong reason. The
    route is pinned as the EXACT sequence walked, so a graph that reached `pr`
    without a capture would fail rather than merely omit a node; the terminal is
    checked against the graph's own `Msquare` declaration rather than against
    the name `exit`; the pointer's bullet lines are compared LINE BY LINE,
    because a build that rewrote the Definition of Done while appending would
    satisfy a containment check just as well; and the diff's vocabulary overlap
    with the assertions is COMPUTED, so a PASS cannot be ambiguous about which
    evidence leg produced it.
    """
    item = _item()

    journey = _drive(tmp_path=tmp_path, monkeypatch=monkeypatch, item=item)

    _assert_drove_the_committed_graph(run=journey.run)
    _assert_three_append_only_records_on_one_draft(run=journey.run, item=item)
    _assert_graded_from_the_verified_record(journey=journey)
    _assert_pointer_reaches_both_records(journey=journey, item=item)


def test_every_condition_the_committed_graph_declares_is_evaluable_by_the_drive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The drive understands the WHOLE graph, not only the clauses the journey reaches.

    Without this case, the journey proves only that the eleven-condition graph
    can be walked along one route: every condition the route short-circuits past
    is unevaluated, so a drive that refused — or worse, mis-answered — some other
    clause would still report a clean journey. Each declared condition is
    therefore evaluated under every state the reserved workflow's nodes can
    report, and the assertion is that none refuses.

    The condition set is cross-checked against an INDEPENDENT scan of the
    committed text, because "every condition was evaluable" is vacuous if the
    edge reader returned no conditions at all.
    """
    journey = _drive(tmp_path=tmp_path, monkeypatch=monkeypatch, item=_item())

    declared = {edge.condition for edge in journey.run.edges if edge.condition is not None}
    independent = set(_CONDITION_ATTRIBUTE.findall(_COMMITTED_GRAPH_TEXT))
    assert declared == independent
    assert independent
    states = [
        _State(outcome=_SUCCEEDED, preferred_label=None, visit=1),
        _State(outcome=_FAILED, preferred_label=None, visit=1),
        _State(outcome=_SUCCEEDED, preferred_label=_LABEL_FIX, visit=1),
        # At the cap, so the review node's two escape-hatch conditions are
        # reached instead of being short-circuited by their first clause.
        _State(
            outcome=_SUCCEEDED,
            preferred_label=_LABEL_FIX,
            visit=int(journey.run.inputs[_CAP_INPUT]),
        ),
        _State(outcome=_SUCCEEDED, preferred_label=_LABEL_APPROVE, visit=1),
        _State(outcome=_SUCCEEDED, preferred_label=_LABEL_ALL_REJECTED, visit=1),
    ]

    answers = [
        _condition_holds(condition=condition, state=state, inputs=journey.run.inputs)
        for condition in sorted(declared)
        for state in states
    ]

    assert len(answers) == len(declared) * len(states)
    # BOTH answers occur, which is what rules out an evaluator that agreed with
    # everything or refused nothing by answering one way always.
    assert set(answers) == {True, False}


def test_the_append_only_instrument_reports_a_rewritten_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The append-only check CAN fail, so the journey's clean verdict means something.

    An instrument that has never reported a violation is not known to be able
    to, and this one reports the absence of a mutation — the hardest kind of
    claim to tell apart from a reader that looks at nothing. The driven run's
    own timeline is taken, the earliest published record is EDITED through the
    forge's one forbidden verb, and the check is asserted to name exactly that
    snapshot pair.
    """
    journey = _drive(tmp_path=tmp_path, monkeypatch=monkeypatch, item=_item())
    forge = journey.run.forge
    assert _append_only_violations(timeline=forge.timeline) == []

    forge.rewrite_comment(index=0, body=_TAMPERED_BODY)
    forge.snapshot()

    last = len(forge.timeline) - 1
    assert _append_only_violations(timeline=forge.timeline) == [
        f"snapshot {last} does not extend snapshot {last - 1}"
    ]


def test_an_assertion_the_verified_record_never_names_stays_unevidenced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for "graded from the record": a fifth assertion cannot pass.

    The journey's PASS is equally consistent with a proof leg that answers
    `True` for every assertion it is handed. The same run, the same records and
    the same diff, with ONE extra assertion the records do not name, must grade
    that one UNEVIDENCED and park — and the four real ones must still grade off
    the verified record, so the park is a property of the fifth assertion rather
    than of the whole pass.

    The pointer is asserted written anyway, which is the pointer clause's own
    requirement: it is written whenever a verified record exists for the merging
    run, "independently of the acceptance verdict".
    """
    item = _item(
        id="bd-ib-proofchainpark",
        description=_definition_of_done(assertions=(*_ASSERTIONS, _UNRECORDED_ASSERTION)),
    )
    # The two ways the extra assertion could pass for the wrong reason, excluded
    # before the run rather than argued afterwards.
    assert _UNRECORDED_ASSERTION not in _VERIFIED_RECORD
    assert _terms(text=_UNRECORDED_ASSERTION) & _terms(text=_MERGED_DIFF) == set()

    journey = _drive(tmp_path=tmp_path, monkeypatch=monkeypatch, item=item)

    assert journey.exit_code == 1
    ai_pass = _record(records=journey.records, stage="acceptance-ai-pass")
    assert ai_pass["verdict"] == "NEEDS_ATTENTION"
    assert ai_pass["absent_evidence"] == [
        f"{PROOF_RECORD_EVIDENCE_LEG} for {_UNRECORDED_ASSERTION!r}"
    ]
    graded = _proof_assertions(records=journey.records)
    verified_url = journey.run.forge.comments[-1].url
    assert [one["evidenced"] for one in graded] == [*([True] * len(_ASSERTIONS)), False]
    assert [one["record_comment"] for one in graded[: len(_ASSERTIONS)]] == [verified_url] * len(
        _ASSERTIONS
    )
    assert _stored()[item.id].status == "acceptance"
    assert _record(records=journey.records, stage=PROOF_POINTER_STAGE)["record_comment"] == (
        verified_url
    )


def test_the_drive_refuses_a_condition_or_a_graph_it_cannot_route() -> None:
    """Four fail-closed properties of the drive, each a way it could mis-route silently.

    A walker that guessed would report a journey through a route the graph does
    not describe — a green result for a run that never happened — so each
    refusal is asserted rather than assumed: a context term outside the closed
    vocabulary, an unresolved workflow input, an operator the drive does not
    evaluate, a node whose every edge is conditional with none matching (the
    `all_conditional_edges` shape the pinned engine rejects outright), and a
    graph with no terminal.
    """
    state = _State(outcome=_SUCCEEDED, preferred_label=None, visit=1)

    with pytest.raises(_DriveRefusedError):
        _ = _condition_holds(condition="context.internal.attempt=1", state=state, inputs={})
    with pytest.raises(_DriveRefusedError):
        _ = _condition_holds(condition="outcome={{ inputs.no_such_input }}", state=state, inputs={})
    with pytest.raises(_DriveRefusedError):
        _ = _condition_holds(condition="outcome ~ succeeded", state=state, inputs={})
    with pytest.raises(_DriveRefusedError):
        _ = _walk(
            edges=(_Edge(source=_START, target="exit", condition=f"{_OUTCOME_TERM}={_FAILED}"),),
            inputs={},
            act=_always_succeeded,
        )
    with pytest.raises(_DriveRefusedError):
        _ = _walk(
            edges=(
                _Edge(source=_START, target="loop", condition=None),
                _Edge(source="loop", target=_START, condition=None),
            ),
            inputs={},
            act=_always_succeeded,
        )
