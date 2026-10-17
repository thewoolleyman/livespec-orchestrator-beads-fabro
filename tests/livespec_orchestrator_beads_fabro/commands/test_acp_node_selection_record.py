"""The per-node SELECTION record one dispatch journals, and what it must carry.

Binds the "Per-node selection" paragraph of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": "Selection is made once per
dispatch from one consistent read of the availability evidence and is journaled
per node with a stable selection identity, the selected candidate index and
identity, the full-chain digest, the primary-generation fingerprint, and the
holds that skipped earlier candidates", together with the sentence that follows
it: "When headroom skips an earlier candidate, the selection record MUST
identify that candidate, reference its headroom assessment, governing floor and
governing horizon ... it MUST NOT represent that skip as an observed hold."

THE INDEX AND THE SKIPS ARE ONE CLAIM, NOT TWO. The record's whole job is to let
a reader reconstruct why this dispatch ran the candidate it ran, and an index of
1 with an empty skip list explains nothing. So every case below asserts the
position AND the reason it moved, and the node that did NOT move asserts an
EMPTY skip list rather than being absent -- a reader cannot tell an absent node
from a node that was never selected.

A HEADROOM SKIP IS ASSERTED TO BE ABSENT FROM `holds`, which is the clause's own
prohibition and is the direction an almost-correct implementation gets wrong. A
shortfall in a usage window is not an observed provider outage; recording it as
one would invite a reader to join it against the availability-hold ledger, where
it matches nothing, and would make a credential that is merely busy
indistinguishable from an entitlement a provider refused.

EXACTLY ONE RECORD PER DISPATCH is asserted by counting, not by indexing. A
dispatch that journaled one record per node would satisfy every field assertion
below while making "which candidate did this dispatch select" a question whose
answer is spread across rows a reader has to collate.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NODE = "implement"
_ITEM = "bd-ib-wvj4rk"
_NOW = "2026-10-16T12:00:00Z"
_FLOOR = 20
_HORIZON = 180

_PRIMARY_DOMAIN = "primary-domain"
_PRIMARY_KEY = "primary-model"
_FALLBACK_DOMAIN = "fallback-domain"
_FALLBACK_KEY = "fallback-model"
_CLAUDE_DOMAIN = "claude-subscription"

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "npx -y claude-acp"
review_adapter = "npx -y claude-acp"

[run.environment]
id = "livespec-ci"
"""

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


def _assert_record_surface() -> None:
    """Prove the names this slice introduces are DECLARED before reaching for them.

    Run FIRST in every case so the Red fails on a genuine assertion rather than
    on an attribute lookup. This package requires every module to enumerate its
    public surface in `__all__`, so a record stage reachable only as an
    undeclared attribute is not a surface the Dispatcher may wire.

    THE SKIP PROJECTION IS ASSERTED BEFORE THE SELECTION MODULE IS REACHED FOR.
    The selection record and the headroom surfaces must describe one skip
    through ONE projection -- two spellings of these keys is how one surface
    comes to report `session_headroom_floor_percent` while another reports
    `floor` and no reader can join them -- so the selection module imports that
    projection BY NAME, and a projection that is private or renamed takes the
    whole package's import graph down rather than failing any assertion here.
    Asking the records module first is what names the missing surface for
    whoever does reach this case, and it states which module owns the key the
    two surfaces share.
    """
    records = _module(name="_acp_session_headroom_records")
    assert "session_headroom_skip_fields" in records.__all__, sorted(records.__all__)
    selection = _module(name="_acp_node_selection")
    headroom = _module(name="_acp_session_headroom")
    assert "ACP_NODE_SELECTION_STAGE" in selection.__all__, sorted(selection.__all__)
    assert "acp_node_selection_record" in selection.__all__, sorted(selection.__all__)
    assert "DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES" in headroom.__all__, sorted(headroom.__all__)


class _RecordingJournal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _manual_primary() -> dict[str, Any]:
    return {
        "display_name": "Primary adapter",
        "candidate_key": _PRIMARY_KEY,
        "availability_key": _PRIMARY_DOMAIN,
        "command": "primary-acp",
        "args": ["--stdio"],
        "env": {"PRIMARY_BASE_URL": "https://primary.example"},
    }


def _manual_fallback() -> dict[str, Any]:
    return {
        "display_name": "Fallback adapter",
        "candidate_key": _FALLBACK_KEY,
        "availability_key": _FALLBACK_DOMAIN,
        "command": "fallback-acp",
        "args": ["--stdio"],
        "env": {"FALLBACK_BASE_URL": "https://fallback.example"},
    }


