"""The DURABLE ledger record of why a run reached the needs-human terminal.

`_dispatcher_needs_human_detail` renders this ending for the dispatch RESULT
and `_dispatcher_blocked` writes the one-line SURFACE for the stream `drive`
captures. Both are transient: the result is read once and the stream scrolls
away. `_needs_attention_needs_human_question` renders the ending in the
attention lane, which looks durable and is not — it re-inspects Fabro on
demand, so its account lasts exactly as long as the run record does. Once the
factory prunes the run, becomes unreachable, or the run is reaped, the causal
fault disappears from every one of those surfaces at the same moment.

The only thing on this tenant that outlives the run is a COMMENT. So this
module writes the fault once, at the escalation, and the attention rendering is
kept beside it rather than replaced — the lane is the right place to SEE this
ending, and a comment is the right place for it to SURVIVE.

WHAT THE RECORD MAY NOT CLAIM. It reports the verdict `_fabro_causal_stage`
reached and nothing beyond it: no stage for an ending that recorded none, no
transport-fault classification a cause does not support, no pending question
when no agent asked, and no denial of one when an agent did. Every one of those
is a claim a reader ACTS on, and this record outlives everything that could
correct it — `bd comments` offers add and list, with no edit and no delete. For
the same reason it claims nothing about PRESERVATION: whether a ref was pushed
is read from the terminal's own sentinels by `_dispatcher_needs_human_detail`,
which has the run output this writer does not. The terminal's own REASON line is
the one thing out of that output this record does carry, and it arrives already
parsed on the outcome rather than re-derived here, precisely because this writer
never sees the text.

TWO HAZARDS COME FROM THE TEXT BEING ENGINE-AUTHORED RATHER THAN OURS, and both
are closed by primitives that already exist rather than by local copies.

A MiniJinja opener anywhere in a ledger comment makes every later dispatch of
that item refuse at the goal preflight, permanently. An engine cause quoting a
shell command is exactly where one arrives, so the text goes through
`comment_safe_external_text` — the same neutralizer the preserve-by-reference
pointer uses, so the two writers cannot drift into two policies that merely
look alike. The record also says on its own face that the rewrite is in force,
so a reader who sees a bracket form does not read it as the command the agent
actually ran.

And a `pr`-stage cause can quote a push against a tokenized origin URL, which
would put a live credential into an append-only record. The credential-shaped
value is replaced WHOLESALE with `_otel_scrub`'s marker rather than partially,
which is the fleet's fail-closed policy for this shape. The CHECK is reused
rather than the whole of `scrub`, because `scrub` also truncates to an OTLP
attribute ceiling of 300 characters — a bound tuned for a span attribute, and
one that can cut a long cause off before the command the record exists to name.
The bounding here is `comment_safe_external_text`'s own, which is sized for a
comment.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit import (
    hook_over_limit_cause_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    comment_safe_external_text,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
)
from livespec_orchestrator_beads_fabro.commands._fabro_transport_fault import (
    TransportFault,
    transport_fault_clause,
    transport_fault_from_cause,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
    CREDENTIAL_URL_RE,
    REDACTION_MARKER,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "NEEDS_HUMAN_CAUSE_MARKER",
    "needs_human_cause_body",
    "record_needs_human_cause",
]

NEEDS_HUMAN_CAUSE_MARKER = "livespec-needs-human-cause"

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

# Stated on the record itself, because the neutralizer rewrites an opener into
# a bracket form that LOOKS like something the agent typed. A reader comparing
# this record against a shell history needs to know the rewrite happened.
_REWRITE_NOTICE = (
    "engine text above is sanitized by the writer: MiniJinja openers are rewritten to "
    "bracket forms (a ledger comment carrying one refuses every later dispatch of this "
    "item), and a credential-shaped value is replaced wholesale with "
    f"`{REDACTION_MARKER}`."
)


def record_needs_human_cause(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Append the causal record for a needs-human ending, once.

    Returns without writing for any other outcome. The writer runs inside the
    shared post-run disposition sequence, which every outcome passes through,
    so the status guard is what keeps this record an account of an ending that
    actually happened rather than a note on every dispatch.

    A ledger write failure is JOURNALED and never raised. The run has already
    ended and the lifecycle write that matters — `blocked` / `needs-human` —
    is `_dispatcher_blocked`'s and has its own error arm; losing this record
    costs an operator the durable account, which is worth a journal row and is
    not worth converting into a dispatch failure after the fact.
    """
    if outcome.status != "blocked":
        return
    if outcome.needs_human_kind is None:
        return
    written = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=needs_human_cause_body(outcome=outcome),
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    stage = (
        "needs-human-cause-record-error"
        if isinstance(written, AttemptFailure)
        else "needs-human-cause-record"
    )
    record: dict[str, object] = {
        "stage": stage,
        "work_item_id": item.id,
        "needs_human_kind": outcome.needs_human_kind,
    }
    if isinstance(written, AttemptFailure):
        record["reason"] = type(written.error).__name__
    journal.append(record=record)


