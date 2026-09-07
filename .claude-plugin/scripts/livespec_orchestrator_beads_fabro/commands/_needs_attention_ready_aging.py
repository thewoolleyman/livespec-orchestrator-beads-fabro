"""Ready-work aging attention lane."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef
from livespec_runtime.cross_repo.types import CrossRepoManifest, RefStatus
from livespec_runtime.work_items.lifecycle import is_item_ready
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_READY_AGING_THRESHOLD_HOURS,
    resolve_ready_aging_threshold_hours,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ReadyAgingContext",
    "ReadyAgingSeams",
    "ready_aging_items",
    "utc_now_iso",
]

_SECONDS_PER_HOUR = 60 * 60


@dataclass(frozen=True, kw_only=True)
class _ReadyAge:
    item: WorkItem
    age_hours: int | None


@dataclass(frozen=True, kw_only=True)
class ReadyAgingContext:
    project_root: Path
    repo: str
    manifest: CrossRepoManifest


@dataclass(frozen=True, kw_only=True)
class ReadyAgingSeams:
    live_lock_lookup: Callable[..., object | None]
    watchable_run_item_ids: Callable[..., Collection[str]]
    now_iso: str | None = None


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ready_aging_items(
    *,
    context: ReadyAgingContext,
    items: list[WorkItem],
    ready_dwell_instants: dict[str, str | None],
    sibling_status_lookup: Callable[[str, str], RefStatus] | None = None,
    seams: ReadyAgingSeams,
) -> list[AttentionItem]:
    eligible = _eligible_ready_items(
        items=items,
        manifest=context.manifest,
        sibling_status_lookup=sibling_status_lookup,
    )
    if not eligible or _dispatch_in_flight(
        project_root=context.project_root,
        items=items,
        live_lock_lookup=seams.live_lock_lookup,
        watchable_run_item_ids=seams.watchable_run_item_ids,
    ):
        return []
    threshold_hours = unsafe_perform_io(
        resolve_ready_aging_threshold_hours(cwd=context.project_root).value_or(
            DEFAULT_READY_AGING_THRESHOLD_HOURS
        )
    )
    now_iso = utc_now_iso() if seams.now_iso is None else seams.now_iso
    ages = [
        _age_for(
            item=item,
            ready_since=ready_dwell_instants.get(item.id),
            now_iso=now_iso,
        )
        for item in eligible
    ]
    aged = [age for age in ages if age.age_hours is not None and age.age_hours > threshold_hours]
    if not aged:
        return []
    unknown = [age.item.id for age in ages if age.age_hours is None]
    oldest = max(aged, key=lambda age: age.age_hours or 0)
    return [
        ConformanceContext(project_root=context.project_root, repo=context.repo).candidate(
            id=f"hygiene:ready-aging:{context.repo}",
            kind="hygiene",
            urgency="high",
            summary=_summary(
                aged_count=len(aged),
                threshold_hours=threshold_hours,
                oldest=oldest,
                unknown=unknown,
            ),
            source_ref=SourceRef(repo=context.repo),
            handoff=Handoff(
                kind="shell",
                command=_handoff_command(project_root=context.project_root, repo=context.repo),
            ),
        )
    ]


def _eligible_ready_items(
    *,
    items: list[WorkItem],
    manifest: CrossRepoManifest,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None,
) -> list[WorkItem]:
    index = {item.id: item for item in items}
    return [
        item
        for item in items
        if item.factory_safety is None
        and is_item_ready(
            item=item,
            index=index,
            manifest=manifest,
            sibling_status_lookup=sibling_status_lookup,
        )
    ]


def _dispatch_in_flight(
    *,
    project_root: Path,
    items: list[WorkItem],
    live_lock_lookup: Callable[..., object | None],
    watchable_run_item_ids: Callable[..., Collection[str]],
) -> bool:
    item_ids = frozenset(item.id for item in items)
    live_watchable_ids = frozenset(watchable_run_item_ids(repo=project_root))
    return bool(item_ids & live_watchable_ids) or any(
        live_lock_lookup(repo=project_root, work_item_id=item.id) is not None for item in items
    )


def _age_for(*, item: WorkItem, ready_since: str | None, now_iso: str) -> _ReadyAge:
    since = _parse_instant(instant=ready_since)
    now = _parse_instant(instant=now_iso)
    if since is None or now is None or now < since:
        return _ReadyAge(item=item, age_hours=None)
    return _ReadyAge(
        item=item,
        age_hours=int((now - since).total_seconds() // _SECONDS_PER_HOUR),
    )


def _parse_instant(*, instant: str | None) -> datetime | None:
    if instant is None:
        return None
    parsed = attempt(
        action=lambda: datetime.fromisoformat(instant.removesuffix("Z") + "+00:00"),
        exceptions=(ValueError,),
    )
    if isinstance(parsed, AttemptFailure):
        return None
    return parsed.astimezone(timezone.utc)


def _summary(
    *,
    aged_count: int,
    threshold_hours: int,
    oldest: _ReadyAge,
    unknown: list[str],
) -> str:
    noun = "work-item has" if aged_count == 1 else "work-items have"
    unknown_suffix = f"; age-unknown: {', '.join(unknown)}" if unknown else ""
    return (
        f"{aged_count} ready {noun} waited past {threshold_hours}h; "
        f"oldest age {oldest.age_hours}h on oldest work-item {oldest.item.id}. "
        "Unblock handoff: start or inspect the Dispatcher admission pass."
        f"{unknown_suffix}"
    )


def _handoff_command(*, project_root: Path, repo: str) -> str:
    prompt = (
        f"ready-aging {repo} in repository {project_root}. "
        "Use the live dispatch lock or watchable Fabro run as the in-flight "
        "authority; otherwise start or inspect the Dispatcher admission pass."
    )
    return f"cd {shlex.quote(str(project_root))} && codex exec {shlex.quote(prompt)} < /dev/null"
