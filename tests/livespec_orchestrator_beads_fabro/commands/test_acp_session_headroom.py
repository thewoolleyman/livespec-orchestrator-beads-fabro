"""The admission session-headroom reading: what is read, and what it journals.

Binds the "Admission filters candidates by projected Claude session headroom"
paragraph of `SPECIFICATION/contracts.md` section "Dispatcher admission, WIP
cap, and post-merge acceptance" together with the five headroom scenarios of
`SPECIFICATION/scenarios.md` Scenario 60.

THREE CONTROLS CARRY MOST OF THE WEIGHT HERE, because each is a claim an
almost-correct implementation gets backwards:

- COVERAGE FOLLOWS PROVENANCE, NEVER SPELLING. The clause says so in as many
  words -- "never display text, a model-name prefix, or a spelling inferred
  from an opaque availability or candidate key" -- so the discriminating case
  is a candidate whose `availability_key` reads `anthropic` while nothing
  about its resolution says it runs Claude. An implementation that matched the
  key would pass every other assertion in this file and would silently assess
  an unrelated provider's credential.
- AN UNOBSERVABLE READING IS NEVER COERCED TO A NUMBER. The clause enumerates
  six ways a reading fails and requires each to be journaled AS unobservable.
  A zero, or a 100, would be a perfectly plausible numeric reading, and the
  skip it produced would be indistinguishable from a measured one.
- THE READING IS TAKEN AT MOST ONCE PER ADMISSION EVALUATION. A per-candidate
  read returns two answers for one credential and cannot be told apart from a
  correct one by looking at the readings -- only by counting the reads.

Everything is HERMETIC: the reading seam is injected, and no credential value
leaves this file. The provider request itself is covered by
`test_dispatcher_session_headroom_io.py`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_io as headroom_io,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from returns.pipeline import is_successful

_NOW = "2026-10-14T12:00:00Z"
_TOKEN = "projected-oauth-token"
_OTHER_TOKEN = "a-different-projected-token"
_BUILTIN_KEY = "builtin-anthropic-0123456789abcdef"


def _identity(*, availability_key: str, candidate_key: str) -> AcpCandidateIdentity:
    return AcpCandidateIdentity(
        display_name=f"{availability_key}/{candidate_key}",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _candidate(*, availability_key: str = "codex", candidate_key: str = "gpt-5-5") -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="adapter", env={}, args=()),
        identity=_identity(availability_key=availability_key, candidate_key=candidate_key),
    )


def _recording_read(calls: list[str | None]) -> Callable[..., Any]:
    """A reading seam that records the token it was handed.

    ONE factory, shared by the cases that expect a read and by the cases that
    expect NONE, so "no usage request was spent" is asserted against an empty
    record of calls rather than against a stand-in that refuses -- a refusing
    stand-in proves only that this case did not call it, while an empty list
    proves it against the same instrument the positive cases exercise.
    """

    def _read(*, token: str | None, observed_at: str) -> Any:
        calls.append(token)
        return headroom.session_headroom_reading(
            credential_identity="cred-1", observed_at=observed_at, utilization=10
        )

    return _read


def _write_floor(*, root: Path, value: str) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        f'{{"session_headroom_floor_percent": {value}}}}}}}',
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# The reading itself.
# ---------------------------------------------------------------------------


def test_a_valid_utilization_yields_the_remaining_headroom_it_implies() -> None:
    """Remaining headroom is 100 minus the provider's utilization percentage."""
    reading = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=55
    )

    assert reading.observable is True
    assert reading.unobservable is None
    assert reading.utilization_percent == 55.0
    assert reading.remaining_percent == 45.0
    assert reading.credential_identity == "cred-1"
    assert reading.observed_at == _NOW


@pytest.mark.parametrize(
    "utilization",
    [None, "55", True, -0.5, 100.5, float("nan"), float("inf"), {"utilization": 55}],
)
def test_a_missing_malformed_or_out_of_range_utilization_is_never_coerced(
    utilization: object,
) -> None:
    """Each of the clause's unreadable shapes becomes an EXPLICIT unobservable.

    The direction that matters is the one not asserted anywhere else: a numeric
    fallback here would be indistinguishable, at every surface downstream, from
    a utilization the provider actually reported.
    """
    reading = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=utilization
    )

    assert reading.observable is False
    assert reading.unobservable == headroom.UNREADABLE_UTILIZATION
    assert reading.utilization_percent is None
    assert reading.remaining_percent is None


def test_the_two_allowance_extremes_are_valid_readings_rather_than_faults() -> None:
    """0 and 100 are inside the inclusive range the clause declares valid."""
    spent = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=100
    )
    untouched = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=0
    )

    assert (spent.observable, spent.remaining_percent) == (True, 0.0)
    assert (untouched.observable, untouched.remaining_percent) == (True, 100.0)


# ---------------------------------------------------------------------------
# Coverage: which candidates this clause assesses at all.
# ---------------------------------------------------------------------------


def test_a_builtin_claude_adapter_is_covered_by_byte_equality_provenance() -> None:
    """The built-in table keys on bytes this build rendered, so it IS provenance."""
    builtin = _candidate(availability_key=ANTHROPIC_DOMAIN, candidate_key=_BUILTIN_KEY)
    pairs = frozenset({(ANTHROPIC_DOMAIN, _BUILTIN_KEY)})

    assert headroom.headroom_covers_candidate(candidate=builtin, builtin_pairs=pairs) is True


