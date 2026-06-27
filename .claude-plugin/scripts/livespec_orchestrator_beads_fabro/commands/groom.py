"""`groom` — the agent-drafts / human-approves regroom front-end.

The one new maintainer surface the grooming realization adds
(SPECIFICATION/contracts.md; the
journey in SPECIFICATION/scenarios.md "Scenario 7 — Regroom an oversized
work-item"; the normative clause in SPECIFICATION/contracts.md):

    Given a `needs-regroom` item, the groom regroom front-end MUST produce
    a READ-ONLY drafted decomposition (candidate slices pre-filled with
    acceptance / autonomy tier / dependency links / repo target / scope
    and arranged into dependency layers) and MUST file nothing until the
    maintainer approves; on approval it MUST file the approved slices via
    `capture-work-item` with dependency edges linked, and MUST route any
    spec-change slice to `/livespec:propose-change` rather than to the
    factory.

The skill is heavyweight: the read-only scoping conversation and the
draft itself are the LLM-driven SKILL.md dialogue. This module is the
load-bearing mechanical seam underneath that dialogue, in two halves:

- `load_groom_context` — the READ-ONLY entry: it confirms the target is
  actually at `needs-regroom` (refusing otherwise) and returns the item's
  title/description so the draft is grounded in the real item. It mutates
  NOTHING — the draft stays read-only until the maintainer approves.
- `file_approved_slices` — the APPROVAL-time commit: it files each
  LOCAL factory slice (repo_target == local_repo) via the same
  `append_work_item` machinery the capture front-ends use (tagging each
  `ready` and linking its dependency edges), then transitions the original
  item OUT of `needs-regroom` via the shared `regroom.exit_regroom` verb
  against the filed slice ids. Cross-repo factory slices (repo_target !=
  local_repo) are NOT filed in the local tenant — they are returned in
  `GroomResult.cross_repo_slices` with their minted ids for the SKILL.md
  prose to route to the target repo's groom/capture front-end (the
  one-slice/one-ledger model). Spec-change slices are returned (not filed)
  for the prose to route to `/livespec:propose-change`. Local slices whose
  `depends_on` title handle resolves to a cross-repo blocker carry a
  `sibling_work_item` dep entry so the Dispatcher can gate on it. The exit
  verb REFUSES (`RegroomExitRefusedError`) unless real `ready` local
  factory slices were filed, so an item is regroomed-OUT, never silently
  dropped.

Per SPECIFICATION/constraints.md (the
Result-vs-bugs split), EXPECTED failures raise the typed errors from
`errors.py` (`WorkItemNotFoundError`, `GroomTargetNotRegroomError`,
`RegroomExitRefusedError`); genuine bugs propagate as raised built-in
exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro import regroom
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.errors import GroomDraftError, GroomTargetNotRegroomError
from livespec_orchestrator_beads_fabro.intake_dor import READY_LABEL
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

    Returned by `load_groom_context` after confirming the target is at
    `needs-regroom`. Carries only what the draft needs; the front-end's
    dialogue reads the spec / scenarios / ledger separately (read-only).
    """

    item_id: str
    title: str
    description: str


@dataclass(frozen=True, kw_only=True)
class CandidateSlice:
    """One drafted candidate slice in the layered decomposition.

    The maintainer-approved shape: every field the intake Definition-of-
    Ready checklist gates on is pre-filled, so a filed factory slice is
    `ready` by construction. `is_spec_change` marks a human-gated
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

    - `filed_slice_ids` — the local factory slices filed `ready` into the
      ledger (in draft order), with their dependency edges linked.
    - `spec_change_slices` — the approved spec-change slices NOT filed
      here; the SKILL.md prose routes each to `/livespec:propose-change`.
    - `cross_repo_slices` — factory slices whose `repo_target` differs from
      `local_repo`; NOT filed in the local tenant. Returned with their
      minted ids for the SKILL.md prose to route to the target repo.
    - `regroomed_out` — True once the original item left `needs-regroom`
      via `regroom.exit_regroom` against the filed factory slices.
    """

    filed_slice_ids: tuple[str, ...] = ()
    spec_change_slices: tuple[CandidateSlice, ...] = ()
    cross_repo_slices: tuple[CrossRepoSlice, ...] = ()
    regroomed_out: bool = False


def load_groom_context(*, path: StoreConfig, item_id: str) -> GroomContext:
    """Read the `needs-regroom` target read-only, refusing a non-regroom id.

    The READ-ONLY entry point: it confirms `item_id` is present (raising
    `WorkItemNotFoundError` otherwise, via the shared regroom predicate)
    and is actually at `needs-regroom` (raising
    `GroomTargetNotRegroomError` otherwise — grooming a `ready` or
    already-groomed item is an expected misuse the front-end surfaces,
    not a silent no-op). Mutates nothing; the draft stays read-only until
    `file_approved_slices` is called on approval.
    """
    if not regroom.is_needs_regroom(path=path, item_id=item_id):
        raise GroomTargetNotRegroomError(item_id=item_id)
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
    """File approved local factory slices `ready`, then regroom the original OUT.

    Called ONLY after the maintainer approves the draft. For each factory
    slice (`is_spec_change == False`):

    - If `repo_target == local_repo` (a LOCAL slice): file via
      `append_work_item`, tag `ready`, link dependency edges. Local slices
      that depend (by draft-title handle) on a cross-repo blocker carry a
      `sibling_work_item` dep so the Dispatcher can gate on it.
    - If `repo_target != local_repo` (a CROSS-REPO slice): mint an id but
      do NOT file locally (the one-slice/one-ledger model). The slice is
      returned in `GroomResult.cross_repo_slices` with its minted id for
      the SKILL.md prose to route to the target repo.

    After all slices are processed, the original item is transitioned out
    of `needs-regroom` via `regroom.exit_regroom` against the filed LOCAL
    slice ids.

    Raises `GroomDraftError` if any factory slice has an empty `repo_target`
    or if a `depends_on` handle names no earlier factory slice in the draft.
    Raises `RegroomExitRefusedError` if no local factory slice was filed.
    Raises `WorkItemNotFoundError` if `regroom_item_id` is absent.
    """
    client = make_beads_client(config=path)
    filed_ids: list[str] = []
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
        append_work_item(
            path=path,
            item=_work_item_for(candidate=candidate, slice_id=slice_id, dep_entries=dep_entries),
        )
        # Tag the freshly-filed factory slice `ready` so the Dispatcher can
        # drain it and so `exit_regroom`'s ready-gate accepts it as a real
        # replacement (the same readiness tag the intake checklist applies).
        client.update_issue(issue_id=slice_id, add_labels=[READY_LABEL])
        filed_ids.append(slice_id)
        id_by_title[candidate.title] = slice_id
    regroom.exit_regroom(path=path, item_id=regroom_item_id, ready_slice_ids=filed_ids)
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
) -> WorkItem:
    """Build the freeform `ready` work-item for one approved local factory slice.

    A groomed slice is freeform (the cut is the maintainer's, not tied to
    a single detected gap clause); its acceptance is folded into the
    description so the dispatched implementer carries it. `dep_entries`
    carries the fully-typed dependency entries (local or sibling_work_item)
    already resolved from the earlier draft slices.
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
        status="open",
        title=candidate.title,
        description=description,
        origin="freeform",
        gap_id=None,
        priority=candidate.priority,
        assignee=None,
        depends_on=dep_entries,
        captured_at=_now_iso(),
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
    )


def _record_str(*, record: BeadsRecord, key: str) -> str:
    value = record.get(key)
    return value if isinstance(value, str) else ""


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
