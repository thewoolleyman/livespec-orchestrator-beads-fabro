"""Read needs-human evidence from Fabro's stage lifecycle records.

A script's emitted output survives in its stage.failed failure.message, even
when the run conclusion only says the terminal has no outgoing fail edge.
Read that field, never command.started's script source (which contains every
sentinel by construction). The port has already normalized the event stream.

BOTH ENGINES' RECORD SHAPES ARE READ HERE, and the Petri-era one is the reason
this module has a per-record reading at all rather than four inline `get`s. That
engine wraps every record in an envelope, renames the ending, moves the verdict
and its failure block inside the step's own `outcome`, and carries the node on
the ENVELOPE rather than on the event, so a reader written against the pinned
spelling returns a clean, plausible "this node recorded nothing" for every node
of every run it is given — see `_event_record`, `_records_a_failure`,
`_event_node` and `_event_failure_block`.

EVERY PETRI-ERA KEY BELOW IS MEASURED, AND ITS MEASUREMENT IS NAMED BESIDE IT.
Nothing here is reconstructed from how an engine might plausibly spell a field.
The first delivery of this reader guessed three — `firing` for the node, a bare
`outcome: "failed"` verdict word, and a top-level `failure` block — and cited a
research note that contains none of them; measured against the shape the notes
DO record, it matched no real record while its own fixture passed. An unmeasured
key cannot match, a reader that matches nothing reports an absent cause, and an
absent cause is now STATED as one, so a guess is rendered as a confident claim
that the engine recorded nothing. That is the failure this module was repaired
to END rather than to restate.

THE RUN CONCLUSION IS THE WRONG PLACE TO ASK WHY A RUN WAS ROUTED HERE, and
that is the second reading this module exists for. `needs_human` is a dead-end
script that exits 1 by design, so on an engine-routed ending the conclusion's
own innermost cause is the terminal's `stage needs_human failed with no
outgoing fail edge` — a sentence that names the graph's shape and no fault.
The routing stage's own failure message is the one line a triager needs, and
it survives only on the stage records below.

THE CURRENT FAILED PREDECESSOR'S OWN FAILURE BLOCK WINS over its historical
events. The checkpoint is the engine's account of the ending; an event is an
account of one attempt, and a node the bounded fix loop retried has older
events that describe a failure the run went on to survive. The event stream is
consulted only where the checkpoint carries no cause, which is the shape the
pinned engine writes when it records a status and no detail.

WHAT THE STAGE READ MAY NOT REPLACE IS THE PROVIDER ATTRIBUTION. By the time
this runs, `_fabro_executed_candidate` may already have re-attributed the
observed ceiling from the run's own labels, which is the only reading that
tells Claude's and Codex's shared "You've hit your usage limit" literal apart.
Re-deriving the vendor from the routing stage's cause text would discard that
correction and name whichever vendor the message happens to resemble — the
exact misattribution that reading exists to retire — so an observed ceiling's
provider and entitlement are carried through unchanged, and an unreadable
routing stage retracts the CAUSE without retracting the ceiling. A dropped
ceiling writes no dispatcher-owned hold, and the next dispatch burns the same
exhausted credential.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID
from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import graph_node_id
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroFailureDetail,
    fabro_failure_detail_from_payload,
    fabro_inspect_record,
)

__all__: list[str] = [
    "routing_stage_failure",
    "terminal_event_output",
]

# Where a record's event name lives, in the descending preference the stall
# reader and the open-command-node reader already use, so one stream shape is
# not read three ways.
_NAME_KEYS: tuple[str, ...] = ("event", "name", "event_name", "type")

# Where the PINNED engine names the node a record belongs to. The Petri-era
# engine names it on the ENVELOPE instead, under `item.subject.node.name`, so
# that read lives in `_event_node` where the envelope is still in hand.
_NODE_KEYS: tuple[str, ...] = ("node_id",)

# How each engine names the ending that MIGHT carry a failure. The pinned engine
# names the failure itself (bare `stage.failed` or namespaced
# `fabro.stage.failed`, hence the suffix match), so the name alone settles it.
# The Petri-era engine names EVERY ending `step.finished` whatever its verdict,
# so the name only says a step ended and the failure BLOCK decides the rest.
_FAILED_NAME_SUFFIX = "stage.failed"
_STEP_ENDING_NAME_SUFFIX = "step.finished"

# Where the Petri-era engine puts a failed step's own failure block: inside the
# step's recorded verdict, at `outcome.status.failure`. Measured on candidate
# v0.371.0-nightly.0 by this repository's committed reproducer
# `plan/fabro-currency/research/004-acp-spend-limit-repro.py`, whose
# `verify_case` reads `body["outcome"]["status"]["failure"]["class"]` and whose
# recorded blocks are in `004-acp-spend-limit-evidence.json`. A SUCCEEDED step
# carries `outcome.status == "success"` — a bare string on that same field — so
# the block and never a verdict word is what tells the two apart.
_VERDICT_KEY = "outcome"
_VERDICT_STATUS_KEY = "status"
_FAILURE_KEY = "failure"

# Where that engine names the node, on the envelope's ITEM rather than on the
# event body. From the same reproducer's `selected_evidence`, which reads
# `item["subject"]["node"]["name"]`. Research note 006's envelope line describes
# the `run.created` record and so is silent about this key rather than denying
# it; neither key has been re-measured on 0.382 itself, and if that engine moved
# one the reader reports the absence honestly instead of guessing a successor.
_SUBJECT_KEY = "subject"
_SUBJECT_NODE_KEY = "node"
_SUBJECT_NODE_NAME_KEYS: tuple[str, ...] = ("name",)


def terminal_event_output(*, payload: object | None) -> str:
    """The latest terminal stage's emitted sentinel lines, or no observation."""
    failures = _stage_failures(payload=payload, node=ESCALATION_NODE_ID)
    if not failures:
        return ""
    message = failures[-1].get("message")
    if not isinstance(message, str):
        return ""
    return "\n".join(line for line in message.splitlines() if line.startswith(NEEDS_HUMAN_MARKER))


