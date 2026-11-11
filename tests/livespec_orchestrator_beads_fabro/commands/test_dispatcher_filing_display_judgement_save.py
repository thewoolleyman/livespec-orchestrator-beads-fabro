"""Filesystem-failure coverage for the filing-display judgement observer."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    CandidateAttempt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
    CandidateChainResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    filing_display,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display_judgement import (
    JudgementObserver,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


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


def test_a_present_governing_verdict_does_not_render_the_unavailable_report(tmp_path: Path) -> None:
    """A successful judgement remains distinct from the unavailable display arm."""
    item = WorkItem(
        id="bd-ib-e3vbbo",
        type="bug",
        status="pending-approval",
        title="The filing display reports its governing judgement",
        description=(
            "## Definition of Done\n\n"
            "- The display reports its governing-heading judgement.\n\n"
            "References: ## A governing heading\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )

    lines = filing_display(item=item, cwd=tmp_path, governing=_judged_reader).splitlines()

    assert "definition-of-done findings: judgement unavailable" not in lines


def _judged_reader(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict:
    """A reader that returned the governing verdict successfully."""
    del item, repo
    return GoverningHeadingVerdict(kind="stated")
