"""The read-only executor behind `diagnose-plan-progress:<epic>`.

This is the operation an expired or unobservable resume EXPOSES, so it has to
exist and it has to run: `_plan_recovery`'s closed grammar admits
`diagnose-plan-progress:<epic>` as executable, and "merely hardcoding a
previously invented token does not make it executable". This module is what
makes that token a real operation rather than a shape.

IT WRITES NOTHING, and that is a requirement rather than an implementation
choice. "An expired wall clock MUST be visible even when no new handoff is
written", and recording a recovery attempt is a SEPARATE sanctioned plan write
with its own evidence requirements — so a diagnosis that repaired what it found
would be recording an attempt nobody authored. It therefore reuses
`evaluate_resume_progress`, the same reader the resume path uses, rather than a
second reader that could disagree with it, and reports `ledger_mutation: False`
and `target_fulfillment: "not-asserted"` on every payload.

WHY IT TAKES NO POINTER AND PARSES NOTHING. The handler this replaces read the
epic's `next_action`, cast the optional parse to a `NextAction` and reached
through it for a result identity. Both halves of that crashed on ordinary
states, measured on `bd-ib-zi5ygh` by an executed probe: an epic with NO pointer
raised `AttributeError: NoneType has no attribute required_result`, and a LEGACY
three-key pointer raised `AttributeError: ResultReferenceRefusal has no
attribute identity` — the parse of a legacy sentinel returns a refusal VALUE,
and the handler indexed it as though it were a reference. The repair is not a
guard in front of those dereferences; it is that the diagnosis reads the
obligation from the AUTHORITY CHAIN, which is the authoritative source anyway,
and the chain answers "no obligation is tracked" as a finding instead of as a
shape some caller must then interrogate. There is nothing here to dereference.

THE PAYLOAD IS `green` EVEN WHEN THE FINDING IS SEVERE. The status reports
whether the DIAGNOSIS ran, not whether the plan is healthy — the plan's health
is the finding's content. A diagnosis that reported `failed` for an expired
obligation would make a successful read indistinguishable from an unreadable
one, which is the distinction the whole surface exists to draw.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._plan_progress_resume import (
    evaluate_resume_progress,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery import (
    DIAGNOSIS_OPERATION_PREFIX,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "PLAN_PROGRESS_DIAGNOSIS_PREFIX",
    "is_plan_progress_diagnosis_action",
    "run_plan_progress_diagnosis",
]

# The SAME literal the recovery grammar admits, imported rather than respelled:
# two spellings of one operation is how a resume comes to expose an action the
# router does not recognise.
PLAN_PROGRESS_DIAGNOSIS_PREFIX = DIAGNOSIS_OPERATION_PREFIX


def is_plan_progress_diagnosis_action(*, action_id: str) -> bool:
    """Whether an action id selects the plan-progress diagnosis executor."""
    return action_id.startswith(PLAN_PROGRESS_DIAGNOSIS_PREFIX) and (
        action_id.removeprefix(PLAN_PROGRESS_DIAGNOSIS_PREFIX).strip() != ""
    )


def run_plan_progress_diagnosis(*, repo: Path, action_id: str) -> dict[str, Any]:
    """Observe one plan's durable obligation and report it, writing nothing."""
    epic_id = action_id.removeprefix(PLAN_PROGRESS_DIAGNOSIS_PREFIX)
    progress = evaluate_resume_progress(
        config=resolve_store_config(cwd=repo, work_items_arg=None),
        epic_id=epic_id,
        now=utc_now_iso(),
    )
    return {
        "action_id": action_id,
        "kind": "plan-progress-diagnosis",
        "work_item_ref": epic_id,
        "status": "green",
        "diagnosis": {
            "executed": True,
            "findings": list(progress.findings),
            "reason": progress.reason,
            "dispatch_permitted": progress.dispatch,
            "authorized_next_operation": progress.authorized_action,
            "ledger_mutation": False,
            "target_fulfillment": "not-asserted",
        },
        "summary": (
            f"Observed plan progress for {epic_id} read-only; no recovery attempt,"
            " execution receipt or target-fulfillment claim was recorded."
        ),
    }
