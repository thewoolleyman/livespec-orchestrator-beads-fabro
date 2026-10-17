"""The minted record names NO account when the admission named none.

Binds the negative half of the mint clause in `SPECIFICATION/contracts.md`
section "Dispatcher admission, WIP cap, and post-merge acceptance": "a record
for a dispatch whose admission journaled no such identity carries none. An
absent identity is not a credential identity: a record minted for a dispatch
whose projected identity was absent carries none."

TWO STATES, ONE ANSWER, AND ONLY ONE OF THEM IS A TOLERANCE. "No assessment
was journaled" is the ordinary shape of every dispatch in a repository routed
wholly away from Claude, and `test_dispatcher_needs_human_provider_limit` and
`test_dispatcher` already assert the minted record's explicit null for it. The
ABSENT identity is different: the assessment DID run, DID journal an identity
string, and the clause rules that string is not a credential identity — so the
mint has to read the journal, find a value, and decline to use it. That is the
one arm a reader could get wrong while every other case stayed green, which is
why it has a case of its own at the MINT rather than only at the reader.

WHY A SEPARATE MODULE. `test_dispatcher_exhaustion_credential_identity` owns
the positive half and its bytes are fixed across its Red-to-Green pair, so this
sits beside it — the same arrangement `test_plan_result_proof_subject.py` has
with `test_plan_result_proof.py`.

THE CONTROL IS THE POSITIVE CASE on the same mint and the same journal, because
a mint that had stopped reading the assessment altogether would satisfy both
negatives here while losing every account label the fix exists to write.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T17:40:00Z"
_ITEM = "bd-ib-b53dhr"
_REAL_ACCOUNT = "1111111111111111"


class _Outcome:
    """The typed provider-usage-limit terminal the mint reads, and nothing more."""

    def __init__(self) -> None:
        self.work_item_id = _ITEM
        self.provider_usage_limit_provider = "anthropic"


class _RecordingJournal:
    """The journal seam, recording what the mint wrote rather than writing it."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _assessment_line(*, identity: str, unobservable: str | None) -> str:
    return json.dumps(
        {
            "at": _NOW,
            "stage": "acp-session-headroom",
            "work_item_id": _ITEM,
            "session_headroom_floor_percent": 20,
            "assessments": [
                {
                    "credential_identity": identity,
                    "utilization_percent": None if unobservable else 10.0,
                    "remaining_percent": None if unobservable else 90.0,
                    "unobservable": unobservable,
                    "observed_at": _NOW,
                    "five_hour_drain_percent_per_hour": None,
                }
            ],
        }
    )


def _minted(*, tmp_path: Path, lines: tuple[str, ...]) -> dict[str, object]:
    exhaustion = import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    journal = _RecordingJournal()

    exhaustion.record_provider_exhaustion_if_observed(
        outcome=_Outcome(), journal=journal, journal_path=path, now_iso=_NOW
    )

    assert [record["stage"] for record in journal.records] == ["provider-exhaustion-observed"]
    return journal.records[0]


def _absent() -> Any:
    return import_module(f"{_PACKAGE}._dispatcher_session_headroom_io").ABSENT_CREDENTIAL_IDENTITY


def test_an_absent_projected_identity_mints_a_record_naming_no_account(
    tmp_path: Path,
) -> None:
    """At the mint: an absent identity is not a credential identity."""
    record = _minted(
        tmp_path=tmp_path,
        lines=(_assessment_line(identity=_absent(), unobservable="absent-credential"),),
    )

    assert record["provider"] == "anthropic"
    assert record["credential_identity"] is None
    # The key is WRITTEN rather than omitted, so a reader can tell this from a
    # record minted by a build that named no accounts at all.
    assert "credential_identity" in record


def test_an_assessment_for_another_item_mints_a_record_naming_no_account(
    tmp_path: Path,
) -> None:
    """One evaluation journals one record per AFFECTED item, not one per journal."""
    other_item = json.loads(_assessment_line(identity=_REAL_ACCOUNT, unobservable=None))
    other_item["work_item_id"] = "bd-somebody-else"

    record = _minted(tmp_path=tmp_path, lines=(json.dumps(other_item),))

    assert record["credential_identity"] is None


def test_the_same_mint_still_names_an_account_the_admission_did_journal(
    tmp_path: Path,
) -> None:
    """The control: a mint that stopped reading the journal passes both negatives."""
    record = _minted(
        tmp_path=tmp_path,
        lines=(_assessment_line(identity=_REAL_ACCOUNT, unobservable=None),),
    )

    assert record["credential_identity"] == _REAL_ACCOUNT
