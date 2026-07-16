"""Published journal surface for Dispatcher auto-disposition decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

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
    records = _read_journal_records(journal_path=journal_path)
    return tuple(record for record in records if record.get("stage") == _AUTO_DISPOSITION_STAGE)


def _read_journal_records(*, journal_path: Path) -> tuple[dict[str, object], ...]:
    if not journal_path.is_file():
        return ()
    records: list[dict[str, object]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            mapping = cast("dict[object, object]", parsed)
            records.append({str(key): value for key, value in mapping.items()})
    return tuple(records)
