"""`/livespec-orchestrator-beads-fabro:next` thin-transport ranker.

CLI surface per `SPECIFICATION/contracts.md` v005:

  next [--limit <count>] [--offset <count>] [--json]
       [--work-items-path <path>] [--project-root <path>]

`--limit <count>` — positive integer, default `5`. Maximum number of
candidates returned in the `candidates` array. Non-positive (or
non-integer) values cause the wrapper to exit `2` with a usage error.

`--offset <count>` — non-negative integer, default `0`. Number of
ranked candidates to skip from the front of the ranked list before
returning. Negative (or non-integer) values cause the wrapper to
exit `2` with a usage error.

The ranker is a pure function of work-items JSONL state plus the
cross-repo manifest at `<project-root>/.livespec.jsonc`. Per
`livespec/SPECIFICATION/contracts.md` v072, the ranker MUST consult
`livespec_runtime.cross_repo.resolve_ref` for every candidate's
`depends_on` entries and MUST exclude any candidate with at least
one entry resolving to `RefStatus.OPEN`. Excluded candidates are
absent from the ranked list (not surfaced with a lower urgency).

Algorithm:

1. Load the cross-repo manifest from `<project-root>/.livespec.jsonc`
   (empty manifest when the file or `cross_repo_targets` block is
   absent).
2. Identify ready items via the shared `lifecycle.is_item_ready`: the
   item renders in the `ready` lane (stored status `ready` AND no
   `depends_on` entry resolves to `OPEN`). Missing local references
   resolve to `UNKNOWN` and therefore do NOT exclude (the doctor's
   `no-orphan-dependency` invariant is the right surface for that).
3. Score by the canonical `lifecycle.ready_sort_key` = `(rank, id)`:
   the fractional `rank` is the sole ordering authority, with `id` as
   the deterministic tie-break.
4. Enumerate ALL ready items in ranked order as candidates.
5. Apply `--offset` then `--limit` to produce the returned slice.
6. Emit a `{candidates[], pagination}` envelope. Each candidate
   carries `action`, `reason`, `urgency`, and `work_item_ref`,
   plus impl-beads-specific `rank` and `origin` fields
   (the cross-plugin contract permits additional fields).

Empty `candidates[]` IS the no-work signal — the wrapper MUST NOT
degrade to any legacy single-object shape. When `offset >= total`,
the wrapper emits `candidates: []` with `has_more: false`.
"""

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from livespec_runtime.cross_repo.types import CrossRepoManifest, RefStatus
from livespec_runtime.work_items.lifecycle import is_item_ready, ready_sort_key

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._sibling_status_lookup import (
    make_sibling_status_lookup,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["build_envelope", "main", "rank_candidates"]


_EXIT_USAGE_ERROR = 2
_DEFAULT_LIMIT = 5
_DEFAULT_OFFSET = 0


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="next")
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--limit", dest="limit_raw", default=str(_DEFAULT_LIMIT))
    _ = parser.add_argument("--offset", dest="offset_raw", default=str(_DEFAULT_OFFSET))
    _ = parser.add_argument("--work-items-path", dest="work_items_path", default=None)
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    args = parser.parse_args(argv)
    limit = _parse_positive_int(raw=args.limit_raw, flag="--limit")
    if limit is None:
        return _EXIT_USAGE_ERROR
    offset = _parse_non_negative_int(raw=args.offset_raw, flag="--offset")
    if offset is None:
        return _EXIT_USAGE_ERROR
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    config = resolve_store_config(
        cwd=project_root,
        work_items_arg=args.work_items_path,
    )
    materialized = _load_work_items(path=config.work_items_path)
    manifest = load_manifest(project_root=project_root)
    sibling_status_lookup = make_sibling_status_lookup(project_root=project_root)
    ranked = rank_candidates(
        items=materialized,
        manifest=manifest,
        sibling_status_lookup=sibling_status_lookup,
    )
    envelope = _slice_envelope(ranked=ranked, offset=offset, limit=limit)
    if args.as_json:
        _ = write_stdout(text=json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    else:
        sliced = ranked[offset : offset + limit]
        _write_human(candidates=sliced)
    return 0


def rank_candidates(
    *,
    items: list[WorkItem],
    manifest: CrossRepoManifest | None = None,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None = None,
) -> list[dict[str, Any]]:
    """Return the full ranked list of candidate envelopes (no slicing).

    Each candidate dict carries:

    - `action` — always `"implement"` (the only non-`none` action this
      ranker emits; `none` is signaled via an empty candidates list).
    - `work_item_ref` — the `id` of the ranked work-item.
    - `urgency` — uniform `"medium"` (the ranked position is the urgency
      signal now that `priority` is gone).
    - `reason` — a one-line human narration.
    - `rank` — the work-item's fractional ordering key (impl-beads
      field; the cross-plugin contract permits additional fields).
    - `origin` — one of `"gap-tied"` or `"freeform"` (impl-beads
      field; the cross-plugin contract permits additional fields).
    """
    effective_manifest = manifest if manifest is not None else CrossRepoManifest(targets={})
    index = {item.id: item for item in items}
    ready = [
        item
        for item in items
        if is_item_ready(
            item=item,
            index=index,
            manifest=effective_manifest,
            sibling_status_lookup=sibling_status_lookup,
        )
    ]
    ready.sort(key=ready_sort_key)
    return [_candidate_for(item=item) for item in ready]


def build_envelope(
    *,
    items: list[WorkItem],
    offset: int,
    limit: int,
    manifest: CrossRepoManifest | None = None,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None = None,
) -> dict[str, Any]:
    """Return the `{candidates[], pagination}` envelope per v005 contract.

    `offset` and `limit` are applied to the full ranked candidate
    list (per `rank_candidates`). The `pagination` block echoes the
    inputs plus `total` (the full ripe-candidate count BEFORE
    slicing) and `has_more` (`true` iff `offset + len(candidates) <
    total`).
    """
    ranked = rank_candidates(
        items=items,
        manifest=manifest,
        sibling_status_lookup=sibling_status_lookup,
    )
    return _slice_envelope(ranked=ranked, offset=offset, limit=limit)


def _slice_envelope(
    *,
    ranked: list[dict[str, Any]],
    offset: int,
    limit: int,
) -> dict[str, Any]:
    total = len(ranked)
    sliced = ranked[offset : offset + limit]
    has_more = offset + len(sliced) < total
    return {
        "candidates": sliced,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": has_more,
        },
    }


