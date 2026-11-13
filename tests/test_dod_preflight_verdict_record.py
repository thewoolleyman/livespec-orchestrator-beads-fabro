"""The repository preflight leaves a reusable Definition-of-Done receipt."""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")


def test_a_passing_preflight_appends_the_shared_verdict_record() -> None:
    """A passed repository-preflight taking names its stage and digest pair."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "verdict_comment" in text
    assert 'stage="repository-preflight"' in text
    assert "append_work_item_comment" in text


def test_an_identical_preflight_reuses_the_record_without_a_candidate() -> None:
    """The repository preflight consults the same digest-pair reuse reader."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "reusable_verdict" in text
    assert 'print(f"REUSED {reused.outcome}")' in text


def test_a_fresh_governing_verdict_is_recorded_before_an_early_refusal() -> None:
    """A governing-heading refusal can be reused by the next preflight."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "GoverningHeadingReceipt(" in text
    assert "governing_heading_subject_digest(" in text
    assert "if reading.holds:" in text


def test_a_completed_preflight_carries_its_governing_receipt_to_the_verdict() -> None:
    """A passed or refused rubric verdict preserves the component it used."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "governing_receipt" in text
    assert "governing=governing" in text
