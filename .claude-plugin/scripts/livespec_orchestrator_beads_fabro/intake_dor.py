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

## The filing-time Definition-of-Done wall (v115)

The Definition-of-Done-and-Proof-of-Done clause of contracts.md gives this
primitive a second duty, and it is the only one of the six-gate duties above
whose input is the item's own DESCRIPTION rather than the capture dialogue:

    A MECHANICAL finding — the section absent, a reference unresolved, a
    proof-mode declaration or `Reason:` line malformed — withholds `ready`: an
    item filed with one outstanding MUST NOT be routed to `ready` by intake. A
    test-existence or scenario-reference finding the wall recognises is
    ADVISORY: it MUST be displayed and MUST NOT withhold `ready`, because only
    the gate can judge it. Either kind MUST be recorded on the filed item as a
    ledger comment, so it is repaired where it was made.

So the auto-admission step below gains ONE extra condition — no outstanding
mechanical finding — and every finding of either kind is appended as a comment.
The wording of each comment comes from `_dispatcher_filing_display`, so the
ledger comment and the pre-confirmation display name the finding identically; a
filer who read the display finds the same sentence on the item.

WHY THE GRADE IS SKIPPED WHEN THE CONNECTION DESCRIPTOR CARRIES NO `repo_root`.
Both halves of the wall are graded against the governed spec tree, which lives
in the repository: with no repository there is no tree, and an empty heading set
is the absence of evidence rather than evidence that a reference is wrong (the
reasoning `_dispatcher_definition_of_done_findings` records for the same read).
The one verdict where that absence could matter is the `ready` approval, and
that branch already raises `TypeError` on it, so nothing can reach `ready`
ungraded.

WHY THE COMMENTS ARE APPENDED AFTER THE STATUS WRITE. The routed status is the
durable outcome a dispatch reads; the comments are the explanation. Beads
comments are append-only, so this primitive is deliberately called ONCE per
filing — a second call on the same item would duplicate them rather than
reconcile them.

Alongside the routed status, `apply_intake_dor` stamps the
`intake:triaged` marker label for EVERY verdict — `pending-approval`,
`ready`, `backlog`, and `blocked` alike. The marker is what makes "the gate
saw this item" observable. Without it a `backlog` item the gate
deliberately parked for decomposition is indistinguishable from one filed
outside the gate entirely (a raw `bd create` never runs this primitive), and
neither is admitted by dispatch nor reported by any attention lane. The read
side of that discriminator lives in `_store_intake_triage`.

