"""What a needs-human terminal's own checkpoint establishes about its cause.

`_fabro_escalation` answers whether the ENGINE routed a run to the terminal;
`_fabro_causal_stage` renders WHICH stage to the operator. This module is the
reading underneath both, and it exists because the two questions those modules
ask were being answered from the wrong fields.

THE INPUT SHAPE, VERIFIED AGAINST THE LIVE CLI AND NOT INFERRED FROM AN EXPORT.
`fabro inspect <run> --server <factory> --json` returns a one-element LIST whose
record carries ONLY a top-level `checkpoint`; there is no `checkpoints` history
array, `current_node` is the terminal, and `next_node_id` is NULL. A `fabro
dump` export carries the history array instead, which is where the
`next_node_id == needs_human` reading came from. So a reader requiring a
non-empty `next_node_id` naming the terminal cannot see a terminated CLI
response AT ALL — it returns a clean, plausible "not escalated" for every real
terminal ending. Both shapes are therefore recognized: `next_node_id` naming
the terminal (the mid-flight and export shape) and `current_node` naming it
with no next node (the terminated shape).

THE AUTHORITATIVE CURRENT EVIDENCE IS `node_outcomes`, NOT THE LOOP COUNTER,
and that is the correction this module carries. Two measurements settle it in
opposite directions:

- A REAL FAILED PREDECESSOR NEED CARRY NO LOOP SIGNATURE. The provider-ceiling
  run records `node_outcomes.implement.status = failed` with
  `implement|transient_infra|acp turn failed` as its failure signature, while
  its only `loop_failure_signatures` entry belongs to the terminal. Requiring a
  loop signature turns that explicit failure into "no stage failed", and the
  renderer then tells the operator no agent asked anything — about a run that
  never asked and never got to.
- A LOOP SIGNATURE IS NOT EVIDENCE THAT ITS STAGE FAILED *NOW*. The engine's
  `CircuitBreakerLifecycle.after_node` accumulates these signatures and never
  clears them when a later visit to the same node succeeds. A run that failed a
  gate, recovered, and then genuinely asked a question still carries the old
  signature, so attributing it reports a fault nobody suffered and suppresses
  the question somebody asked.

So a signature is graded AGAINST the outcome map: one whose stage is recorded
failed is that stage's own signature, and one whose stage is not is retained as
HISTORY. History is carried rather than dropped because it is real evidence
about the run — just not about this ending.

`outcomes_observed` is the honest-unknown lever and is never inferred. A record
with no readable outcome map cannot ground the grading above, so the renderer
needs to know the difference between "graded, and nothing failed" (a genuine
request) and "nothing to grade against" (undetermined). Collapsing the two
would make an unreadable record indistinguishable from a question, which is the
direction that invents an agent.

THE TERMINAL NODE IS EXCLUDED FROM EVERY ANSWER. It is a dead-end script that
exits 1 by design, so it records a failed outcome and a loop signature of its
own on every run that reaches it. It runs only because something else already
failed, which makes it the one node that cannot be the cause — and the
unordered outcome map would otherwise let it be picked first.

THE PETRI ENGINE RECORDS NO `node_outcomes` AT ALL, so the grading above has a
second input rather than a second reader. A terminated run's checkpoint on that
engine carries only `current_node`, `git_commit_sha` and `timestamp`; the
per-stage results live in the record's own top-level `stages` map, keyed
`<node>@<visit>`, each entry carrying `handler`, `state`, `output` and
`response`. Reading that map is what keeps a Petri ending from landing in
`UNESTABLISHED` — measured 2026-10-15 on run `01M4Y7EJWTQWK5CWWS0NKDHY7T`,
whose `inspect` named 48 succeeded stages and 2 failed ones while the durable
ledger comment said the record established nothing.

It is a FALLBACK and never a merge: a record carrying `node_outcomes` is graded
from them exactly as before, because that map is the checkpoint's own account
of the ending while the stage map is the run's account of its whole history,
and a reader preferring the broader one would answer a different question on
the engine that supplies both. Only the `state` field is read, and an entry
carrying none is dropped rather than counted — the honest-unknown lever above
is what distinguishes "graded, and nothing failed" from "nothing to grade", so
an ungradeable entry must not make the map look readable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record

__all__: list[str] = [
    "TerminalEvidence",
    "terminal_evidence",
]

_FAILED_STATUS = "failed"


@dataclass(frozen=True, kw_only=True)
class TerminalEvidence:
    """One needs-human terminal's own account of what failed before it.

    `failed_stages` carries EVERY failed non-terminal node rather than only the
    newest, because more than one node can fail in a single loop and naming one
    of several hides the rest behind an answer that looks complete.
    `current_predecessor` is the last of them in the engine's own completed
    order, which is the one a triager starts from.
    """

    current_predecessor: str | None
    failed_stages: tuple[str, ...]
    stage_signatures: tuple[str, ...]
    history_signatures: tuple[str, ...]
    outcomes_observed: bool


def terminal_evidence(*, payload: object | None) -> TerminalEvidence | None:
    """Read one `inspect` payload's needs-human terminal, or None for no terminal.

    `None` means the record shows no needs-human terminal checkpoint — an
    unusable payload, or a run still executing an ordinary node. It never means
    "terminated but said nothing": a terminal checkpoint carrying no readable
    outcomes still yields evidence, with `outcomes_observed` False to say so.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    checkpoint = _terminal_checkpoint(record=record)
    if checkpoint is None:
        return None
    outcomes = _node_outcomes(checkpoint=checkpoint) or _stage_state_outcomes(record=record)
    failed = _failed_stages(checkpoint=checkpoint, outcomes=outcomes)
    return TerminalEvidence(
        current_predecessor=failed[-1] if failed else None,
        failed_stages=failed,
        stage_signatures=_stage_signatures(outcomes=outcomes, failed=failed),
        history_signatures=_history_signatures(checkpoint=checkpoint, failed=failed),
        outcomes_observed=bool(outcomes),
    )