def routing_stage_failure(
    *,
    observed: FabroFailureDetail | None,
    inspect_payload: object | None,
    events_payload: object | None,
    stage: str,
) -> FabroFailureDetail | None:
    """What the stage that routed this run to the terminal recorded, if anything.

    `stage` comes from the terminal checkpoint's causal verdict, which already
    excludes recovered nodes and orders the failed ones by the engine's own
    completed order. The terminal itself is refused outright: it is the one
    node that cannot be the cause, and attributing its deliberate exit-1 is the
    whole defect being closed.

    A stage whose failure NOTHING records leaves the cause UNKNOWN rather than
    falling back to the run conclusion. The conclusion is where the terminal's
    own failure lives, so the fallback would report the exact sentence this
    reader exists to suppress — and would report it indistinguishably from a
    genuine attribution.

    THE TERMINAL IS REFUSED THROUGH `graph_node_id` AND NEVER BY A DIRECT
    COMPARISON, which is what keeps the Petri-era read below SAFE. That engine
    spells the same node `needs_human@1`, so a bare equality test matches
    nothing and the refusal silently stops refusing — and the terminal's own
    designed `exit 1` would then be reported as this ending's innermost cause,
    which is strictly worse than naming none: it is true of every needs-human
    ending there has ever been, so it reads as a finding while carrying no
    information. `_fabro_terminal_evidence` excludes the terminal from the
    verdict this `stage` comes off too, so the two exclusions are belt and
    braces; this one must still be able to fire.
    """
    routed = (
        None
        if graph_node_id(node=stage) == ESCALATION_NODE_ID
        else _routed_failure(
            inspect_payload=inspect_payload,
            events_payload=events_payload,
            stage=stage,
        )
    )
    return _carrying_observed_ceiling(routed=routed, observed=observed)


def _routed_failure(
    *,
    inspect_payload: object | None,
    events_payload: object | None,
    stage: str,
) -> FabroFailureDetail | None:
    """One stage's own failure from checkpoint, events, then stage output.

    THE NEWEST EVENT BLOCK THAT YIELDS A DETAIL WINS, not merely the newest
    block. One node records more than one failure — the bounded fix loop
    retries it, and an engine may follow an ending with a further node-scoped
    record — so taking the last block unconditionally lands on whichever
    happened to come last. Where that one carries nothing readable the real
    cause, recorded earlier, is discarded; and because the Petri-era checkpoint
    carries no `node_outcomes` to fall back to, the surfaces then report the
    stated absence for a cause the engine did supply. That is strictly worse
    than the silence this reader was widened to end: it is a confident claim
    about the engine drawn from the reader's own choice of record.
    """
    checkpoint = _checkpoint_failure(payload=inspect_payload, stage=stage)
    if checkpoint is not None and checkpoint.cause is not None:
        return checkpoint
    for block in reversed(_stage_failures(payload=events_payload, node=stage)):
        detail = _failure_detail(block=block)
        if detail is not None:
            return detail
    return _stage_output_failure(payload=inspect_payload, stage=stage) or checkpoint


