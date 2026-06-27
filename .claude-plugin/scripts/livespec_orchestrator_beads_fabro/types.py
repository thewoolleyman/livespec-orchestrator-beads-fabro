"""Spec Reader output dataclasses + re-export of the shared work-item model.

The work-item MODEL (`WorkItem`, `AuditRecord`) and its schema
enums/aliases (`WorkItemStatus`/`WorkItemType`/`Origin`/`Resolution`/
`DependsOnRaw`) are the SHARED surface published by
`livespec_runtime.work_items.types` at runtime v0.4.0 — beads used to
re-implement them identically here. They are now re-exported from the
runtime package so the single canonical definition is the source of
record; every existing call site that imports them from
`livespec_orchestrator_beads_fabro.types` keeps working unchanged. The work-item
schema is codified by SPECIFICATION/contracts.md; the runtime model carries the unified 16-field
shape (beads' historical record MINUS the append-only `supersedes`
pointer, which the unified model adds defaulted `None` — beads is
inherently one-record-per-id and never populates it).

The Spec Reader return types (`SpecSnapshot`/`SpecDiff`/`FileDiff`) and
the beads-tenant connection descriptor (`StoreConfig`) are NOT part of
the shared lift — they stay LOCAL here (per
SPECIFICATION/contracts.md and the beads
connection model).
"""

from dataclasses import dataclass, field

from livespec_runtime.work_items.types import (
    AuditRecord,
    DependsOnRaw,
    Origin,
    Resolution,
    WorkItem,
    WorkItemStatus,
    WorkItemType,
)

__all__ = [
    "AuditRecord",
    "DependsOnRaw",
    "FileDiff",
    "Origin",
    "Resolution",
    "SpecDiff",
    "SpecSnapshot",
    "StoreConfig",
    "WorkItem",
    "WorkItemStatus",
    "WorkItemType",
]


@dataclass(frozen=True, kw_only=True)
class SpecSnapshot:
    """A read-only view of a Specification at a particular version.

    `files` maps spec_root-relative file paths to their full text content.
    `version` is the snapshot's vNNN integer (1-indexed). For the live
    specification (the top-level spec_root tree), `version` is the latest
    history version the snapshot corresponds to per
    SPECIFICATION/contracts.md capability 3.
    """

    version: int
    files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class SpecDiff:
    """Structured diff between two SpecSnapshot versions.

    `per_file` maps each file path that differs between the two snapshots
    to a per-file summary carrying added and removed line counts plus a
    unified-diff body. Files present only in one snapshot appear with the
    other side's count zero. Files identical in both snapshots are NOT
    included.
    """

    version_a: int
    version_b: int
    per_file: dict[str, "FileDiff"] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class FileDiff:
    """Per-file diff summary inside a SpecDiff."""

    path: str
    added_lines: int
    removed_lines: int
    unified_diff: str


@dataclass(frozen=True, kw_only=True)
class StoreConfig:
    """Beads-tenant connection descriptor, resolved from .livespec.jsonc + env.

    This REPLACES the plaintext sibling's path-based `StoreConfig`. The
    beads store has no on-disk JSONL files; the substrate is a per-repo
    tenant database on the shared `dolt-server`. The fields below are the
    verified v1.0.5 server-mode FLAGS connection surface
    (beads-schema-mapping.md §2.1):

    - `tenant` — the logical tenant name (the livespec-family repo).
    - `prefix` — the beads id prefix (bd's server-stored create-prefix),
      DECOUPLED from the tenant database name: a short, readable alias
      that MAY differ from it (e.g. `bd-ib`), NOT `database`.
    - `server_host` / `server_port` — TCP connection (default
      `127.0.0.1:3307`).
    - `socket` — optional unix-socket path; when set it OVERRIDES
      host/port (the §2.1 `--server-socket` semantics).
    - `server_user` — the least-privilege tenant user scoped to the DB.
    - `database` — the tenant DB selected explicitly via `--database`
      (== `tenant` == `server_user`; the load-bearing tenant identity,
      DECOUPLED from `prefix`).
    - `bd_path` — absolute path to the pinned bd v1.0.5 binary (NEVER the
      mise shim; resolved from config/env in `commands/_config.py`).
    - `fake` — hermetic toggle. When True the store talks to an in-memory
      `FakeBeadsClient` (the default CI tier and the no-live-connection
      runtime fallback); when False it shells out to `bd` over the live
      connection. Resolved from the connection block overlaid by
      `LIVESPEC_BEADS_FAKE`.

    The tenant PASSWORD is deliberately NOT a field: it is read only from
    the `BEADS_DOLT_PASSWORD` environment variable at `bd`-call time and
    is never stored on the descriptor or committed to `.livespec.jsonc`.

    REPURPOSED-PATH NOTE: the store's public functions keep the
    keyword `path` (so the command call sites do not change), but `path`
    is now typed as this `StoreConfig` rather than a filesystem `Path`.
    The `work_items_path` PROPERTY below returns `self` so the legacy
    call expression `read_work_items(path=config.work_items_path)`
    passes the connection descriptor straight through as the `path`
    argument.
    """

    tenant: str
    prefix: str
    server_user: str
    database: str
    bd_path: str
    server_host: str = "127.0.0.1"
    server_port: int = 3307
    socket: str | None = None
    fake: bool = False

    @property
    def work_items_path(self) -> "StoreConfig":
        """Return the connection descriptor itself (see REPURPOSED-PATH NOTE)."""
        return self
