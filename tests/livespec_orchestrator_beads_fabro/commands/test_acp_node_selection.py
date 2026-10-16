"""WHICH ONE candidate each ACP node renders, taken from the admission verdict.

Binds the "Per-node selection" paragraph of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -- "the Dispatcher MUST choose the
first candidate in configured order that has no covering live hold, has
satisfied any outstanding post-expiry availability confirmation, has not been
skipped by the admission-time credential-usability probe for this evaluation,
and has not been skipped by the admission session-headroom filter for this
evaluation" -- and Scenario 127's "A domain-held primary is skipped and the
first eligible candidate is the node's only adapter".

THE VERDICT IS BUILT BY THE REAL ADMISSION MACHINERY, not hand-assembled. The
clause binds the selection to "one consistent read of the availability
evidence", and the whole claim under test is that `prepare_acp_nodes` consumes
the verdict ADMISSION produced rather than re-deriving an answer of its own. A
hand-built `NodePreflight` would prove the selection reads a parameter; routing
the same chains through `build_acp_preflight_verdict` with a live hold proves it
reads the verdict admission actually computes -- including that the candidate
objects the two halves exchange compare equal, which is the one way the
plumbing can be wired correctly and still select the wrong position.

THE PRIMARY'S OWN BYTES ARE ASSERTED ABSENT, not merely the fallback's present.
"candidate one's adapter is the only adapter rendered for that node" is a claim
about what is NOT there, and a resolution that rendered both -- or that rendered
the primary while recording the fallback -- satisfies every assertion about the
fallback's presence.

THE NO-VERDICT CASE IS THE ADDITIVE GUARANTEE and is asserted for its own sake.
Every non-dispatch caller of `prepare_acp_nodes` reaches it with no verdict at
all, and the contract's opening promise is that such a resolution stays
byte-identical to section "ACP node adapter configuration". An implementation
that required a verdict would strand those callers; one that silently selected
something else would move bytes nobody asked it to move.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

# The two modules this slice introduces: the PURE selection and the dispatch-side
# step that renders it. Named as paths so the Red fails on a genuine assertion
# rather than on an unimportable module.
_NEW_MODULES = ("_acp_node_selection", "_dispatcher_acp_selection")

_NODE = "implement"
_PRIMARY_DOMAIN = "primary-domain"
_PRIMARY_KEY = "primary-model"
_FALLBACK_DOMAIN = "fallback-domain"
_FALLBACK_KEY = "fallback-model"

_PRIMARY_BYTES = "PRIMARY_BASE_URL=https://primary.example primary-acp --stdio"
_FALLBACK_BYTES = "FALLBACK_BASE_URL=https://fallback.example fallback-acp --stdio"

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "npx -y claude-acp"
review_adapter = "npx -y claude-acp"

[run.environment]
id = "livespec-ci"
"""

# One start, one green terminal, and two ACP nodes both dominating it, so the
# configured node is genuinely admission-required rather than passed over as
# unreachable.
_WORKFLOW_GRAPH = """digraph implement {
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="{{ inputs.implement_adapter }}", timeout="60s"]
    review    [backend="acp", acp.command="{{ inputs.review_adapter }}", timeout="60s"]
    start -> implement
    implement -> review
    review -> exit
}
"""


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _assert_slice_exists() -> None:
    """Prove each module this slice introduces is on disk before importing it.

    A top-level import would make the Red a COLLECTION error, which proves only
    unimportability. This is the genuine assertion the Red fails on.
    """
    for name in _NEW_MODULES:
        assert (_COMMANDS / f"{name}.py").is_file(), f"{name}.py is not implemented yet"