def test_an_availability_key_that_merely_spells_a_vendor_is_not_covered() -> None:
    """The discriminating case: the right spelling with no resolved provenance.

    The clause forbids inferring coverage from an opaque key, and this candidate
    is exactly what that inference would wrongly sweep in -- an arbitrary manual
    adapter whose operator happened to name its account after the vendor.
    """
    spelled = _candidate(availability_key=ANTHROPIC_DOMAIN, candidate_key="hand-rolled")

    assert headroom.headroom_covers_candidate(candidate=spelled, builtin_pairs=frozenset()) is False


def test_a_builtin_candidate_outside_the_claude_domain_is_not_covered() -> None:
    """A built-in Codex adapter matches the table and is still not this clause's."""
    builtin = _candidate(availability_key="codex", candidate_key="builtin-codex-abc")
    pairs = frozenset({("codex", "builtin-codex-abc")})

    assert headroom.headroom_covers_candidate(candidate=builtin, builtin_pairs=pairs) is False


def test_an_identity_less_legacy_candidate_is_outside_this_clause() -> None:
    legacy = AcpCandidate(adapter=AcpAdapter(command="adapter", env={}, args=()))

    assert headroom.headroom_covers_candidate(candidate=legacy, builtin_pairs=frozenset()) is False


# ---------------------------------------------------------------------------
# The per-evaluation policy: the floor, and one read per projected credential.
# ---------------------------------------------------------------------------


def test_the_policy_reads_the_projected_snapshot_at_most_once_per_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every candidate sharing the projected credential shares ONE reading."""
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _TOKEN)
    tokens: list[str | None] = []
    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, read=_recording_read(tokens)
    )

    first = policy.read()
    again = policy.read()

    assert tokens == [_TOKEN]
    assert first is again
    assert first.observed_at == _NOW


def test_the_floor_defaults_to_the_ratified_twenty_and_is_committed_only(tmp_path: Path) -> None:
    """Building the policy resolves the dial and spends no usage request."""
    tokens: list[str | None] = []
    assert headroom.DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT == 20

    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, read=_recording_read(tokens)
    )

    assert policy.floor_percent == headroom.DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT
    assert tokens == []


@pytest.mark.parametrize(("configured", "expected"), [("0", 0), ("100", 100), ("35", 35)])
def test_a_committed_floor_inside_the_inclusive_range_is_honoured(
    tmp_path: Path, configured: str, expected: int
) -> None:
    _write_floor(root=tmp_path, value=configured)

    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, read=_recording_read([])
    )

    assert policy.floor_percent == expected


@pytest.mark.parametrize("configured", ["101", "-1", '"20"', "true", "20.5"])
def test_a_floor_outside_the_declared_range_is_refused_rather_than_clamped(
    tmp_path: Path, configured: str
) -> None:
    """An unreadable dial resolves to the RATIFIED default, never to a guess."""
    _write_floor(root=tmp_path, value=configured)

    resolved = headroom_gate.resolve_session_headroom_floor_percent(cwd=tmp_path)
    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, read=_recording_read([])
    )

    assert is_successful(resolved) is False
    assert policy.floor_percent == headroom.DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT


# ---------------------------------------------------------------------------
# The journaled assessment record.
# ---------------------------------------------------------------------------


def test_the_assessment_record_names_the_item_the_identity_and_the_reading() -> None:
    """The four things the clause requires of the journaled reading."""
    reading = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=55
    )

    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=20, assessments=(reading,)
    )

    assert record["stage"] == headroom_records.SESSION_HEADROOM_STAGE
    assert record["work_item_id"] == "bd-ib-item"
    assert record["session_headroom_floor_percent"] == 20
    assert record["assessments"] == [
        {
            "credential_identity": "cred-1",
            "utilization_percent": 55.0,
            "remaining_percent": 45.0,
            "unobservable": None,
            "observed_at": _NOW,
        }
    ]


def test_the_assessment_record_carries_an_unobservable_result_explicitly() -> None:
    reading = headroom.unobservable_session_headroom(
        credential_identity="cred-1", observed_at=_NOW, reason="timed-out"
    )

    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=20, assessments=(reading,)
    )

    assert record["assessments"] == [
        {
            "credential_identity": "cred-1",
            "utilization_percent": None,
            "remaining_percent": None,
            "unobservable": "timed-out",
            "observed_at": _NOW,
        }
    ]


def test_the_record_carries_no_credential_value_or_raw_provider_response() -> None:
    """The clause forbids both; the reading type is what makes that structural."""
    reading = headroom.session_headroom_reading(
        credential_identity=headroom_io.projected_credential_identity(token=_TOKEN),
        observed_at=_NOW,
        utilization=55,
    )

    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=20, assessments=(reading,)
    )

    rendered = json.dumps(record, sort_keys=True)
    assert _TOKEN not in rendered
    assert "secret" not in rendered
    assert set(headroom.SessionHeadroomReading.__dataclass_fields__) == {
        "credential_identity",
        "observed_at",
        "utilization_percent",
        "remaining_percent",
        "unobservable",
    }
