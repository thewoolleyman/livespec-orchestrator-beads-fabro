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

BEING THE WHOLE HISTORY, THAT MAP IS COLLAPSED TO ONE VISIT PER NODE BEFORE IT
IS GRADED, and this is the second reading of the recovered-stage measurement
above rather than a new concern. `node_outcomes` is keyed by NODE and carries
that node's CURRENT status, which is why `_node_failed` can say a retried node
reports `succeeded`; the stage map is keyed `<node>@<visit>` and the engine
never retires an entry, so a visit that failed and was then repaired by the
graph's bounded fix loop keeps its own `failed` entry for the life of the
record. Grading entry-by-entry therefore attributes a repaired node on the
ORDINARY shape of every run the fix loop rescued — `janitor@1` failed, `fix@1`
succeeded, `janitor@2` succeeded — which blames a stage nobody should look at
and reports that no answer is owed on a run where one is. That per-visit
entries persist is measured rather than supposed: the run this reading was
filed from carries `proof_capture@1` succeeded beside `proof_capture@2` failed.

The latest visit is chosen by the suffix AS A NUMBER, because neither
alternative holds. Map order is this module's ordering fallback for SEQUENCE
but is not evidence of visit order, and a text comparison puts `@10` before
`@9` — both agree with the numeric answer on the measured record and disagree
on a longer loop, so a fixture that never crossed ten would pass against either
wrong rule. A suffix carrying no number is left to document order, which is the
only ordering evidence such a record offers; retaining both entries because
neither can be ranked would be the attribution defect returning through the one
shape no engine writes.

The collapse runs AFTER the ungradeable entries are dropped, which keeps one
rule rather than two: an entry with no readable `state` is not a reading at
all, so it is not a visit that can outlive an earlier one. Collapsing first
would let an unreadable latest entry suppress its node's last readable state,
and a node suppressed that way reads downstream as a node that did not fail —
the direction that invents an agent, which the lever above exists to refuse.
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

    The map is per VISIT, so only each node's newest visit survives the
    projection — the module docstring records why, and why that step runs here
    rather than against the already-graded outcomes.
    """
    graded = {
        stage: {"status": state}
        for stage, entry in _mapping_entries(raw=record.get("stages")).items()
        if (state := _text(value=entry.get("state"))) is not None
    }
    newest = _newest_visits(stages=tuple(graded))
    return {stage: outcome for stage, outcome in graded.items() if stage in newest}


def _newest_visits(*, stages: tuple[str, ...]) -> frozenset[str]:
    """One stage key per node — the newest visit of each, by visit number.

    A frozenset of the SURVIVING KEYS rather than a node-to-key map, so the
    caller filters its own already-ordered mapping and each retained entry
    keeps its own position in the record. Carrying the node half out of here
    would place every multi-visit node at its FIRST visit's position instead.
    """
    newest: dict[str, str] = {}
    for stage in stages:
        held = newest.get(_stage_node(stage=stage))
        if held is None or _stage_visit(stage=stage) >= _stage_visit(stage=held):
            newest[_stage_node(stage=stage)] = stage
    return frozenset(newest.values())


def _stage_visit(*, stage: str) -> int:
    """The visit number of a `<node>@<visit>` key; 0 for one carrying none.

    `>=` at the call site is what makes the no-number case fall back to
    document order: two unnumbered visits of one node compare equal, so the
    later-written entry replaces the earlier one.
    """
    visit = stage.partition("@")[2].strip()
    return int(visit) if visit.isdigit() else 0


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

    It is the whole reason the terminal exclusion reaches a Petri record: the
    excluded value is a NODE id, while Petri keys its stages by node AND visit,
    so a direct comparison silently matched nothing and let the dead-end
    terminal be attributed on every ending. `_newest_visits` reads it for the
    other question a visit-keyed map raises — which entries describe one node —
    and the two must agree on where that key divides, which is why there is one
    reading of it rather than a split in each caller. A pinned-engine key
    carries no `@` and is returned unchanged.
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
