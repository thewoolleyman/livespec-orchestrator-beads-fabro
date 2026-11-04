"""The approved groom cut, fully decided before the first ledger write.

Filing a slice is three writes with no transaction behind them and no
compensating delete, so every id is minted and every dependency handle resolved
here, writing nothing: a malformed draft raises while the ledger is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._groom_dep_handles import resolve_dep_entries
from livespec_orchestrator_beads_fabro.commands._groom_tenant_prefix import target_tenant_prefix
from livespec_orchestrator_beads_fabro.commands._groom_types import (
    CandidateSlice,
    CrossRepoSlice,
)
from livespec_orchestrator_beads_fabro.errors import GroomDraftError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import DependsOnRaw, StoreConfig

__all__: list[str] = [
    "GroomPlan",
    "PlannedLocalSlice",
    "plan_approved_slices",
]


@dataclass(frozen=True, kw_only=True)
class PlannedLocalSlice:
    """One local factory slice, fully resolved and awaiting only its writes."""

    candidate: CandidateSlice
    slice_id: str
    dep_entries: tuple[DependsOnRaw, ...]


@dataclass(frozen=True, kw_only=True)
class GroomPlan:
    """The whole approved cut, decided before the first slice is filed."""

    local: tuple[PlannedLocalSlice, ...]
    spec_change: tuple[CandidateSlice, ...]
    cross_repo: tuple[CrossRepoSlice, ...]


def plan_approved_slices(
    *, slices: list[CandidateSlice], local_repo: str, path: StoreConfig
) -> GroomPlan:
    """Mint every id and resolve every dependency handle, writing nothing.

    Pure with respect to the ledger: it walks the draft in order, sorts each
    slice into its route (spec-change, cross-repo, local), and resolves each
    slice's `depends_on` handles — local and cross-repo alike — against the
    slices that PRECEDE it. Any malformed draft raises here, where the ledger
    has not yet been touched.
    """
    # A spec-change slice routes to propose-change and is never minted, so no
    # id can ever exist for it. Its title is carried separately purely so the
    # refusal can say WHY the handle is unresolvable rather than merely that it
    # is — the two are the same observation to a maintainer re-drafting a cut.
    spec_change_titles = frozenset(
        candidate.title for candidate in slices if candidate.is_spec_change
    )
    local: list[PlannedLocalSlice] = []
    spec_change: list[CandidateSlice] = []
    cross_repo: list[CrossRepoSlice] = []
    # Maps each factory slice's draft title -> its minted id so that a later
    # slice's `depends_on` title handles resolve to real ids. Populated for
    # both local and cross-repo slices as they are processed in draft order.
    id_by_title: dict[str, str] = {}
    # Maps each factory slice's draft title -> its repo_target so a dependent
    # slice's entries are typed from its own tenant's point of view.
    repo_by_title: dict[str, str] = {}
    # Each cross-repo target's own id prefix, resolved once per repository.
    target_prefixes: dict[str, str] = {}
    for candidate in slices:
        if candidate.is_spec_change:
            spec_change.append(candidate)
            continue
        if not candidate.repo_target:
            raise GroomDraftError(detail=f"slice {candidate.title!r} has an empty repo_target")
        is_cross_repo = candidate.repo_target != local_repo
        if is_cross_repo and candidate.repo_target not in target_prefixes:
            target_prefixes[candidate.repo_target] = target_tenant_prefix(
                path=path, repo=candidate.repo_target
            )
        slice_id = new_work_item_id(
            prefix=target_prefixes[candidate.repo_target] if is_cross_repo else path.prefix
        )
        dep_entries = resolve_dep_entries(
            slice_title=candidate.title,
            owner_repo=candidate.repo_target,
            handles=candidate.depends_on,
            id_by_title=id_by_title,
            repo_by_title=repo_by_title,
            spec_change_titles=spec_change_titles,
        )
        id_by_title[candidate.title] = slice_id
        repo_by_title[candidate.title] = candidate.repo_target
        if is_cross_repo:
            # Not filed in the local tenant: returned for external routing.
            cross_repo.append(
                CrossRepoSlice(candidate=candidate, minted_id=slice_id, dep_entries=dep_entries)
            )
            continue
        local.append(
            PlannedLocalSlice(candidate=candidate, slice_id=slice_id, dep_entries=dep_entries)
        )
    return GroomPlan(
        local=tuple(local), spec_change=tuple(spec_change), cross_repo=tuple(cross_repo)
    )
