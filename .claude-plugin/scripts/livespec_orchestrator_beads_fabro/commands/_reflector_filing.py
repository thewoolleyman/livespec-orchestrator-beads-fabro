from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
from livespec_orchestrator_beads_fabro.commands._otel_scrub import scrub as _scrub
from livespec_orchestrator_beads_fabro.commands._reflector_filing_store import (
    OpenItem,
    file_new,
    label_index,
    make_client,
    record_labels,
    severity_priority,
)
from livespec_orchestrator_beads_fabro.commands._reflector_findings_parse import ReflectorFinding
from livespec_orchestrator_beads_fabro.commands._reflector_lessons import (
    LessonProposal,
    LessonsProposer,
)

__all__: list[str] = [
    "ReflectorReport",
    "check_budget",
    "file_findings",
    "fingerprint",
    "label_index",
    "record_labels",
    "severity_priority",
]

_MAX_NEW_ITEMS_PER_PASS = 3
_WARN_MIN_OCCURRENCES = 2
_FINGERPRINT_HEX_LEN = 12
_BUDGET_EXCEEDED_MESSAGE = "out-of-band reflector exceeded its scan time budget"


class JournalWriter(Protocol):
    def append(self, *, record: dict[str, object]) -> None: ...


@dataclass(frozen=True, kw_only=True)
class ReflectorReport:
    mode: str
    repo: str
    findings: tuple[ReflectorFinding, ...]
    filed: tuple[str, ...]
    bumped: tuple[str, ...]
    muted: tuple[str, ...]
    digested: tuple[str, ...]
    lesson_proposed: bool


def fingerprint(*, category: str, stage: str, repo: str, subject: str) -> str:
    normalized = " ".join(subject.lower().split())
    material = f"{category}|{stage}|{repo}|{normalized}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:_FINGERPRINT_HEX_LEN]


def file_findings(
    *,
    repo: Path,
    journal: JournalWriter,
    findings: tuple[ReflectorFinding, ...],
    lessons_proposer: LessonsProposer,
    mode: str,
    deadline: float,
) -> ReflectorReport:
    client = make_client(repo=repo)
    index = label_index(client=client)
    disposition = _Disposition()
    new_count = 0
    for finding in findings:
        check_budget(deadline=deadline)
        new_count = _dispose_one(
            finding=finding,
            repo=repo,
            client=client,
            index=index,
            disposition=disposition,
            new_count=new_count,
            journal=journal,
        )
    lesson_proposed = _maybe_propose_lesson(
        findings=findings, repo=repo, proposer=lessons_proposer, journal=journal
    )
    journal.append(
        record={
            "stage": "reflector-oob",
            "mode": mode,
            "finding_count": len(findings),
            "filed": list(disposition.filed),
            "bumped": list(disposition.bumped),
            "muted": list(disposition.muted),
            "digested": list(disposition.digested),
        }
    )
    return ReflectorReport(
        mode=mode,
        repo=str(repo),
        findings=findings,
        filed=tuple(disposition.filed),
        bumped=tuple(disposition.bumped),
        muted=tuple(disposition.muted),
        digested=tuple(disposition.digested),
        lesson_proposed=lesson_proposed,
    )


@dataclass(kw_only=True)
class _Disposition:
    filed: list[str] = field(default_factory=list)
    bumped: list[str] = field(default_factory=list)
    muted: list[str] = field(default_factory=list)
    digested: list[str] = field(default_factory=list)


def _dispose_one(  # noqa: PLR0913 - kw-only inner dispatcher; each arg is an independent collaborator.
    *,
    finding: ReflectorFinding,
    repo: Path,
    client: BeadsClient,
    index: dict[str, OpenItem],
    disposition: _Disposition,
    new_count: int,
    journal: JournalWriter,
) -> int:
    fp = fingerprint(
        category=finding.category, stage=finding.stage, repo=str(repo), subject=finding.subject
    )
    existing = index.get(fp)
    if existing is not None and existing.muted:
        disposition.muted.append(fp)
        return new_count
    if existing is not None and not existing.closed:
        client.add_comment(issue_id=existing.issue_id, body=_bump_body(finding=finding))
        disposition.bumped.append(existing.issue_id)
        return new_count
    if not _should_file(finding=finding):
        disposition.digested.append(fp)
        return new_count
    if new_count >= _MAX_NEW_ITEMS_PER_PASS:
        disposition.digested.append(fp)
        return new_count
    issue_id = file_new(finding=finding, fingerprint_hex=fp, client=client, repo=repo)
    disposition.filed.append(issue_id)
    journal.append(record={"stage": "reflector-oob-filed", "issue_id": issue_id, "fingerprint": fp})
    return new_count + 1


def _should_file(*, finding: ReflectorFinding) -> bool:
    if finding.severity == "info":
        return False
    if finding.severity == "warn":
        return finding.occurrences >= _WARN_MIN_OCCURRENCES
    return finding.severity == "critical"


def _bump_body(*, finding: ReflectorFinding) -> str:
    note = (
        f"reflection recurrence (x{finding.occurrences}): {finding.subject} "
        f"[severity={finding.severity}, score={finding.score:.2f}, label={finding.label}]"
    )
    return _scrub(value=note)


def _maybe_propose_lesson(
    *,
    findings: tuple[ReflectorFinding, ...],
    repo: Path,
    proposer: LessonsProposer,
    journal: JournalWriter,
) -> bool:
    critical = [f for f in findings if f.severity == "critical"]
    if not critical:
        return False
    top = critical[0]
    proposal = LessonProposal(
        title=f"reflection lesson: {top.category}",
        body=_scrub(value=f"- {top.subject}\n\n  {top.detail}".strip()),
    )
    pr_ref = proposer.propose(proposal=proposal, repo=repo)
    journal.append(
        record={
            "stage": "reflector-oob-lesson-proposed",
            "pr_ref": pr_ref,
            "category": top.category,
        }
    )
    return True


def check_budget(*, deadline: float) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError(_BUDGET_EXCEEDED_MESSAGE)
