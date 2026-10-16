"""The operator-facing detail a needs-human terminal reports.

Split out of `_dispatcher_fabro_terminal` by cohesion: that module ROUTES a
Fabro run's exit onto one of the three terminal outcomes, while this one is the
pure rendering of the needs-human terminal's own account. Keeping the render
here is what lets it read the causal stage and the structured failure without
the routing module growing a second concern.

THE THREE ENDINGS SHARE ONE STATUS AND MUST NOT SHARE ONE WORDING, which is the
same defect `_blocked_detail` already fixed for the `blocked` status and which
the v093 terminal made unreachable again (epic `bd-ib-ctagnf`, opening research
note "Failure analysis and mechanism candidates", section "The needs-human
terminal renders one wording for two endings"). An AGENT that ended through the
needs-human protocol asked a question and a human has something to decide; an
ENGINE that routed a non-retryable node failure here asked nothing, and telling
its triager that a decision awaits them sends them hunting for a question nobody
wrote. A record that establishes NEITHER must claim neither.

The discriminator is `_fabro_causal_stage`'s verdict, which grades the terminal
checkpoint's own per-node outcome map. It is deliberately NOT the absence of a
loop failure signature: that absence is ambiguous in both directions, and
reading it as "an agent asked" is what made a provider-ceiling run — which
never got as far as asking anything — render as a pending question.

The agent-reported wording is kept BYTE-IDENTICAL to what it was before the
stage attribution existed. That ending was never mis-rendered, so changing its
text would be churn in the one arm this change is not about.

EVERY ARM NAMES THE SAME LEDGER VALVE, and that is not a redundancy to be
collapsed. The lifecycle does not branch — the item rests at `blocked /
needs-human` and `resolve-blocked:<id>:ready` is its only exit — so an arm that
withheld the valve would describe a state with no way out. What the arms differ
on is whether a QUESTION is pending, which is what the reader goes looking for.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    CausalStageFailure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail
from livespec_orchestrator_beads_fabro.commands._fabro_transport_fault import (
    transport_fault_clause,
    transport_fault_from_cause,
)

__all__: list[str] = [
    "needs_human_terminal_detail",
    "needs_human_terminal_preservation",
    "needs_human_terminal_reason",
]

_UNKNOWN_RUN = "unknown-run"
_POINTER_PHRASE = "the preserve-by-reference pointer on the item for the dump digest"
_PRESERVED_POINTER = f"see {_POINTER_PHRASE}"
_FALL_BACK_TO_POINTER = (
    f"rework from the preserve-by-reference dump pointer instead — see {_POINTER_PHRASE}"
)

# The two NEGATIVE sentinels the terminal node writes when it preserved
# nothing, derived from the ONE shared marker so a workflow edit cannot
# desynchronise them. Both CONTAIN the bare marker, so each match keys on its
# own distinguishing suffix.
_PUSH_FAILED_SENTINEL = f"{NEEDS_HUMAN_MARKER}_PUSH_FAILED"
_NO_RUN_ID_SENTINEL = f"{NEEDS_HUMAN_MARKER}_NO_RUN_ID"

# The POSITIVE sentinel, which is the only evidence that a push LANDED. It is
# colon-and-space terminated because the node writes the ref it pushed after it,
# and that ref is what gets reported rather than one derived from the run id.
_PRESERVED_SENTINEL = f"{NEEDS_HUMAN_MARKER}_PRESERVED: "

# The terminal's own reason line, and the routing suffix it always carries.
# The reason is the ONLY account of why the loop gave up that a node whose
# failure the engine never classified can leave, so it is rendered for every
# ending rather than only the attributed ones.
_REASON_PREFIX = f"{NEEDS_HUMAN_MARKER}: "
_REASON_SUFFIX = "; run terminated, work preserved by reference, decision routed to the ledger"
_REASON_UNRECORDED = "not recorded"

# The label every outlived loop signature is reported under. It says in as many
# words that the signature is NOT this ending's cause, because the signature
# text alone is identical to a causal one and a reader cannot tell them apart.
_HISTORY_LABEL = " ".join(
    (
        "earlier loop failure signatures the run outlived,",
        "recorded as history and NOT as this ending's cause",
    )
)


def needs_human_terminal_detail(
    *,
    work_item_id: str,
    run_id: str | None,
    text: str,
    causal: CausalStageFailure,
    failure: FabroFailureDetail | None,
) -> str:
    """Render one needs-human terminal for the operator who has to triage it.

    `text` is the run's own output — the same channel the sentinel was matched
    on — and it is read for exactly two questions: whether the terminal
    preserved anything, and what reason it printed. Nothing else in the render
    depends on it.
    """
    run_label = _UNKNOWN_RUN if run_id is None else run_id
    clauses = (
        _head(run_label=run_label, causal=causal),
        *_attribution(causal=causal, failure=failure),
        _reason(text=text),
        needs_human_terminal_preservation(text=text),
        _decision(work_item_id=work_item_id, causal=causal),
    )
    return "; ".join(clauses)


def needs_human_terminal_reason(*, text: str) -> str | None:
    """The reason the terminal node itself emitted, stripped of its routing suffix.

    PUBLIC because TWO surfaces owe an operator this line and neither may
    re-derive it. `_reason` below renders it into the dispatch RESULT, which is
    read once; `_dispatcher_needs_human_cause` writes it into the item's DURABLE
    record, which is appended long after the run's output has scrolled away and
    is the only account that survives the factory pruning the run. So the parse
    is resolved ONCE here and carried on `DispatchOutcome.needs_human_reason`,
    for the same resolve-once-project-everywhere reason every other typed field
    on that outcome exists: a second partition of the same text in a module that
    never sees the text is not reachable at all, and one in a module that does
    is a second implementation of one rule.

    The line matters because it is the only channel some failures have at all: a
    `publish_draft` refusal writes its whole diagnosis — the file it refused and
    the permission it lacked — into it, the terminal writes the open-Red clause
    for a stage that timed out mid Red-Green pair, and the engine classifies no
    cause for either.

    `None` RATHER THAN A PLACEHOLDER, because the two callers owe an absence
    opposite renderings. The detail says `not recorded` in as many words, since
    its reader is looking for the clause and needs to know it was looked for.
    The record OMITS the line, since every line it carries is a claim a reader
    acts on and the comment cannot be edited afterwards — "the terminal recorded
    nothing" is a claim about the terminal, and an unreadable run output supports
    it no better than it supports any other.
    """
    if _REASON_PREFIX not in text:
        return None
    lines = text.partition(_REASON_PREFIX)[2].partition(_REASON_SUFFIX)[0].splitlines()
    if not lines:
        return None
    return lines[0].strip() or None


def _reason(*, text: str) -> str:
    """The terminal's own reason as the dispatch result reports it."""
    return f"terminal reason: {needs_human_terminal_reason(text=text) or _REASON_UNRECORDED}"


