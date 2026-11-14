"""Read or take the governing-heading verdict shown by a filing display."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_filing_governing_receipt import (
    filing_governing_receipt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    governing_heading_subject_digest,
    reusable_governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_comments import (
    judgement_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    GoverningHeadingTaking,
    host_governing_heading_taking_reader,
)
from livespec_orchestrator_beads_fabro.effects import attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["FilingGoverningReading", "filing_governing_heading_reading"]

_LEDGER_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


@dataclass(frozen=True, kw_only=True)
class FilingGoverningReading:
    """The display verdict and a reason when no usable verdict was produced."""

    verdict: GoverningHeadingVerdict | None
    not_taken_reason: str | None = None


def filing_governing_heading_reading(*, item: WorkItem, repo: Path) -> FilingGoverningReading:
    """Reuse the current component receipt, otherwise take and append one.

    A comment-sidecar failure is advisory at filing: the display still takes its
    own verdict, but cannot safely establish or persist reuse provenance.
    """
    try:
        path = store_config(repo=repo)
        comments = judgement_comment_bodies(path=path, work_item_id=item.id, repo=repo)
    except _LEDGER_ERRORS:
        path = None
        comments = None
    if comments is not None:
        reused = reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)
        if reused is not None:
            return FilingGoverningReading(verdict=reused)
    taking: GoverningHeadingTaking = host_governing_heading_taking_reader(
        runner=ShellCommandRunner()
    )(item=item, repo=repo)
    verdict = taking.verdict
    if verdict is None:
        return FilingGoverningReading(verdict=None, not_taken_reason=taking.not_taken_reason)
    if path is not None and comments is not None:
        _ = attempt(
            action=lambda: append_work_item_comment(
                path=path,
                work_item_id=item.id,
                body=filing_governing_receipt(
                    item_id=item.id,
                    subject_digest=governing_heading_subject_digest(item=item, comments=comments),
                    verdict=verdict,
                ),
            ),
            exceptions=_LEDGER_ERRORS,
        )
    return FilingGoverningReading(verdict=verdict)
