"""Which STAGE's failure routed a run to the needs-human terminal.

`_fabro_escalation` answers whether the ENGINE routed a run to the terminal at
all; this module answers the next question, which the operator-facing rendering
needs and which that reader deliberately does not take a position on: WHICH
node's failure did it. The two are separate because the discriminator for
"escalated or not" is the presence of any signature, while the attribution
needs the signatures taken apart.

A loop failure signature is `<node>|<category>|<cause label>` — measured as
`pr|deterministic|acp turn failed` on run 01M44F9E56XCEWZNMVJX4M14Z6 and
`review|deterministic|acp turn failed` on run 01M10CYZ8S9TNPZ2MW096NJW7V — so
the stage is the first field.

THE TERMINAL'S OWN SIGNATURE IS EXCLUDED, and that exclusion is the whole
reason this module exists rather than a one-line split at the call site. The
`needs_human` node is a dead-end script that exits 1 by design, so a run that
reaches it ends `stage needs_human failed with no outgoing fail edge` and can
record a signature for the terminal BESIDE the one for the node that actually
failed. The signatures arrive as an unordered map, so a reader that took
whichever it met first would name the terminal — a node that only ever runs
because something else already failed, and therefore the one node that cannot
be the cause. The wrong answer is a plausible, non-empty, confidently-rendered
stage attribution, which is why it has to be refused structurally.

Every surviving signature is carried, not just the first. More than one node
CAN record a failure in a single loop, and naming one of several would hide the
rest behind an answer that looks complete.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID

__all__: list[str] = [
    "CausalStageFailure",
    "causal_stage_failure",
]

_FIELD_SEPARATOR = "|"


@dataclass(frozen=True, kw_only=True)
class CausalStageFailure:
    """The non-terminal stages a terminated run recorded a loop failure for."""

    stages: tuple[str, ...]
    signatures: tuple[str, ...]


def causal_stage_failure(*, signatures: tuple[str, ...]) -> CausalStageFailure | None:
    """The causal stages behind a needs-human terminal, or None when there are none.

    `None` is the AGENT-REPORTED ending: a node that SUCCEEDED and rode a
    conditional edge records no loop failure signature, so there is no stage to
    attribute and the generic needs-human wording is the correct one. It is also
    the answer when the only signature the loop recorded belongs to the terminal
    itself, because that says the terminal ran and nothing about why.
    """
    causal = tuple(
        signature for signature in signatures if _stage(signature=signature) != ESCALATION_NODE_ID
    )
    if not causal:
        return None
    stages: list[str] = []
    for signature in causal:
        stage = _stage(signature=signature)
        if stage not in stages:
            stages.append(stage)
    return CausalStageFailure(stages=tuple(stages), signatures=causal)


def _stage(*, signature: str) -> str:
    """The node field of one signature — everything before the first separator."""
    return signature.split(_FIELD_SEPARATOR, maxsplit=1)[0].strip()
