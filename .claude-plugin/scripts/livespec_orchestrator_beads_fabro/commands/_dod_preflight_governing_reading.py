"""The governing-heading reading the repository preflight takes of one item.

`dev-tooling/dod-preflight.sh` is the third host taking of the Definition-of-Done
judgement, and the pre-dispatch gate reads `reusable_governing_heading_verdict`
before it asks the host reader. The preflight used to call the host reader on every
run, so a launch re-took a judgement the item already carried a current record for,
and the retaking could flip the verdict on identical bytes (`bd-ib-ot4av7`). This
module is the one reading both the script and its tests go through: a recorded
verdict the component's own reuse rule still allows (a current subject digest and
clauses, or a standing `release-spec-tier` attestation) decides and starts no judge
candidate; only an item with no such record is put to the host reader.

The reading also owns the lines and findings the script prints, so a reused verdict
and a fresh one are reported by one rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    reusable_governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
    governing_heading_findings,
    governing_heading_holds,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    host_governing_heading_reader,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["PreflightGoverningReading", "preflight_governing_heading_reading"]


@dataclass(frozen=True, kw_only=True)
class PreflightGoverningReading:
    """One item's governing-heading verdict with the lines and findings it prints.

    `verdict` is `None` when the judgement could not be taken, which fails open
    exactly as it does at the gate: no finding is raised on an outage no edit
    could clear. `holds` is whether `findings` hold the item rather than advise.
    """

    verdict: GoverningHeadingVerdict | None
    report: tuple[str, ...]
    findings: tuple[str, ...]
    holds: bool


def preflight_governing_heading_reading(
    *, item: WorkItem, repo: Path, comments: Sequence[str], runner: CommandRunner
) -> PreflightGoverningReading:
    """Read the item's governing-heading verdict as the gate does, spending a model last."""
    verdict = reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)
    if verdict is None:
        verdict = host_governing_heading_reader(runner=runner)(item=item, repo=repo)
    section = definition_of_done(description=item.description)
    findings = governing_heading_findings(item=item, section=section, verdict=verdict)
    report = (
        ("governing-heading-kind: unobserved",)
        if verdict is None
        else (
            f"governing-heading-kind: {verdict.kind}",
            *(f"governing-heading: {heading}" for heading in verdict.stated_by),
        )
    )
    return PreflightGoverningReading(
        verdict=verdict,
        report=report,
        findings=findings,
        holds=bool(findings) and governing_heading_holds(section=section, verdict=verdict),
    )