def _claude_primary() -> dict[str, Any]:
    """A STRUCTURED `claude-acp` primary, which is what headroom covers.

    Coverage follows resolved agent provenance, so the structured form is the
    only way to put a covered candidate at position zero without borrowing a
    built-in's rendered bytes.
    """
    return {
        "agent": "claude-acp",
        "model": "claude-opus-5",
        "effort": "high",
        "availability_key": _CLAUDE_DOMAIN,
        "candidate_key": "claude-opus-5",
        "display_name": "Claude Opus 5",
    }


def _repo(*, tmp_path: Path, acp_nodes: dict[str, Any]) -> Path:
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


def _domain_hold(*, hold_key: str) -> Any:
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


def _headroom_policy(*, utilization: object = 90) -> Any:
    headroom = _module(name="_acp_session_headroom")
    reading = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=utilization
    )
    return headroom.SessionHeadroomPolicy(
        floor_percent=_FLOOR, horizon_minutes=_HORIZON, read=lambda: reading
    )


def _verdict(*, repo: Path, holds: tuple[Any, ...] = (), headroom: Any = None) -> Any:
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")
    ledger_module = _module(name="_acp_hold_ledger")
    preflight = _module(name="_acp_candidate_preflight")
    verdicts = _module(name="_acp_preflight_verdict")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = sources.repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, graph_text, builtin_pairs = resolved
    return verdicts.build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger_module.AcpHoldLedger(
            holds=holds, unobservable=(), observation_ids=frozenset()
        ),
        inputs=preflight.PreflightInputs(
            holds=holds, builtin_pairs=builtin_pairs, headroom=headroom
        ),
    )


def _selection_record(*, repo: Path, verdict: Any) -> dict[str, Any]:
    """The ONE record this dispatch journals under the selection stage."""
    nodes = _module(name="_dispatcher_acp_nodes")
    selection = _module(name="_acp_node_selection")
    journal = _RecordingJournal()
    resolution = nodes.prepare_acp_nodes(
        repo=repo,
        committed=repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml",
        overrides=(),
        journal=journal,
        work_item_id=_ITEM,
        verdict=verdict,
    )
    assert not isinstance(resolution, str), resolution
    matching = [
        record
        for record in journal.records
        if record.get("stage") == selection.ACP_NODE_SELECTION_STAGE
    ]
    assert len(matching) == 1, journal.records
    return matching[0]


def test_one_record_names_the_selected_position_identity_and_both_digests(
    tmp_path: Path,
) -> None:
    """The record a reader reconstructs the dispatch's choice from."""
    _assert_record_surface()
    repo = _repo(
        tmp_path=tmp_path,
        acp_nodes={_NODE: {**_manual_primary(), "fallbacks": [_manual_fallback()]}},
    )
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    record = _selection_record(repo=repo, verdict=verdict)

    assert record["work_item_id"] == _ITEM
    selections: Any = record["selections"]
    chosen = selections[_NODE]
    assert chosen["selected_index"] == 1
    assert chosen["selected_availability_key"] == _FALLBACK_DOMAIN
    assert chosen["selected_candidate_key"] == _FALLBACK_KEY
    assert chosen["selection_identity"]
    assert chosen["primary_generation_digest"]
    assert chosen["full_chain_digest"]
    assert chosen["primary_generation_digest"] != chosen["full_chain_digest"]


def test_the_record_names_the_hold_that_skipped_the_earlier_candidate(
    tmp_path: Path,
) -> None:
    """ "the holds that skipped earlier candidates", with their typed cause."""
    _assert_record_surface()
    repo = _repo(
        tmp_path=tmp_path,
        acp_nodes={_NODE: {**_manual_primary(), "fallbacks": [_manual_fallback()]}},
    )
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    record = _selection_record(repo=repo, verdict=verdict)

    selections: Any = record["selections"]
    assert selections[_NODE]["holds"] == [
        {
            "availability_key": _PRIMARY_DOMAIN,
            "candidate_key": _PRIMARY_KEY,
            "reason": "typed-availability-hold",
            "cause": "quota",
            "scope": "availability-domain",
            "hold_key": _PRIMARY_DOMAIN,
        }
    ]


def test_a_node_that_did_not_move_reports_position_zero_and_no_skips(
    tmp_path: Path,
) -> None:
    """The negative node is present with empty lists rather than absent.

    A reader cannot tell an absent node from one that was never selected, and
    "which nodes moved" is the question the record exists to answer.
    """
    _assert_record_surface()
    repo = _repo(
        tmp_path=tmp_path,
        acp_nodes={_NODE: {**_manual_primary(), "fallbacks": [_manual_fallback()]}},
    )
    verdict = _verdict(repo=repo, holds=(_domain_hold(hold_key="some-unrelated-domain"),))

    record = _selection_record(repo=repo, verdict=verdict)

    selections: Any = record["selections"]
    chosen = selections[_NODE]
    assert chosen["selected_index"] == 0
    assert chosen["selected_candidate_key"] == _PRIMARY_KEY
    assert chosen["holds"] == []
    assert chosen["headroom_skips"] == []
    assert "review" in selections


