"""`groom` — the agent-drafts / human-approves backlog decomposition front-end.

The grooming contract targets ordinary `backlog` items in the seven-state
lifecycle: intake-routed epics and Dispatcher non-convergence bounces. The
draft remains read-only until maintainer approval. On approval, local factory
slices are filed through the same store + intake Definition-of-Ready routing
used by capture front-ends, while spec-change and cross-repo slices are returned
for the prose layer to route to their target operations.

The original backlog item is never silently dropped. Once at least one local
factory slice is filed, it is explicitly closed as no longer applicable with a
reason naming the replacement slices.

Expected failures raise typed errors from `errors.py` (`WorkItemNotFoundError`,
`GroomTargetNotBacklogError`, `GroomExitRefusedError`, `GroomDraftError`);
genuine bugs propagate as built-in exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from livespec_runtime.work_items.rank import key_between

from livespec_orchestrator_beads_fabro import regroom
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.errors import GroomDraftError
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import DependsOnRaw, WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "CandidateSlice",
    "CrossRepoSlice",
    "GroomContext",
    "GroomResult",
    "file_approved_slices",
    "load_groom_context",
]

_DEFAULT_PRIORITY = 2


@dataclass(frozen=True, kw_only=True)
class GroomContext:
    """The read-only scoping context a groom draft is grounded in.

    Returned by `load_groom_context` after confirming the target is in
    `backlog`. Carries only what the draft needs; the front-end's dialogue
    reads the spec / scenarios / ledger separately (read-only).
    """

    item_id: str
    title: str
    description: str


@dataclass(frozen=True, kw_only=True)
class CandidateSlice:
    """One drafted candidate slice in the layered decomposition.

    The maintainer-approved shape: every field the intake Definition-of-
    Ready checklist gates on is pre-filled, so a filed factory slice can be
    routed through the shared intake primitive. `is_spec_change` marks a human-gated
    spec-change slice that routes to `/livespec:propose-change` instead of
    being filed into the factory ledger.

    `depends_on` carries the dependency-layer arrangement as DRAFT-LOCAL
    handles — the `title` of an EARLIER factory slice in the same approved
    draft that this slice is blocked by. Filing mints each slice's id, so
    a slice cannot name a not-yet-minted id; `file_approved_slices`
    resolves each title handle to the earlier slice's minted id and links
    the real `blocks` edge. The maintainer arranges the draft so a slice's
    blockers precede it (later layers after earlier layers).
    """

    title: str
    description: str
    acceptance: str
    autonomy_tier: str
    repo_target: str
    depends_on: tuple[str, ...] = ()
    is_spec_change: bool = False
    priority: int = _DEFAULT_PRIORITY


@dataclass(frozen=True, kw_only=True)
class CrossRepoSlice:
    """A factory slice targeting a different repo, returned for external routing.

    Not filed in the local tenant (the one-slice/one-ledger model: each
    slice goes into its target repo's tenant). The `minted_id` is assigned
    at groom time so local slices that depend on this cross-repo slice can
    reference it as a `sibling_work_item` dependency with a known id.
    """

    candidate: CandidateSlice
    minted_id: str


@dataclass(frozen=True, kw_only=True)
class GroomResult:
    """The outcome of an approved groom: what was filed, routed, and exited.

    - `filed_slice_ids` — the local factory slices filed and then routed by
      the intake Definition-of-Ready primitive (in draft order), with their
      dependency edges linked.
    - `spec_change_slices` — the approved spec-change slices NOT filed
      here; the SKILL.md prose routes each to `/livespec:propose-change`.
    - `cross_repo_slices` — factory slices whose `repo_target` differs from
      `local_repo`; NOT filed in the local tenant. Returned with their
      minted ids for the SKILL.md prose to route to the target repo.
    - `regroomed_out` — True once the original backlog item is explicitly
      closed against the filed factory slices.
    """

    filed_slice_ids: tuple[str, ...] = ()
    spec_change_slices: tuple[CandidateSlice, ...] = ()
    cross_repo_slices: tuple[CrossRepoSlice, ...] = ()
    regroomed_out: bool = False


def load_groom_context(*, path: StoreConfig, item_id: str) -> GroomContext:
    """Read the backlog target read-only, refusing any other lifecycle state.

    The READ-ONLY entry point: it confirms `item_id` is present and currently
    in `backlog`. Mutates nothing; the draft stays read-only until
    `file_approved_slices` is called on approval.
    """
    regroom.require_backlog_target(path=path, item_id=item_id)
    record = make_beads_client(config=path).show_issue(issue_id=item_id)
    return GroomContext(
        item_id=item_id,
        title=_record_str(record=record, key="title"),
        description=_record_str(record=record, key="description"),
    )


def file_approved_slices(
    *,
    path: StoreConfig,
    regroom_item_id: str,
    slices: list[CandidateSlice],
    local_repo: str,
) -> GroomResult:
    """File approved local factory slices through intake, then close the original.

    Called ONLY after the maintainer approves the draft. For each factory
    slice (`is_spec_change == False`):

    - If `repo_target == local_repo` (a LOCAL slice): file via
      `append_work_item`, route through the intake DoR primitive, and link
      dependency edges. Local slices that depend (by draft-title handle) on a
      cross-repo blocker carry a `sibling_work_item` dep so the Dispatcher can
      gate on it.
    - If `repo_target != local_repo` (a CROSS-REPO slice): mint an id but
      do NOT file locally (the one-slice/one-ledger model). The slice is
      returned in `GroomResult.cross_repo_slices` with its minted id for
      the SKILL.md prose to route to the target repo.

    After all slices are processed, the original backlog item is explicitly
    closed against the filed LOCAL slice ids.

    Raises `GroomDraftError` if any factory slice has an empty `repo_target`
    or if a `depends_on` handle names no earlier factory slice in the draft.
    Raises `GroomExitRefusedError` if no local factory slice was filed.
    Raises `WorkItemNotFoundError` if `regroom_item_id` is absent.
    """
    filed_ids: list[str] = []
    spec_change: list[CandidateSlice] = []
    cross_repo: list[CrossRepoSlice] = []
    # Each filed local slice gets a `rank` appended below the previous one
    # (threaded `key_between`), so the dependency-layered draft order becomes
    # the ready-lane drain order.
    prev_rank: str | None = None
    # Maps each factory slice's draft title -> its minted id so that a later
    # slice's `depends_on` title handles resolve to real ids. Populated for
    # both local and cross-repo slices as they are processed in draft order.
    id_by_title: dict[str, str] = {}
    # Maps a cross-repo slice's draft title -> its repo_target so that a
    # local slice depending on it can emit a sibling_work_item dep entry.
    cross_repo_title_to_repo: dict[str, str] = {}
    for candidate in slices:
        if candidate.is_spec_change:
            spec_change.append(candidate)
            continue
        if not candidate.repo_target:
            raise GroomDraftError(detail=f"slice {candidate.title!r} has an empty repo_target")
        slice_id = new_work_item_id(prefix=path.prefix)
        if candidate.repo_target != local_repo:
            # Cross-repo slice: mint id, track for dep resolution, return for
            # external routing. NOT filed in the local tenant.
            id_by_title[candidate.title] = slice_id
            cross_repo_title_to_repo[candidate.title] = candidate.repo_target
            cross_repo.append(CrossRepoSlice(candidate=candidate, minted_id=slice_id))
            continue
        dep_entries = _resolve_dep_entries(
            candidate=candidate,
            id_by_title=id_by_title,
            cross_repo_title_to_repo=cross_repo_title_to_repo,
        )
        rank = key_between(a=prev_rank, b=None)
        prev_rank = rank
        append_work_item(
            path=path,
            item=_work_item_for(
                candidate=candidate, slice_id=slice_id, dep_entries=dep_entries, rank=rank
            ),
        )
        _route_approved_slice_intake(path=path, item_id=slice_id)
        filed_ids.append(slice_id)
        id_by_title[candidate.title] = slice_id
    regroom.close_regroomed_out(path=path, item_id=regroom_item_id, replacement_slice_ids=filed_ids)
    return GroomResult(
        filed_slice_ids=tuple(filed_ids),
        spec_change_slices=tuple(spec_change),
        cross_repo_slices=tuple(cross_repo),
        regroomed_out=True,
    )


def _resolve_dep_entries(
    *,
    candidate: CandidateSlice,
    id_by_title: dict[str, str],
    cross_repo_title_to_repo: dict[str, str],
) -> tuple[DependsOnRaw, ...]:
    """Resolve a slice's draft-local title handles to typed dependency entries.

    A `depends_on` handle that does not name an EARLIER factory slice in
    the same draft is a malformed cut (the maintainer arranged a slice
    before its blocker, or pointed at a spec-change/absent title) — an
    expected authoring error surfaced as `GroomDraftError` so the
    front-end re-drafts rather than filing a dangling edge.

    A handle that resolves to a cross-repo slice (tracked in
    `cross_repo_title_to_repo`) emits a `sibling_work_item` dep entry so
    the Dispatcher can gate on it via `resolve_ref`. All other handles emit
    a `local` dep entry (same-tenant beads `blocks` edge).
    """
    resolved: list[DependsOnRaw] = []
    for handle in candidate.depends_on:
        dep_id = id_by_title.get(handle)
        if dep_id is None:
            raise GroomDraftError(
                detail=(
                    f"slice {candidate.title!r} depends on {handle!r}, which is not "
                    f"an earlier factory slice in the approved draft"
                )
            )
        repo = cross_repo_title_to_repo.get(handle)
        if repo is not None:
            resolved.append({"kind": "sibling_work_item", "repo": repo, "work_item_id": dep_id})
        else:
            resolved.append({"kind": "local", "work_item_id": dep_id})
    return tuple(resolved)


def _work_item_for(
    *,
    candidate: CandidateSlice,
    slice_id: str,
    dep_entries: tuple[DependsOnRaw, ...],
    rank: str,
) -> WorkItem:
    """Build the freeform work-item for one approved local factory slice.

    A groomed slice is freeform (the cut is the maintainer's, not tied to
    a single detected gap clause); its acceptance is folded into the
    description so the dispatched implementer carries it. `dep_entries`
    carries the fully-typed dependency entries (local or sibling_work_item)
    already resolved from the earlier draft slices. The initial status is the
    capture-style shell; `_route_approved_slice_intake` moves it through A1
    lifecycle routing after creation.
    """
    description = (
        f"{candidate.description}\n\n"
        f"Acceptance: {candidate.acceptance}\n"
        f"Autonomy tier: {candidate.autonomy_tier}\n"
        f"Repo target: {candidate.repo_target}"
    ).strip()
    return WorkItem(
        id=slice_id,
        type="task",
        status="pending-approval",
        title=candidate.title,
        description=description,
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=dep_entries,
        captured_at=_now_iso(),
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _route_approved_slice_intake(*, path: StoreConfig, item_id: str) -> None:
    """Route a freshly filed approved slice through the shared intake primitive."""
    _ = apply_intake_dor(
        path=path,
        item_id=item_id,
        checklist=DefinitionOfReadyChecklist(
            single_coherent_done=True,
            autonomously_verifiable=True,
            autonomy_tiered=True,
            dependency_linked=True,
            repo_targeted=True,
            above_floor=True,
        ),
    )


def _record_str(*, record: BeadsRecord, key: str) -> str:
    value = record.get(key)
    return value if isinstance(value, str) else ""


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
