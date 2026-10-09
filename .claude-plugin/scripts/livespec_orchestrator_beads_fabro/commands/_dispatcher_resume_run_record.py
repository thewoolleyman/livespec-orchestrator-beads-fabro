"""Which node a terminated run was executing, read off its own factory record.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" defines the resumed-at stage as "the node the earlier run was
executing when it terminated, or, when it terminated between nodes, the target of
the edge its last succeeded node's outcome selected". One reading answers both
halves: the NEWEST checkpoint's `next_node_id` is the node the engine had selected
and was executing, and for a run that died between nodes it is the edge target its
last outcome chose. There is no third case to discriminate, which is why this is
one field rather than a classifier.

WHY THIS IS THE PRECISE SOURCE AND THE VERDICT FALLBACK IS NOT. The clause demands
the factory's record FIRST and allows the verdict fallback only "when that factory
answers that it no longer holds the run", and the difference is operational: this
reading names the node the run died INSIDE, while a verdict can only name the last
node that PUBLISHED. A run that died partway through `pr` published its `verified`
record from `proof_verify`, so the fallback sends the resume to `pr` too — but a
run that died in `review` after `proof_capture` published `captured` would be sent
to `review` either way only by luck of the mapping. The resume record names which
source decided it for exactly that reason.

WHY A BLANK IS NOT A NODE NAME. `graph_entered_at` refuses a name the graph does
not declare, so a blank would reach it and be refused there — but the refusal would
read as "this workflow declares no node ''", which points at the graph rather than
at the unreadable record. Answering `None` here routes the same run to the verdict
fallback instead, which is the behaviour the clause gives for a factory that cannot
name the stage.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

__all__: list[str] = [
    "executing_node_from_payload",
]


def executing_node_from_payload(*, payload: object | None) -> str | None:
    """The node one run record's newest checkpoint names, or `None` for no reading.

    `None` covers every shape that cannot name a stage — an unusable payload, a
    record with no checkpoint at all, and a checkpoint whose `next_node_id` is
    absent, non-string or blank — because all three mean the same thing to a
    resume: the factory did not say where the run was, so the verdict of its
    latest record has to.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    node: str | None = None
    for checkpoint in fabro_inspect_checkpoints(record=record):
        candidate: object = checkpoint.get("next_node_id")
        if isinstance(candidate, str) and candidate.strip():
            node = candidate.strip()
    return node
