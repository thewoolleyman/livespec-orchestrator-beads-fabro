"""Coverage for the shared host Definition-of-Done judgement journal helper."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_dod_judgement_journal as journal_module,
)


def test_a_reused_judgement_does_not_append_a_second_journal_row(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-use reads a receipt; it is not another host judgement taking."""
    records: list[dict[str, object]] = []

    class _JournalFile:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def append(self, *, record: dict[str, object]) -> None:
            records.append(record)

    monkeypatch.setattr(journal_module, "JournalFile", _JournalFile)

    journal_module.journal_taken_judgement(
        repo=tmp_path,
        item_id="bd-ib-reused",
        judgement_stage="pre-admission",
        decision=SimpleNamespace(reused=True),
    )

    assert records == []
