"""What the retry-discipline guard SAYS when it refuses.

PURE, and split from `_dispatcher_retry_records` on the seam that module's
docstring implies: that one owns what a record IS, this one owns what an
operator READS. The two have different readers — a record is parsed by the next
dispatch, prose by nobody — so keeping the prose out of the record module is
what lets a refusal grow a clause without touching the format the guard matches
on.

EVERY REFUSAL NAMES THE REMEDY, AND THE REMEDY IS ONE FLAG. The rule being
implemented is that a re-dispatch after a failure must name what changed, so a
refusal that quoted the signature without saying how to proceed would read as a
dead end and send the operator hunting for a valve. `BECAUSE_FLAG` is spelled
once here and forwarded verbatim by every surface that builds a dispatcher argv.

THE SOURCE-MODULE CLAUSE HAS THREE OUTCOMES AND THEY ARE NOT INTERCHANGEABLE.
Byte-identical says the refusing code is the same code, so a re-dispatch on this
build meets the same decision; not byte-identical says the code moved, which is
the one named change the comparison can establish by itself. UNDETERMINED is
neither, and it is reported as its own answer rather than folded onto either:
"the comparison could not be taken" and "the two copies agree" support opposite
conclusions, and collapsing them would let an unreadable build read as a
confirmed repeat.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_retry_records import RetryRecord

__all__: list[str] = [
    "BECAUSE_FLAG",
    "armed_refusal",
    "blank_reason_refusal",
    "module_identity_clause",
    "unreadable_timeline_refusal",
]

BECAUSE_FLAG = "--because"

_RECORDING_BUILD = "recording"
_EXECUTING_BUILD = "executing"


def blank_reason_refusal() -> str:
    """The refusal for a `--because` carrying no reason at all.

    Refused WHATEVER the item's timeline says, and that is deliberate: a blank
    reason is never a statement about anything, so grading it against the guard
    would make the same empty string acceptable on an unarmed item and a refusal
    on an armed one — one item's worth of difference, which the operator who
    typed it cannot see.
    """
    return (
        f"ERROR: {BECAUSE_FLAG} was given an empty reason. The reason must name what "
        "changed since the recorded failure — a different dispatching build, a "
        "configuration key, a landed fix — because a re-dispatch that names no change "
        "is a re-run of the attempt that already failed.\n"
    )


def unreadable_timeline_refusal(*, work_item_id: str, detail: str) -> str:
    """The refusal for an item whose retry timeline could not be read.

    FAIL-CLOSED, because the alternative is a gauge that passes when blinded: an
    unreadable timeline is indistinguishable from an empty one, and treating it
    as empty admits exactly the re-dispatch this guard exists to refuse while
    leaving a record that reads like a healthy admission.
    """
    return (
        f"ERROR: dispatch of {work_item_id} refused: its retry-discipline timeline "
        f"could not be read ({detail}), so whether a previous dispatch recorded a "
        "refusal signature is UNDETERMINED. The guard fails closed rather than "
        "admitting on a ledger it could not read.\n"
    )


def module_identity_clause(*, module: str, recorded: bytes | None, executing: bytes | None) -> str:
    """Whether the refusing stage's source module is the same bytes in both builds."""
    if module == "":
        return (
            "Source-module comparison: UNDETERMINED — the refusing stage names no "
            "source module this build can locate."
        )
    unreadable = [
        name
        for name, payload in ((_RECORDING_BUILD, recorded), (_EXECUTING_BUILD, executing))
        if payload is None
    ]
    if unreadable:
        return (
            f"Source-module comparison: UNDETERMINED — the {' and '.join(unreadable)} "
            f"build's copy of {module} could not be read."
        )
    if recorded == executing:
        return (
            "Source-module comparison: the recording and executing builds' copies of "
            f"{module} are BYTE-IDENTICAL."
        )
    return (
        "Source-module comparison: the recording and executing builds' copies of "
        f"{module} are NOT byte-identical."
    )


def armed_refusal(
    *,
    work_item_id: str,
    signature: RetryRecord,
    module_clause: str,
    ineffective_reason: str | None,
) -> str:
    """The refusal that quotes an armed signature and names the way to proceed."""
    headline = (
        f"ERROR: dispatch of {work_item_id} refused: its most recent recorded dispatch "
        "outcome is a refusal signature, so no Fabro run was created."
    )
    remedy = (
        f"To proceed, name what changed since that failure: {BECAUSE_FLAG} " '"<what changed>".'
    )
    lines = [
        headline,
        f"  refusing stage or admission: {signature.stage}",
        f"  error class: {signature.error_class}",
        f"  orchestrator build: {signature.build.version}",
        f"  plugin root: {signature.build.plugin_root}",
        f"  recorded at: {signature.recorded_at}",
        module_clause,
        *_ineffective_clause(reason=ineffective_reason),
        remedy,
    ]
    return "\n".join(lines) + "\n"


def _ineffective_clause(*, reason: str | None) -> tuple[str, ...]:
    """The clause for an override whose attempt ended the way it started.

    EMPTY when there was no override, and empty too when the override's attempt
    ended at a DIFFERENT stage or class: that is a named change which moved the
    failure, and reporting it as ineffective would tell the operator their change
    did nothing while the record shows it did.
    """
    if reason is None:
        return ()
    clause = (
        "The previous reason did NOT change the outcome — this attempt ended at the "
        f'same stage and error class it overrode: "{reason}"'
    )
    return (clause,)