def _head(*, run_label: str, causal: CausalStageFailure) -> str:
    """The opening clause, which is where the three endings part company.

    The `UNESTABLISHED` arm keeps the wording the generic ending always had,
    because that wording asserts only what every needs-human terminal has in
    common: the run terminated there. It is the one arm that must claim nothing
    about WHY, so it says nothing about why — and in particular it does not say
    no agent asked anything, which the fault arm says and which no unreadable
    record can support.
    """
    if not causal.is_stage_failure:
        return f"run {run_label} terminated at the {ESCALATION_NODE_ID} node (needs-human)"
    return (
        f"run {run_label} failed at {_stage_phrase(stages=causal.stages)} after a "
        f"non-retryable fault and the graph routed it to the {ESCALATION_NODE_ID} "
        "terminal — no agent asked anything, so there is no question to answer"
    )


def _stage_phrase(*, stages: tuple[str, ...]) -> str:
    """`stage pr` for one, `stages pr, review` for several — never a bare list."""
    if len(stages) == 1:
        return f"stage {stages[0]}"
    return f"stages {', '.join(stages)}"


def _attribution(
    *,
    causal: CausalStageFailure,
    failure: FabroFailureDetail | None,
) -> tuple[str, ...]:
    """What the engine recorded about the failure, innermost cause first.

    Carries no cause for an ending no stage failure caused. The cause is the
    INNERMOST element of the chain, already selected by `_fabro_port_records`:
    the outer element is the fixed `ACP protocol error` wrapper, which
    identifies the transport and names no fault.

    The CLASSIFICATION rides beside the cause rather than replacing it. Quoting
    the cause alone already happens to contain the backgrounded command, inside
    the engine's own prose — so a reader could find the command and still have
    no idea it was a transport fault, which is the whole misreading this clause
    exists to prevent.

    HISTORY IS REPORTED UNDER EVERY KIND, and labelled as history. A loop
    signature whose stage is not currently failed survives from a failure the
    run outlived; the engine never clears it. Dropping it loses the run's own
    account, and reporting it as the cause invents one — so it is named as what
    it is, which is also what tells the reader why this ending's attribution
    does not mention it.
    """
    clauses: list[str] = []
    if causal.is_stage_failure:
        if failure is not None and failure.cause is not None:
            clauses.append(f"innermost cause: {failure.cause}")
            fault = transport_fault_from_cause(cause=failure.cause)
            if fault is not None:
                clauses.append(transport_fault_clause(fault=fault))
        if causal.signatures:
            clauses.append(f"recorded loop failure signature: {', '.join(causal.signatures)}")
    if causal.history:
        outlived = ", ".join(causal.history)
        clauses.append(f"{_HISTORY_LABEL}: {outlived}")
    return tuple(clauses)


