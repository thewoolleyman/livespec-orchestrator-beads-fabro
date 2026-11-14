"""A pool slot named by a live provider-exhaustion record is not chosen.

Binds bd-ib-wx4yha's slot-selection assertions. Measured 2026-11-14 on the
petri factory: session-headroom admission chose CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_0
for all eleven admissions from 05:09Z to 07:21Z, because its five-hour window
reset soonest. Its account had hit the organisation's monthly spend limit, every
run on it died at its first Claude node, and the dispatcher had already journaled
`provider-exhaustion-observed` records naming that slot's credential identity.
The ranking read only the provider's rate windows, so the record could refuse a
dispatch but never move admission to another slot, while two other slots sat at
1 and 0 percent seven-day utilization.

The records here are written to a real journal file and read back through the
gate, so the test exercises the same journal walk admission uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection import (
    headroom_skip_kind,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    session_headroom_reading_fields,
)

_NOW = "2026-11-14T07:30:00Z"
_EXPIRES = "2026-11-14T07:44:00Z"
_SLOT_0 = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_0"
_SLOT_1 = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_1"
# Slot 0's window resets sooner, so without the exhaustion record it wins the ranking.
_IDENTITY_BY_TOKEN = {"token-0": "identity-0", "token-1": "identity-1"}
_RESET_BY_TOKEN = {"token-0": "1700000000", "token-1": "1800000000"}


def _exhaustion_record(*, credential_identity: str) -> dict[str, str]:
    return {
        "at": "2026-11-14T07:29:00Z",
        "stage": "provider-exhaustion-observed",
        "provider": "anthropic",
        "governing_condition": "provider_usage_limit",
        "record_expires_at": _EXPIRES,
        "work_item_id": "bd-ib-yw7yot",
        "credential_identity": credential_identity,
    }


def _journal(*, tmp_path: Path, identities: tuple[str, ...]) -> Path:
    journal = tmp_path / "fabro-dispatch-journal.jsonl"
    lines = [json.dumps(_exhaustion_record(credential_identity=i)) for i in identities]
    _ = journal.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return journal


def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
    key = token or ""
    return headroom.session_headroom_reading(
        credential_identity=_IDENTITY_BY_TOKEN.get(key, "unnumbered"),
        observed_at=observed_at,
        utilization=10,
        provider_reset_claim=_RESET_BY_TOKEN.get(key),
    )


def _policy(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, identities: tuple[str, ...]
) -> headroom.SessionHeadroomPolicy:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv(_SLOT_0, "token-0")
    monkeypatch.setenv(_SLOT_1, "token-1")
    return headroom_gate.session_headroom_policy(
        repo=tmp_path,
        now_iso=_NOW,
        journal_path=_journal(tmp_path=tmp_path, identities=identities),
        read=_read,
    )


def _slot_fields(
    *, readings: tuple[headroom.SessionHeadroomReading, ...], identity: str
) -> dict[str, object]:
    by_identity = {
        reading.credential_identity: session_headroom_reading_fields(reading=reading)
        for reading in readings
    }
    return by_identity.get(identity, {})


def test_a_slot_with_a_live_exhaustion_record_is_skipped_for_the_next_ranked_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    policy = _policy(monkeypatch=monkeypatch, tmp_path=tmp_path, identities=("identity-0",))
    chosen = policy.read()
    assert policy.pool_read is not None
    pooled = policy.pool_read()
    excluded = _slot_fields(readings=pooled, identity="identity-0")
    excluded_slot = cast("dict[str, object]", excluded.get("slot", {}))
    facts = (
        chosen.credential_identity == "identity-1",
        excluded_slot.get("chosen") is False,
        excluded_slot.get("not_chosen_reason") == "provider-exhaustion-skip",
        excluded.get("provider_exhaustion_expires_at") == _EXPIRES,
        excluded.get("credential_identity") == "identity-0",
    )
    assert all(facts), facts


def test_when_every_slot_is_exhausted_the_covered_candidate_is_skipped_by_exhaustion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    policy = _policy(
        monkeypatch=monkeypatch, tmp_path=tmp_path, identities=("identity-0", "identity-1")
    )
    representative = policy.read()
    assert policy.pool_read is not None
    pooled = policy.pool_read()
    kind = headroom_skip_kind(reading=representative, floor_percent=policy.floor_percent)
    facts = (
        kind == "provider-exhaustion",
        not any(reading.slot is not None and reading.slot.chosen for reading in pooled),
    )
    assert all(facts), (kind, facts)


def test_an_exhaustion_skip_applies_even_with_the_headroom_floor_at_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    policy = _policy(monkeypatch=monkeypatch, tmp_path=tmp_path, identities=("identity-0",))
    assert policy.pool_read is not None
    pooled = policy.pool_read()
    excluded = [r for r in pooled if r.credential_identity == "identity-0"]
    kinds = [headroom_skip_kind(reading=r, floor_percent=0) for r in excluded]
    assert kinds == ["provider-exhaustion"], kinds
