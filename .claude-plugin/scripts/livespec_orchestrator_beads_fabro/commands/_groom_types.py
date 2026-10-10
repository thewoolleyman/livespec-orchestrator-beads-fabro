"""The drafted-slice and filed-groom result shapes."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    EffectiveCriteria,
)

__all__: list[str] = [
    "CandidateSlice",
    "CrossRepoSlice",
    "GroomResult",
    "SliceCriteriaParse",
]


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
    size_justification: object = None


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
