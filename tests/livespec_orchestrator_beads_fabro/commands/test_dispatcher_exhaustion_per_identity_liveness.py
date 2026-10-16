"""ONE record per vendor was one record too few: the account is part of the key.

Binds `SPECIFICATION/scenarios.md` "## Scenario 186" case "A newer record for
one identity does not retire another identity's record", against
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "Records are distinct per provider and credential
identity: a newer record for one identity neither supersedes nor retires a live
record for another."

WHY THIS IS NOT MERELY TIDY. The journal walk is newest-first and stops at the
first live record it has not already decided. Keyed on the VENDOR alone, the
four `anthropic-1` runs that met the session limit between 17:35Z and 17:41Z on
2026-10-16 each retired their predecessor, so the one record that survived was
whichever finished last -- and an `anthropic-3` record minted a minute later
would have retired all of them, silently, while every account still held its
own ceiling. Keyed on the PAIR, each account's ceiling is its own record and
the walk reports every one of them.

THE CONTROL IS THE SAME-ACCOUNT CASE, and it is what tells per-account keying
apart from no keying at all: a walk that simply appended every unexpired record
it met would satisfy every multi-account assertion here while reporting four
records for one account's single ceiling.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T17:42:00Z"
_LIVE_EXPIRY = "2099-01-01T00:00:00Z"
_PAST_EXPIRY = "2026-10-16T17:00:00Z"
_EXHAUSTED_ACCOUNT = "1111111111111111"
_ROTATED_ACCOUNT = "2222222222222222"


def _exhaustion() -> Any:
    return import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")


def _observation(
    *,
    identity: str | None,
    expires_at: str = _LIVE_EXPIRY,
    provider: str = "anthropic",
    work_item_id: str = "bd-observer",
) -> dict[str, object]:
    return {
        "at": _NOW,
        "stage": "provider-exhaustion-observed",
        "work_item_id": work_item_id,
        "provider": provider,
        "credential_identity": identity,
        "governing_condition": "provider_usage_limit",
        "record_expires_at": expires_at,
    }


def _journal(*, tmp_path: Path, records: tuple[dict[str, object], ...]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")
    return path


def _live(*, path: Path) -> list[str | None]:
    return [
        record.credential_identity
        for record in _exhaustion().live_provider_exhaustions(journal_path=path, now_iso=_NOW)
    ]


def test_a_newer_record_for_one_account_leaves_another_accounts_record_live(
    tmp_path: Path,
) -> None:
    """Scenario 186: both records are live, newest observation first."""
    path = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(identity=_EXHAUSTED_ACCOUNT),
            _observation(identity=_ROTATED_ACCOUNT),
        ),
    )

    assert _live(path=path) == [
        _ROTATED_ACCOUNT,
        _EXHAUSTED_ACCOUNT,
    ], "the newer account's record retired the other account's live ceiling"


def test_a_newer_record_for_the_same_account_still_retires_only_its_predecessor(
    tmp_path: Path,
) -> None:
    """The control: the account is part of the key, not a replacement for it.

    Four runs on one account each mint a record as they meet the same ceiling.
    They are one ceiling, so the walk must still report one record -- which a
    walk that had simply stopped deciding anything would not.
    """
    path = _journal(
        tmp_path=tmp_path,
        records=tuple(
            _observation(identity=_EXHAUSTED_ACCOUNT, work_item_id=f"bd-run-{index}")
            for index in range(4)
        ),
    )

    assert _live(path=path) == [_EXHAUSTED_ACCOUNT]
    assert [
        record.work_item_id
        for record in _exhaustion().live_provider_exhaustions(journal_path=path, now_iso=_NOW)
    ] == ["bd-run-3"]


def test_an_account_named_record_and_a_provider_only_record_are_distinct(
    tmp_path: Path,
) -> None:
    """Distinct per provider AND credential identity: the absence is a key too."""
    path = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(identity=_EXHAUSTED_ACCOUNT),
            _observation(identity=None),
        ),
    )

    assert _live(path=path) == [None, _EXHAUSTED_ACCOUNT]


def test_one_accounts_expired_record_does_not_hide_anothers_live_one(
    tmp_path: Path,
) -> None:
    """An expired record decides nothing, for its own account or any other."""
    path = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(identity=_EXHAUSTED_ACCOUNT),
            _observation(identity=_ROTATED_ACCOUNT, expires_at=_PAST_EXPIRY),
        ),
    )

    assert _live(path=path) == [_EXHAUSTED_ACCOUNT]
    # And the vendor axis still separates them: a codex record naming the same
    # digest is a different record from the anthropic one.
    both = _journal(
        tmp_path=tmp_path / "both",
        records=(
            _observation(identity=_EXHAUSTED_ACCOUNT),
            _observation(identity=_EXHAUSTED_ACCOUNT, provider="codex"),
        ),
    )
    assert [
        (record.provider, record.credential_identity)
        for record in _exhaustion().live_provider_exhaustions(journal_path=both, now_iso=_NOW)
    ] == [("codex", _EXHAUSTED_ACCOUNT), ("anthropic", _EXHAUSTED_ACCOUNT)]
