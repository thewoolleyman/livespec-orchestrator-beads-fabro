"""The intake Definition-of-Ready checklist — the shared capture-time triage.

The grooming realization gives every capture front-end one intake gate so
that only autonomously-dispatchable work reaches the factory
(SPECIFICATION/scenarios.md "Scenario 8 — Intake Definition-of-Ready
triage"; the normative clause in contracts.md §"Gap-detectable behavior
clauses"):

    The `capture-work-item` and `capture-impl-gaps` capture front-ends
    MUST run the intake Definition-of-Ready checklist over the six gates
    at capture and MUST tag the resulting item `ready`, `needs-regroom`,
    or `not-yet-actionable` accordingly — a single-coherent-done,
    autonomously-verifiable, autonomy-tiered, dependency-linked,
    repo-targeted, above-floor item is tagged `ready`; an item with more
    than one coherent "done" (an epic) MUST be tagged `needs-regroom`; an
    item whose acceptance is not autonomously verifiable, or that has
    unresolved blockers, MUST be tagged `not-yet-actionable` and MUST NOT
    be filed as `ready`.

This module is the ONE shared primitive both front-ends call — the
gate logic lives here once, never duplicated. A front-end's
SKILL.md gathers the six checklist answers from the capture dialogue,
files the item through the normal store path, and then calls
`apply_intake_dor` to evaluate the verdict and stamp the tag on the
filed item.

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

The verdict and its tagging (per the clause's precedence):

- A non-autonomously-verifiable item, OR one with unresolved blockers, is
  `not-yet-actionable` — it needs a human judgement call or a blocker
  cleared before the factory can touch it, so it MUST NOT be filed
  `ready`. This is the hardest invariant and is checked FIRST.
- An item with more than one coherent "done" (an epic) is `needs-regroom`
  — it is surfaced for grooming via the shared `regroom.enter` verb (the
  same single entry the Dispatcher non-convergence bounce uses), never
  filed `ready`.
- An item that clears all six gates is `ready` — eligible for autonomous
  dispatch.
- Any other gate failure (a single-done, verifiable, unblocked item that
  is nonetheless missing its autonomy tier, dependency links, repo
  target, or sits below the size floor) is `not-yet-actionable`: it is
  not dispatchable as-filed and needs a maintainer to fill in the missing
  facet, which is itself a judgement call. It is never silently filed
  `ready`.

Per SPECIFICATION/constraints.md §"Inherited from livespec" (the
Result-vs-bugs split), the expected failure of stamping a phantom id
raises `WorkItemNotFoundError` (from `regroom`'s `_assert_present`);
genuine bugs propagate as raised built-in exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from livespec_orchestrator_beads_fabro import regroom
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "NOT_YET_ACTIONABLE_LABEL",
    "READY_LABEL",
    "DefinitionOfReadyChecklist",
    "Verdict",
    "apply_intake_dor",
    "evaluate",
]

Verdict = Literal["ready", "needs-regroom", "not-yet-actionable"]

# The readiness tag the checklist stamps on an autonomously-dispatchable
# slice. Shared with `regroom.READY_LABEL` (the `exit_regroom` gate looks
# for this exact label on replacement slices), so it is re-exported from
# the one canonical definition rather than re-spelled here.
READY_LABEL = regroom.READY_LABEL

# The tag for an item the factory must NOT auto-dispatch — its acceptance
# needs a human judgement call, it has an unresolved blocker, or it is
# missing a dispatch facet. A bare label (no `key:value`) because its
# presence IS the state, the same encoding `needs-regroom` uses.
NOT_YET_ACTIONABLE_LABEL = "not-yet-actionable"


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
    """Map the six checklist gates onto the intake verdict.

    Pure function — no I/O. The precedence:

    1. An epic (more than one coherent "done") is `needs-regroom` FIRST —
       decomposition is the actionable next step, and per-slice
       verifiability/deps/tier/repo get resolved during grooming, so an
       epic is surfaced for grooming even if other gates also fail.
    2. Otherwise, a non-autonomously-verifiable item OR one with
       unresolved blockers (its dependencies are not linked) is
       `not-yet-actionable` — it needs a human judgement call or a blocker
       cleared, so it MUST NOT fall through to `ready`.
    3. Otherwise, an item that clears the remaining `ready` gates
       (autonomy-tiered, repo-targeted, above-floor) is `ready`.
    4. Any other gate failure leaves a single-done, verifiable, unblocked
       item that is missing a dispatch facet — `not-yet-actionable`, never
       silently `ready`.
    """
    if not checklist.single_coherent_done:
        return "needs-regroom"
    # An unlinked dependency is an unresolved blocker for triage purposes.
    if not checklist.autonomously_verifiable or not checklist.dependency_linked:
        return "not-yet-actionable"
    if checklist.autonomy_tiered and checklist.repo_targeted and checklist.above_floor:
        return "ready"
    return "not-yet-actionable"


def apply_intake_dor(
    *,
    path: StoreConfig,
    item_id: str,
    checklist: DefinitionOfReadyChecklist,
) -> Verdict:
    """Evaluate the checklist and stamp the verdict tag on a filed item.

    The shared call every capture front-end makes AFTER filing the item:
    it evaluates the six gates, then applies the resulting tag to
    `item_id` through the store/client seam:

    - `needs-regroom` is applied via the shared `regroom.enter` verb (the
      one observable entry mutation, shared with the Dispatcher
      non-convergence bounce).
    - `ready` / `not-yet-actionable` are applied as the corresponding
      bare label.

    Returns the `Verdict` so the front-end can narrate the outcome to the
    user. Raises `WorkItemNotFoundError` if `item_id` is not present in
    the tenant (the expected failure of stamping a phantom id).
    """
    verdict = evaluate(checklist=checklist)
    if verdict == "needs-regroom":
        regroom.enter(path=path, item_id=item_id)
        return verdict
    label = READY_LABEL if verdict == "ready" else NOT_YET_ACTIONABLE_LABEL
    client = make_beads_client(config=path)
    if not client.exists(issue_id=item_id):
        # The same phantom-id guarantee the regroom verbs give: a triage
        # against an id that was never filed is an expected failure the
        # caller surfaces, not a silent no-op mutating nothing.
        raise WorkItemNotFoundError(item_id=item_id)
    client.update_issue(issue_id=item_id, add_labels=[label])
    return verdict
