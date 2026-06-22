"""Cross-repo manifest + dependency-entry helpers shared by next + list-work-items.

Per `livespec/SPECIFICATION/contracts.md` v072 §"Cross-repo dependency
awareness" — the impl-beads consumers MUST call
`livespec_runtime.cross_repo.resolve_ref` for every typed `depends_on`
entry and treat `OPEN` as a blocking state. This module bundles:

- `load_manifest(project_root)` — read `.livespec.jsonc` and extract
  the `cross_repo_targets` block as a typed `CrossRepoManifest`.
  Returns an empty manifest when the file or block is absent; this
  is the legitimate "no cross-repo deps configured" state.
- `parse_entry(raw)` — dispatch a raw `depends_on` entry (bare string
  or typed dict) into a typed `DependsOnEntry`. Bare strings are
  converted to `LocalDependency` for forward-compatibility with the
  pre-v072 plaintext stores; the data-migration script has the
  authoritative typed-form conversion.
- `is_item_ready(item, *, index, manifest)` — predicate consumed by
  the next ranker and the list-work-items "ready" filter. An item is
  ready iff its status is "open" AND no typed `depends_on` entry
  resolves to `OPEN` via `resolve_ref`.
- `ready_sort_key(item)` — the single canonical ranking authority both
  the next ranker and the Fabro Dispatcher's drain order compose, so
  the two never diverge on which ready item runs first.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from livespec_runtime.cross_repo.errors import CrossRepoSchemaError
from livespec_runtime.cross_repo.resolve import resolve_ref
from livespec_runtime.cross_repo.types import (
    CrossRepoManifest,
    CrossRepoTarget,
    DependsOnEntry,
    LocalDependency,
    RefStatus,
    parse_cross_repo_manifest,
    parse_depends_on_entry,
)

from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.store import read_work_items
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "is_item_ready",
    "load_manifest",
    "parse_entry",
    "ready_sort_key",
]


_LIVESPEC_CONFIG = ".livespec.jsonc"


def load_manifest(*, project_root: Path) -> CrossRepoManifest:
    """Return the project's CrossRepoManifest, or an empty one if absent.

    Reads `<project_root>/.livespec.jsonc` and extracts the top-level
    `cross_repo_targets` block. A missing file, missing block, or
    malformed manifest all collapse to the empty-manifest sentinel —
    the impl-beads consumers tolerate degraded manifest views and
    let the spec-side doctor's `cross-repo-targets-wellformedness`
    invariant flag the malformed-config case.
    """
    config_path = project_root / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return CrossRepoManifest(targets={})
    raw_text = config_path.read_text(encoding="utf-8")
    try:
        parsed = _jsonc.loads(text=raw_text)
    except _jsonc.JsoncParseError:
        return CrossRepoManifest(targets={})
    if not isinstance(parsed, dict):
        return CrossRepoManifest(targets={})
    parsed_dict = cast("dict[str, Any]", parsed)
    block_raw = parsed_dict.get("cross_repo_targets")
    if not isinstance(block_raw, dict):
        return CrossRepoManifest(targets={})
    block = cast("dict[str, Any]", block_raw)
    try:
        return parse_cross_repo_manifest(parsed=block)
    except CrossRepoSchemaError:
        return CrossRepoManifest(targets={})


def parse_entry(*, raw: object) -> DependsOnEntry | None:
    """Dispatch a raw entry into a typed `DependsOnEntry`.

    Returns `None` for entries that cannot be parsed (legacy malformed
    shape, unknown discriminator). The caller decides how to treat
    None — the next ranker conservatively treats unparseable entries
    as blocking so a malformed record cannot accidentally surface as
    a "ready" candidate.
    """
    if isinstance(raw, str):
        return LocalDependency(work_item_id=raw)
    if isinstance(raw, dict):
        typed_raw = cast("dict[str, Any]", raw)
        try:
            return parse_depends_on_entry(parsed=typed_raw)
        except CrossRepoSchemaError:
            return None
    return None


def _local_lookup_for(*, index: dict[str, WorkItem]) -> Callable[[str], RefStatus]:
    """Build the `local_status_lookup` callable resolve_ref expects.

    Missing ids → `UNKNOWN` per the doctor convention; closed items →
    `CLOSED`; everything else (open / blocked / in_progress / deferred)
    → `OPEN`. The ranker's exclusion gate fires only on `OPEN`, so a
    missing reference does NOT exclude the candidate (the doctor's
    `no-orphan-dependency` invariant is the right surface for that).
    """

    def _lookup(work_item_id: str) -> RefStatus:
        record = index.get(work_item_id)
        if record is None:
            return RefStatus.UNKNOWN
        if record.status == "closed":
            return RefStatus.CLOSED
        return RefStatus.OPEN

    return _lookup


def _try_read_sibling(*, target: CrossRepoTarget) -> dict[str, WorkItem] | None:
    if target.local_clone is None:
        return None
    try:
        config = resolve_store_config(cwd=target.local_clone, work_items_arg=None)
        return {item.id: item for item in read_work_items(path=config)}
    except Exception:
        return None


def _sibling_lookup_for(*, manifest: CrossRepoManifest) -> Callable[[str, str], RefStatus] | None:
    """Build a sibling_status_lookup from available local_clone reads.

    Reads work items from each manifest target that provides a
    `local_clone` path, tolerating any read failure per the
    tolerate-partial-visibility contract. Returns None when no sibling
    store is readable, which causes resolve_ref to return UNKNOWN for
    sibling_work_item entries.
    """
    sibling_indices: dict[str, dict[str, WorkItem]] = {}
    for slug, target in manifest.targets.items():
        result = _try_read_sibling(target=target)
        if result is not None:
            sibling_indices[slug] = result
    if not sibling_indices:
        return None

    def _lookup(repo: str, work_item_id: str) -> RefStatus:
        index = sibling_indices.get(repo)
        if index is None:
            return RefStatus.UNKNOWN
        record = index.get(work_item_id)
        if record is None:
            return RefStatus.UNKNOWN
        if record.status == "closed":
            return RefStatus.CLOSED
        return RefStatus.OPEN

    return _lookup


def _entry_blocks(
    *,
    raw: object,
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None,
) -> bool:
    """Return True iff the raw entry resolves to `OPEN` via `resolve_ref`.

    Unparseable entries (per `parse_entry` returning None) are treated
    as blocking — a malformed depends_on cell must not let a candidate
    slip through the ranker.
    """
    entry = parse_entry(raw=raw)
    if entry is None:
        return True
    status = resolve_ref(
        entry=entry,
        manifest=manifest,
        local_status_lookup=_local_lookup_for(index=index),
        sibling_status_lookup=sibling_status_lookup,
    )
    return status == RefStatus.OPEN


def is_item_ready(
    *,
    item: WorkItem,
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
) -> bool:
    """Return True iff the item is OPEN and no depends_on entry is OPEN.

    Mirrors the contract: only `RefStatus.OPEN` entries exclude a
    candidate. `CLOSED` and `UNKNOWN` resolutions do not exclude;
    they signify the dependency has cleared (or its state can't be
    determined, which the doctor invariants surface separately).
    """
    if item.status != "open":
        return False
    sibling_lookup = _sibling_lookup_for(manifest=manifest)
    return not any(
        _entry_blocks(raw=raw, index=index, manifest=manifest, sibling_status_lookup=sibling_lookup)
        for raw in item.depends_on
    )


_GAP_TIED_RANK = 0
_FREEFORM_RANK = 1


def ready_sort_key(item: WorkItem) -> tuple[int, int, str, str]:
    """Canonical ranking key for ready items, composed by next + Dispatcher.

    Ordering (ascending tuple comparison):

    1. `priority` — lower number is more urgent.
    2. `origin` — gap-tied before freeform at the same priority.
    3. `captured_at` — oldest first (FIFO) within the same priority/origin.
    4. `id` — lexicographic tie-break.

    Both the `next` ranker and the Fabro Dispatcher's `_ready_items`
    drain order compose this single function, so the two can never
    diverge on which ready item runs first. The signature mirrors the
    `key=` callable precedent (a single positional `item`, not
    keyword-only) so it can be passed directly to `list.sort` /
    `sorted`.
    """
    origin_rank = _GAP_TIED_RANK if item.origin == "gap-tied" else _FREEFORM_RANK
    return (item.priority, origin_rank, item.captured_at, item.id)
