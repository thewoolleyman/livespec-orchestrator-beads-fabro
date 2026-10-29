"""Published journal surface for Dispatcher auto-disposition decisions."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)

__all__: list[str] = [
    "auto_disposition_journal_record",
    "read_auto_disposition_decisions",
]

_AUTO_DISPOSITION_STAGE = "auto-disposition"


def auto_disposition_journal_record(
    *,
    work_item_id: str,
    disposition: str,
    governing_settings: tuple[str, ...],
) -> dict[str, object]:
    """Build the published audit record for one automatic Dispatcher disposition."""
    return {
        "stage": _AUTO_DISPOSITION_STAGE,
        "work_item_id": work_item_id,
        "disposition": disposition,
        "governing_settings": list(governing_settings),
    }


def read_auto_disposition_decisions(*, journal_path: Path) -> tuple[dict[str, object], ...]:
    """Read auto-disposition records from the append-only Dispatcher journal."""
    records = read_journal_records(journal_path=journal_path)
    return tuple(record for record in records if record.get("stage") == _AUTO_DISPOSITION_STAGE)