Per SPECIFICATION/constraints.md (the Result-vs-bugs split), routing a phantom
id raises `WorkItemNotFoundError`; genuine bugs propagate as raised built-in
exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from returns.io import IOFailure, IOResult, IOSuccess
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_advisories import (
    advisory_definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_findings import (
    definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    resolve_adopted_assertion_count_ceiling,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    ADVISORY_FINDING_PREFIX,
    MECHANICAL_FINDING_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_ADMISSION_POLICY,
    effective_admission_policy,
)
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.store import (
    INTAKE_TRIAGED_LABEL,
    materialize_work_items,
    read_work_items,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "DefinitionOfReadyChecklist",
    "FilingFindings",
    "Verdict",
    "apply_intake_dor",
    "evaluate",
    "filing_findings",
]

Verdict = Literal["pending-approval", "ready", "backlog", "blocked"]

_AUTO_ADMISSION = "auto"
_BLOCKED_REASON_NEEDS_HUMAN = "needs-human"
_BLOCKED_REASON_LABEL = f"blocked-reason:{_BLOCKED_REASON_NEEDS_HUMAN}"
_PENDING_APPROVAL_STATUS = "pending-approval"
_READY_STATUS = "ready"
_BACKLOG_STATUS = "backlog"
_BLOCKED_STATUS = "blocked"
_RETIRED_INTAKE_LABELS = ["not-yet-actionable"]


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


@dataclass(frozen=True, kw_only=True)
class FilingFindings:
    """One filed item's Definition-of-Done findings, split by what they DO.

    The two tuples are kept apart rather than merged behind a flag because their
    consequences are opposite: `mechanical` withholds `ready` and `advisory` is
    forbidden to. A single list carrying a kind marker is one dropped marker away
    from either holding every item out of the queue or admitting a malformed one.
    """

    mechanical: tuple[str, ...]
    advisory: tuple[str, ...]

    @property
    def withholds_ready(self) -> bool:
        """Whether an outstanding finding keeps this item out of `ready`."""
        return bool(self.mechanical)

    def comment_bodies(self) -> tuple[str, ...]:
        """One ledger-comment body per finding, mechanical ones first.

        The wording is the display's, imported rather than re-spelled, so the
        comment an operator finds on the item is the sentence the filing display
        showed them. Mechanical ones lead because they are the ones holding the
        item back.
        """
        return tuple(
            f"{MECHANICAL_FINDING_PREFIX} {finding}" for finding in self.mechanical
        ) + tuple(f"{ADVISORY_FINDING_PREFIX} {finding}" for finding in self.advisory)


def filing_findings(*, item: WorkItem, repo_root: Path | None) -> FilingFindings:
    """Both halves of the host-side wall for one filed item.

    A `None` repository root yields EMPTY findings rather than a refusal: both
    halves are graded against the governed spec tree, and with no repository
    there is no tree to grade against. That is not a fail-open on the `ready`
    approval — the approval branch raises `TypeError` on a `None` root before it
    can admit anything.
    """
    if repo_root is None:
        return FilingFindings(mechanical=(), advisory=())
    return FilingFindings(
        mechanical=definition_of_done_findings(item=item, cwd=repo_root),
        advisory=advisory_definition_of_done_findings(item=item, cwd=repo_root),
    )


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
) -> IOResult[Verdict, WorkItemNotFoundError | PolicySettingUnreadable]:
    """Evaluate the checklist and route a filed item into its lifecycle state.

    An item the store does not hold is an EXPECTED failure and rides the
    failure track. A `StoreConfig` with no `repo_root` is NOT: that is a
    caller bug, and it still raises `TypeError` for the outermost
    supervisor. `IOResult` because the whole body is store and
    filesystem IO.

    The Definition-of-Done findings are graded BEFORE the auto-admission step,
    because a mechanical one is what that step has to stop on, and they are
    recorded on the item afterwards whatever the verdict was.
    """
    repo_root = path.repo_root
    if repo_root is not None:
        ceiling = resolve_adopted_assertion_count_ceiling(cwd=repo_root)
        if not is_successful(ceiling):
            return IOFailure(unsafe_perform_io(ceiling.failure()))

    client = make_beads_client(config=path)
    if not client.exists(issue_id=item_id):
        return IOFailure(WorkItemNotFoundError(item_id=item_id))

    item = materialize_work_items(records=read_work_items(path=path))[item_id]
    verdict = evaluate(checklist=checklist)
    status = _routed_status(verdict=verdict, has_dependencies=bool(item.depends_on))
    findings = filing_findings(item=item, repo_root=path.repo_root)
    if status == _PENDING_APPROVAL_STATUS and not item.depends_on:
        repo_root = path.repo_root
        if repo_root is None:
            msg = "StoreConfig.repo_root is required for intake admission policy resolution"
            raise TypeError(msg)
        # An unreadable `.livespec.jsonc` falls back to the safe `manual`
        # default, visibly and here rather than inside the reader: an item
        # whose policy cannot be read waits for a human instead of being
        # routed straight to `ready`. `unsafe_perform_io` is required —
        # `IOResult.value_or` returns `IO[value]`, not the value.
        policy = unsafe_perform_io(
            effective_admission_policy(item=item, cwd=repo_root).value_or(DEFAULT_ADMISSION_POLICY)
        )
        # An outstanding MECHANICAL finding stops the approval here. An ADVISORY
        # one deliberately does not: only the gate can judge a test-existence or
        # scenario-reference form, and withholding `ready` on a judgement this
        # surface cannot make would hand the operator a refusal nothing clears.
        if policy == _AUTO_ADMISSION and not findings.withholds_ready:
            status = _READY_STATUS

    # The triage marker is stamped for EVERY verdict, not just the routed-on
    # ones: it records that the gate SAW this item, which is the only thing
    # that distinguishes a deliberately-parked `backlog` epic from an item
    # filed through a door the gate never guarded (see `_store_intake_triage`).
    add_labels = [INTAKE_TRIAGED_LABEL]
    if status == _BLOCKED_STATUS:
        add_labels.append(_BLOCKED_REASON_LABEL)
    remove_labels = list(_RETIRED_INTAKE_LABELS)
    if status != _BLOCKED_STATUS:
        remove_labels.append(_BLOCKED_REASON_LABEL)
    client.update_issue(
        issue_id=item_id,
        status=status,
        add_labels=add_labels,
        remove_labels=remove_labels,
    )
    for body in findings.comment_bodies():
        client.add_comment(issue_id=item_id, body=body)
    return IOSuccess(status)


def _routed_status(*, verdict: Verdict, has_dependencies: bool) -> Verdict:
    """Keep linked dependencies out of direct `ready` routing."""
    if has_dependencies and verdict == _PENDING_APPROVAL_STATUS:
        return _PENDING_APPROVAL_STATUS
    return verdict
