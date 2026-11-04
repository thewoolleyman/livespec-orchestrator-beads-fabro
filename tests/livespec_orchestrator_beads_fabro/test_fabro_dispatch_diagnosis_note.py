"""The diagnosis note names the factory-addressed reader for undecodable runs."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_diagnosis_note_quotes_the_unknown_variant_error_and_names_the_reader() -> None:
    """A diagnostician is pointed at the factory client, not told data is missing."""
    note = (_REPO_ROOT / ".ai" / "fabro-dispatch-diagnosis.md").read_text(encoding="utf-8")

    assert "unknown variant `kubernetes`" in note
    assert "dispatcher.py inspect --factory" in note
    assert "PATH" in note
