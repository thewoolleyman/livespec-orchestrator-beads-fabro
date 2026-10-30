"""Admission picks the factory credential from the whole injected slot pool.

Binds Scenario 278 in `SPECIFICATION/scenarios.md`. The caam loop publishes
"anthropic-2" for interactive spend, yet the factory dispatch takes the
best-qualifying injected slot, journals the chosen and every rejected slot with
its reason, refuses with the existing headroom outcome only when no slot
qualifies, and never writes the caam record.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission_eligibility as eligibility_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_pool as pool_module,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    SELECTED_ACCOUNT_RECORD_REL,
    injected_credential_slots,
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-30T22:00:00Z"
_PREFIX = "CLAUDE_CODE_OAUTH_TOKEN__"
_SLOT_2 = f"{_PREFIX}ANTHROPIC_2"
_SLOT_3 = f"{_PREFIX}ANTHROPIC_3"
_SLOT_4 = f"{_PREFIX}ANTHROPIC_4"
_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_GRAPH = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    implement [backend="acp", acp.command="a"]
    start -> implement
    implement -> exit
"""


def _publish_caam_selection(*, home: Path, profile: str) -> bytes:
    record = home / SELECTED_ACCOUNT_RECORD_REL
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"profile": profile}), encoding="utf-8")
    return record.read_bytes()


def _inject(*, monkeypatch: pytest.MonkeyPatch, home: Path, slots: dict[str, str]) -> None:
    monkeypatch.setenv("HOME", str(home))
    for name, token in slots.items():
        monkeypatch.setenv(name, token)


def _reader(
    *, utilization_by_token: dict[str, float | None], reset_by_token: dict[str, str] | None = None
) -> Any:
    resets = reset_by_token or {}

    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        identity = f"id-{token}"
        utilization = utilization_by_token.get(token or "")
        if utilization is None:
            return headroom.unobservable_session_headroom(
                credential_identity=identity, observed_at=observed_at, reason="transport-failed"
            )
        return headroom.session_headroom_reading(
            credential_identity=identity,
            observed_at=observed_at,
            utilization=utilization,
            provider_reset_claim=resets.get(token or ""),
        )

    return _read


def _verdict(*, policy: headroom.SessionHeadroomPolicy) -> AcpPreflightVerdict:
    candidate = AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name="claude",
            candidate_key=_PAIR[1],
            availability_key=_PAIR[0],
        ),
    )
    chain = ResolvedAcpChain(
        node="implement",
        primary=candidate,
        fallbacks=(),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )
    return build_acp_preflight_verdict(
        chains={"implement": chain},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(
            holds=(), builtin_pairs=frozenset({_PAIR}), headroom=policy
        ),
    )


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _ready_item() -> WorkItem:
    return WorkItem(
        id="bd-ib-ready",
        type="task",
        status="ready",
        title="Task",
        description="Do it.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy=None,
        acceptance_policy=None,
    )


def _run_admission(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verdict: AcpPreflightVerdict,
    policy: headroom.SessionHeadroomPolicy,
) -> tuple[admission_module.Admission, list[dict[str, Any]], list[dict[str, object]]]:
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(admission_module, "resolve_acp_preflight", lambda **_: verdict)
    monkeypatch.setattr(admission_module, "session_headroom_policy", lambda **_: policy)
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(
        admission_module,
        "update_work_item_status",
        lambda **kwargs: writes.append(dict(kwargs)),
    )
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    journal_path = tmp_path / "journal.jsonl"
    admission = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_ready_item()],
        journal=JournalFile(path=journal_path),
        enforce_cap=False,
    )
    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return admission, records, writes


def _slot_rows(*, assessments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["slot"]["name"]: row["slot"] for row in assessments}


def test_admission_projects_the_qualifying_slot_not_the_caam_selected_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    caam_bytes = _publish_caam_selection(home=tmp_path, profile="anthropic-2")
    _inject(
        monkeypatch=monkeypatch,
        home=tmp_path,
        slots={_SLOT_2: "tok-2", _SLOT_3: "tok-3", "CLAUDE_CODE_OAUTH_TOKEN": "legacy"},
    )
    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path,
        now_iso=_NOW,
        journal_path=None,
        read=_reader(utilization_by_token={"tok-2": 90, "tok-3": 0}),
    )
    verdict = _verdict(policy=policy)

    admission, records, writes = _run_admission(
        tmp_path=tmp_path, monkeypatch=monkeypatch, verdict=verdict, policy=policy
    )
    choice = select_factory_credential(environ=dict(os.environ), home=tmp_path, warn=print)

    assert verdict.viable
    assert [item.id for item in admission.admitted] == ["bd-ib-ready"]
    assert choice.env_name == _SLOT_3
    assert choice.fallback_reason is None
    [row] = [record for record in records if record["stage"] == SESSION_HEADROOM_STAGE]
    slots = _slot_rows(assessments=row["assessments"])
    assert slots[_SLOT_3] == {
        "name": _SLOT_3,
        "skip_kind": None,
        "chosen": True,
        "not_chosen_reason": None,
    }
    assert slots[_SLOT_2]["not_chosen_reason"] == "floor-skip"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in slots
    assert [write["status"] for write in writes] == ["active"]
    assert (tmp_path / SELECTED_ACCOUNT_RECORD_REL).read_bytes() == caam_bytes