def _terminal_checkpoint(*, record: dict[str, Any]) -> dict[str, Any] | None:
    """The NEWEST checkpoint sitting at the needs-human terminal, or None.

    Both measured shapes count, and neither subsumes the other: a checkpoint
    ROUTING to the terminal names it in `next_node_id`, while one that has
    REACHED it names it in `current_node` and carries no next node at all.
    """
    found: dict[str, Any] | None = None
    for checkpoint in fabro_inspect_checkpoints(record=record):
        if _routes_to_terminal(checkpoint=checkpoint) or _sits_at_terminal(checkpoint=checkpoint):
            found = checkpoint
    return found


def _routes_to_terminal(*, checkpoint: dict[str, Any]) -> bool:
    """Whether this checkpoint's NEXT node is the terminal."""
    return _text(value=checkpoint.get("next_node_id")) == ESCALATION_NODE_ID


def _sits_at_terminal(*, checkpoint: dict[str, Any]) -> bool:
    """Whether this checkpoint has REACHED the terminal with nothing queued after.

    The absent-next test is part of the predicate rather than decoration: a
    checkpoint naming the terminal as current WHILE queueing another node has
    not terminated there, and reading it as terminal would attribute a live
    run's history to an ending that has not happened.
    """
    if _text(value=checkpoint.get("current_node")) != ESCALATION_NODE_ID:
        return False
    return _text(value=checkpoint.get("next_node_id")) is None