def test_a_headroom_skip_carries_its_assessment_floor_and_horizon(tmp_path: Path) -> None:
    """A usage-window shortfall is recorded as a headroom skip, never as a hold.

    The reading, the governing floor and the governing horizon travel together
    because none of the three is interpretable without the other two: the same
    10 percent remaining is a skip under a floor of 20 and ample under a floor
    of 5, and the horizon is the committed dial a reader of an old journal line
    cannot recover from the repository as it now stands.

    THE SKIP KIND RIDES WITH THEM because the two shortfalls are not exclusive:
    a reading can sit below the floor AND project an exhaustion inside the
    horizon, so the dials alone cannot say which test actually stopped the
    candidate. Asserting it HERE is also what proves the selection record and
    the headroom surfaces describe one skip through one projection rather than
    through two that agree today.
    """
    _assert_record_surface()
    repo = _repo(
        tmp_path=tmp_path,
        acp_nodes={
            _NODE: {**_claude_primary(), "fallbacks": [_manual_fallback()]},
            # `review` is configured with an uncovered manual adapter rather than
            # left at its workflow default: every workflow default is registered
            # as a BUILT-IN Claude adapter, so an unconfigured node would be
            # headroom-covered too, its single-candidate chain would empty, and
            # the dispatch would refuse before any record was written. Admission
            # refuses such an item before claim; this case is about the record a
            # SURVIVING chain leaves behind.
            "review": _manual_primary(),
        },
    )
    verdict = _verdict(repo=repo, headroom=_headroom_policy())

    record = _selection_record(repo=repo, verdict=verdict)

    selections: Any = record["selections"]
    chosen = selections[_NODE]
    assert chosen["selected_index"] == 1
    assert chosen["selected_candidate_key"] == _FALLBACK_KEY
    assert chosen["holds"] == []
    assert chosen["headroom_skips"] == [
        {
            "availability_key": _CLAUDE_DOMAIN,
            "candidate_key": "claude-opus-5",
            "session_headroom_floor_percent": _FLOOR,
            "session_headroom_horizon_minutes": _HORIZON,
            "headroom_skip_kind": "floor",
            "headroom": {
                "credential_identity": "cred-1",
                "utilization_percent": 90.0,
                "remaining_percent": 10.0,
                "unobservable": None,
                "observed_at": _NOW,
                "five_hour_drain_percent_per_hour": None,
                "projection": None,
                "unverified_provider_reset_claim": None,
            },
        }
    ]


def test_a_probe_refusal_is_recorded_as_its_own_ephemeral_skip(tmp_path: Path) -> None:
    """A credential-probe refusal explains its position without inventing a hold.

    It is neither a durable observation nor a usage reading, so it carries the
    probe CONDITION and no typed availability cause. Without a record of it the
    selected index would jump with nothing in the journal accounting for the
    candidate it passed over.
    """
    _assert_record_surface()
    repo = _repo(
        tmp_path=tmp_path,
        acp_nodes={_NODE: {**_manual_primary(), "fallbacks": [_manual_fallback()]}},
    )
    verdict = _verdict_with_probe(repo=repo)

    record = _selection_record(repo=repo, verdict=verdict)

    selections: Any = record["selections"]
    chosen = selections[_NODE]
    assert chosen["selected_index"] == 1
    assert chosen["holds"] == []
    assert chosen["headroom_skips"] == []
    assert chosen["probe_skips"] == [
        {
            "availability_key": _PRIMARY_DOMAIN,
            "candidate_key": _PRIMARY_KEY,
            "condition": "exhausted",
        }
    ]


def _verdict_with_probe(*, repo: Path) -> Any:
    """A verdict whose probe refuses the PRIMARY's credential alone.

    Keyed on the availability key rather than returning one answer for every
    candidate, because a probe that refused everything would empty the chain and
    the dispatch would refuse before any record was written.
    """
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")
    ledger_module = _module(name="_acp_hold_ledger")
    preflight = _module(name="_acp_candidate_preflight")
    verdicts = _module(name="_acp_preflight_verdict")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = sources.repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, graph_text, builtin_pairs = resolved
    return verdicts.build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger_module.AcpHoldLedger(holds=(), unobservable=(), observation_ids=frozenset()),
        inputs=preflight.PreflightInputs(
            builtin_pairs=builtin_pairs,
            probe=lambda key: "exhausted" if key == _PRIMARY_DOMAIN else "usable",
        ),
    )