def needs_human_cause_body(*, outcome: DispatchOutcome) -> str:
    """Render the record. PURE, so every claim it makes is testable in isolation."""
    lines = [
        NEEDS_HUMAN_CAUSE_MARKER,
        "",
        f"work-item: {outcome.work_item_id}",
        f"run id: {outcome.fabro_run_id or '(not parsed from the launch output)'}",
        f"ending: {outcome.needs_human_kind}",
        *_attribution(outcome=outcome),
        *_terminal_reason(outcome=outcome),
        *_provider(outcome=outcome),
        "",
        _decision(outcome=outcome),
        "",
        _REWRITE_NOTICE,
    ]
    return "\n".join(lines)


def _attribution(*, outcome: DispatchOutcome) -> tuple[str, ...]:
    """The measured half: what the engine recorded, and what it classifies as.

    Each line is emitted only when its own evidence is present, which is what
    keeps the record's silences meaningful. A `failed stage:` line on an ending
    that attributed none would invent one, and a `transport fault:` line on a
    cause the classifier declined would be the item's own prohibition on
    treating every ACP failure as a backgrounded tool.
    """
    if outcome.needs_human_kind != STAGE_FAILURE:
        return ()
    lines: list[str] = []
    if outcome.needs_human_stages:
        lines.append(f"failed stage: {', '.join(outcome.needs_human_stages)}")
    if outcome.fabro_failure_cause is not None:
        lines.append(f"innermost cause: {_safe(text=outcome.fabro_failure_cause)}")
        lines.extend(_fault(cause=outcome.fabro_failure_cause))
    # The hook-over-limit classification, when the ending is attributed to one.
    #
    # OUR OWN TEXT, so it does not pass through `_safe`: every field is an
    # enumerated node name, an enumerated operation, or an integer this
    # module's own parse produced, and none of it is engine prose that could
    # carry a MiniJinja opener or a tokenized URL.
    #
    # It is rendered only under STAGE_FAILURE, which is what keeps a RECOVERED
    # event from being named as the cause of a later ending: the clause forbids
    # exactly that, and the event reaching this writer at all means the run
    # ended on the stage the observation came from.
    lines.extend(hook_over_limit_cause_lines(event=outcome.hook_over_limit))
    if outcome.fabro_failure_category is not None:
        lines.append(f"failure category: {outcome.fabro_failure_category}")
    if outcome.fabro_failure_signature is not None:
        lines.append(f"failure signature: {_safe(text=outcome.fabro_failure_signature)}")
    return tuple(lines)


def _fault(*, cause: str) -> tuple[str, ...]:
    """The classification, and whatever the engine's own wording identified.

    The command and the task ride on their OWN labelled lines rather than being
    left inside the quoted cause. The cause already contains the command, so a
    record that only quoted it would satisfy "names the backgrounded command"
    while telling the reader nothing about what kind of failure this was —
    which is the misreading the whole classification exists to prevent.

    THE CLAUSE IS RENDERED FROM A COMMAND-FREE COPY OF THE FAULT, and that is a
    sanitization boundary rather than a tidiness choice.
    `transport_fault_clause` interpolates the command into its own prose, so
    rendering the real fault here put the engine's unsanitized command into the
    body on a line that never passed through `_safe` — which leaked a tokenized
    push URL and a live MiniJinja opener in exactly the two cases this module's
    tests cover. Passing a bare copy keeps the family wording (which is ours,
    and safe) while leaving the command to the one line that sanitizes it. Do
    not "simplify" this back to `transport_fault_clause(fault=fault)`.
    """
    fault = transport_fault_from_cause(cause=cause)
    if fault is None:
        return ()
    bare = TransportFault(family=fault.family, command=None, task_id=None)
    lines = [
        f"transport fault: {fault.family}",
        f"classification: {transport_fault_clause(fault=bare)}",
    ]
    if fault.command is not None:
        lines.append(f"backgrounded command: {_safe(text=fault.command)}")
    if fault.task_id is not None:
        lines.append(f"backgrounded task: {fault.task_id}")
    return tuple(lines)