def test_two_qualifying_slots_through_admission_choose_the_sooner_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _inject(
        monkeypatch=monkeypatch,
        home=tmp_path,
        slots={_SLOT_3: "tok-3", _SLOT_4: "tok-4"},
    )
    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path,
        now_iso=_NOW,
        journal_path=None,
        read=_reader(
            utilization_by_token={"tok-3": 10, "tok-4": 30},
            reset_by_token={"tok-3": "1761814400", "tok-4": "1761804000"},
        ),
    )

    chosen = policy.read()
    pooled = policy.pool_read() if policy.pool_read is not None else ()

    assert chosen.slot is not None
    assert chosen.slot.slot == _SLOT_4
    loser = next(
        reading.slot for reading in pooled if reading.slot and reading.slot.slot == _SLOT_3
    )
    assert loser is not None
    assert loser.not_chosen_reason == pool_module.RANKED_LOWER_LATER_RESET
    environ = {_SLOT_3: "tok-3", _SLOT_4: "tok-4"}
    assert select_factory_credential(environ=environ, home=tmp_path, warn=print).env_name == _SLOT_4


def test_no_qualifying_slot_refuses_with_the_headroom_outcome_naming_every_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _inject(
        monkeypatch=monkeypatch,
        home=tmp_path,
        slots={_SLOT_2: "tok-2", _SLOT_3: "tok-3", _SLOT_4: "tok-4"},
    )
    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path,
        now_iso=_NOW,
        journal_path=None,
        read=_reader(utilization_by_token={"tok-2": 85, "tok-3": None, "tok-4": 95}),
    )
    verdict = _verdict(policy=policy)

    admission, records, writes = _run_admission(
        tmp_path=tmp_path, monkeypatch=monkeypatch, verdict=verdict, policy=policy
    )

    assert not verdict.viable
    assert admission.admitted == []
    assert writes == []
    refusal = next(record for record in records if record["stage"] == ACP_PREFLIGHT_REFUSAL_STAGE)
    slots = _slot_rows(assessments=refusal["session_headroom_assessments"])
    assert {name: row["skip_kind"] for name, row in slots.items()} == {
        _SLOT_2: "floor",
        _SLOT_3: "floor",
        _SLOT_4: "floor",
    }
    assert all(row["chosen"] is False for row in slots.values())
    unobservable = [reading["unobservable"] for reading in refusal["session_headroom_assessments"]]
    assert "transport-failed" in unobservable
    assert refusal["session_headroom_skipped"]["implement"]
    environ = {_SLOT_2: "tok-2", _SLOT_3: "tok-3", _SLOT_4: "tok-4"}
    assert select_factory_credential(environ=environ, home=tmp_path, warn=print).env_name != _SLOT_3


def test_a_pool_with_no_injected_slot_reads_one_absent_credential(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    tokens: list[str | None] = []

    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        tokens.append(token)
        return headroom.unobservable_session_headroom(
            credential_identity="absent", observed_at=observed_at, reason="absent-credential"
        )

    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=None, read=_read
    )

    assert policy.read().slot is None
    assert tokens == [None]


def test_the_unnumbered_token_is_the_pool_only_when_no_numbered_slot_is_injected() -> None:
    legacy = "CLAUDE_CODE_OAUTH_TOKEN"

    assert injected_credential_slots(environ={legacy: "t", _SLOT_3: "x", _SLOT_2: "y"}) == (
        _SLOT_2,
        _SLOT_3,
    )
    assert injected_credential_slots(environ={legacy: "t", _SLOT_3: ""}) == (legacy,)
    assert injected_credential_slots(environ={legacy: "", _SLOT_3: ""}) == ()


def test_a_chooser_naming_a_slot_that_is_no_longer_injected_falls_back_to_the_caam_record(
    tmp_path: Path,
) -> None:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
        register_admission_slot_chooser,
    )

    _publish_caam_selection(home=tmp_path, profile="anthropic-2")
    environ = {_SLOT_2: "tok-2", _SLOT_3: "tok-3"}
    register_admission_slot_chooser(chooser=lambda: f"{_PREFIX}ANTHROPIC_9")
    stale = select_factory_credential(environ=environ, home=tmp_path, warn=print)
    register_admission_slot_chooser(chooser=lambda: None)
    unchosen = select_factory_credential(environ=environ, home=tmp_path, warn=print)

    assert stale.env_name == _SLOT_2
    assert unchosen.env_name == _SLOT_2


@pytest.mark.parametrize("claim", ["nan", "not-a-reset", None])
def test_an_unreadable_reset_claim_ranks_after_a_readable_one(claim: str | None) -> None:
    def _qualifying(*, identity: str, reset: str | None) -> headroom.SessionHeadroomReading:
        return headroom.session_headroom_reading(
            credential_identity=identity,
            observed_at=_NOW,
            utilization=5,
            provider_reset_claim=reset,
        )

    selection = pool_module.select_pool_slot(
        readings=(
            (_SLOT_2, _qualifying(identity="id2", reset=claim)),
            (_SLOT_3, _qualifying(identity="id3", reset="1761814400")),
        ),
        floor_percent=20,
    )

    assert selection.chosen_slot == _SLOT_3
