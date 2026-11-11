"""Filesystem-failure coverage for the filing-display judgement observer."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    CandidateAttempt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
    CandidateChainResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display_judgement import (
    JudgementObserver,
)


def test_an_unparseable_reply_that_cannot_be_saved_is_reported(tmp_path: Path) -> None:
    """The advisory display names its diagnostic write failure rather than raising."""
    _ = (tmp_path / "tmp").write_text("not a directory", encoding="utf-8")
    observer = JudgementObserver()
    observer.observe(
        chain=CandidateChainResult(
            reply=None,
            cause="unparseable-verdict",
            attempts=(
                CandidateAttempt(
                    agent="codex-acp",
                    model="gpt-5.6-terra",
                    exit_code=0,
                    outcome="unparseable-verdict",
                    reply_text="not a verdict",
                ),
            ),
        )
    )

    lines = observer.report_lines(item_id="bd-ib-e3vbbo", cwd=tmp_path)

    assert len(lines) == 2
    assert "could not be saved" in lines[1]
