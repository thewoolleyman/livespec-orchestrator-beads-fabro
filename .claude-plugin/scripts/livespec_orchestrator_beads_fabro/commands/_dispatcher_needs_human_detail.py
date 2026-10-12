"""The operator-facing detail a needs-human terminal reports.

Split out of `_dispatcher_fabro_terminal` by cohesion: that module ROUTES a
Fabro run's exit onto one of the three terminal outcomes, while this one is the
pure rendering of the needs-human terminal's own account. Keeping the render
here is what lets it read the causal stage and the structured failure without
the routing module growing a second concern.

THE TWO ENDINGS SHARE ONE STATUS AND MUST NOT SHARE ONE WORDING, which is the
same defect `_blocked_detail` already fixed for the `blocked` status and which
the v093 terminal made unreachable again
(`plan/pr-stage-backgrounded-push-fault/research/001-failure-analysis-and-mechanism-candidates-2026-10-08.md`
section 3.5). An AGENT that ended through the needs-human protocol asked a
question and a human has something to decide; an ENGINE that routed a
non-retryable node failure here asked nothing, and telling its triager that a
decision awaits them sends them hunting for a question nobody wrote. The
discriminator is the causal stage: an agent-reported ending rides a conditional
edge off a node that SUCCEEDED, so it records no loop failure signature.

The agent-reported wording is kept BYTE-IDENTICAL to what it was before the
stage attribution existed. That ending was never mis-rendered, so changing its
text would be churn in the one arm this change is not about.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import CausalStageFailure
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail
from livespec_orchestrator_beads_fabro.commands._fabro_transport_fault import (
    transport_fault_clause,
    transport_fault_from_cause,
)

__all__: list[str] = [
    "needs_human_terminal_detail",
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
        _preservation(run_id=run_id, text=text),
        _decision(work_item_id=work_item_id),
    )
    return "; ".join(clauses)


def _reason(*, text: str) -> str:
    """The terminal node's own emitted reason, stripped of its routing suffix.

    Rendered for every ending because it is the only channel some failures have
    at all: a `publish_draft` refusal writes its whole diagnosis — the file it
    refused and the permission it lacked — into this line, and the engine
    classifies no cause for it. Dropping the clause lost that diagnosis from the
    one surface an operator reads.
    """
    with_fallback = f"{text}\n{_REASON_PREFIX}{_REASON_UNRECORDED}"
    recorded = (
        with_fallback.partition(_REASON_PREFIX)[2]
        .partition(_REASON_SUFFIX)[0]
        .splitlines()[0]
        .strip()
    )
    return f"terminal reason: {recorded or _REASON_UNRECORDED}"


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


def _preservation(*, run_id: str | None, text: str) -> str:
    """What a rework can start FROM — the fact the ledger answer turns on.

    The ref used to be DERIVED from the run id and asserted unconditionally, so
    a preservation push that failed read exactly like one that landed and sent
    the operator to a ref `git fetch` cannot find. The terminal node says which
    happened; this reads it.

    SILENCE IS THE PRESERVED ARM, deliberately. Only an explicit negative
    sentinel — or an unparsed run id, which makes a run-scoped ref unnameable
    on its face — retracts the ref. A record that reports neither outcome is
    the ordinary one, and treating it as failure would retract a ref that is
    really there, which is the mirror-image lie.
    """
    if run_id is None:
        return _not_pushed(because="no run id was parsed from the launch output")
    if _NO_RUN_ID_SENTINEL in text:
        return _not_pushed(because="the terminal reported that no run id reached it")
    if _PUSH_FAILED_SENTINEL in text:
        return _not_pushed(because="the terminal reported that its preservation push failed")
    ref = f"refs/heads/needs-human/{run_id}"
    return f"the tree was preserved on {ref} ({_PRESERVED_POINTER})"


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


def _decision(*, work_item_id: str) -> str:
    """Where the decision lives, which is the ledger and never a live run."""
    return (
        "no run is waiting — the decision lives in the ledger: answer with "
        f"`resolve-blocked:{work_item_id}:ready` (re-dispatch, seeding rework from "
        "the preserved ref or from scratch) or leave the item blocked"
    )