def _carrying_observed_ceiling(
    *,
    routed: FabroFailureDetail | None,
    observed: FabroFailureDetail | None,
) -> FabroFailureDetail | None:
    """Keep a provider ceiling the observation established, whatever the stage said.

    A ceiling is a fact about the RUN, so failing to name the stage that hit it
    is no reason to stop holding the credential. The observation's provider and
    entitlement win over the routed read's own classification because only the
    observation can have been re-attributed from the run's labels; where the
    observation records no ceiling, the routed read's classification stands and
    may newly find one the conclusion's winning block never carried.
    """
    if observed is None or not observed.provider_usage_limit:
        return routed
    if routed is None:
        return replace(observed, cause=None, category=None, signature=None)
    return replace(
        routed,
        provider_usage_limit=True,
        provider_usage_limit_provider=observed.provider_usage_limit_provider,
        provider_usage_limit_entitlement=observed.provider_usage_limit_entitlement,
    )


def _checkpoint_failure(*, payload: object | None, stage: str) -> FabroFailureDetail | None:
    """The newest checkpoint that records an outcome for `stage`, read for its failure.

    The map is keyed by whatever the engine spelled, so the lookup is exact
    rather than normalized: `stage` was itself taken off one of these maps.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    for checkpoint in reversed(fabro_inspect_checkpoints(record=record)):
        outcomes = _mapping(value=checkpoint.get("node_outcomes"))
        if stage in outcomes:
            outcome = _mapping(value=outcomes[stage])
            return _failure_detail(block=_mapping(value=outcome.get("failure")))
    return None


def _stage_output_failure(*, payload: object | None, stage: str) -> FabroFailureDetail | None:
    """The ACP error text a Petri stage retained after its event read timed out.

    Petri's inspect checkpoint can omit ``node_outcomes`` and a long run's
    terminal-events read can time out together, while the failed stage record
    still retains its ACP response in ``output``.  The ACP transport prefixes
    the provider sentence with ``Internal error:``; the provider's sentence is
    what the journal and needs-human outcome must name.
    """
    record = fabro_inspect_record(payload=payload)
    stages = _mapping(value=None if record is None else record.get("stages"))
    stage_record = _mapping(value=stages.get(stage))
    output = stage_record.get("output")
    if not isinstance(output, str):
        return None
    message = output.partition("Internal error: ")[2] or output
    return _failure_detail(block={"message": message})


def _failure_detail(*, block: dict[str, object]) -> FabroFailureDetail | None:
    """Adapt a stage's direct message to the shared cause-chain classifier.

    A stage failure carries its text in `message`, while the conclusion reader
    knows `causes` and `detail.message`. Presenting the message as a `detail`
    is what routes it through the ONE classification pass that decides whether
    a fault is permanent and which vendor refused — a second, parallel pass
    here would be a second place for those two verdicts to disagree, and both
    would look well-formed while they did. Causes, category and signature ride
    along untouched so a block carrying a real chain keeps it.
    """
    normalized = dict(block)
    message = block.get("message")
    if isinstance(message, str):
        normalized["detail"] = {"message": message, "category": block.get("category")}
    return fabro_failure_detail_from_payload(payload={"failure": normalized})


def _stage_failures(*, payload: object | None, node: str) -> tuple[dict[str, object], ...]:
    """Every failed-stage failure block one node recorded, oldest first.

    The node match is normalized on BOTH sides because the two engines spell a
    stage differently: the pinned engine keys its outcome map `implement` while
    the Petri-era engine keys its stage map `002-implement@1`, and the event
    stream carries the bare graph node id on either. A direct comparison
    therefore cannot match a Petri-derived `stage` against any event it was
    looking for, and would report a clean, plausible "this node recorded
    nothing" for a node whose failure is right there.

    EVERY OTHER FIELD IS READ THROUGH THE SAME TOLERANCE, because normalizing
    the node alone was not enough and the shortfall was measured. On the
    Petri-era engine this reader returned nothing for EVERY node of EVERY run —
    the envelope hides the event's own fields (`_event_record`), the ending is
    named `step.finished` rather than `stage.failed`, the failure block sits
    inside the step's own verdict, and the node is named on the envelope's item
    — so a needs-human record written on that engine carried no innermost cause
    at all, with no error and nothing to say one was missing (`bd-ib-3nu5vv`,
    measured on hp-candidate).

    A RECORD NAMING NO NODE IS KEPT OUT OF EVERY NODE'S LIST. The whole read is
    node-scoped, so an event this reader cannot place must not be placed: a
    run-level abort, or another node's fault, would otherwise be reported as
    whichever stage the checkpoint happened to name.
    """
    if not isinstance(payload, list):
        return ()
    wanted = graph_node_id(node=node)
    failures: list[dict[str, object]] = []
    for raw in cast("list[object]", payload):
        if not isinstance(raw, dict):
            continue
        envelope = cast("dict[str, object]", raw)
        record = _event_record(envelope=envelope)
        event_node = _event_node(envelope=envelope, record=record)
        block = _event_failure_block(record=record)
        if not _records_a_failure(record=record, block=block):
            continue
        if event_node is None or graph_node_id(node=event_node) != wanted:
            continue
        failures.append(block)
    return tuple(failures)


def _event_record(*, envelope: dict[str, object]) -> dict[str, object]:
    """One event's OWN fields, unwrapped from the Petri-era envelope.

    The pinned engine prints the event, so its record is the mapping as it
    stands. The Petri-era engine prints an ENVELOPE — `{run_id, stream_seq,
    kind, id, recorded_at, item: {seq, recorded_at, record: {kind, body}}}`,
    measured on v0.378.0-nightly.0 (research note 006) and already relied on by
    the stall watchdog's `recorded_at` reading — and puts every field this
    reader needs two levels in, under `item.record.body`.

    An envelope whose body is unreadable falls back to the envelope itself,
    which matches NOTHING rather than half-matching: the envelope's own `kind`
    duplicates the body's event name but carries neither the node nor the
    failure, so a record assembled from it would name a stage and no cause.
    """
    item = _mapping(value=envelope.get("item"))
    record = _mapping(value=item.get("record"))
    return _mapping(value=record.get("body")) or envelope


def _records_a_failure(*, record: dict[str, object], block: dict[str, object]) -> bool:
    """Whether this event record is one node's FAILED ending.

    EACH ENGINE IS ASKED THE QUESTION ITS OWN RECORDS CAN ANSWER, and the two
    arms are not symmetrical. The pinned engine NAMES the failure, so its name
    settles the verdict on its own. The Petri-era engine names every ending
    `step.finished` whatever happened, so there the name says only that a step
    ended and the failure BLOCK is the verdict — which is also why no verdict
    WORD is read: a succeeded step carries `outcome.status == "success"`, a bare
    string on the very field a failure nests its block under, so a reader keyed
    on the presence of `outcome`, or on any word inside it, counts a success as
    a failure and attributes a cause-free block to the stage.

    A record naming NO ending is not a failure. That is what keeps the envelope
    fallback in `_event_record` matching nothing: the envelope's own keys carry
    no event name this reader knows, so an unreadable body yields no verdict
    rather than a stage named with no cause.
    """
    name = _event_text(record=record, keys=_NAME_KEYS)
    if name is None:
        return False
    if name.endswith(_FAILED_NAME_SUFFIX):
        return True
    return name.endswith(_STEP_ENDING_NAME_SUFFIX) and bool(block)


def _event_node(*, envelope: dict[str, object], record: dict[str, object]) -> str | None:
    """The node this event belongs to, under either engine's key, or None.

    The pinned engine's key is on the event itself; the Petri-era engine's is
    on the ENVELOPE, under `item.subject.node.name`, which is why the envelope
    is still in hand here rather than being discarded by `_event_record`.

    `None` for a record naming no node is what keeps an unattributable event
    out of every node's failure list: the whole read is node-scoped, so a
    record that cannot be placed must not be placed anywhere.
    """
    named = _event_text(record=record, keys=_NODE_KEYS)
    if named is not None:
        return named
    item = _mapping(value=envelope.get("item"))
    subject = _mapping(value=item.get(_SUBJECT_KEY))
    return _event_text(
        record=_mapping(value=subject.get(_SUBJECT_NODE_KEY)),
        keys=_SUBJECT_NODE_NAME_KEYS,
    )


def _event_failure_block(*, record: dict[str, object]) -> dict[str, object]:
    """This record's failure block, under either engine's spelling.

    The pinned engine nests it under `properties` or puts it beside the event;
    the Petri-era engine carries it inside the step's own recorded verdict, at
    `outcome.status.failure`. The named spellings are tried first so the pinned
    shape reads exactly as it did before the verdict read was added.
    """
    properties = _mapping(value=record.get("properties"))
    named = _mapping(value=properties.get(_FAILURE_KEY, record.get(_FAILURE_KEY)))
    if named:
        return named
    verdict = _mapping(value=record.get(_VERDICT_KEY))
    status = _mapping(value=verdict.get(_VERDICT_STATUS_KEY))
    return _mapping(value=status.get(_FAILURE_KEY))


def _event_text(*, record: dict[str, object], keys: tuple[str, ...]) -> str | None:
    """The first of `keys` carrying non-blank text, read beside the record then
    under its `properties`.

    The record's own level is preferred because the engine puts `node_id` on
    the envelope of its stage events while other event families nest their
    fields — the same order `_dispatcher_stall_run_reading` reads them in, so
    one stream shape is not read two ways.
    """
    for source in (record, _mapping(value=record.get("properties"))):
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}