class _RecordingJournal:
    """Collects journal records so a dispatch's own record can be asserted on."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _primary_entry() -> dict[str, Any]:
    return {
        "display_name": "Primary adapter",
        "candidate_key": _PRIMARY_KEY,
        "availability_key": _PRIMARY_DOMAIN,
        "command": "primary-acp",
        "args": ["--stdio"],
        "env": {"PRIMARY_BASE_URL": "https://primary.example"},
    }


def _fallback_entry() -> dict[str, Any]:
    return {
        "display_name": "Fallback adapter",
        "candidate_key": _FALLBACK_KEY,
        "availability_key": _FALLBACK_DOMAIN,
        "command": "fallback-acp",
        "args": ["--stdio"],
        "env": {"FALLBACK_BASE_URL": "https://fallback.example"},
    }


def _chained_entry() -> dict[str, Any]:
    return {**_primary_entry(), "fallbacks": [_fallback_entry()]}


def _repo(*, tmp_path: Path, acp_nodes: dict[str, Any]) -> Path:
    """A governed repository carrying one workflow and one chain table."""
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_WORKFLOW_GRAPH, encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Operator",
                    "operator_email": "operator@example.com",
                },
                "livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes": acp_nodes}},
            }
        ),
        encoding="utf-8",
    )
    return repo


def _committed(*, repo: Path) -> Path:
    return repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"


def _domain_hold(*, hold_key: str) -> Any:
    """One live schema-v1 domain observation, as the hold ledger yields them."""
    records = _module(name="_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="acp-obs-0123456789abcdef",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at="2026-10-16T10:00:00Z",
        expires_at="2026-10-16T22:00:00Z",
    )


def _sources(*, repo: Path) -> tuple[Any, str | None, frozenset[tuple[str, str]]]:
    """This repository's resolved chains, its graph text and its built-in pairs.

    Every input is the real one: the workflow-scoped block, the declared chains,
    the resolved primaries and the committed graph. Sharing this between the
    verdict and the chain assertions is what keeps the two halves talking about
    one configuration rather than two readings of it.
    """
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = sources.repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    return resolved


def _chains(*, repo: Path) -> Any:
    return _sources(repo=repo)[0]


def _verdict(*, repo: Path, holds: tuple[Any, ...]) -> Any:
    """The verdict ADMISSION would resolve for this repository, built its own way.

    Only the LEDGER is supplied directly, because a journal file would add a
    serialization round trip to a claim that is about selection.
    """
    ledger_module = _module(name="_acp_hold_ledger")
    preflight = _module(name="_acp_candidate_preflight")
    verdicts = _module(name="_acp_preflight_verdict")
    chains, graph_text, builtin_pairs = _sources(repo=repo)
    return verdicts.build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger_module.AcpHoldLedger(
            holds=holds, unobservable=(), observation_ids=frozenset()
        ),
        inputs=preflight.PreflightInputs(holds=holds, builtin_pairs=builtin_pairs),
    )


def _prepare(*, repo: Path, verdict: Any, journal: _RecordingJournal) -> Any:
    nodes = _module(name="_dispatcher_acp_nodes")
    return nodes.prepare_acp_nodes(
        repo=repo,
        committed=_committed(repo=repo),
        overrides=(),
        journal=journal,
        work_item_id="bd-ib-wvj4rk",
        verdict=verdict,
    )


def test_a_domain_held_primary_is_skipped_and_the_fallback_is_the_only_adapter(
    tmp_path: Path,
) -> None:
    """Scenario 127: candidate one's adapter is the node's ONLY rendered adapter."""
    _assert_slice_exists()
    repo = _repo(tmp_path=tmp_path, acp_nodes={_NODE: _chained_entry()})
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    resolution = _prepare(repo=repo, verdict=verdict, journal=_RecordingJournal())

    assert not isinstance(resolution, str), resolution
    assert resolution.nodes[_NODE].rendered == _FALLBACK_BYTES
    assert resolution.nodes[_NODE].rendered != _PRIMARY_BYTES


def test_an_unheld_primary_stays_the_selected_candidate(tmp_path: Path) -> None:
    """The control: selection moves past a candidate only when a hold covers it.

    Without this, an implementation that always took the LAST candidate -- or
    that took the chain's only fallback unconditionally -- would satisfy the case
    above exactly as well as a correct one.
    """
    _assert_slice_exists()
    repo = _repo(tmp_path=tmp_path, acp_nodes={_NODE: _chained_entry()})
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key="some-unrelated-domain"),))

    resolution = _prepare(repo=repo, verdict=verdict, journal=_RecordingJournal())

    assert not isinstance(resolution, str), resolution
    assert resolution.nodes[_NODE].rendered == _PRIMARY_BYTES


def test_a_resolution_with_no_verdict_keeps_its_configured_primary(tmp_path: Path) -> None:
    """A caller that resolved no verdict renders exactly what the layers produced.

    Reconcile, the check subcommands and the hermetic tier all reach
    `prepare_acp_nodes` this way, and the contract's additive guarantee covers
    them: no verdict is not an empty verdict, and it must not move a byte.
    """
    _assert_slice_exists()
    repo = _repo(tmp_path=tmp_path, acp_nodes={_NODE: _chained_entry()})

    resolution = _prepare(repo=repo, verdict=None, journal=_RecordingJournal())

    assert not isinstance(resolution, str), resolution
    assert resolution.nodes[_NODE].rendered == _PRIMARY_BYTES


def test_a_node_the_graph_never_reaches_keeps_its_primary_when_its_chain_empties(
    tmp_path: Path,
) -> None:
    """An unreachable node imposes no candidate requirement, so it is not refused.

    "A node proven unreachable in that graph imposes no candidate requirement."
    The `review` node here is configured with a single held candidate and is
    REMOVED from the graph, so its chain empties while admission requires
    nothing of it. Selection keeps its configured primary rather than refusing a
    dispatch over a node this graph cannot execute.
    """
    _assert_slice_exists()
    repo = _repo(
        tmp_path=tmp_path,
        acp_nodes={_NODE: _chained_entry(), "review": _primary_entry()},
    )
    graph = repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.fabro"
    _ = graph.write_text(
        _WORKFLOW_GRAPH.replace("    implement -> review\n    review -> exit\n", "")
        .replace(
            '    review    [backend="acp", acp.command="{{ inputs.review_adapter }}", '
            'timeout="60s"]\n',
            "",
        )
        .replace("    start -> implement\n", "    start -> implement\n    implement -> exit\n"),
        encoding="utf-8",
    )
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    resolution = _prepare(repo=repo, verdict=verdict, journal=_RecordingJournal())

    assert not isinstance(resolution, str), resolution
    assert resolution.nodes["review"].rendered == _PRIMARY_BYTES
    assert resolution.nodes[_NODE].rendered == _FALLBACK_BYTES


def test_an_admission_required_node_with_an_empty_chain_refuses_the_dispatch(
    tmp_path: Path,
) -> None:
    """Fail CLOSED: no adapter is rendered for a node every hold covers.

    "It MUST NOT render or start a candidate covered by a live hold, including
    for conditional repair or adjudication nodes." Admission refuses such an item
    before claim, so this state should be unreachable from a dispatch -- which is
    exactly why the selection must refuse rather than quietly fall back to the
    held primary it was told not to run.
    """
    _assert_slice_exists()
    repo = _repo(tmp_path=tmp_path, acp_nodes={_NODE: _primary_entry()})
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    refusal = _prepare(repo=repo, verdict=verdict, journal=_RecordingJournal())

    assert isinstance(refusal, str), refusal
    assert _NODE in refusal


def test_a_verdict_naming_a_candidate_this_dispatch_did_not_resolve_refuses(
    tmp_path: Path,
) -> None:
    """A chain edited between admission and launch refuses rather than guessing.

    The verdict is resolved before the claim and the adapters at materialization,
    so a committed edit can land between them. The selected candidate is then
    absent from the chain this dispatch holds, and there is no position to
    report: a selection that fell back to candidate zero would render the very
    primary the verdict had skipped.
    """
    _assert_slice_exists()
    repo = _repo(tmp_path=tmp_path, acp_nodes={_NODE: _chained_entry()})
    verdict = _verdict(repo=repo, holds=())
    rewritten = _repo(tmp_path=tmp_path / "second", acp_nodes={_NODE: _fallback_entry()})

    refusal = _prepare(repo=rewritten, verdict=verdict, journal=_RecordingJournal())

    assert isinstance(refusal, str), refusal
    assert _NODE in refusal


@pytest.mark.parametrize(
    ("hold_key", "index", "candidate_key"),
    [(_PRIMARY_DOMAIN, 1, _FALLBACK_KEY), (_FALLBACK_DOMAIN, 0, _PRIMARY_KEY)],
)
def test_selection_reports_the_position_it_chose(
    tmp_path: Path, hold_key: str, index: int, candidate_key: str
) -> None:
    """The pure selection names the POSITION it chose, plus the chain's digests.

    Asserted on the pure surface because the index is what every later record is
    read by: a selection that rendered the right bytes while reporting position
    zero would read, afterwards, exactly like a dispatch that never fell back.
    The pair of rows is what makes either able to fail -- an implementation
    hard-coding one index satisfies exactly one of them.
    """
    _assert_slice_exists()
    selection = _module(name="_acp_node_selection")
    assert "select_acp_candidates" in selection.__all__, sorted(selection.__all__)
    repo = _repo(tmp_path=tmp_path, acp_nodes={_NODE: _chained_entry()})
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key=hold_key),))
    chains = _chains(repo=repo)

    selected = selection.select_acp_candidates(chains=chains, verdict=verdict)

    assert not isinstance(selected, str), selected
    one = selected[_NODE]
    assert one.index == index
    assert one.candidate.identity is not None
    assert one.candidate.identity.candidate_key == candidate_key
    assert one.full_chain == chains[_NODE].full_chain
    assert one.primary_generation == chains[_NODE].primary_generation
    assert one.selection_identity != ""


def test_a_selection_that_splits_a_shared_workflow_input_refuses(tmp_path: Path) -> None:
    """One workflow input cannot carry two adapters, selected or resolved.

    A four-input workflow shares `acp_adapter` across `implement`, `fix` and
    `review_fix`, so moving ONE of them to a fallback leaves that input with two
    values. The dispatch refuses naming the input, exactly as the first
    rendering does -- silently picking a winner would send the run an adapter
    nobody selected while the journal reported the one that was.

    All three nodes are configured IDENTICALLY so the first rendering succeeds:
    a configuration that already split the input would refuse before any
    selection ran, and this case would then prove nothing about the second
    rendering. Only `implement` carries a fallback, so only it moves.
    """
    _assert_slice_exists()
    repo = _repo(
        tmp_path=tmp_path,
        acp_nodes={
            _NODE: _chained_entry(),
            "fix": _primary_entry(),
            "review_fix": _primary_entry(),
        },
    )
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    _ = (workflow / "workflow.toml").write_text(
        _WORKFLOW_TOML.replace("implement_adapter =", "acp_adapter ="), encoding="utf-8"
    )
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    refusal = _prepare(repo=repo, verdict=verdict, journal=_RecordingJournal())

    assert isinstance(refusal, str), refusal
    assert "acp_adapter" in refusal


def test_one_selection_identity_is_stable_across_two_resolutions(tmp_path: Path) -> None:
    """The identity is a function of the selection, not of the moment it was taken.

    Two resolutions of one unchanged repository must produce the SAME identity,
    or nothing downstream can recognize two dispatches as having selected the
    same thing; and a selection of a DIFFERENT position must produce a different
    one, or the identity names nothing.
    """
    _assert_slice_exists()
    selection = _module(name="_acp_node_selection")
    repo = _repo(tmp_path=tmp_path, acp_nodes={_NODE: _chained_entry()})
    unheld = _verdict(repo=repo, holds=())
    held = _verdict(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))
    chains = _chains(repo=repo)

    first = selection.select_acp_candidates(chains=chains, verdict=unheld)
    second = selection.select_acp_candidates(chains=_chains(repo=repo), verdict=unheld)
    other = selection.select_acp_candidates(chains=chains, verdict=held)

    assert not isinstance(first, str), first
    assert not isinstance(second, str), second
    assert not isinstance(other, str), other
    assert first[_NODE].selection_identity == second[_NODE].selection_identity
    assert first[_NODE].selection_identity != other[_NODE].selection_identity
