"""The human ANSWER a `resolve-blocked` valve carries back to the work-item.

Contract v093 (`SPECIFICATION/contracts.md`, the clause holding that a factory
run never awaits a human) settles the shape of this route before any code does.
A factory run that needs a decision TERMINATES: it does not park, it cannot be
resumed, and the item rests at `blocked / needs-human` until an operator
answers through `resolve-blocked:<item-id>:ready|backlog`, which is a
re-dispatch. So the answer has to reach a FUTURE run rather than the run that
asked — which means it has to travel on a channel the next dispatch already
reads.

That channel already exists, which is why this module adds no seam of its own.
`_dispatcher_goal.render_goal` assembles the item's ledger comments into the
brief verbatim, under a heading that tells the implementer to treat them as
part of the assignment. Writing the answer as a ledger comment therefore flows
it back over the SAME channel the question was published on, and no
re-dispatch can forget to read it without also forgetting the operator riders
it already honours.

It is deliberately NOT the lessons-injection seam. Ratified lessons are
human-merged through `loop-reflection-gate/lessons.md` and are standing
guidance for every dispatch of every item; an answer is one operator's
decision about one item. Routing it through lessons would both mis-scope it
and bypass the ratification that file exists to require.

THE PREFLIGHT IS THE LOAD-BEARING PART, and it is why the answer is graded
before it is written rather than escaped as it is rendered. A ledger comment is
append-only — `bd comments` offers neither edit nor delete — so an answer
carrying a MiniJinja opening delimiter would poison every FUTURE goal render
for this item permanently, killing each dispatch before a run exists; this
repository's agent instructions record three items already lost that way. The
answer is graded with the same detector the dispatch-time goal preflight uses
(`minijinja_openers_in_text`), so an opener that would refuse the dispatch can
never be admitted by the writer that feeds it. A poisoned answer is REFUSED
with nothing written rather than silently escaped: a rewritten answer is not
the answer the human gave, and rewording one costs the operator seconds while
an unusable ledger comment costs the item its dispatchability forever.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import valve_refusal
from livespec_orchestrator_beads_fabro.store import append_work_item_comment
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "ANSWER_COMMENT_MARKER",
    "ANSWER_JOURNAL_STAGE",
    "AnswerDelivery",
    "answer_delivery",
    "answer_note",
    "answering_action_id",
    "deliver_answer",
    "render_answer_comment",
]

# The stable opening token of every answer comment. The goal brief renders a
# ledger comment verbatim, so this line is what tells the re-dispatched
# implementer that what follows is the operator's ANSWER rather than one more
# rider appended after filing.
ANSWER_COMMENT_MARKER = "livespec-human-answer"
ANSWER_JOURNAL_STAGE = "human-valve-resolve-blocked-answer"

# The header's opening and closing punctuation, and the separator between its
# fields. Named because `answering_action_id` below is the exact inverse of
# `render_answer_comment` and both ends must move together.
_HEADER_OPEN = " ("
_HEADER_CLOSE = "):"
_HEADER_FIELD_SEPARATOR = ", "

_JOURNAL_RELATIVE_PATH = ("tmp", "fabro-dispatch-journal.jsonl")
# The source label the preflight's findings carry. It names the OPERATOR's
# input rather than a goal-brief field, because that is what the refusal has to
# send them back to reword.
_ANSWER_SOURCE = "answer"


@dataclass(frozen=True, kw_only=True)
class AnswerDelivery:
    """One operator answer, bound to who gave it and where to journal it."""

    answer: str
    identity: InvokerIdentity
    repo: Path


def answer_delivery(
    *, answer: str | None, identity: InvokerIdentity, repo: Path
) -> AnswerDelivery | None:
    """Bind an answer to its invoker, or None when the invocation carried none.

    Exists so the valve transport stays a straight line: an invocation without
    `--answer` produces None here and the resolve path is byte-for-byte the one
    that shipped before this route, rather than a second branch that has to be
    kept equivalent.
    """
    if answer is None:
        return None
    return AnswerDelivery(answer=answer, identity=identity, repo=repo)


def answer_note(*, delivery: AnswerDelivery | None) -> str:
    """The clause saying the answer reached the ledger, or nothing at all.

    Lives here rather than at the valve because the operator's evidence that
    the route WORKED is this sentence: the transition would read identically
    whether or not the answer landed, and a valve reporting only the status
    move is how a silently-dropped answer stays invisible.
    """
    if delivery is None:
        return ""
    return "; the answer is on the ledger and the next dispatch's brief carries it"


def deliver_answer(
    *, config: StoreConfig, item: WorkItem, aid: str, delivery: AnswerDelivery
) -> dict[str, Any] | None:
    """Write the answer to the ledger and journal it; a refusal payload, or None.

    None means DELIVERED, so the caller may proceed to the status transition. A
    returned payload is a refusal that wrote NOTHING — not the comment, not the
    journal line — so the operator can reword and re-run the identical action.

    The journal line is written after the ledger comment rather than before it,
    so the journal records answers that actually landed. A comment write that
    raised would otherwise leave a journal asserting a delivery the next
    dispatch's brief cannot corroborate.
    """
    refusal = _answer_refusal(aid=aid, wid=item.id, answer=delivery.answer)
    if refusal is not None:
        return refusal
    answered_at = utc_now_iso()
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=render_answer_comment(
            answer=delivery.answer,
            aid=aid,
            identity=delivery.identity,
            at=answered_at,
        ),
    )
    JournalFile(
        path=delivery.repo.joinpath(*_JOURNAL_RELATIVE_PATH), identity=delivery.identity
    ).append(
        record={
            "actor": "operator",
            "stage": ANSWER_JOURNAL_STAGE,
            "work_item_id": item.id,
            "action_id": aid,
            "answer": delivery.answer,
            "answered_at": answered_at,
        }
    )
    return None


def render_answer_comment(*, answer: str, aid: str, identity: InvokerIdentity, at: str) -> str:
    """Render the comment body a re-dispatched brief will carry verbatim.

    The attribution and the timestamp are written INTO the body rather than
    left to beads' own `author` / `created_at` columns. The goal brief does
    render a comment's provenance, but it reads those columns — and they carry
    the tenant's bd connection user, which every operator on this repo shares.
    The invoker the drive surface resolved is the one that names WHO answered,
    so it has to be in the text if the next run is to see it at all.
    """
    return (
        f"{ANSWER_COMMENT_MARKER}{_HEADER_OPEN}{identity.invoker} via {identity.invoker_source}"
        f"{_HEADER_FIELD_SEPARATOR}{at}{_HEADER_FIELD_SEPARATOR}{aid}{_HEADER_CLOSE}\n{answer}"
    )


def answering_action_id(*, text: str) -> str | None:
    """The valve action id an answer comment was written under, or None.

    The exact inverse of `render_answer_comment`, and it lives beside it for
    that reason: the header is the ONLY place the DISPOSITION an answer
    carried survives into the ledger, so a reader that re-derives the header's
    shape elsewhere drifts from the writer silently — and the drift's symptom
    is a `resolve-blocked:<id>:backlog` send-back read as a `:ready` consent,
    not a parse error anyone would notice.

    `None` means the text is not an answer comment this reader can speak for:
    the marker does not open its first line, or that line's header is not
    closed. Both are refused rather than salvaged, because a header whose
    disposition cannot be read must never be treated as one that consents.
    """
    head = text.split("\n", 1)[0]
    prefix = f"{ANSWER_COMMENT_MARKER}{_HEADER_OPEN}"
    if not head.startswith(prefix) or not head.endswith(_HEADER_CLOSE):
        return None
    fields = head[len(prefix) : -len(_HEADER_CLOSE)]
    return fields.rsplit(_HEADER_FIELD_SEPARATOR, 1)[-1].strip()


def _answer_refusal(*, aid: str, wid: str, answer: str) -> dict[str, Any] | None:
    if answer.strip() == "":
        return valve_refusal(
            aid=aid,
            wid=wid,
            err="empty-answer",
            msg=(
                "resolve-blocked refused: the answer is empty. Omit --answer "
                "entirely to resolve the item without one."
            ),
        )
    findings = minijinja_openers_in_text(source=_ANSWER_SOURCE, text=answer)
    if not findings:
        return None
    openers = ", ".join(sorted({finding.opener for finding in findings}))
    return valve_refusal(
        aid=aid,
        wid=wid,
        err="answer-would-poison-goal",
        msg=(
            f"resolve-blocked refused: the answer carries MiniJinja opening "
            f"delimiter(s) {openers}. A ledger comment cannot be edited or "
            f"deleted, so writing it would fail every future goal render for "
            f"{wid} before any run exists. Nothing was written; reword the "
            f"answer without them."
        ),
    )