def _terminal_reason(*, outcome: DispatchOutcome) -> tuple[str, ...]:
    """The reason the terminal node printed, which for some endings is the only one.

    RENDERED UNDER EVERY KIND, unlike `_attribution` above, because the terminal
    prints this line whatever routed the run to it and the engine classifies no
    cause for several of the endings that reach it. A `publish_draft` permission
    refusal and a stage that timed out mid Red-Green pair both arrive here with
    the whole diagnosis in this one line and nothing in the outcome map; the
    transient surfaces already carry it (`_dispatcher_needs_human_detail`), and
    without it here the durable record — the one that outlives the run — was the
    only surface missing the account (work-item bd-ib-qhv7qs).

    OMITTED rather than reported absent, per this module's own rule that a
    silence is meaningful: a line saying the terminal recorded nothing is a
    claim about the TERMINAL, and an unreadable or truncated run output supports
    it no better than it supports any other.

    Through `_safe` for the same reason every other engine-authored line is: the
    reason can quote an agent's own words, a path, or a command, and this record
    cannot be repaired after the fact.
    """
    if outcome.needs_human_reason is None:
        return ()
    return (f"terminal reason: {_safe(text=outcome.needs_human_reason)}",)


def _provider(*, outcome: DispatchOutcome) -> tuple[str, ...]:
    """The vendor ceiling, named because the next dispatch acts on it.

    Keyed on the PROVIDER rather than on the boolean, for the reason
    `_dispatcher_fabro_terminal` gives for carrying both: the exhaustion record
    this informs is labelled with the vendor, so a ceiling observed without one
    is a hold nobody can apply.
    """
    if outcome.provider_usage_limit_provider is None:
        return ()
    return (f"provider ceiling: {outcome.provider_usage_limit_provider} refused this run",)


def _decision(*, outcome: DispatchOutcome) -> str:
    """What the human is being asked to do, which is where the arms part.

    The valve is named in every arm because the lifecycle does not branch: the
    item rests at `blocked` / `needs-human` and `resolve-blocked:<id>:ready` is
    its only exit. What differs is whether a QUESTION is pending — the thing
    the reader goes looking for, and the thing one wording had to be wrong
    about for two of the three endings.

    THE UNESTABLISHED ARM AVOIDS THE AFFIRMATIVE PHRASE the request arm uses,
    and that is deliberate. Its sentence has to NAME both possibilities in
    order to disclaim them, so a disclaimer worded with the affirmative in it
    reads as the affirmative to anything that searches this record by phrase —
    a grep, a console filter, or a reader skimming. The same hazard bit an
    audit of this repository's own notes, where a retracted claim was found
    inside its own retraction and nearly re-filed as live. Keep the two arms
    lexically distinct, not merely semantically distinct.
    """
    valve = f"`resolve-blocked:{outcome.work_item_id}:ready`"
    if outcome.needs_human_kind == AGENT_REQUEST:
        return (
            f"decision: an agent asked a question and a human has something to decide; "
            f"answer with {valve} (re-dispatch, seeding rework from the preserved ref or "
            "from scratch) or leave the item blocked"
        )
    if outcome.needs_human_kind == STAGE_FAILURE:
        return (
            "decision: no agent asked anything, so no answer is owed; triage the fault "
            f"recorded above, then release the item with {valve} to re-dispatch, or leave "
            "it blocked"
        )
    return (
        "decision: this run's record does not establish whether a stage failed or a "
        "decision was genuinely requested, so neither is claimed; triage the run to find "
        f"out, then release it with {valve} to re-dispatch, or leave it blocked"
    )


def _safe(*, text: str) -> str:
    """Engine text made safe for an append-only comment. See the module docstring."""
    if CREDENTIAL_URL_RE.search(text) is not None:
        return REDACTION_MARKER
    return comment_safe_external_text(text=text)
