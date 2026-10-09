"""Terminate an orphaned Fabro run, preferring the route that records intent.

Three routes, tried in a fixed order, and the order is the point.

A BLOCKED run is holding a pending interview, so it is answered with the
graph's own Abandon option through the server's answer route. That leaves
Fabro's record saying an operator-equivalent authority abandoned the run,
which is a different and more honest artifact than a run that simply
vanished. The option text is matched on the word "abandon" rather than on a
fixed label, because the label belongs to the workflow graph's edge
(`[A] Abandon (leave open for triage)`) and may be reworded there.

What is SENT, though, is the option's `key` and not its label: the server's
typed `SubmitAnswerRequest` selects by key and rejects a label with 422. So
an option carrying no key is not answerable however plainly it says
"abandon", and such a question falls through to the cancel route rather than
posting a body the server will refuse.

Anything else — and any blocked run whose interview could not be answered —
is cancelled through the server's cancel route. The caller's hold predicate is
checked AFTER question discovery and immediately before every answer, cancel,
or force-remove. Route preparation therefore cannot carry stale authorization
across a slow request, and one failed destructive route cannot authorize the
next one.

`fabro rm --force` is the LAST resort, taken only after the HTTP routes
have failed, and the caller journals it under its own stage name. It
destroys everything reachable through `inspect` / `dump` / `attach` for that
run, which is exactly why it is not the first thing tried and why the export
is an unconditional precondition of reaching this module at all.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "TERMINATION_ROUTE_ANSWER",
    "TERMINATION_ROUTE_CANCEL",
    "TERMINATION_ROUTE_RM",
    "PendingAbandonAnswer",
    "TerminationOutcome",
    "abandon_answer",
    "terminate_orphan_run",
]

TERMINATION_ROUTE_ANSWER = "questions-answer"
TERMINATION_ROUTE_CANCEL = "cancel"
TERMINATION_ROUTE_RM = "rm-force"

_BLOCKED_STATUS_KIND = "blocked"
_ABANDON_HINT = "abandon"
_QUESTION_ID_KEYS = ("id", "question_id", "qid")
_QUESTION_LIST_KEYS = ("data", "questions")
_OPTION_KEYS = ("options", "choices", "answers")
_OPTION_TEXT_KEYS = ("label", "text", "value")
_OPTION_KEY_KEYS = ("key", "option_key")
_HTTP_TIMEOUT_SECONDS = 60.0
_RM_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class _AbandonOption:
    """One question option's wire key beside the label it was matched on."""

    key: str
    label: str


@dataclass(frozen=True, kw_only=True)
class PendingAbandonAnswer:
    """The question to answer, and the option that abandons the run.

    `option_key` is what the answer route is given; `option` is the label it
    was matched on, carried so the journalled detail names something an
    operator can recognise in the workflow graph.
    """

    question_id: str
    option_key: str
    option: str


@dataclass(frozen=True, kw_only=True)
class TerminationOutcome:
    """Which route ended the run, whether it worked, and what was observed."""

    route: str
    succeeded: bool
    detail: str


def abandon_answer(*, payload: object | None) -> PendingAbandonAnswer | None:
    """Find the pending question's Abandon option in a questions payload."""
    for question in _questions(payload=payload):
        question_id = _first_str(record=question, keys=_QUESTION_ID_KEYS)
        option = _abandon_option(question=question)
        if question_id is not None and option is not None:
            return PendingAbandonAnswer(
                question_id=question_id,
                option_key=option.key,
                option=option.label,
            )
    return None


def terminate_orphan_run(
    *,
    port: FabroPort,
    run_id: str,
    status_kind: str,
    destructive_action_held: Callable[[], bool] = lambda: False,
) -> TerminationOutcome | None:
    """Terminate through the first route that works, or hold before an action."""
    server_api = port.server_api()
    pending = _pending_abandon(port=port, run_id=run_id, status_kind=status_kind)
    if pending is not None:
        if destructive_action_held():
            return None
        answered = server_api.answer_question(
            run_id=run_id,
            question_id=pending.question_id,
            option_key=pending.option_key,
            timeout_seconds=_HTTP_TIMEOUT_SECONDS,
        )
        if answered.succeeded:
            return TerminationOutcome(
                route=TERMINATION_ROUTE_ANSWER,
                succeeded=True,
                detail=f"answered question {pending.question_id} with {pending.option!r}",
            )
    if destructive_action_held():
        return None
    cancelled = server_api.cancel(run_id=run_id, timeout_seconds=_HTTP_TIMEOUT_SECONDS)
    if cancelled.succeeded:
        return TerminationOutcome(
            route=TERMINATION_ROUTE_CANCEL,
            succeeded=True,
            detail=f"cancel route returned {cancelled.status}",
        )
    unavailable = _route_detail(status=cancelled.status, error=cancelled.error)
    if destructive_action_held():
        return None
    removed = port.rm(run_id=run_id, timeout_seconds=_RM_TIMEOUT_SECONDS)
    return TerminationOutcome(
        route=TERMINATION_ROUTE_RM,
        succeeded=removed.command.exit_code == 0,
        detail=(
            f"cancel route unavailable ({unavailable}); "
            f"fabro rm -f exited {removed.command.exit_code}"
        ),
    )


def _pending_abandon(
    *,
    port: FabroPort,
    run_id: str,
    status_kind: str,
) -> PendingAbandonAnswer | None:
    if status_kind != _BLOCKED_STATUS_KIND:
        return None
    listed = port.server_api().questions(run_id=run_id, timeout_seconds=_HTTP_TIMEOUT_SECONDS)
    return abandon_answer(payload=listed.payload) if listed.succeeded else None


def _route_detail(*, status: int, error: str | None) -> str:
    return error if error is not None else f"status {status}"


def _questions(*, payload: object | None) -> tuple[dict[str, Any], ...]:
    if not isinstance(payload, dict):
        return _question_records(value=payload)
    # The live envelope carries its listing under `data` beside a `meta`
    # block; `questions` is kept as a tolerated alias, and a mapping holding
    # neither is read as one question sent bare.
    record = cast("dict[str, Any]", payload)
    for key in _QUESTION_LIST_KEYS:
        nested: object = record.get(key)
        if isinstance(nested, list):
            return _question_records(value=cast("list[object]", nested))
    return (record,)


def _question_records(*, value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    entries = cast("list[object]", value)
    return tuple(cast("dict[str, Any]", entry) for entry in entries if isinstance(entry, dict))


def _abandon_option(*, question: dict[str, Any]) -> _AbandonOption | None:
    for key in _OPTION_KEYS:
        raw: object = question.get(key)
        if not isinstance(raw, list):
            continue
        option = _abandon_from_options(options=cast("list[object]", raw))
        if option is not None:
            return option
    return None


def _abandon_from_options(*, options: Sequence[object]) -> _AbandonOption | None:
    for option in options:
        if not isinstance(option, dict):
            continue
        record = cast("dict[str, Any]", option)
        label = _first_str(record=record, keys=_OPTION_TEXT_KEYS)
        option_key = _first_str(record=record, keys=_OPTION_KEY_KEYS)
        if label is not None and option_key is not None and _ABANDON_HINT in label.lower():
            return _AbandonOption(key=option_key, label=label)
    return None


def _first_str(*, record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value: object = record.get(key)
        if isinstance(value, str) and value != "":
            return value
    return None
