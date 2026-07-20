"""Dispatcher admission + post-merge acceptance valves (pure planning layer).

The Dispatcher (`dispatcher.py` `dispatch`/`loop`) is the sole enforcer of
the two human-delegable policy valves that bracket the WIP-limited autonomous
middle of the work-item lifecycle, per the admission / WIP-cap / post-merge
acceptance contract in SPECIFICATION/contracts.md:

- **Approval (`pending-approval -> ready`) + admission (`ready -> active`).**
  The Dispatcher surfaces effective-`manual` `pending-approval` items for a
  human `approve:` and auto-approves only effective-`auto` items into `ready`.
  Once an item is `ready`, admission is mechanical: when a WIP slot frees, the
  Dispatcher admits the highest-`rank` ready item with a resolvable assignee,
  sets its `assignee`, and transitions it to `active`. The per-repo WIP cap
  (`livespec-orchestrator-beads-fabro.dispatcher.wip_cap` in `.livespec.jsonc`,
  default 5) bounds how many items are driven into `active` at once.
- **Post-merge acceptance (`acceptance -> done`).** `complete` merges on
  green into `acceptance` (merged + live); `accept` then confirms post-ship
  per the effective `acceptance_policy` (`ai-only` -> autonomously to `done`;
  `human-only` / `ai-then-human` (the default) -> park in `acceptance` until a
  human confirms). `reject` from `acceptance` routes by corrective kind
  (`rework -> active` fix-forward; `re-groom -> backlog` revert + re-decompose).

This module is the PURE planning layer: it owns the policy-resolution and
selection decisions as deterministic functions over in-memory `WorkItem`s plus
the `.livespec.jsonc` WIP-cap read. The store writes (the `ready -> active`
admit, the `active -> acceptance` complete, the `acceptance -> done` accept,
the bounce/reject transitions) live in `store.update_work_item_status` and are
sequenced by `dispatcher.py`; keeping the decisions here keeps them small,
testable, and free of dispatch IO.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_ACCEPTANCE_POLICY,
    DEFAULT_ACCEPTANCE_REWORK_CAP,
    DEFAULT_ADMISSION_POLICY,
    DEFAULT_AUTO_APPROVE_READY,
    DEFAULT_MERGE_ON_REVIEW_CAP,
    DEFAULT_REVIEW_FIX_CAP,
    DEFAULT_WIP_CAP,
    effective_acceptance_policy,
    effective_acceptance_rework_cap,
    effective_admission_policy,
    effective_merge_on_review_cap,
    effective_review_fix_cap,
    resolve_acceptance_mode,
    resolve_acceptance_rework_cap,
    resolve_auto_approve_ready,
    resolve_merge_on_review_cap,
    resolve_review_fix_cap,
    resolve_wip_cap,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DEFAULT_ACCEPTANCE_POLICY",
    "DEFAULT_ACCEPTANCE_REWORK_CAP",
    "DEFAULT_ADMISSION_POLICY",
    "DEFAULT_AUTO_APPROVE_READY",
    "DEFAULT_DOER",
    "DEFAULT_MERGE_ON_REVIEW_CAP",
    "DEFAULT_REVIEW_FIX_CAP",
    "DEFAULT_WIP_CAP",
    "AcceptanceDecision",
    "AdmissionPlan",
    "acceptance_decision",
    "admission_held_detail",
    "effective_acceptance_policy",
    "effective_acceptance_rework_cap",
    "effective_admission_policy",
    "effective_merge_on_review_cap",
    "effective_review_fix_cap",
    "plan_admissions",
    "reject_routing",
    "resolve_acceptance_mode",
    "resolve_acceptance_rework_cap",
    "resolve_assignee",
    "resolve_auto_approve_ready",
    "resolve_merge_on_review_cap",
    "resolve_review_fix_cap",
    "resolve_wip_cap",
]

# The autonomous doer the admission valve assigns when an item carries no
# explicit assignee. `assignee` is the reused work-item field (not a new
# `owner`), per the admission contract.
DEFAULT_DOER = "fabro"

# The one admission policy that auto-admits without a human in the loop.
_AUTO_ADMISSION = "auto"

# The one acceptance policy that confirms to `done` without a human.
_AI_ONLY_ACCEPTANCE = "ai-only"

# `reject` corrective kinds (per SPECIFICATION/contracts.md): `rework` is a
# fix-forward patch on top of the live change (back to `active`); `re-groom`
# reverts the merged change and re-decomposes (back to `backlog`).
_REJECT_REWORK = "rework"
_REJECT_REGROOM = "re-groom"
_REWORK_TARGET = "active"
_REGROOM_TARGET = "backlog"

# Hold reasons surfaced when the admission valve refuses to admit a ready item.
_HELD_MANUAL = "manual-admission"
_HELD_UNRESOLVABLE = "unresolvable-assignee"


@dataclass(frozen=True, kw_only=True)
class AdmissionPlan:
    """The admission decision over a rank-sorted ready candidate set.

    `approved` carries each effective-`auto` pending item to drive
    `pending-approval -> ready`; `admitted` carries each `(item, assignee)` to
    drive `ready -> active`; `held` carries each `(item, reason)` the
    maintainer must act on (a `manual-admission` approval or an
    `unresolvable-assignee` assignment).
    A capacity-deferred admission-eligible item (one beyond the free WIP
    slots) appears in NEITHER list — it simply waits for the next pass.
    """

    approved: tuple[WorkItem, ...]
    admitted: tuple[tuple[WorkItem, str], ...]
    held: tuple[tuple[WorkItem, str], ...]


@dataclass(frozen=True, kw_only=True)
class AcceptanceDecision:
    """The post-ship acceptance decision for one item's effective policy.

    `to_done` is True only for `ai-only` (the AI pass confirms and accepts
    autonomously); every other policy parks the item in `acceptance` until a
    human confirms.
    """

    policy: str
    to_done: bool


def resolve_assignee(*, item: WorkItem) -> str | None:
    """Resolve the assignee for an item being admitted.

    An explicit `assignee` is honored; otherwise the autonomous doer
    (`DEFAULT_DOER`) is assigned. The `str | None` return is the contract
    seam for "an item whose assignee cannot be resolved is not admitted" —
    the planner holds a `None`-resolving item rather than admitting it.
    """
    return item.assignee or DEFAULT_DOER


def plan_admissions(
    *,
    ready_items: Sequence[WorkItem],
    free_slots: int,
    cwd: Path,
    resolve_assignee: Callable[..., str | None],
    admission_policy: Callable[..., str] = effective_admission_policy,
) -> AdmissionPlan:
    """Plan which rank-sorted candidates to approve, admit, hold, or defer.

    `ready_items` MUST already be in dispatch order and may contain `ready`
    items plus `pending-approval` items whose dependencies are clear. Each item
    resolves to exactly one of:

    - HELD with `manual-admission` — a `pending-approval` item whose effective
      `admission_policy != "auto"`, surfaced for explicit human approval.
    - APPROVED — a `pending-approval` item whose effective policy is `auto`; it
      moves to `ready` and may also be admitted in the same pass if capacity is
      available.
    - HELD with `unresolvable-assignee` — approved/ready, but
      `resolve_assignee` returns `None` (no assignee to drive the work).
    - ADMITTED — ready + resolvable + a free slot remains.
    - DEFERRED (in neither admitted nor held) — ready + resolvable but no free
      slot left; it waits at `ready` for the next pass.

    `admission_policy` gates only the pending approval transition. Once an item
    is `ready`, admission to `active` is mechanical. The `admission_policy`
    resolver is an injected seam defaulting to `effective_admission_policy`,
    and `cwd` is required so global policy settings cannot be skipped.
    keeping this a PURE, mode-agnostic planner.
    """
    approved: list[WorkItem] = []
    admitted: list[tuple[WorkItem, str]] = []
    held: list[tuple[WorkItem, str]] = []
    for item in ready_items:
        if item.status == "pending-approval":
            if admission_policy(item=item, cwd=cwd) != _AUTO_ADMISSION:
                held.append((item, _HELD_MANUAL))
                continue
            approved.append(item)
        assignee = resolve_assignee(item=item)
        if assignee is None:
            held.append((item, _HELD_UNRESOLVABLE))
            continue
        if len(admitted) >= free_slots:
            continue
        admitted.append((item, assignee))
    return AdmissionPlan(approved=tuple(approved), admitted=tuple(admitted), held=tuple(held))


def acceptance_decision(*, policy: str) -> AcceptanceDecision:
    """Decide whether the AI acceptance pass confirms straight to `done`.

    `ai-only` accepts autonomously; `human-only` / `ai-then-human` park in
    `acceptance` until a human confirms (there is no "release with zero
    verification" — the AI pass always runs first regardless of policy).
    """
    return AcceptanceDecision(policy=policy, to_done=policy == _AI_ONLY_ACCEPTANCE)


def reject_routing(*, kind: str) -> str:
    """Map a `reject` corrective kind to its target status.

    `rework` -> `active` (fix-forward on the live change); `re-groom` ->
    `backlog` (revert + re-decompose). An unknown kind is a programmer error
    (a bug, not an expected domain error), so it raises `ValueError`.
    """
    if kind == _REJECT_REWORK:
        return _REWORK_TARGET
    if kind == _REJECT_REGROOM:
        return _REGROOM_TARGET
    msg = f"unknown reject kind {kind!r} (expected 'rework' or 're-groom')"
    raise ValueError(msg)


def admission_held_detail(*, item_id: str, reason: str) -> str:
    """Build the actionable surface message for an item held at the admission valve.

    Routed as DATA (the held `DispatchOutcome.detail` for a targeted
    dispatch, and the stderr SURFACE line for a loop drain), so the
    maintainer reads a clear instruction: a `manual-admission` item awaits an
    explicit approve into `ready`; an `unresolvable-assignee` item needs an
    assignee before it can be driven. Nothing is closed — the item stays put.
    """
    if reason == _HELD_MANUAL:
        return (
            f"approval held: work-item {item_id} has effective admission_policy "
            "manual and rests at pending-approval until a human explicitly "
            "approves it into ready; the Dispatcher never auto-approves "
            "risky/irreversible work."
        )
    return (
        f"admission held: work-item {item_id} could not be admitted because its "
        "assignee is unresolvable — surface it for the maintainer to assign a "
        "doer before it can be driven into active."
    )
