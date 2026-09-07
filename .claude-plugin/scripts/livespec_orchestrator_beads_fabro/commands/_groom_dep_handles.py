"""Draft-local dependency-handle resolution for an approved groom cut.

A `depends_on` handle is a DRAFT-LOCAL name — the `title` of another slice in
the same approved draft — because filing is what mints ids, so a slice cannot
name a not-yet-minted id. This module owns the translation from those handles
into the typed dependency entries a filed work-item carries, and the refusal a
handle that cannot translate produces.

It is deliberately a pure function over strings and maps, holding no store
handle: the caller decides WHEN to resolve — for the whole cut, before the
first write — and this module decides only WHETHER a handle resolves and to
what. Expected authoring errors raise `GroomDraftError`; bugs propagate as
built-in exceptions.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.errors import GroomDraftError
from livespec_orchestrator_beads_fabro.types import DependsOnRaw

__all__: list[str] = [
    "resolve_dep_entries",
]


def resolve_dep_entries(
    *,
    slice_title: str,
    handles: tuple[str, ...],
    id_by_title: dict[str, str],
    cross_repo_title_to_repo: dict[str, str],
    spec_change_titles: frozenset[str],
) -> tuple[DependsOnRaw, ...]:
    """Resolve a slice's draft-local title handles to typed dependency entries.

    A handle that does not name an EARLIER factory slice in the same draft is
    a malformed cut (the maintainer arranged a slice before its blocker, or
    pointed at a spec-change/absent title) — an expected authoring error
    surfaced as `GroomDraftError` so the front-end re-drafts rather than
    filing a dangling edge.

    A handle that resolves to a cross-repo slice (tracked in
    `cross_repo_title_to_repo`) emits a `sibling_work_item` dep entry so the
    Dispatcher can gate on it via `resolve_ref`. All other handles emit a
    `local` dep entry (same-tenant beads `blocks` edge).
    """
    resolved: list[DependsOnRaw] = []
    for handle in handles:
        dep_id = id_by_title.get(handle)
        if dep_id is None:
            raise GroomDraftError(
                detail=_unresolvable_handle_detail(
                    slice_title=slice_title, handle=handle, spec_change_titles=spec_change_titles
                )
            )
        repo = cross_repo_title_to_repo.get(handle)
        if repo is not None:
            resolved.append({"kind": "sibling_work_item", "repo": repo, "work_item_id": dep_id})
        else:
            resolved.append({"kind": "local", "work_item_id": dep_id})
    return tuple(resolved)


def _unresolvable_handle_detail(
    *, slice_title: str, handle: str, spec_change_titles: frozenset[str]
) -> str:
    """Say which slice named which unresolvable handle, and why it cannot resolve.

    The spec-change case is called out by name because it is the one the draft
    grammar positively INVITES: a spec-change slice is a legitimate member of
    the approved cut and a later factory slice really can be blocked by it, so
    the maintainer's arrangement is sound and only its representation is not.
    The generic wording would send them hunting for a missing or misordered
    slice that is neither missing nor misordered.
    """
    if handle in spec_change_titles:
        return (
            f"slice {slice_title!r} depends on spec-change slice {handle!r}, "
            f"which cannot be represented: a spec-change slice routes to "
            f"propose-change and is never minted as a work-item"
        )
    return (
        f"slice {slice_title!r} depends on {handle!r}, which is not "
        f"an earlier factory slice in the approved draft"
    )
