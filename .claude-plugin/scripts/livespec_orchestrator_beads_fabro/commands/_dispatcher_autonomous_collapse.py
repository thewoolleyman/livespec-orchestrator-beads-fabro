"""Full autonomous mode — the two-valve collapse decision layer (S3).

Full autonomous mode (specified in SPECIFICATION/spec.md,
SPECIFICATION/contracts.md, and SPECIFICATION/constraints.md) collapses the two
human-delegable valves that bracket the WIP-limited autonomous middle of the
work-item lifecycle to their autonomous leg, for the duration of a single armed
run. This module owns the pure collapse DECISIONS, layered over the existing
pure valve functions in `_dispatcher_valves` (`effective_admission_policy`,
`effective_acceptance_policy`, `acceptance_decision`):

- **Admission (`approve`) collapse.** Under an armed run a ROUTINE
  manual-admission `pending-approval` item's effective admission policy
  collapses to `auto`, so it is auto-approved into `ready` rather than resting
  for a human (SPECIFICATION/scenarios.md Scenario 33). The one EXCEPT is a
  design-human-gated spec-change-tier slice, which stays escalated
  (SPECIFICATION/scenarios.md Scenario 36's design-human-gated leg). Admission
  to `active` then follows the unchanged mechanical valve.
- **Acceptance (`ai-then-human` -> `ai-only`) collapse.** Under an armed run an
  item's effective acceptance policy collapses to `ai-only`, so a passing AI
  acceptance pass accepts it straight to `done` rather than parking it for the
  human leg (SPECIFICATION/scenarios.md Scenario 34). The one EXCEPT is a
  `human-only` item, a deliberate human gate that still parks
  (SPECIFICATION/scenarios.md Scenario 36's human-only leg). The AI pass STILL
  runs first, honoring the no-release-with-zero-verification floor.

Both collapses are PURE armed-mode OVERRIDES: when a run is NOT armed every
function returns the unchanged base decision, so behavior is exactly unchanged.
The store writes and the per-decision audit (the S2
`autonomous_decision_journal_record`, `gate` `approve` / `acceptance`,
`disposition` `auto-resolved`) are the IO layer's concern (`dispatcher.py`);
this module makes only the decision.

The spec-change-tier backstop is CONSERVATIVE and fails SAFE by holding.
Structural routing is the PRIMARY protection: a spec-change slice routes to
`/livespec:propose-change` / `/livespec:revise` and is never factory-dispatched
(SPECIFICATION/contracts.md), so the collapse structurally cannot reach a
well-routed slice. This backstop additionally distinguishes the
design-human-gated tier from routine `manual` admission by an EXISTING
spec-change signal (an item carrying a spec-commitment linkage,
`spec_commitment_hint`), NOT by the bare `manual` value — holding on the signal
rather than collapsing. It adds NO new persisted work-item field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    AcceptanceDecision,
    acceptance_decision,
    effective_acceptance_policy,
    effective_admission_policy,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "acceptance_decision_under_mode",
    "collapse_acceptance_to_ai_only",
    "collapse_admission_to_auto",
    "effective_admission_policy_under_mode",
    "is_spec_change_tier",
]

# The one admission policy that auto-admits without a human — the collapse
# TARGET for the approve gate under an armed run.
_AUTO_ADMISSION = "auto"

# The one acceptance policy that confirms to `done` without a human — the
# collapse TARGET for the acceptance gate under an armed run.
_AI_ONLY_ACCEPTANCE = "ai-only"

# The acceptance policy the collapse MUST NOT touch: a deliberate human gate
# that still parks even under an armed run (Scenario 36's human-only leg).
_HUMAN_ONLY_ACCEPTANCE = "human-only"

# The pending status the approve-gate collapse acts on — admission policy gates
# only the `pending-approval -> ready` transition.
_PENDING_APPROVAL = "pending-approval"


def is_spec_change_tier(*, item: WorkItem) -> bool:
    """Whether the item reads as a design-human-gated spec-change-tier slice.

    The conservative spec-change backstop (SPECIFICATION/contracts.md): a
    spec-change-tier slice is human-gated by design and MUST stay escalated even
    under an armed run, never auto-approved. The tier is distinguished from
    routine `manual` admission by an EXISTING spec-change signal, NOT by the
    bare `manual` value: an item carrying a spec-commitment linkage
    (`spec_commitment_hint is not None`, the pairing field set when the item is
    filed against a spec-side commitment) reads as spec-change-tier. This is a
    fail-SAFE guard — it holds on the presence of the signal, and it adds no new
    persisted field.
    """
    return item.spec_commitment_hint is not None


def collapse_admission_to_auto(*, item: WorkItem, armed: bool, cwd: Path | None = None) -> bool:
    """Whether an armed run collapses this item's approve gate to `auto`.

    True only for an armed run over a routine `pending-approval` manual-admission
    item that is NOT a design-human-gated spec-change-tier slice (Scenario 33
    collapses; Scenario 36's design-human-gated leg does not). Not armed, a
    non-pending item, an already-`auto` item, or a spec-change-tier slice => no
    collapse.
    """
    if not armed:
        return False
    if item.status != _PENDING_APPROVAL:
        return False
    if effective_admission_policy(item=item, cwd=cwd) == _AUTO_ADMISSION:
        return False
    return not is_spec_change_tier(item=item)


def effective_admission_policy_under_mode(
    *, item: WorkItem, armed: bool, cwd: Path | None = None
) -> str:
    """The item's effective admission policy with the armed collapse layered on.

    Returns `auto` when the armed run collapses the approve gate for this item
    (`collapse_admission_to_auto`), else the unchanged base
    `effective_admission_policy`. Injected into the pure `plan_admissions` valve
    so the valve stays autonomous-mode-agnostic; when not armed this is exactly
    the base policy.
    """
    if collapse_admission_to_auto(item=item, armed=armed, cwd=cwd):
        return _AUTO_ADMISSION
    return effective_admission_policy(item=item, cwd=cwd)


def collapse_acceptance_to_ai_only(*, item: WorkItem, armed: bool, cwd: Path | None = None) -> bool:
    """Whether an armed run collapses this item's acceptance gate to `ai-only`.

    True for an armed run over an item whose effective acceptance policy is
    neither already `ai-only` nor `human-only` — i.e. `ai-then-human`, the leg
    the mode auto-accepts on a passing AI pass (Scenario 34). A `human-only`
    item is a deliberate human gate that still parks (Scenario 36's human-only
    leg); an already-`ai-only` item is not a collapse. Not armed => no collapse.
    """
    if not armed:
        return False
    base = effective_acceptance_policy(item=item, cwd=cwd)
    return base not in (_AI_ONLY_ACCEPTANCE, _HUMAN_ONLY_ACCEPTANCE)


def acceptance_decision_under_mode(
    *, item: WorkItem, armed: bool, cwd: Path | None = None
) -> AcceptanceDecision:
    """The item's acceptance decision with the armed collapse layered on.

    Returns the `ai-only` decision (accept straight to `done`) when the armed run
    collapses the acceptance gate for this item (`collapse_acceptance_to_ai_only`),
    else the unchanged base `acceptance_decision` over the effective policy. When
    not armed — and for a `human-only` item even when armed — this is exactly the
    base decision, so a `human-only` item still parks.
    """
    if collapse_acceptance_to_ai_only(item=item, armed=armed, cwd=cwd):
        return acceptance_decision(policy=_AI_ONLY_ACCEPTANCE)
    return acceptance_decision(policy=effective_acceptance_policy(item=item, cwd=cwd))