def _node_outcomes(*, checkpoint: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The per-node outcome map, keyed by node id, in the record's own order.

    JSON object order is preserved by the parser, so the map's own order is the
    engine's document order — a better fallback than sorting, which would
    impose an alphabetical answer on a question about sequence.
    """
    return _mapping_entries(raw=checkpoint.get("node_outcomes"))


def _stage_state_outcomes(*, record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The Petri `stages` map projected onto the outcome shape, in record order.

    The projection keeps ONE grading path rather than giving the engine its own
    reader: everything downstream asks whether a node is recorded failed and in
    what order, which `state` answers exactly as `status` does. The stage KEY is
    carried whole, visit suffix included, because `proof_capture@2` says which
    visit failed and `proof_capture` would discard a fact the engine recorded.
    """
    return {
        stage: {"status": state}
        for stage, entry in _mapping_entries(raw=record.get("stages")).items()
        if (state := _text(value=entry.get("state"))) is not None
    }


def _mapping_entries(*, raw: object) -> dict[str, dict[str, Any]]:
    """One engine-written map of node id to mapping, malformed entries dropped.

    Shared by both outcome readers so a record whose keys or values are
    unusable degrades the same way whichever engine wrote it.
    """
    if not isinstance(raw, dict):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for key, value in cast("dict[object, object]", raw).items():
        if isinstance(key, str) and key.strip() and isinstance(value, dict):
            entries[key.strip()] = cast("dict[str, Any]", value)
    return entries


def _failed_stages(
    *,
    checkpoint: dict[str, Any],
    outcomes: dict[str, dict[str, Any]],
) -> tuple[str, ...]:
    """Every failed non-terminal node, in the engine's own completed order.

    `completed_nodes` is a LIST and is therefore the only ordering evidence on
    the checkpoint; nodes it does not mention keep their map order behind it, so
    a record that omits the list still reports every failure it recorded.
    """
    failed = [
        node
        for node, outcome in outcomes.items()
        if _stage_node(stage=node) != ESCALATION_NODE_ID and _node_failed(outcome=outcome)
    ]
    ordered = [node for node in _completed_nodes(checkpoint=checkpoint) if node in failed]
    ordered.extend(node for node in failed if node not in ordered)
    return tuple(ordered)


def _completed_nodes(*, checkpoint: dict[str, Any]) -> tuple[str, ...]:
    """The node ids the engine recorded as completed, oldest first."""
    raw: object = checkpoint.get("completed_nodes")
    if not isinstance(raw, list):
        return ()
    entries = cast("list[object]", raw)
    return tuple(node for item in entries if (node := _text(value=item)) is not None)


def _node_failed(*, outcome: dict[str, Any]) -> bool:
    """Whether one node outcome records a failure.

    An explicit `status` WINS over the presence of a `failure` block, which is
    what makes the recovered-stage control work: a node the loop retried to
    success reports `succeeded` while an earlier failure block can still hang
    off the record, and reading the block first would report every recovered
    node as currently failed. The block is the fallback for the export shape,
    which records no per-node status.
    """
    status = _text(value=outcome.get("status"))
    if status is not None:
        return status.casefold() == _FAILED_STATUS
    return isinstance(outcome.get("failure"), dict)


def _stage_signatures(
    *,
    outcomes: dict[str, dict[str, Any]],
    failed: tuple[str, ...],
) -> tuple[str, ...]:
    """The failure signature each currently-failed stage recorded for itself."""
    signatures: list[str] = []
    for node in failed:
        failure: object = outcomes[node].get("failure")
        if not isinstance(failure, dict):
            continue
        signature = _text(value=cast("dict[str, Any]", failure).get("signature"))
        if signature is not None and signature not in signatures:
            signatures.append(signature)
    return tuple(signatures)


def _history_signatures(
    *,
    checkpoint: dict[str, Any],
    failed: tuple[str, ...],
) -> tuple[str, ...]:
    """Loop signatures belonging to no currently-failed stage, sorted.

    These are real failures the loop counted and then outlived. They are
    reported as history so the record is complete, and kept OUT of the
    attribution so a recovered stage cannot be blamed for an ending it did not
    cause. The terminal's own signature is dropped rather than carried: it says
    the terminal ran, which is already known from reaching this module.
    """
    raw: object = checkpoint.get("loop_failure_signatures")
    if not isinstance(raw, dict):
        return ()
    mapping = cast("dict[object, object]", raw)
    return tuple(
        sorted(
            signature
            for key in mapping
            if (signature := _text(value=key)) is not None
            and (stage := _signature_stage(signature=signature)) != ESCALATION_NODE_ID
            and stage not in failed
        )
    )


def _stage_node(*, stage: str) -> str:
    """The node half of a `<node>@<visit>` stage key, or the key as it stands.

    This exists for the terminal exclusion alone, and it is the whole reason
    that exclusion reaches a Petri record: the excluded value is a NODE id,
    while Petri keys its stages by node AND visit, so a direct comparison
    silently matched nothing and let the dead-end terminal be attributed on
    every ending. A pinned-engine key carries no `@` and is returned unchanged.
    """
    return stage.split("@", maxsplit=1)[0].strip()


def _signature_stage(*, signature: str) -> str:
    """The node field of one `<node>|<category>|<label>` loop signature."""
    return signature.split("|", maxsplit=1)[0].strip()


def _text(*, value: object) -> str | None:
    """One field as non-empty text, or None for anything else — null included."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
