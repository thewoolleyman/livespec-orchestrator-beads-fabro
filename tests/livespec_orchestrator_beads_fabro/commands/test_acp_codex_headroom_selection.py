"""The per-node ACP selection record names a Codex headroom skip as one.

Binds the second Definition-of-Done assertion of the Codex-headroom work-item to
"Admission filters Codex candidates by projected usage-window headroom" in
`SPECIFICATION/contracts.md` and Scenario 243: a dispatch whose Codex primary is
skipped for headroom selects the next eligible candidate in configured order, and
its `acp-node-selection` record names the skip by its kind -- a Codex limit skip,
a floor skip or a projection skip -- and names the provider as `codex`.

The record is produced through the PRODUCTION path (`prepare_acp_nodes`) over a
real repository fixture, so the shape asserted here is the one the Dispatcher
journals and not one a unit built for the purpose.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom as codex
from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom_projection as projection
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NODE = "implement"
_ITEM = "bd-ib-4jdgcw"
_NOW = "2026-10-28T06:00:00Z"
_FLOOR = 20
_HORIZON = 180
_CODEX_DOMAIN = "openai-subscription"
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


class _RecordingJournal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _codex_primary() -> dict[str, Any]:
    return {
        "agent": "codex-acp",
        "model": "gpt-5.5",
        "effort": "high",
        "availability_key": _CODEX_DOMAIN,
        "candidate_key": "gpt-5.5",
        "display_name": "GPT 5.5",
    }


def _claude_fallback() -> dict[str, Any]:
    return {
        "agent": "claude-acp",
        "model": "claude-opus-5",
        "effort": "high",
        "availability_key": _CLAUDE_DOMAIN,
        "candidate_key": "claude-opus-5",
        "display_name": "Claude Opus 5",
    }


def _uncovered_review() -> dict[str, Any]:
    return {
        "display_name": "Review adapter",
        "candidate_key": "review-model",
        "availability_key": "review-domain",
        "command": "review-acp",
        "args": ["--stdio"],
        "env": {"REVIEW_BASE_URL": "https://review.example"},
    }


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_WORKFLOW_GRAPH, encoding="utf-8")
    acp_nodes = {
        _NODE: {**_codex_primary(), "fallbacks": [_claude_fallback()]},
        "review": _uncovered_review(),
    }
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


def _codex_response(*, secondary_used: float | None = None, **limits: object) -> dict[str, Any]:
    secondary = (
        None
        if secondary_used is None
        else {"used_percent": secondary_used, "limit_window_seconds": 604800}
    )
    return {
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {"used_percent": 10, "limit_window_seconds": 18000},
            "secondary_window": secondary,
            **limits,
        }
    }


def _policy(*, reading: codex.CodexHeadroomReading) -> headroom.SessionHeadroomPolicy:
    untouched = headroom.session_headroom_reading(
        credential_identity="claude-cred", observed_at=_NOW, utilization=0
    )
    return headroom.SessionHeadroomPolicy(
        floor_percent=_FLOOR,
        horizon_minutes=_HORIZON,
        read=lambda: untouched,
        codex_read=lambda: reading,
    )


def _selection(*, tmp_path: Path, reading: codex.CodexHeadroomReading) -> dict[str, Any]:
    repo = _repo(tmp_path=tmp_path)
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")
    ledger_module = _module(name="_acp_hold_ledger")
    preflight = _module(name="_acp_candidate_preflight")
    verdicts = _module(name="_acp_preflight_verdict")
    nodes = _module(name="_dispatcher_acp_nodes")
    selection = _module(name="_acp_node_selection")

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
    verdict = verdicts.build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger_module.AcpHoldLedger(holds=(), unobservable=(), observation_ids=frozenset()),
        inputs=preflight.PreflightInputs(
            builtin_pairs=builtin_pairs, headroom=_policy(reading=reading)
        ),
    )
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
    chosen: Any = matching[0]["selections"]
    return chosen[_NODE]


def _graded(**limits: object) -> codex.CodexHeadroomReading:
    return codex.codex_headroom_reading(
        credential_identity="codex-cred", observed_at=_NOW, response=_codex_response(**limits)
    )


def test_a_codex_limit_skip_selects_the_fallback_and_is_named_as_a_codex_skip(
    tmp_path: Path,
) -> None:
    chosen = _selection(tmp_path=tmp_path, reading=_graded(limit_reached=True))

    assert chosen["selected_index"] == 1
    assert chosen["selected_agent_id"] == "claude-acp"
    assert chosen["selected_candidate_key"] == "claude-opus-5"
    assert chosen["holds"] == []
    assert chosen["probe_skips"] == []
    assert len(chosen["headroom_skips"]) == 1
    skip = chosen["headroom_skips"][0]
    assert skip.get("headroom_provider") == "codex"
    assert skip["headroom_skip_kind"] == "codex-limit"
    assert skip["availability_key"] == _CODEX_DOMAIN
    assert skip["candidate_key"] == "gpt-5.5"
    assert skip["session_headroom_floor_percent"] == _FLOOR
    assert skip["session_headroom_horizon_minutes"] == _HORIZON


def test_a_floor_skip_is_named_by_its_kind_and_provider(tmp_path: Path) -> None:
    primary = {"used_percent": 85, "limit_window_seconds": 18000}

    chosen = _selection(tmp_path=tmp_path, reading=_graded(primary_window=primary))

    skip = chosen["headroom_skips"][0]
    assert skip.get("headroom_provider") == "codex"
    assert skip["headroom_skip_kind"] == "floor"
    assert chosen["selected_agent_id"] == "claude-acp"


def test_a_projection_skip_names_the_window_that_governed(tmp_path: Path) -> None:
    graded = _graded(secondary_window={"used_percent": 60, "limit_window_seconds": 604800})
    baseline = SessionHeadroomBaseline(
        utilization_percent=30.0, observed_at="2026-10-28T05:00:00Z", elapsed_hours=1.0
    )
    reading = projection.assessed_codex_reading(
        reading=graded,
        baselines={604800: baseline},
        floor_percent=_FLOOR,
        horizon_minutes=_HORIZON,
    )

    chosen = _selection(tmp_path=tmp_path, reading=reading)

    skip = chosen["headroom_skips"][0]
    assert skip.get("headroom_provider") == "codex"
    assert skip["headroom_skip_kind"] == "projection"
    assert skip.get("projection_window_seconds") == 604800
    assert chosen["selected_agent_id"] == "claude-acp"


def test_a_codex_primary_that_passes_is_selected_with_no_headroom_skip(tmp_path: Path) -> None:
    chosen = _selection(tmp_path=tmp_path, reading=_graded())

    assert chosen["selected_index"] == 0
    assert chosen["selected_agent_id"] == "codex-acp"
    assert chosen["headroom_skips"] == []
