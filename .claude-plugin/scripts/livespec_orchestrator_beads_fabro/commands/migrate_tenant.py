"""`migrate-tenant` - one-shot beads tenant schema bootstrap.

An orchestrator-PRIVATE maintenance command for onboarding a pre-created
beads tenant, or for applying the mechanical L2 migration to an existing
one. The tenant database itself is an operator-side precondition; this
command never creates databases and assumes the repository already has the
`.beads/` pointer files produced by the governed `beads pointer initialization` step.

The migration composes the two idempotent primitives operators previously
ran by hand: register the livespec custom statuses, then seed real `rank`
keys for every live head using the legacy beads-native
`priority -> captured_at -> id` order.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands.rebalance_ranks import LegacySeedRow, legacy_seed
from livespec_orchestrator_beads_fabro.io import write_stdout
from livespec_orchestrator_beads_fabro.store import (
    materialize_work_items,
    read_work_item_native_priorities,
    read_work_items,
    register_custom_statuses,
    update_work_item_rank,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["main", "migrate_tenant"]

_LIVESPEC_DONE = "done"


def migrate_tenant(*, config: StoreConfig) -> int:
    """Register custom statuses and backfill live-head ranks.

    Returns the number of live heads whose rank changed. Re-running after a
    successful migration is a no-op because the same legacy seed order
    produces the same evenly spaced keys.
    """
    register_custom_statuses(path=config)
    return _backfill_legacy_ranks(config=config)


def _backfill_legacy_ranks(*, config: StoreConfig) -> int:
    items = materialize_work_items(records=read_work_items(path=config))
    priorities = read_work_item_native_priorities(path=config)
    live = [item for item in items.values() if item.status != _LIVESPEC_DONE]
    seeded = legacy_seed(rows=_legacy_rows(items=live, priorities=priorities))
    changed = 0
    for item_id, rank in seeded:
        item = items[item_id]
        if item.rank == rank:
            continue
        update_work_item_rank(path=config, item=replace(item, rank=rank))
        changed += 1
    return changed


def _legacy_rows(*, items: list[WorkItem], priorities: dict[str, int]) -> list[LegacySeedRow]:
    return [
        LegacySeedRow(
            priority=priorities[item.id],
            captured_at=item.captured_at,
            work_item_id=item.id,
        )
        for item in items
    ]


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate-tenant",
        description=(
            "Register livespec custom statuses and backfill legacy ranks. "
            "Precondition: the tenant DB exists and .beads pointer files have "
            "already been initialized by the governed beads pointer step."
        ),
    )
    _ = parser.add_argument("--work-items-path", dest="work_items_path", default=None)
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    config = resolve_store_config(cwd=project_root, work_items_arg=args.work_items_path)
    rekeyed = migrate_tenant(config=config)
    _ = write_stdout(
        text=f"migrate-tenant: statuses registered; re-keyed {rekeyed} live work-item(s)\n"
    )
    return 0
