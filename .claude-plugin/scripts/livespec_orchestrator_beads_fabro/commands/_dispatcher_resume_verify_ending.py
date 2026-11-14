"""Whether a terminated run ended at `proof_verify` without publishing a record.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" paragraph "A resume after an ended `proof_verify` re-enters at
`proof_verify`" reads three facts off the earlier run's factory record: a `review`
visit after the `proof_capture` visit whose outcome selected `approve`, a later
`proof_verify` visit that ended without publishing a proof record, and no stage
after that visit other than a terminal node. This module reads those three facts
and nothing else; WHAT the resume does with the answer is `resume_anchor`'s.

WHY THE EXECUTING NODE CANNOT ANSWER THIS. `executing_node_from_payload` reads the
newest checkpoint's `next_node_id`, which names a stage only for a run that died
INSIDE one. A run whose `proof_verify` failed took the `needs_human` terminal, so
its record names no running stage, the anchor fell to the verdict of the latest
record, and a `captured` record entered at `review` -- repeating `review`, any
`review_fix`, a commit settle and a fresh capture to re-run one read-only replay of
a capture that was already good.

WHY THE APPROVAL IS READ OFF THE SEQUENCE. The Petri engine writes the per-stage
results in the record's top-level `stages` map, keyed `<node>@<visit>` in the
engine's own order (`_fabro_port_node_outcomes`), and records no per-edge
selection. `review -> proof_verify` is the graph's only edge from `review` into
`proof_verify`, and it is the `approve` one, so a succeeded `review` visit that is
immediately followed by a `proof_verify` visit IS the `approve` selection. The
specification scopes the anchor the same way: "in every repository whose implement
workflow carries the `review -> proof_verify` edge on `approve`".

WHY THE LATEST RECORD IS NOT READ HERE. That the latest proof record is `captured`,
and that its head equals the pull request's current head, are measurements of the
pull request; this module reads the factory's record alone, and `resume_anchor`
combines the two. The head comparison is the resume ladder's existing head-moved
refusal.

WHY NO STATE IS REQUIRED OF THE `proof_verify` VISIT. The clause admits every way it
can end without a record -- failed, retries exhausted, timed out, or succeeded with
no verdict label -- and a visit that posted one is excluded by the latest record
not being `captured`, which `resume_anchor` checks. A run that is still executing
the visit is refused by the ladder's live-run refusal before any stage is read.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

__all__: list[str] = [
    "proof_verify_ended_from_payload",
]

# The node sequence the run's last non-terminal visits must spell: the capture, the
# review that approved it, and the replay that ended without a record.
_ENDING_SEQUENCE = ("proof_capture", "review", "proof_verify")

# The nodes a run may enter AFTER the verify and still have "ended there": the
# terminals the clause names. Any other node entered after it means the verify
# reached a verdict the graph routed on.
_TERMINAL_NODES = frozenset({"needs_human", "non_converged", "exit"})


def proof_verify_ended_from_payload(*, payload: object | None) -> bool:
    """Whether one run record shows an approved capture whose replay ended with no record.

    `False` for every shape that cannot show it -- an unusable payload, a record
    with no readable `stages` map, and a sequence that is not capture, review,
    verify -- because all of them mean the factory did not establish the ending,
    so the verdict of the latest record decides the stage as it does today.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return False
    stages: object = record.get("stages")
    if not isinstance(stages, dict):
        return False
    visits = [
        (fabro_stage_node(stage=key), cast("dict[str, Any]", entry))
        for key, entry in cast("dict[object, object]", stages).items()
        if isinstance(key, str) and isinstance(entry, dict)
    ]
    settled = len(visits)
    while settled > 0 and visits[settled - 1][0] in _TERMINAL_NODES:
        settled -= 1
    visits = visits[:settled]
    tail = visits[-len(_ENDING_SEQUENCE) :]
    if tuple(node for node, _ in tail) != _ENDING_SEQUENCE:
        return False
    return tail[1][1].get("state") == "succeeded"
