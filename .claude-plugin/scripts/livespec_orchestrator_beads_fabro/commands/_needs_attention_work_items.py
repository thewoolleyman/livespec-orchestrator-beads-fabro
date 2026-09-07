"""Work-item derived attention lanes for needs-attention."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef
from livespec_runtime.cross_repo.types import CrossRepoManifest, RefStatus
from livespec_runtime.needs_attention import ImplNextOutput, WorkItemHumanValveLane
from livespec_runtime.work_items.lifecycle import lane_of

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import repo_run_attribution
from livespec_orchestrator_beads_fabro.commands._drive_valve_predicates import (
    awaits_dispatcher_admission,
    can_approve_item,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroPort,
    FabroPsResult,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_answer_disposition import (
    answer_disposition_summary,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    dispatcher_loop_command,
    drive_command,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_needs_human_question import (
    needs_human_question_summary,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_stranded_dispatch import (
    stranded_dispatch_items as _stranded_dispatch_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_waits import (
    acceptance_wait_summary,
    host_only_items,
    provider_exhaustion_items,
    provider_exhaustion_wait_active,
)
from livespec_orchestrator_beads_fabro.commands.next import rank_candidates
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "auto_admission_items",
    "host_only_items",
    "human_valves",
    "impl_next",
    "live_dispatch_lock_lookup",
    "provider_exhaustion_items",
    "stranded_dispatch_items",
    "watchable_fabro_run_item_ids",
    "watchable_fabro_run_lookup",
]


def impl_next(
    *,
    project_root: Path,
    items: list[WorkItem],
    manifest: CrossRepoManifest,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None = None,
) -> ImplNextOutput | None:
    if provider_exhaustion_wait_active(project_root=project_root):
        return None
    ranked = rank_candidates(
        items=[item for item in items if item.factory_safety is None],
        manifest=manifest,
        sibling_status_lookup=sibling_status_lookup,
    )
    if not ranked:
        return None
    candidate = ranked[0]
    work_item = str(candidate["work_item_ref"])
    return ImplNextOutput(
        work_item=work_item,
        summary=str(candidate["reason"]),
        command=drive_command(project_root=project_root, action_id=f"impl:{work_item}"),
        urgency="medium",
    )


def human_valves(
    *,
    project_root: Path,
    items: list[WorkItem],
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None = None,
    answer_disposition_labels: Mapping[str, Sequence[str]] | None = None,
) -> list[WorkItemHumanValveLane]:
    lanes: list[WorkItemHumanValveLane] = []
    answer_labels: Mapping[str, Sequence[str]] = (
        answer_disposition_labels if answer_disposition_labels is not None else {}
    )
    for item in items:
        item_id = item.id
        title = item.title
        status = item.status
        lane_reason = lane_of(
            item=item,
            index=index,
            manifest=manifest,
            sibling_status_lookup=sibling_status_lookup,
        ).reason
        if can_approve_item(item=item, cwd=project_root):
            lanes.append(
                _valve(
                    verb="approve",
                    work_item=item_id,
                    summary=f"Approve pending work-item {item_id}: {title}",
                    project_root=project_root,
                    action_id=f"approve:{item_id}",
                )
            )
        elif status == "acceptance":
            lanes.append(
                _valve(
                    verb="accept",
                    work_item=item_id,
                    summary=acceptance_wait_summary(
                        project_root=project_root,
                        item=item,
                        default_summary=f"Accept completed work-item {item_id}: {title}",
                    ),
                    project_root=project_root,
                    action_id=f"accept:{item_id}",
                )
            )
        elif status == "blocked" and lane_reason == "needs-human":
            lanes.append(
                _valve(
                    verb="resolve-blocked",
                    work_item=item_id,
                    # The terminated run's own account of why the loop gave up
                    # and where the work survived, then WHO may answer the
                    # question it parked on. Enrichment only: an unreadable run
                    # leaves the title-only summary standing, because the
                    # decision is already waiting in the ledger.
                    summary=answer_disposition_summary(
                        project_root=project_root,
                        item=item,
                        raw_labels=answer_labels.get(item_id, ()),
                        default_summary=needs_human_question_summary(
                            project_root=project_root,
                            item_id=item_id,
                            default_summary=(
                                f"Resolve human-needed block for work-item {item_id}: {title}"
                            ),
                        ),
                    ),
                    project_root=project_root,
                    action_id=f"resolve-blocked:{item_id}:ready",
                )
            )
    return lanes


def auto_admission_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
) -> list[AttentionItem]:
    return [
        _awaiting_admission_item(project_root=project_root, repo=repo, item=item)
        for item in items
        if awaits_dispatcher_admission(item=item, cwd=project_root)
    ]


def stranded_dispatch_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
    held_work_item_ids: frozenset[str] = frozenset(),
) -> list[AttentionItem]:
    return _stranded_dispatch_items(
        project_root=project_root,
        repo=repo,
        items=items,
        live_lock_lookup=_live_dispatch_lock,
        watchable_run_lookup=_watchable_fabro_run,
        held_work_item_ids=held_work_item_ids,
    )


def live_dispatch_lock_lookup(*, repo: Path, work_item_id: str) -> object | None:
    return _live_dispatch_lock(repo=repo, work_item_id=work_item_id)


def watchable_fabro_run_lookup(*, repo: Path, work_item_id: str) -> object | None:
    return _watchable_fabro_run(repo=repo, work_item_id=work_item_id)


def watchable_fabro_run_item_ids(*, repo: Path) -> frozenset[str]:
    result = _fabro_ps(repo=repo)
    if result.command.exit_code != 0:
        return frozenset()
    attribution = repo_run_attribution(repo=repo)
    return frozenset(
        work_item_id
        for run in result.runs
        if (work_item_id := attribution.work_item_id_for(run=run)) is not None
        and run.status_kind in {"runnable", "running"}
    )


def _live_dispatch_lock(*, repo: Path, work_item_id: str) -> object | None:
    return live_dispatch_lock(repo=repo, work_item_id=work_item_id)


def _watchable_fabro_run(*, repo: Path, work_item_id: str) -> object | None:
    result = _fabro_ps(repo=repo)
    if result.command.exit_code != 0:
        return None
    attribution = repo_run_attribution(repo=repo)
    return next(
        (
            run
            for run in result.runs
            if attribution.owns(run=run, work_item_id=work_item_id)
            and run.status_kind in {"runnable", "running"}
        ),
        None,
    )


def _fabro_ps(*, repo: Path) -> FabroPsResult:
    return FabroPort(
        fabro_bin=resolve_fabro_bin(cwd=repo),
        target=FabroTarget(),
        runner=ShellCommandRunner(),
        cwd=repo,
    ).ps(timeout_seconds=15)


def _awaiting_admission_item(*, project_root: Path, repo: str, item: WorkItem) -> AttentionItem:
    return AttentionItem(
        # `internal` is a ratified `kind`, but it is NOT a ratified stable-ID
        # PREFIX, so `internal:...` failed the runtime validator outright. The
        # orchestrator-owned fact form is `hygiene:<type>:<resource>`; the kind
        # is unchanged because the validator governs the id alone.
        id=f"hygiene:awaiting-admission:{item.id}",
        kind="internal",
        urgency="medium",
        summary=(
            f"Work-item {item.id} is pending automatic approval; "
            "awaiting the next Dispatcher admission pass."
        ),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(kind="shell", command=dispatcher_loop_command(project_root=project_root)),
    )


def _valve(
    *,
    verb: str,
    work_item: str,
    summary: str,
    project_root: Path,
    action_id: str,
) -> WorkItemHumanValveLane:
    return WorkItemHumanValveLane(
        verb=verb,
        work_item=work_item,
        summary=summary,
        action_id=action_id,
        command=drive_command(project_root=project_root, action_id=action_id),
    )
