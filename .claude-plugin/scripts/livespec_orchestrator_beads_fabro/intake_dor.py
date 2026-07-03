"""The intake Definition-of-Ready checklist — shared capture-time routing.

The capture front-ends use one intake gate so newly filed work-items enter
their lifecycle state consistently (SPECIFICATION/scenarios.md "Scenario 8 —
Intake Definition-of-Ready triage"; the normative clause in contracts.md):

    The `capture-work-item` and `capture-impl-gaps` capture front-ends
    MUST run the intake Definition-of-Ready checklist over the six gates
    at capture and MUST route the resulting item into its lifecycle state
    accordingly — a single-coherent-done, autonomously-verifiable,
    autonomy-tiered, dependency-linked, repo-targeted, above-floor item
    lands in `pending-approval` (approved on into `ready` when its
    effective `admission_policy` is `auto`); an item with more than one
    coherent "done" (an epic) MUST land in `backlog`; an item whose
    acceptance is not autonomously verifiable MUST land in `blocked` with
    `blocked_reason: needs-human`; an item with unresolved blockers is
    filed with its dependency edges linked and MUST NOT land directly in
    `ready`.

This module is the ONE shared primitive both front-ends call. A front-end's
prose gathers the six checklist answers from the capture dialogue, files the
item through the normal store path, and then calls `apply_intake_dor` to
evaluate the verdict and route the filed item through the store/client seam.

The six gates (each a boolean the capture dialogue resolves):

- `single_coherent_done` — the item has exactly one coherent "done" (not
  an epic). False means more than one coherent "done".
- `autonomously_verifiable` — the acceptance can be checked by the factory
  WITHOUT a human judgement call.
- `autonomy_tiered` — the item carries an explicit autonomy tier.
- `dependency_linked` — the item's blockers/deps are linked (or it has
  none).
- `repo_targeted` — the item names the repo it lands in.
- `above_floor` — the item is above the size floor (not too small to be
  worth a discrete dispatch).

The verdict and routing precedence:

- An item with more than one coherent "done" (an epic) is `backlog` so it
  can be decomposed before dispatch.
- A non-autonomously-verifiable item, or a single-slice item missing another
  dispatch facet, is `blocked` with `blocked_reason: needs-human`.
- An item that clears all six gates is `pending-approval`; if its effective
  `admission_policy` is `auto` and it has no dependency edges, the primitive
  approves it onward into `ready`.
- A filed item with dependency edges stays out of direct `ready` routing even
  when its effective admission policy is `auto`; the dependency lane is
  derived from those linked edges.

Per SPECIFICATION/constraints.md (the Result-vs-bugs split), routing a phantom
id raises `WorkItemNotFoundError`; genuine bugs propagate as raised built-in
exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DefinitionOfReadyChecklist",
    "Verdict",
    "apply_intake_dor",
    "evaluate",
]

Verdict = Literal["pending-approval", "ready", "backlog", "blocked"]

_AUTO_ADMISSION = "auto"
_BLOCKED_REASON_NEEDS_HUMAN = "needs-human"
_BLOCKED_REASON_LABEL = f"blocked-reason:{_BLOCKED_REASON_NEEDS_HUMAN}"
_PENDING_APPROVAL_STATUS = "pending-approval"
_READY_STATUS = "ready"
_BACKLOG_STATUS = "backlog"
_BLOCKED_STATUS = "blocked"
_RETIRED_INTAKE_LABELS = ["ready", "needs-regroom", "not-yet-actionable"]


@dataclass(frozen=True, kw_only=True)
class DefinitionOfReadyChecklist:
    """The six intake gates the capture dialogue resolves for one item.

    Each field is the capture front-end's answer to one gate. The
    front-end SKILL.md walks the maintainer (or auto-fills from the gap /
    freeform inputs) through these, then hands the assembled
    checklist to `apply_intake_dor`.
    """

    single_coherent_done: bool
    autonomously_verifiable: bool
    autonomy_tiered: bool
    dependency_linked: bool
    repo_targeted: bool
    above_floor: bool


def evaluate(*, checklist: DefinitionOfReadyChecklist) -> Verdict:
    """Map the six checklist gates onto the intake lifecycle verdict.

    Pure function — no I/O and no admission-policy lookup. Auto-admission and
    dependency-edge handling are applied by `apply_intake_dor`, because they
    depend on the filed work-item's current store record.
    """
    if not checklist.single_coherent_done:
        return _BACKLOG_STATUS
    if (
        not checklist.autonomously_verifiable
        or not checklist.dependency_linked
        or not checklist.autonomy_tiered
        or not checklist.repo_targeted
        or not checklist.above_floor
    ):
        return _BLOCKED_STATUS
    return _PENDING_APPROVAL_STATUS


def apply_intake_dor(
    *,
    path: StoreConfig,
    item_id: str,
    checklist: DefinitionOfReadyChecklist,
) -> Verdict:
    """Evaluate the checklist and route a filed item into its lifecycle state."""
    client = make_beads_client(config=path)
    if not client.exists(issue_id=item_id):
        raise WorkItemNotFoundError(item_id=item_id)

    item = materialize_work_items(records=read_work_items(path=path))[item_id]
    verdict = evaluate(checklist=checklist)
    status = _routed_status(verdict=verdict, has_dependencies=bool(item.depends_on))
    if (
        status == _PENDING_APPROVAL_STATUS
        and item.admission_policy == _AUTO_ADMISSION
        and not item.depends_on
    ):
        status = _READY_STATUS

    add_labels = [_BLOCKED_REASON_LABEL] if status == _BLOCKED_STATUS else []
    remove_labels = list(_RETIRED_INTAKE_LABELS)
    if status != _BLOCKED_STATUS:
        remove_labels.append(_BLOCKED_REASON_LABEL)
    client.update_issue(
        issue_id=item_id,
        status=status,
        add_labels=add_labels,
        remove_labels=remove_labels,
    )
    return status


def _routed_status(*, verdict: Verdict, has_dependencies: bool) -> Verdict:
    """Keep linked dependencies out of direct `ready` routing."""
    if has_dependencies and verdict == _PENDING_APPROVAL_STATUS:
        return _PENDING_APPROVAL_STATUS
    return verdict
