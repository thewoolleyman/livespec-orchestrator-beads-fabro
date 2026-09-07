"""Stranded merged-dispatch attention lanes."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    pr_view_command,
    reconcile_merged_command,
    release_to_ready_command,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "stranded_dispatch_items",
]

_DISPATCHER_JOURNAL_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"
_STRANDED_REASON = "stranded-dispatch"


class _LiveLockLookup(Protocol):
    def __call__(self, *, repo: Path, work_item_id: str) -> object | None: ...


class _WatchableRunLookup(Protocol):
    def __call__(self, *, repo: Path, work_item_id: str) -> object | None: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class _DispatchEvidence:
    work_item_id: str
    status: str
    stage: str
    pr_number: int | None = None
    merge_sha: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class _StrandedDispatch:
    evidence: _DispatchEvidence
    attempts: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _DispatchHistories:
    latest: dict[str, _DispatchEvidence | None]
    opening_attempts: dict[str, int]
    outcome_attempts: dict[str, int]


def stranded_dispatch_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
    live_lock_lookup: _LiveLockLookup,
    watchable_run_lookup: _WatchableRunLookup | None = None,
    held_work_item_ids: frozenset[str] = frozenset(),
) -> list[AttentionItem]:
    # `rework:pending` is a DISCRIMINATOR here, not an incidental filter: a
    # marked item is `active` with no live lock by design, which is the exact
    # shape this surface reads as stranded. The marker partitions the two
    # populations cleanly, so a marked item is never reported as stranded.
    #
    # The `merge-hold:` label joins it as the second discriminator, for the same
    # reason and by the same ratified clause: a held item is `active` with no
    # live lock BY CONSTRUCTION — its run terminated green at the pr stage and
    # its claim was reclaimed — so without this it would read as the exact
    # population this surface exists to find. Its own row is
    # `hygiene:merge-hold:<id>`, which is the only one it produces for the hold.
    watchable_lookup = (
        watchable_run_lookup if watchable_run_lookup is not None else _no_watchable_run
    )
    active_items = {
        item.id: item
        for item in items
        if item.status == "active" and not item.rework_pending and item.id not in held_work_item_ids
    }
    stranded = _stranded_dispatches(project_root=project_root, active_item_ids=active_items.keys())
    attention: list[AttentionItem] = []
    for item_id, dispatch in stranded.items():
        if live_lock_lookup(repo=project_root, work_item_id=item_id) is not None:
            continue
        if watchable_lookup(repo=project_root, work_item_id=item_id) is not None:
            continue
        attention.append(
            _stranded_dispatch_item(
                project_root=project_root,
                repo=repo,
                work_item=active_items[item_id],
                stranded_dispatch=dispatch,
            )
        )
    return attention


def _stranded_dispatches(
    *, project_root: Path, active_item_ids: Collection[str]
) -> dict[str, _StrandedDispatch]:
    active_ids = frozenset(active_item_ids)
    journal = project_root / _DISPATCHER_JOURNAL_PATH
    if not journal.is_file():
        return {}
    loaded = attempt(action=lambda: journal.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(loaded, AttemptFailure):
        return {}
    histories = _DispatchHistories(latest={}, opening_attempts={}, outcome_attempts={})
    for line in loaded.splitlines():
        record = _journal_record(line=line)
        if record is None:
            continue
        evidence = _dispatch_evidence(record=record)
        if evidence is None or evidence.work_item_id not in active_ids:
            continue
        _record_evidence(histories=histories, evidence=evidence)
    return {
        item_id: _StrandedDispatch(
            evidence=evidence,
            attempts=_attempts(
                evidence=evidence,
                opening_attempts=histories.opening_attempts,
                outcome_attempts=histories.outcome_attempts,
            ),
        )
        for item_id, evidence in histories.latest.items()
        if evidence is not None
    }


def _journal_record(*, line: str) -> dict[str, Any] | None:
    parsed = parse_json(text=line)
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, Any]", parsed)


def _dispatch_evidence(*, record: dict[str, Any]) -> _DispatchEvidence | None:
    if record.get("stage") in {"dispatch-id", "ledger-admit"}:
        return _opening_evidence(record=record)
    if record.get("stage") == "outcome":
        return _outcome_evidence(record=record)
    outcome = record.get("outcome")
    if isinstance(outcome, dict):
        return _terminal_outcome_payload(payload=cast("dict[str, Any]", outcome))
    return None


def _record_evidence(
    *,
    histories: _DispatchHistories,
    evidence: _DispatchEvidence,
) -> None:
    if evidence.status in {"failed", "green"}:
        _record_outcome_evidence(histories=histories, evidence=evidence)
    else:
        _record_opening_evidence(histories=histories, evidence=evidence)


def _record_outcome_evidence(*, histories: _DispatchHistories, evidence: _DispatchEvidence) -> None:
    if evidence.status == "green":
        histories.latest[evidence.work_item_id] = None
        return
    histories.outcome_attempts[evidence.work_item_id] = (
        histories.outcome_attempts.get(evidence.work_item_id, 0) + 1
    )
    histories.latest[evidence.work_item_id] = evidence


def _record_opening_evidence(*, histories: _DispatchHistories, evidence: _DispatchEvidence) -> None:
    if evidence.stage == "dispatch-id":
        latest = histories.latest.get(evidence.work_item_id)
        if latest is None or latest.stage != "ledger-admit":
            histories.opening_attempts[evidence.work_item_id] = (
                histories.opening_attempts.get(evidence.work_item_id, 0) + 1
            )
    elif histories.opening_attempts.get(evidence.work_item_id, 0) == 0:
        histories.opening_attempts[evidence.work_item_id] = 1
    histories.latest[evidence.work_item_id] = evidence


def _opening_evidence(*, record: dict[str, Any]) -> _DispatchEvidence | None:
    work_item_id = record.get("work_item_id")
    stage = record.get("stage")
    if not isinstance(work_item_id, str) or not work_item_id:
        return None
    return _DispatchEvidence(work_item_id=work_item_id, status="claimed", stage=str(stage))


def _outcome_evidence(*, record: dict[str, Any]) -> _DispatchEvidence | None:
    outcome = record.get("outcome")
    if not isinstance(outcome, dict):
        return None
    return _terminal_outcome_payload(payload=cast("dict[str, Any]", outcome))


def _terminal_outcome_payload(*, payload: dict[str, Any]) -> _DispatchEvidence | None:
    work_item_id = payload.get("work_item_id")
    status = payload.get("status")
    stage = payload.get("stage")
    pr_number = payload.get("pr_number")
    merge_sha = payload.get("merge_sha")
    if status not in {"failed", "green"}:
        return None
    if not isinstance(work_item_id, str) or not work_item_id:
        return None
    if not isinstance(stage, str) or not stage:
        return None
    if pr_number is not None and (not isinstance(pr_number, int) or isinstance(pr_number, bool)):
        return None
    if merge_sha is not None and not isinstance(merge_sha, str):
        return None
    return _DispatchEvidence(
        work_item_id=work_item_id,
        status=status,
        stage=stage,
        pr_number=pr_number,
        merge_sha=merge_sha if merge_sha else None,
    )


def _attempts(
    *,
    evidence: _DispatchEvidence,
    opening_attempts: dict[str, int],
    outcome_attempts: dict[str, int],
) -> int:
    if evidence.status == "failed":
        return max(1, outcome_attempts.get(evidence.work_item_id, 0))
    return max(1, opening_attempts.get(evidence.work_item_id, 0))


def _no_watchable_run(*, repo: Path, work_item_id: str) -> None:
    _ = (repo, work_item_id)


def _stranded_dispatch_item(
    *,
    project_root: Path,
    repo: str,
    work_item: WorkItem,
    stranded_dispatch: _StrandedDispatch,
) -> AttentionItem:
    evidence = stranded_dispatch.evidence
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"host-only:{_STRANDED_REASON}:{work_item.id}",
        kind="host-only",
        urgency="high",
        summary=_summary(
            work_item=work_item,
            evidence=evidence,
            attempts=stranded_dispatch.attempts,
        ),
        source_ref=SourceRef(repo=repo, work_item=work_item.id),
        handoff=_handoff(project_root=project_root, work_item=work_item, evidence=evidence),
    )


def _summary(*, work_item: WorkItem, evidence: _DispatchEvidence, attempts: int) -> str:
    attempt_label = "attempt" if attempts == 1 else "attempts"
    if evidence.pr_number is not None and evidence.merge_sha is not None:
        return (
            f"Reconcile merged active work-item {work_item.id}: PR #{evidence.pr_number} "
            f"merged at {evidence.merge_sha}; {evidence.stage} failed across "
            f"{attempts} prior {attempt_label}."
        )
    if evidence.pr_number is not None:
        return (
            f"Inspect stranded active work-item {work_item.id}: PR #{evidence.pr_number} "
            f"has no recorded merge SHA; {evidence.stage} failed across "
            f"{attempts} prior {attempt_label}."
        )
    return (
        f"Release stranded active work-item {work_item.id}: latest dispatch evidence is "
        f"{evidence.stage} with no PR; {attempts} prior {attempt_label}."
    )


def _handoff(*, project_root: Path, work_item: WorkItem, evidence: _DispatchEvidence) -> Handoff:
    if evidence.pr_number is not None and evidence.merge_sha is not None:
        command = reconcile_merged_command(project_root=project_root, work_item=work_item.id)
    elif evidence.pr_number is not None:
        command = pr_view_command(project_root=project_root, pr_number=evidence.pr_number)
    else:
        command = release_to_ready_command(project_root=project_root, work_item=work_item.id)
    return Handoff(kind="shell", command=command)
