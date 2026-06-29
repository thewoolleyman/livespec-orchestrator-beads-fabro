"""`rebalance-ranks` — on-demand bulk re-key of work-item ranks.

An orchestrator-PRIVATE maintenance command (not a query-only
thin-transport skill, not a contract CLI): it deterministically re-keys
the live work-item queue so the fractional `rank` keys stay short and
evenly spaced. `rank` is the sole ordering authority
(SPECIFICATION/contracts.md), so a long run of single-position inserts
can fragment the keys; this command compacts them WITHOUT changing the
order. It is on-demand only and NEVER auto-fires.

Two pure entry points back it:

- `rebalanced(items)` — the rebalance core: order the items by the
  canonical `ready_sort_key` (`(rank, id)`) and assign `n` evenly-spaced
  fresh keys via `livespec_runtime.work_items.rank.n_keys_between`,
  preserving the order. `main` walks the live (non-`done`) heads through
  this and writes each changed key back in place.
- `legacy_seed(rows)` — the one-time L2 backfill primitive (reused by the
  fleet's L2 status+rank migration, not by `main`): order the
  pre-migration rows by the legacy `priority → captured_at → id` key
  (SPECIFICATION/contracts.md) and assign evenly-spaced fresh keys, so a
  tenant migrated off the dropped `priority` column lands a real `rank`
  order matching its old priority order.
"""

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_runtime.work_items.lifecycle import ready_sort_key
from livespec_runtime.work_items.rank import n_keys_between

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.store import (
    materialize_work_items,
    read_work_items,
    update_work_item_rank,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["LegacySeedRow", "legacy_seed", "main", "rebalanced"]

_LIVESPEC_DONE = "done"


@dataclass(frozen=True, kw_only=True)
class LegacySeedRow:
    """One pre-migration row for the L2 `rank` backfill seed.

    Carries the legacy ordering signal the dropped logical `priority`
    field is replaced by: `priority` (the beads-native column, lower =
    more urgent), `captured_at` (ISO-8601), and the work-item `id`.
    """

    priority: int
    captured_at: str
    work_item_id: str


def rebalanced(*, items: list[WorkItem]) -> list[WorkItem]:
    """Return `items` re-keyed with evenly-spaced ranks, order preserved.

    Orders by the canonical `ready_sort_key` (`(rank, id)`) — the same
    authority `next` and the Dispatcher compose — then assigns `n`
    evenly-spaced fresh keys. The output preserves that order; only each
    item's `rank` changes. An empty input yields an empty list.
    """
    ordered = sorted(items, key=ready_sort_key)
    keys = n_keys_between(a=None, b=None, n=len(ordered))
    return [replace(item, rank=key) for item, key in zip(ordered, keys, strict=True)]


def legacy_seed(*, rows: list[LegacySeedRow]) -> list[tuple[str, str]]:
    """Return `(work_item_id, rank)` pairs for the one-time L2 backfill.

    Orders the pre-migration rows by the legacy `priority → captured_at →
    id` key and assigns `n` evenly-spaced fresh keys, so a tenant migrated
    off the dropped `priority` column lands a real `rank` order matching
    its old priority order. The pairs are returned in seed order. An empty
    input yields an empty list.
    """
    ordered = sorted(rows, key=lambda row: (row.priority, row.captured_at, row.work_item_id))
    keys = n_keys_between(a=None, b=None, n=len(ordered))
    return [(row.work_item_id, key) for row, key in zip(ordered, keys, strict=True)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rebalance-ranks")
    _ = parser.add_argument("--work-items-path", dest="work_items_path", default=None)
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    config = resolve_store_config(cwd=project_root, work_items_arg=args.work_items_path)
    rekeyed = _rebalance_live(config=config)
    _ = sys.stdout.write(f"rebalance-ranks: re-keyed {rekeyed} live work-item(s)\n")
    return 0


def _rebalance_live(*, config: StoreConfig) -> int:
    """Re-key every live (non-`done`) head in place; return the changed count."""
    items = list(materialize_work_items(records=read_work_items(path=config)).values())
    live = [item for item in items if item.status != _LIVESPEC_DONE]
    changed = 0
    for item in rebalanced(items=live):
        before = next(original for original in live if original.id == item.id)
        if item.rank == before.rank:
            continue
        update_work_item_rank(path=config, item=item)
        changed += 1
    return changed
