"""How a post-merge acceptance disposition is reported in the dispatch result.

The parking-verdict clause of `SPECIFICATION/contracts.md` (v115) governs the
RESULT, not just the ledger: for an item a pass leaves in `acceptance` the result
"MUST report `stage: acceptance` and `verdict: <verdict>`, with `status: green`
for a PASS that parked or has a pending leg and `status: needs-attention` for
NEEDS_ATTENTION", and "`stage: done` MUST be reported only for an item the pass
closed". The exit code follows from `status` through the existing
`dispatch_exit_code`, which already grades anything outside the green set as 1 —
so no new exit code is introduced here.

WHY THE RUN'S OWN TERMINAL IS NOT WHAT GETS REPORTED. The post-merge janitor
builds a `green` outcome at stage `done` BEFORE the acceptance valve runs, because
at that point the run genuinely had merged and passed. The valve then either
closes the item or parks it, and nothing used to carry that back: finding F7(b) of
plan `definition-and-proof-of-done` measured `bd-ib-mxqrr4` resting in
`acceptance` on a NEEDS_ATTENTION verdict while `drive` reported `green at done`,
so every surface downstream of the exit code read the dispatch as a completed
close.

WHAT THE REVISION COSTS, recorded here because it is a deliberate trade and not
an oversight. Three post-verdict stages key on `status == "green"` by their own
design — the cost gate, the plugin self-update, and the run-turn telemetry guard —
so a NEEDS_ATTENTION park no longer reaches them. That is the honest reading of
their own condition: a dispatch that merged but cannot be judged is not a green
dispatch. A PASS that merely PARKS keeps `status: green` and therefore still
reaches all three; only the cannot-judge verdict loses them, which is the same set
of runs the alarm and the exit code now report.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    NEEDS_ATTENTION_VERDICT,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome

__all__: list[str] = [
    "ACCEPTANCE_STAGE",
    "NEEDS_ATTENTION_STATUS",
    "AcceptanceDisposition",
    "outcome_after_acceptance",
]

ACCEPTANCE_STAGE = "acceptance"
NEEDS_ATTENTION_STATUS = "needs-attention"
_GREEN_STATUS = "green"


@dataclass(frozen=True, kw_only=True)
class AcceptanceDisposition:
    """What the post-merge acceptance valve did with one item.

    `closed` rather than `parked` is the carried fact, because the clause draws
    its line there: `stage: done` is reserved for an item the pass CLOSED, and
    everything else — a park, a rework route, a block — rests at the acceptance
    stage. Naming the negative would make the rework route look like a park.
    """

    verdict: str
    closed: bool


def outcome_after_acceptance(
    *, outcome: DispatchOutcome, disposition: AcceptanceDisposition
) -> DispatchOutcome:
    """The run terminal, re-reported as the acceptance valve left the item.

    The merge facts are carried through untouched: the run DID merge, and an
    operator triaging a park needs the pull request its records live on.
    """
    if disposition.closed:
        return replace(outcome, verdict=disposition.verdict)
    status = (
        NEEDS_ATTENTION_STATUS if disposition.verdict == NEEDS_ATTENTION_VERDICT else _GREEN_STATUS
    )
    return replace(outcome, status=status, stage=ACCEPTANCE_STAGE, verdict=disposition.verdict)
