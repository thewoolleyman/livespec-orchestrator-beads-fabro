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
