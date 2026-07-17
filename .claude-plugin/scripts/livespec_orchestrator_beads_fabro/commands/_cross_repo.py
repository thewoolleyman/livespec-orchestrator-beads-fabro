"""Cross-repo manifest + dependency-entry helpers shared by next + list-work-items.

This module is the manifest/parse half of the cross-repo surface. The
readiness predicate (`is_item_ready`), the canonical ranking key
(`ready_sort_key`), and the `lane_of` lane authority are RELOCATED to the
shared `livespec_runtime.work_items.lifecycle` module (they are pure
functions over an in-memory `index: dict[str, WorkItem]` the caller already
holds, so they no longer belong to this beads-specific transport). What
stays here is exactly the two helpers that read THIS repo's
`.livespec.jsonc` manifest and dispatch a raw `depends_on` cell:

- `load_manifest(project_root)` — read `.livespec.jsonc` and extract
  the `cross_repo_targets` block as a typed `CrossRepoManifest`.
  Returns an empty manifest when the file or block is absent; this
  is the legitimate "no cross-repo deps configured" state.
- `parse_entry(raw)` — dispatch a raw `depends_on` entry (bare string
  or typed dict) into a typed `DependsOnEntry`. Bare strings are
  converted to `LocalDependency` for forward-compatibility with the
  pre-v072 plaintext stores; the data-migration script has the
  authoritative typed-form conversion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from livespec_runtime.cross_repo.errors import CrossRepoSchemaError
from livespec_runtime.cross_repo.types import (
    CrossRepoManifest,
    DependsOnEntry,
    LocalDependency,
    parse_cross_repo_manifest,
    parse_depends_on_entry,
)

from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "load_manifest",
    "parse_entry",
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
    parsed = _jsonc.parse(text=raw_text)
    if isinstance(parsed, _jsonc.JsoncFailure):
        return CrossRepoManifest(targets={})
    if not isinstance(parsed, dict):
        return CrossRepoManifest(targets={})
    parsed_dict = cast("dict[str, Any]", parsed)
    block_raw = parsed_dict.get("cross_repo_targets")
    if not isinstance(block_raw, dict):
        return CrossRepoManifest(targets={})
    block = cast("dict[str, Any]", block_raw)
    manifest = attempt(
        action=lambda: parse_cross_repo_manifest(parsed=block),
        exceptions=(CrossRepoSchemaError,),
    )
    if isinstance(manifest, AttemptFailure):
        return CrossRepoManifest(targets={})
    return manifest


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
        entry = attempt(
            action=lambda: parse_depends_on_entry(parsed=typed_raw),
            exceptions=(CrossRepoSchemaError,),
        )
        if isinstance(entry, AttemptFailure):
            return None
        return entry
    return None
