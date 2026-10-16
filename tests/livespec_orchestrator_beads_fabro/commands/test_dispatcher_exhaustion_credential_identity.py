"""Which CREDENTIAL ACCOUNT a provider-exhaustion record speaks for.

Binds the credential-identity clause of `SPECIFICATION/contracts.md` section
"Dispatcher admission, WIP cap, and post-merge acceptance" -> "Every observed
availability record is scoped, versioned, and expires", and the scenario
`SPECIFICATION/scenarios.md` "## Scenario 186 -- A provider exhaustion observed
on one credential account does not refuse dispatch on another account of the
same vendor", at the two seams that decide it: the MINT, which labels the
record, and the COVERAGE predicate, which decides whom it reaches.

WHY THE VENDOR LABEL WAS NOT ENOUGH, measured 2026-10-16: the account selector
rotated the Anthropic selection from `anthropic-1` to `anthropic-3` at 16:52Z,
four in-flight `anthropic-1` runs then met the session limit between 17:35Z and
17:41Z, and the records their closes minted refused every `anthropic-3` dispatch
until 17:50:19Z. The vendor was right and the account was wrong, so the rotation
that existed to restore capacity was defeated by records naming a ceiling the
admitted dispatches could not have hit.

Everything here is HERMETIC: the journal is a file under `tmp_path`, every
reading is a literal, no provider is reached and no adapter is launched.
"""

from __future__ import annotations

import dataclasses
import json
from importlib import import_module
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T17:40:00Z"
_ITEM = "bd-ib-b53dhr"
# The two opaque digests `projected_credential_identity` would return for two
# accounts of one vendor. Their VALUES carry no meaning; only their inequality
# does, which is the whole point of a domain-separated fingerprint.
_EXHAUSTED_ACCOUNT = "1111111111111111"
_ROTATED_ACCOUNT = "2222222222222222"


class _Outcome:
    """The typed provider-usage-limit terminal the mint reads, and nothing more."""

    def __init__(self, *, provider: str | None) -> None:
        self.work_item_id = _ITEM
        self.provider_usage_limit_provider = provider


def _exhaustion() -> Any:
    return import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")


def _journal(*, tmp_path: Path, records: tuple[dict[str, object], ...]) -> Path:
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")
    return path


def _assessment(*, identities: tuple[str, ...]) -> dict[str, object]:
    """One admission evaluation's session-headroom record for this work-item."""
    return {
        "at": _NOW,
        "stage": "acp-session-headroom",
        "work_item_id": _ITEM,
        "session_headroom_floor_percent": 20,
        "assessments": [
            {
                "credential_identity": identity,
                "utilization_percent": 10.0,
                "remaining_percent": 90.0,
                "unobservable": None,
                "observed_at": _NOW,
                "five_hour_drain_percent_per_hour": None,
            }
            for identity in identities
        ],
    }


class _AppendingJournal:
    """The journal seam, appending to the SAME file the mint reads its history from."""

    def __init__(self, *, path: Path) -> None:
        self.path = path

    def append(self, *, record: dict[str, object]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            _ = handle.write(f"{json.dumps(record)}\n")


def _minted(*, path: Path) -> dict[str, object]:
    observed = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("stage") == "provider-exhaustion-observed"
    ]
    assert len(observed) == 1
    return observed[0]


def test_the_minted_record_names_the_identity_the_admission_assessment_journaled(
    tmp_path: Path,
) -> None:
    """Scenario 186: "A record names the credential identity ... projected"."""
    exhaustion = _exhaustion()
    assert "credential_identity" in {
        field.name for field in dataclasses.fields(exhaustion.ProviderExhaustionRecord)
    }, "the record cannot yet carry the account that observed the limit"
    path = _journal(tmp_path=tmp_path, records=(_assessment(identities=(_EXHAUSTED_ACCOUNT,)),))
    journal = _AppendingJournal(path=path)

    exhaustion.record_provider_exhaustion_if_observed(
        outcome=_Outcome(provider="anthropic"),
        journal=journal,
        journal_path=path,
        now_iso=_NOW,
    )

    record = _minted(path=path)
    assert record["provider"] == "anthropic"
    assert record["credential_identity"] == _EXHAUSTED_ACCOUNT
    # The label survives the round trip through the journal, so the gate that
    # reads it back is deciding on the account the run actually spent.
    live = exhaustion.live_provider_exhaustions(journal_path=path, now_iso=_NOW)
    assert [held.credential_identity for held in live] == [_EXHAUSTED_ACCOUNT]
