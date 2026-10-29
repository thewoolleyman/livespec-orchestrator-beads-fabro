"""The `implement` prose's ledger-read snippet must call the keyword-only reader API."""

from __future__ import annotations

import inspect
from pathlib import Path

from livespec_orchestrator_beads_fabro.store import materialize_work_items

_PROSE = Path(__file__).resolve().parent.parent / ".claude-plugin" / "prose" / "implement.md"
_KEYWORD_CALL = "materialize_work_items(records=read_work_items(path=config))"


def test_implement_prose_snippet_calls_materialize_work_items_by_keyword() -> None:
    text = _PROSE.read_text(encoding="utf-8")
    assert _KEYWORD_CALL in text
    assert "materialize_work_items(read_work_items(" not in text


def test_materialize_work_items_is_keyword_only() -> None:
    parameters = inspect.signature(materialize_work_items).parameters.values()
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters)
