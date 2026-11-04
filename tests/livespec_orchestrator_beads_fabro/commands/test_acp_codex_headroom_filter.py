"""Admission skips a covered Codex candidate whose window projects exhaustion.

Binds the first Definition-of-Done assertion of the Codex-headroom work-item to
"Admission filters Codex candidates by projected usage-window headroom" in
`SPECIFICATION/contracts.md` and to `SPECIFICATION/scenarios.md` Scenario 243:
before claim the Dispatcher assesses every otherwise-selectable `codex-acp`
candidate against the usage window of the credential the dispatch would project,
and a candidate whose projected exhaustion falls inside the admission horizon
leaves the selectable set.

THE CONTROLS ARE THE MIRROR IMAGES OF THE MISTAKES. A slow drain keeps the
candidate (a projection that always skipped would pass the main case), a Claude
candidate is never assessed by the Codex read, and a Codex candidate is never
assessed by the Claude read -- asserted by counting the reads.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    CLAUDE_AGENT_ID,
    CODEX_AGENT_ID,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_NOW = "2026-10-28T06:00:00Z"
_BASELINE_AT = "2026-10-28T05:00:00Z"
_IDENTITY = "codex-credential"
_WINDOW_SECONDS = 18000
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._acp_codex_headroom"


def _codex_module() -> ModuleType:
    path = Path(headroom.__file__).with_name("_acp_codex_headroom.py")
    assert path.is_file()
    return importlib.import_module(_MODULE_NAME)


def _candidate(*, agent_id: str, availability_key: str, candidate_key: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command=f"{agent_id}-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=f"{availability_key}/{candidate_key}",
            candidate_key=candidate_key,
            availability_key=availability_key,
        ),
        agent_id=agent_id,
    )


def _chain() -> ResolvedAcpChain:
    primary = _candidate(
        agent_id=CODEX_AGENT_ID, availability_key="openai-account", candidate_key="gpt-6"
    )
    fallback = _candidate(
        agent_id=CLAUDE_AGENT_ID, availability_key="anthropic-account", candidate_key="opus"
    )
    return ResolvedAcpChain(
        node="implement",
        primary=primary,
        fallbacks=(fallback,),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _journal_baseline(*, path: Path, used_percent: float, window_seconds: int) -> Path:
    record = {
        "stage": "acp-codex-session-headroom",
        "work_item_id": "bd-ib-4jdgcw",
        "assessments": [
            {
                "credential_identity": _IDENTITY,
                "observed_at": _BASELINE_AT,
                "windows": [
                    {
                        "name": "primary",
                        "limit_window_seconds": window_seconds,
                        "used_percent": used_percent,
                    }
                ],
            }
        ],
    }
    _ = path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return path


def _response(*, used_percent: float) -> dict[str, Any]:
    return {
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": used_percent,
                "limit_window_seconds": _WINDOW_SECONDS,
            },
            "secondary_window": None,
        }
    }


def _filtered(
    *, tmp_path: Path, baseline_percent: float, used_percent: float, reads: list[str]
) -> preflight.NodePreflight:
    codex = _codex_module()
    journal = _journal_baseline(
        path=tmp_path / "journal.jsonl",
        used_percent=baseline_percent,
        window_seconds=_WINDOW_SECONDS,
    )

    def _claude_read(*, token: str | None, observed_at: str) -> Any:
        _ = token
        reads.append("claude")
        return headroom.session_headroom_reading(
            credential_identity="claude-credential", observed_at=observed_at, utilization=0
        )

    def _codex_read(*, auth_json: str | None, observed_at: str) -> Any:
        _ = auth_json
        reads.append("codex")
        return codex.codex_headroom_reading(
            credential_identity=_IDENTITY,
            observed_at=observed_at,
            response=_response(used_percent=used_percent),
        )

    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path,
        now_iso=_NOW,
        journal_path=journal,
        read=_claude_read,
        codex_read=_codex_read,
    )
    return preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(headroom=policy),
        assessed={},
    )


def test_a_codex_primary_projecting_exhaustion_inside_the_horizon_is_skipped(
    tmp_path: Path,
) -> None:
    reads: list[str] = []

    node = _filtered(tmp_path=tmp_path, baseline_percent=30.0, used_percent=60.0, reads=reads)

    assert [candidate.agent_id for candidate in node.candidates] == [CLAUDE_AGENT_ID]
    assert len(node.skipped) == 1
    skip = node.skipped[0]
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.headroom_skip_kind == preflight.PROJECTION_SKIP_KIND
    assert skip.headroom is None
    assert skip.codex_headroom is not None
    assert skip.codex_headroom.credential_identity == _IDENTITY
    window = skip.codex_headroom.windows[0]
    assert window.limit_window_seconds == _WINDOW_SECONDS
    assert window.drain_percent_per_hour == 30.0
    assert window.projection is not None
    assert window.projection.result == headroom.PROJECTED_RESULT
    assert window.projection.skip_applied is True
    assert node.codex_assessments == (skip.codex_headroom,)


def test_a_codex_primary_draining_slowly_stays_selectable(tmp_path: Path) -> None:
    reads: list[str] = []

    node = _filtered(tmp_path=tmp_path, baseline_percent=30.0, used_percent=31.0, reads=reads)

    assert [candidate.agent_id for candidate in node.candidates] == [
        CODEX_AGENT_ID,
        CLAUDE_AGENT_ID,
    ]
    assert node.skipped == ()
    assert len(node.codex_assessments) == 1


def test_each_candidate_is_assessed_by_its_own_providers_read_exactly_once(
    tmp_path: Path,
) -> None:
    reads: list[str] = []

    _ = _filtered(tmp_path=tmp_path, baseline_percent=30.0, used_percent=31.0, reads=reads)

    assert sorted(reads) == ["claude", "codex"]