def _candidate_for(*, item: WorkItem) -> dict[str, Any]:
    return {
        "action": "implement",
        "work_item_ref": item.id,
        # `rank` is the sole ordering authority now; relative position in the
        # ranked list IS the urgency signal, so every ready candidate carries
        # a uniform `medium` urgency (the prior priority-derived high/low
        # tiering is gone with the `priority` field).
        "urgency": "medium",
        "reason": (f"ranked ready item (rank {item.rank}, origin {item.origin})"),
        "rank": item.rank,
        "origin": item.origin,
    }


def _load_work_items(*, path: StoreConfig) -> list[WorkItem]:
    # The beads store has no on-disk file to be missing: an unconfigured or
    # empty tenant simply yields an empty issue stream, so the JSONL-era
    # `StoreFileMissingError` fallback the plaintext sibling carried is not
    # reachable here. An empty tenant is the natural empty-result path.
    return list(materialize_work_items(records=read_work_items(path=path)).values())


def _parse_positive_int(*, raw: str, flag: str) -> int | None:
    """Parse a CLI integer that MUST be `>= 1`. Returns None on invalid input.

    Emits a usage-style error narration to stderr before returning
    None, mirroring the `detect_impl_gaps` `--since-version`
    treatment. The caller maps None to `_EXIT_USAGE_ERROR`.
    """
    parsed = _parse_int_or_none(raw=raw)
    if parsed is None or parsed < 1:
        _ = write_stderr(
            text=f"ERROR: {flag} requires a positive integer (got '{raw}').\n",
        )
        return None
    return parsed


def _parse_non_negative_int(*, raw: str, flag: str) -> int | None:
    """Parse a CLI integer that MUST be `>= 0`. Returns None on invalid input."""
    parsed = _parse_int_or_none(raw=raw)
    if parsed is None or parsed < 0:
        _ = write_stderr(
            text=f"ERROR: {flag} requires a non-negative integer (got '{raw}').\n",
        )
        return None
    return parsed


def _parse_int_or_none(*, raw: str) -> int | None:
    """Parse `raw` as a signed integer; return None on any parse failure.

    Strips a leading `-` before testing `isdigit()` so negative
    integers parse; `isdigit()` alone rejects the sign. After the
    `isdigit()` gate the body of `int(raw)` cannot raise, so no
    additional guard is needed.
    """
    candidate = raw.lstrip("-")
    if not candidate.isdigit():
        return None
    return int(raw)


def _write_human(*, candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        _ = write_stdout(text="No candidates ready (queue empty or all blocked)\n")
        return
    for candidate in candidates:
        line = (
            f"{candidate['action']}  {candidate['work_item_ref']}"
            f"  [{candidate['urgency']}]  {candidate['reason']}\n"
        )
        _ = write_stdout(text=line)
