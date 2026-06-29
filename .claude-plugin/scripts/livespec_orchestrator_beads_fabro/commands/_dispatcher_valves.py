"""Dispatcher admission + post-merge acceptance valves (pure planning layer).

The Dispatcher (`dispatcher.py` `dispatch`/`loop`) is the sole enforcer of
the two human-delegable policy valves that bracket the WIP-limited autonomous
middle of the work-item lifecycle, per the admission / WIP-cap / post-merge
acceptance contract in SPECIFICATION/contracts.md:

- **Admission (`ready -> active`).** When a WIP slot frees, the Dispatcher
  admits the highest-`rank` admission-eligible `ready` item — eligible =
  effective `admission_policy == "auto"` AND a resolvable assignee — sets its
  `assignee`, and transitions it to `active`. A `manual` (or `None` ->
  inherit -> `manual`) item is HELD at the valve (surfaced for the maintainer
  to approve), never auto-admitted. The per-repo WIP cap
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
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DEFAULT_ACCEPTANCE_POLICY",
    "DEFAULT_ADMISSION_POLICY",
    "DEFAULT_DOER",
    "DEFAULT_WIP_CAP",
    "AcceptanceDecision",
    "AdmissionPlan",
    "acceptance_decision",
    "admission_held_detail",
    "effective_acceptance_policy",
    "effective_admission_policy",
    "plan_admissions",
    "reject_routing",
    "resolve_assignee",
    "resolve_wip_cap",
]

# The per-repo WIP cap default — NOT a fleet-wide number. Total fleet
# concurrency is the sum of the per-repo caps (per SPECIFICATION/contracts.md).
DEFAULT_WIP_CAP = 5

# The autonomous doer the admission valve assigns when an item carries no
# explicit assignee. `assignee` is the reused work-item field (not a new
# `owner`), per the admission contract.
DEFAULT_DOER = "fabro"

# The safe-by-default effective policies for a `None` (inherit) field: a
# work-item with no explicit `admission_policy` waits for a human's explicit
# approval; with no explicit `acceptance_policy` it requires a human's final
# acceptance after the AI pass (per SPECIFICATION/contracts.md).
DEFAULT_ADMISSION_POLICY = "manual"
DEFAULT_ACCEPTANCE_POLICY = "ai-then-human"

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

_LIVESPEC_CONFIG = ".livespec.jsonc"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_DISPATCHER_KEY = "dispatcher"
_WIP_CAP_KEY = "wip_cap"


@dataclass(frozen=True, kw_only=True)
class AdmissionPlan:
    """The admission decision over a rank-sorted ready candidate set.

    `admitted` carries each `(item, assignee)` to drive `ready -> active`;
    `held` carries each `(item, reason)` the maintainer must act on (a
    `manual-admission` approval or an `unresolvable-assignee` assignment).
    A capacity-deferred admission-eligible item (one beyond the free WIP
    slots) appears in NEITHER list — it simply waits for the next pass.
    """

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


def resolve_wip_cap(*, cwd: Path) -> int:
    """Read the per-repo WIP cap from `.livespec.jsonc`, defaulting to 5.

    The cap lives at `livespec-orchestrator-beads-fabro.dispatcher.wip_cap`.
    A missing file/block/key, a parse error, or a non-positive / non-int
    value all fall back to `DEFAULT_WIP_CAP` (the read never raises — an
    unconfigured repo gets the safe default, mirroring the merge-evidence
    check's `_resolve_canonical_branch`).
    """
    value = _read_nested_config_value(cwd=cwd, keys=(_PLUGIN_BLOCK, _DISPATCHER_KEY, _WIP_CAP_KEY))
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return DEFAULT_WIP_CAP


def _read_nested_config_value(*, cwd: Path, keys: tuple[str, ...]) -> object:
    """Descend `.livespec.jsonc` along `keys`, returning the leaf value or None.

    Returns None on a missing file, a parse error, or any intermediate level
    that is absent or not a JSON object — so the caller applies its own
    default rather than the read raising.
    """
    config_path = cwd / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return None
    try:
        node: object = _jsonc.loads(text=config_path.read_text(encoding="utf-8"))
    except _jsonc.JsoncParseError:
        return None
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = cast("dict[str, Any]", node).get(key)
    return node


def effective_admission_policy(*, item: WorkItem) -> str:
    """The item's effective admission policy (`None` inherits the safe default)."""
    return item.admission_policy or DEFAULT_ADMISSION_POLICY


def effective_acceptance_policy(*, item: WorkItem) -> str:
    """The item's effective acceptance policy (`None` inherits the safe default)."""
    return item.acceptance_policy or DEFAULT_ACCEPTANCE_POLICY


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
    resolve_assignee: Callable[..., str | None],
) -> AdmissionPlan:
    """Plan which rank-sorted ready items to admit, hold, or defer.

    `ready_items` MUST already be in admission order (highest-rank first);
    `free_slots` is the number of WIP slots available (`wip_cap -
    active_count`, floored at 0). Each item resolves to exactly one of:

    - HELD with `manual-admission` — effective `admission_policy != "auto"`
      (the safe default), surfaced for an explicit human approval.
    - HELD with `unresolvable-assignee` — `auto`, but `resolve_assignee`
      returns `None` (no assignee to drive the work).
    - ADMITTED — `auto` + resolvable + a free slot remains.
    - DEFERRED (in neither list) — `auto` + resolvable but no free slot left;
      it waits for the next pass.

    Holds are independent of capacity (a manual item is always surfaced);
    only admissions consume the free slots, filling them highest-rank first.
    """
    admitted: list[tuple[WorkItem, str]] = []
    held: list[tuple[WorkItem, str]] = []
    for item in ready_items:
        if effective_admission_policy(item=item) != _AUTO_ADMISSION:
            held.append((item, _HELD_MANUAL))
            continue
        assignee = resolve_assignee(item=item)
        if assignee is None:
            held.append((item, _HELD_UNRESOLVABLE))
            continue
        if len(admitted) >= free_slots:
            continue
        admitted.append((item, assignee))
    return AdmissionPlan(admitted=tuple(admitted), held=tuple(held))


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
            f"admission held: work-item {item_id} has effective admission_policy "
            "manual and has not been explicitly approved by a human — it is "
            "surfaced for the maintainer to approve into ready, never "
            "auto-dispatched (risky/irreversible work is held at admission)."
        )
    return (
        f"admission held: work-item {item_id} could not be admitted because its "
        "assignee is unresolvable — surface it for the maintainer to assign a "
        "doer before it can be driven into active."
    )
