"""`migrate-plan-records` — the one-shot, idempotent plan-record migration.

The orchestrator-PRIVATE maintenance command contracts.md's plan-record
conformance clauses require to run once per family tenant before the
error-verdict plan-record checks arm there: it writes the missing `plan_slug`
tags, the missing `associated_work_item_id` anchors, and the missing typed
`next_action` pointers that every plan predating those contracts lacks.

WHAT IT DECIDES LIVES NEXT DOOR. `_plan_record_migration` holds every judgement
— the slug derivation and its collision refusal, whether an anchor already
stands, what a handoff seeds — and this module is only the reads, the writes,
and the report. That split is what makes "running it twice changes nothing"
checkable without a repository or a tenant.

EVERY LEDGER WRITE GOES THROUGH THIS PLUGIN'S EXISTING STORE BRIDGE, as the
contract requires: `tag_epic_plan_slug` and `set_next_action`, the same
primitives the `plan` front-end uses, never a hand-rolled metadata update. It
matters more here than elsewhere: `bd update --metadata` replaces a nested
object wholesale, so a bespoke `next_action` write would destroy the sub-keys it
omitted, and a migration doing that across a whole tenant would be the largest
possible instance of that loss.

RUNNING IT IS ONE THING; LANDING IT IS ANOTHER. The anchor files this writes are
repository files, and the contract requires them to reach master through the
repository's ordinary worktree → pull-request → merge discipline. This command
writes the working tree and reports what it wrote; it never commits, and the
fleet-wide run across tenants is an operator follow-up.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._plan_identity import (
    PLAN_ANCHOR_FILENAME,
    PLAN_SLUG_METADATA_KEY,
    tag_epic_plan_slug,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NEXT_ACTION_METADATA_KEY,
    parse_next_action,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_record_migration import (
    MIGRATION_SESSION,
    PlanEpic,
    PlanRecordMigrationReport,
    SlugDecision,
    anchor_content,
    render_report,
    seeded_next_action,
    slug_decisions,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import HANDOFF_KIND, read_timeline
from livespec_orchestrator_beads_fabro.io import write_stdout

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["main", "migrate_plan_records"]

_EPIC_TYPE = "epic"
# The closed spellings: a record carries the beads-native `closed`, and the
# livespec name `done` maps onto it. Everything else is an open epic.
_CLOSED_STATUSES = frozenset({"closed", "done"})
_PLAN_DIR = "plan"
_ARCHIVE_DIR = "archive"


def migrate_plan_records(
    *,
    config: StoreConfig,
    project_root: Path,
    now: str,
) -> PlanRecordMigrationReport:
    """Migrate one tenant's plan records and its repository's plan anchors.

    The order is load-bearing: slugs are decided and written first, because the
    anchors and the `next_action` seeds both key on which epic carries which
    slug, and an epic tagged in this same run must anchor its own directory
    rather than reading as unassigned for one more migration.
    """
    epics = _plan_epics(config=config)
    decisions = slug_decisions(epics=epics)
    slugs_written = _write_slugs(config=config, epics=epics, decisions=decisions)
    epic_by_slug = _epic_by_slug(epics=epics, decisions=decisions)
    anchors_written, anchors_skipped = _write_anchors(
        project_root=project_root, epic_by_slug=epic_by_slug
    )
    seeded, seeds_skipped = _seed_next_actions(
        config=config,
        project_root=project_root,
        epics=epics,
        epic_by_slug=epic_by_slug,
        now=now,
    )
    return PlanRecordMigrationReport(
        slugs_written=tuple(slugs_written),
        anchors_written=tuple(anchors_written),
        next_actions_seeded=tuple(seeded),
        skipped=tuple([*_slug_skips(epics=epics), *anchors_skipped, *seeds_skipped]),
        refused=tuple(_slug_refusals(decisions=decisions)),
    )


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate-plan-records",
        description=(
            "Write the missing plan_slug tags, associated_work_item_id anchors, "
            "and typed next_action pointers for one tenant. Idempotent: a second "
            "run reports zero writes. Anchor files land through the repository's "
            "ordinary worktree, pull-request and merge discipline."
        ),
    )
    _ = parser.add_argument("--work-items-path", dest="work_items_path", default=None)
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    config = resolve_store_config(cwd=project_root, work_items_arg=args.work_items_path)
    report = migrate_plan_records(config=config, project_root=project_root, now=_utc_now_iso())
    _ = write_stdout(text=render_report(report=report))
    return 0


def _plan_epics(*, config: StoreConfig) -> tuple[PlanEpic, ...]:
    client = make_beads_client(config=config)
    epics = [
        _plan_epic(record=record)
        for record in client.list_issues()
        if _text(value=record.get("issue_type")) == _EPIC_TYPE
    ]
    return tuple(sorted(epics, key=lambda epic: epic.epic_id))


def _plan_epic(*, record: BeadsRecord) -> PlanEpic:
    metadata = _metadata(record=record)
    # Native fields win over the metadata copies the retired content-field
    # encoding left behind, exactly as the store's own record mapping merges
    # them, so an epic written by either build reads the same here.
    content = {**metadata, **record}
    return PlanEpic(
        epic_id=_text(value=record.get("id")),
        title=_text(value=record.get("title")),
        notes=_text(value=content.get("notes")),
        spec_commitment_hint=_text(value=record.get("spec_id")),
        plan_slug=_text(value=metadata.get(PLAN_SLUG_METADATA_KEY)),
        is_open=_text(value=record.get("status")) not in _CLOSED_STATUSES,
        has_next_action=parse_next_action(value=metadata.get(NEXT_ACTION_METADATA_KEY)) is not None,
    )


def _write_slugs(
    *,
    config: StoreConfig,
    epics: Sequence[PlanEpic],
    decisions: Sequence[SlugDecision],
) -> list[str]:
    titles = {epic.epic_id: epic.title for epic in epics}
    written: list[str] = []
    for decision in decisions:
        if decision.holder_id is not None:
            continue
        _ = tag_epic_plan_slug(
            config=config,
            epic_id=decision.epic_id,
            title=titles[decision.epic_id],
            slug=decision.slug,
        )
        written.append(f"{decision.epic_id} plan_slug={decision.slug}")
    return written


def _slug_skips(*, epics: Sequence[PlanEpic]) -> list[str]:
    return [
        f"{epic.epic_id} already carries plan_slug={epic.plan_slug}"
        for epic in epics
        if epic.plan_slug != ""
    ]


def _slug_refusals(*, decisions: Sequence[SlugDecision]) -> list[str]:
    return [
        _slug_refusal(decision=decision) for decision in decisions if decision.holder_id is not None
    ]


def _slug_refusal(*, decision: SlugDecision) -> str:
    derives = f"{decision.epic_id} derives plan_slug={decision.slug}"
    return f"{derives}, already carried by {decision.holder_id}"


def _epic_by_slug(
    *,
    epics: Sequence[PlanEpic],
    decisions: Sequence[SlugDecision],
) -> dict[str, str]:
    mapping = {epic.plan_slug: epic.epic_id for epic in epics if epic.plan_slug != ""}
    for decision in decisions:
        if decision.holder_id is None:
            mapping[decision.slug] = decision.epic_id
    return mapping


def _write_anchors(
    *,
    project_root: Path,
    epic_by_slug: dict[str, str],
) -> tuple[list[str], list[str]]:
    written: list[str] = []
    skipped: list[str] = []
    for directory in _plan_directories(project_root=project_root):
        anchor = directory / PLAN_ANCHOR_FILENAME
        current = anchor.read_text(encoding="utf-8") if anchor.is_file() else None
        content = anchor_content(current=current, epic_id=epic_by_slug.get(directory.name))
        relative = anchor.relative_to(project_root).as_posix()
        if content is None:
            skipped.append(f"{relative} already anchored")
            continue
        _ = anchor.write_text(f"{content}\n", encoding="utf-8")
        written.append(f"{relative} -> {content}")
    return written, skipped


def _seed_next_actions(
    *,
    config: StoreConfig,
    project_root: Path,
    epics: Sequence[PlanEpic],
    epic_by_slug: dict[str, str],
    now: str,
) -> tuple[list[str], list[str]]:
    live = _live_slugs(project_root=project_root)
    slug_of = {epic_id: slug for slug, epic_id in epic_by_slug.items()}
    seeded: list[str] = []
    skipped: list[str] = []
    for epic in epics:
        # An archived or slugless plan has no live directory to resume, and a
        # closed epic has nothing left to do; neither owes a pointer.
        if not epic.is_open or slug_of.get(epic.epic_id) not in live:
            continue
        if epic.has_next_action:
            skipped.append(f"{epic.epic_id} already carries next_action")
            continue
        action = seeded_next_action(
            handoff_body=_newest_handoff(config=config, epic_id=epic.epic_id),
            prefix=config.prefix,
        )
        _ = set_next_action(
            config=config,
            epic_id=epic.epic_id,
            action=action,
            session=MIGRATION_SESSION,
            now=now,
        )
        seeded.append(f"{epic.epic_id} kind={action.kind} ref={action.ref!r}")
    return seeded, skipped


def _newest_handoff(*, config: StoreConfig, epic_id: str) -> str | None:
    bodies = [
        entry.body
        for entry in read_timeline(config=config, epic_id=epic_id)
        if entry.kind == HANDOFF_KIND
    ]
    if not bodies:
        return None
    return bodies[-1]


def _plan_directories(*, project_root: Path) -> list[Path]:
    plan_dir = project_root / _PLAN_DIR
    live = [child for child in _subdirectories(parent=plan_dir) if child.name != _ARCHIVE_DIR]
    return [*live, *_subdirectories(parent=plan_dir / _ARCHIVE_DIR)]


def _live_slugs(*, project_root: Path) -> set[str]:
    return {
        child.name
        for child in _subdirectories(parent=project_root / _PLAN_DIR)
        if child.name != _ARCHIVE_DIR
    }


def _subdirectories(*, parent: Path) -> list[Path]:
    if not parent.is_dir():
        return []
    return sorted((child for child in parent.iterdir() if child.is_dir()), key=lambda p: p.name)


def _metadata(*, record: BeadsRecord) -> dict[str, Any]:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    return dict(cast("dict[str, Any]", metadata))


def _text(*, value: object) -> str:
    return value if isinstance(value, str) else ""


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