def needs_human_terminal_preservation(*, text: str) -> str:
    """What a rework can start FROM — the fact the ledger answer turns on.

    THE INVARIANT IS THREE-WAY AND EVERY ARM NEEDS ITS OWN EVIDENCE: a POSITIVE
    sentinel means preserved, an explicit NEGATIVE sentinel means failed, and
    the absence of both means UNKNOWN.

    Silence used to be the preserved arm, and that is the defect this function
    exists to close. A missing failure marker is not positive evidence of a
    successful push: a legacy ending, an output capture that never reached this
    reader, and a genuine failure whose sentinel was truncated all look
    identical to a push that landed, and all three were sent to
    `refs/heads/needs-human/<run>` — a ref `git fetch` cannot find. Unknown is
    not the failure claim either, because inventing a failed push sends the
    operator to the dump pointer while the ref is really there; that is the same
    lie pointing the other way.

    THE REF IS READ OFF THE POSITIVE SENTINEL, never derived from the run id.
    The node prints the ref it actually pushed, so deriving one would be this
    module's guess about another component's act — and the two can differ.

    AN UNPARSED RUN ID IS A PARSE GAP, NOT A PUSH FAILURE. It says nothing about
    what the terminal did, and it can co-exist with a positive sentinel that
    names the ref outright — which is why the sentinel is tested FIRST and the
    run id is never consulted here at all.
    """
    preserved_ref = _after(text=text, sentinel=_PRESERVED_SENTINEL)
    if preserved_ref is not None:
        return f"the tree was preserved on {preserved_ref} ({_PRESERVED_POINTER})"
    if _NO_RUN_ID_SENTINEL in text:
        return _not_pushed(because="the terminal reported that no run id reached it")
    if _PUSH_FAILED_SENTINEL in text:
        return _not_pushed(because="the terminal reported that its preservation push failed")
    return (
        "whether the tree reached a run-scoped ref is UNKNOWN — the run's "
        f"record carries neither the terminal's {_PRESERVED_SENTINEL.strip().rstrip(':')} "
        f"sentinel nor a failure one, so no ref can be named; {_FALL_BACK_TO_POINTER}"
    )


def _after(*, text: str, sentinel: str) -> str | None:
    """The non-empty text following the first occurrence of one sentinel.

    Returns None for a sentinel that is present but names nothing. A positive
    preservation sentinel whose ref is blank has not identified a ref, and
    reporting the empty string as one would claim preservation on a ref nobody
    can fetch — the very class of claim this module refuses.
    """
    for line in text.splitlines():
        index = line.find(sentinel)
        if index >= 0:
            trailing = line[index + len(sentinel) :].strip()
            if trailing != "":
                return trailing
    return None


def _not_pushed(*, because: str) -> str:
    """The negative preservation clause, naming the measurement that retracted the ref.

    Says both that the tree was not PUSHED and that it is therefore not
    PRESERVED there, because those are two different facts an operator acts on
    separately: the first is what happened, the second is why the ref named
    elsewhere in this detail is not worth fetching.
    """
    return (
        f"the tree was not pushed to a run-scoped ref, so it is NOT preserved there "
        f"({because}); {_FALL_BACK_TO_POINTER}"
    )


def _decision(*, work_item_id: str, causal: CausalStageFailure) -> str:
    """What the human is actually being asked to do, which differs by ending.

    THE VALVE IS NAMED IN EVERY ARM and the lifecycle never moves: the item
    rests at `blocked / needs-human` and `resolve-blocked:<id>:ready` is the
    only route out of it. What the arms disagree about is whether a QUESTION is
    pending, and that is not a nuance — it decides what the operator goes
    looking for.

    The GENUINE REQUEST arm is byte-identical to the wording this clause always
    had. An agent asked something, a human has something to decide, and that
    ending was never mis-rendered.

    The other two arms do NOT say the decision lives in the ledger awaiting an
    answer, because for them there is no answer to give. A transport fault asked
    nothing; telling its triager a decision awaits them is what sent one
    incident hunting for roughly twenty hours for a question nobody wrote. They
    get triage-and-re-dispatch guidance instead — the same valve, a different
    instruction — and the UNESTABLISHED arm additionally says that the ending
    itself is unexplained, so the triager starts by establishing which of the
    other two it was rather than by assuming.
    """
    valve = f"`resolve-blocked:{work_item_id}:ready`"
    if causal.kind == AGENT_REQUEST:
        return (
            "no run is waiting — the decision lives in the ledger: answer with "
            f"{valve} (re-dispatch, seeding rework from "
            "the preserved ref or from scratch) or leave the item blocked"
        )
    if causal.is_stage_failure:
        return (
            "no run is waiting and no answer is owed — triage the failure named above, "
            f"then release the item with {valve} to re-dispatch (seeding rework from the "
            "preserved tree or from scratch), or leave the item blocked"
        )
    return (
        "no run is waiting, and this record does not establish whether a stage failed "
        "or an agent asked — triage the run to find out before answering, then release "
        f"the item with {valve} to re-dispatch, or leave the item blocked"
    )
