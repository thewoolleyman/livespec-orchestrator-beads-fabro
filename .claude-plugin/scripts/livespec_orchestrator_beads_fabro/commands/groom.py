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

Filing is gated on an approval RECORD, not on the calling agent's judgement:
`file_approved_slices` requires a `GroomApproval` naming the approver identity
and the route the approval arrived on, refuses a call carrying none before any
slice is filed, and stamps the record on every filed slice and on the closed
original so a later reader can query who approved the cut.

Filing is ALL-OR-NOTHING for the same reason: the whole approved cut — every
minted id and every resolved dependency handle — is decided before the first
write, so a malformed draft is refused with the ledger untouched. Filing one
slice is three writes with no transaction behind them, and there is no
compensating delete, so a refusal raised mid-loop would strand the cut half
applied with no record of which ids it had already minted.

Expected failures raise typed errors from `errors.py` (`WorkItemNotFoundError`,
`GroomTargetNotBacklogError`, `GroomExitRefusedError`, `GroomDraftError`,
`GroomApprovalRequiredError`); genuine bugs propagate as built-in exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from livespec_runtime.work_items.rank import key_between

from livespec_orchestrator_beads_fabro import regroom
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro._store_groom_approval import (
    GroomApproval,
    record_groom_approval,
    require_groom_approval,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    EffectiveCriteria,
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import (
    GroomDispatch,
    GroomDoorRefusal,
    groom_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._groom_dep_handles import resolve_dep_entries
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

# `GroomDispatch` / `GroomDoorRefusal` / `groom_dispatch` are RE-EXPORTS of the
# groom door, whose mechanism lives beside the Dispatcher's own claim and pin
# seams rather than here. The door is a front-end operation — the contract says
# the front-end's operator performs it — so this module is where the front-end
# reaches for it, exactly as `GroomApproval` is re-exported above.
__all__: list[str] = [
    "CandidateSlice",
    "CrossRepoSlice",
    "GroomApproval",
    "GroomContext",
    "GroomDispatch",
    "GroomDoorRefusal",
    "GroomResult",
    "SliceCriteriaParse",
    "file_approved_slices",
    "groom_dispatch",
    "load_groom_context",
]


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
class SliceCriteriaParse:
    """One filed slice's effective-criteria parse, for the front-end to display.

    Carried as a RESULT rather than enforced as a gate: the
    effective-acceptance-criteria clause of contracts.md requires groom to
    display the parse and forbids it refusing on an empty one, because a
    groomed slice's criteria may legitimately arrive at approve time.
    """

    slice_id: str
    criteria: EffectiveCriteria


@dataclass(frozen=True, kw_only=True)
class GroomResult:
    """The outcome of an approved groom: what was filed, routed, and exited.

    - `filed_slice_ids` — the local factory slices filed and then routed by
      the intake Definition-of-Ready primitive (in draft order), with their
      dependency edges linked.
    - `criteria_parses` — each filed local slice's effective-criteria parse
      (the gradeable-assertion count and the resolved source), for the
      front-end to display.
    - `spec_change_slices` — the approved spec-change slices NOT filed
      here; the SKILL.md prose routes each to `/livespec:propose-change`.
    - `cross_repo_slices` — factory slices whose `repo_target` differs from
      `local_repo`; NOT filed in the local tenant. Returned with their
      minted ids for the SKILL.md prose to route to the target repo.
    - `regroomed_out` — True once the original backlog item is explicitly
      closed against the filed factory slices.
    """

    filed_slice_ids: tuple[str, ...] = ()
    criteria_parses: tuple[SliceCriteriaParse, ...] = ()
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
    approval: GroomApproval | None,
) -> GroomResult:
    """File approved local factory slices through intake, then close the original.

    Called ONLY after the maintainer approves the draft, and the `approval`
    record is what carries that approval INTO the seam rather than leaving it
    an obligation on the calling agent's judgement: it names the approver
    identity and the route the approval arrived on, it is checked before any
    slice is filed, and it is stamped on every filed slice and on the closed
    original so a later reader can tell an approved cut from an unapproved
    one (the groom-cut clause of `SPECIFICATION/contracts.md`).

    For each factory slice (`is_spec_change == False`):

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

    Raises `GroomApprovalRequiredError` — before any slice is filed — if the
    approval record is absent or names no approver identity or route.
    Raises `GroomDraftError` — also before any slice is filed — if any factory
    slice has an empty `repo_target` or if a `depends_on` handle names no
    earlier factory slice in the draft.
    Raises `GroomExitRefusedError` if no local factory slice was filed.
    Raises `WorkItemNotFoundError` if `regroom_item_id` is absent.
    """
    approved = require_groom_approval(approval=approval)
    # The WHOLE cut is resolved before the FIRST write. Filing a slice is three
    # writes with no transaction behind them and no compensating delete, so a
    # malformed draft discovered mid-loop would leave the ledger holding some
    # approved slices while the rest do not exist and the original is still
    # open — a state a re-run cannot repair, because nothing records which ids
    # the failed attempt already minted. Refusing up front makes the seam
    # all-or-nothing without a transaction, which is the guarantee an absent
    # approval record already carried.
    plan = _plan_approved_slices(slices=slices, local_repo=local_repo, prefix=path.prefix)
    filed_ids: list[str] = []
    parses: list[SliceCriteriaParse] = []
    # Each filed local slice gets a `rank` appended below the previous one
    # (threaded `key_between`), so the dependency-layered draft order becomes
    # the ready-lane drain order.
    prev_rank: str | None = None
    for planned in plan.local:
        rank = key_between(a=prev_rank, b=None)
        prev_rank = rank
        item = _work_item_for(
            candidate=planned.candidate,
            slice_id=planned.slice_id,
            dep_entries=planned.dep_entries,
            rank=rank,
        )
        parses.append(_file_local_slice(path=path, item=item, approval=approved))
        filed_ids.append(planned.slice_id)
    regroom.close_regroomed_out(path=path, item_id=regroom_item_id, replacement_slice_ids=filed_ids)
    record_groom_approval(path=path, work_item_id=regroom_item_id, approval=approved)
    return GroomResult(
        filed_slice_ids=tuple(filed_ids),
        criteria_parses=tuple(parses),
        spec_change_slices=plan.spec_change,
        cross_repo_slices=plan.cross_repo,
        regroomed_out=True,
    )


@dataclass(frozen=True, kw_only=True)
class _PlannedLocalSlice:
    """One local factory slice, fully resolved and awaiting only its writes."""

    candidate: CandidateSlice
    slice_id: str
    dep_entries: tuple[DependsOnRaw, ...]


@dataclass(frozen=True, kw_only=True)
class _GroomPlan:
    """The whole approved cut, decided before the first slice is filed."""

    local: tuple[_PlannedLocalSlice, ...]
    spec_change: tuple[CandidateSlice, ...]
    cross_repo: tuple[CrossRepoSlice, ...]


def _plan_approved_slices(
    *, slices: list[CandidateSlice], local_repo: str, prefix: str
) -> _GroomPlan:
    """Mint every id and resolve every dependency handle, writing nothing.

    Pure with respect to the ledger: it walks the draft in order, sorts each
    slice into its route (spec-change, cross-repo, local), and resolves each
    local slice's `depends_on` handles against the slices that PRECEDE it. Any
    malformed draft raises here, where the ledger has not yet been touched.
    """
    # A spec-change slice routes to propose-change and is never minted, so no
    # id can ever exist for it. Its title is carried separately purely so the
    # refusal can say WHY the handle is unresolvable rather than merely that it
    # is — the two are the same observation to a maintainer re-drafting a cut.
    spec_change_titles = frozenset(
        candidate.title for candidate in slices if candidate.is_spec_change
    )
    local: list[_PlannedLocalSlice] = []
    spec_change: list[CandidateSlice] = []
    cross_repo: list[CrossRepoSlice] = []
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
        slice_id = new_work_item_id(prefix=prefix)
        if candidate.repo_target != local_repo:
            # Cross-repo slice: mint id, track for dep resolution, return for
            # external routing. NOT filed in the local tenant.
            id_by_title[candidate.title] = slice_id
            cross_repo_title_to_repo[candidate.title] = candidate.repo_target
            cross_repo.append(CrossRepoSlice(candidate=candidate, minted_id=slice_id))
            continue
        dep_entries = resolve_dep_entries(
            slice_title=candidate.title,
            handles=candidate.depends_on,
            id_by_title=id_by_title,
            cross_repo_title_to_repo=cross_repo_title_to_repo,
            spec_change_titles=spec_change_titles,
        )
        local.append(
            _PlannedLocalSlice(candidate=candidate, slice_id=slice_id, dep_entries=dep_entries)
        )
        id_by_title[candidate.title] = slice_id
    return _GroomPlan(
        local=tuple(local), spec_change=tuple(spec_change), cross_repo=tuple(cross_repo)
    )


def _file_local_slice(
    *, path: StoreConfig, item: WorkItem, approval: GroomApproval
) -> SliceCriteriaParse:
    """File one approved local slice, route it, stamp its approval, parse it.

    The three writes are kept in one place because they are one act: a slice
    that is filed but not routed is not ready, and a slice that is filed but
    not stamped is a slice nobody can attribute later.
    """
    append_work_item(path=path, item=item)
    _route_approved_slice_intake(path=path, item_id=item.id)
    # Stamped AFTER intake routing: the router rewrites the slice's modeled
    # metadata, so a stamp placed before it would be overlaid by the very
    # write that makes the slice ready.
    record_groom_approval(path=path, work_item_id=item.id, approval=approval)
    # Advisory only: an empty parse is REPORTED, never a refusal.
    return SliceCriteriaParse(slice_id=item.id, criteria=effective_criteria(item=item))


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
