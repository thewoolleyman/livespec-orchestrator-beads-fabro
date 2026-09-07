"""Tests for the v093-native answer route the `resolve-blocked` valve carries."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_answer import (
    ANSWER_COMMENT_MARKER,
    ANSWER_JOURNAL_STAGE,
    AnswerDelivery,
    answer_delivery,
    answer_note,
    answering_action_id,
    deliver_answer,
    render_answer_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_item_comments
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

# The two-character MiniJinja openers, built rather than written literally: this
# file's own text is read by nothing that renders a goal, but the repository's
# convention is to keep the literal pair out of prose that discusses it.
_EXPRESSION_OPENER = "{" + "{"
_STATEMENT_OPENER = "{" + "%"
_COMMENT_OPENER = "{" + "#"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _identity() -> InvokerIdentity:
    return InvokerIdentity(invoker="operator:cwoolley", invoker_source="flag")


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-blocked",
        type="task",
        status="blocked",
        title="Blocked",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )
    return replace(base, **overrides)


def _delivery(*, answer: str, repo: Path) -> AnswerDelivery:
    return AnswerDelivery(answer=answer, identity=_identity(), repo=repo)


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    if not journal.is_file():
        return []
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line]


def test_a_poisoned_answer_is_refused_with_nothing_written(tmp_path: Path) -> None:
    """A template opener would permanently poison the item's goal render."""
    item = _item()
    append_work_item(path=_config(), item=item)
    poisoned = f"Take option B, then run {_EXPRESSION_OPENER} justfile.recipe }}}}."

    result = deliver_answer(
        config=_config(),
        item=item,
        aid="resolve-blocked:bd-ib-blocked:ready",
        delivery=_delivery(answer=poisoned, repo=tmp_path),
    )

    assert result is not None
    assert result["domain_error"] == "answer-would-poison-goal"
    assert _EXPRESSION_OPENER in str(result["summary"])
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-blocked") == ()
    assert _journal_records(repo=tmp_path) == []


def test_every_minijinja_opener_is_refused_and_reported(tmp_path: Path) -> None:
    """All three openers are graded, not just the expression one.

    The answer preflight reaches the SAME detector the dispatch-time goal
    preflight uses, so an opener the dispatch would refuse can never be
    admitted here; the three-opener sweep is what makes that checkable.
    """
    item = _item(id="bd-ib-openers")
    append_work_item(path=_config(), item=item)
    answer = f"{_STATEMENT_OPENER} if x {_EXPRESSION_OPENER} y {_COMMENT_OPENER} z"

    result = deliver_answer(
        config=_config(),
        item=item,
        aid="resolve-blocked:bd-ib-openers:ready",
        delivery=_delivery(answer=answer, repo=tmp_path),
    )

    assert result is not None
    summary = str(result["summary"])
    for opener in (_EXPRESSION_OPENER, _STATEMENT_OPENER, _COMMENT_OPENER):
        assert opener in summary
    assert minijinja_openers_in_text(source="answer", text=answer) != ()


def test_an_empty_answer_is_refused_rather_than_written_as_a_blank_rider(
    tmp_path: Path,
) -> None:
    item = _item(id="bd-ib-blank")
    append_work_item(path=_config(), item=item)

    result = deliver_answer(
        config=_config(),
        item=item,
        aid="resolve-blocked:bd-ib-blank:ready",
        delivery=_delivery(answer="   \n ", repo=tmp_path),
    )

    assert result is not None
    assert result["domain_error"] == "empty-answer"
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-blank") == ()


def test_a_clean_answer_lands_as_a_ledger_comment_and_a_journal_record(
    tmp_path: Path,
) -> None:
    item = _item(id="bd-ib-answered")
    append_work_item(path=_config(), item=item)

    result = deliver_answer(
        config=_config(),
        item=item,
        aid="resolve-blocked:bd-ib-answered:ready",
        delivery=_delivery(answer="Take option B: keep the guard fail-closed.", repo=tmp_path),
    )

    assert result is None
    [comment] = read_work_item_comments(path=_config(), work_item_id="bd-ib-answered")
    assert comment.text.startswith(ANSWER_COMMENT_MARKER)
    assert "Take option B: keep the guard fail-closed." in comment.text
    assert "operator:cwoolley" in comment.text
    [record] = _journal_records(repo=tmp_path)
    assert record["stage"] == ANSWER_JOURNAL_STAGE
    assert record["work_item_id"] == "bd-ib-answered"
    assert record["answer"] == "Take option B: keep the guard fail-closed."
    assert record["invoker"] == "operator:cwoolley"


def test_the_comment_body_carries_the_invoker_rather_than_only_the_bd_author() -> None:
    """The bd `author` column is the shared tenant user, so it cannot name who answered."""
    body = render_answer_comment(
        answer="Ship it.",
        aid="resolve-blocked:bd-ib-x:ready",
        identity=_identity(),
        at="2026-09-06T12:00:00Z",
    )

    assert body.startswith(ANSWER_COMMENT_MARKER)
    assert "operator:cwoolley via flag" in body
    assert "2026-09-06T12:00:00Z" in body
    assert "resolve-blocked:bd-ib-x:ready" in body
    assert body.endswith("Ship it.")


def test_answer_delivery_is_none_without_an_answer_and_bound_with_one(tmp_path: Path) -> None:
    assert answer_delivery(answer=None, identity=_identity(), repo=tmp_path) is None

    bound = answer_delivery(answer="yes", identity=_identity(), repo=tmp_path)

    assert bound == AnswerDelivery(answer="yes", identity=_identity(), repo=tmp_path)


def test_the_answer_note_reports_delivery_and_is_silent_without_one(tmp_path: Path) -> None:
    assert answer_note(delivery=None) == ""

    note = answer_note(delivery=_delivery(answer="yes", repo=tmp_path))

    assert "the answer is on the ledger" in note


def test_the_action_id_round_trips_through_the_rendered_comment() -> None:
    """The reader is the writer's inverse, so drive it against the writer's own output.

    Reading the disposition back is what lets a `backlog` send-back be told
    apart from a `:ready` approval. A hand-written fixture would prove only
    that the parser matches THIS test's idea of the header; rendering it
    proves the pair cannot drift.
    """
    for disposition in ("ready", "backlog"):
        body = render_answer_comment(
            answer="Multi-line answers are ordinary.\nSecond line.",
            aid=f"resolve-blocked:bd-ib-x:{disposition}",
            identity=_identity(),
            at="2026-09-06T12:00:00Z",
        )

        assert answering_action_id(text=body) == f"resolve-blocked:bd-ib-x:{disposition}"


def test_a_comment_that_is_not_an_answer_names_no_action_id() -> None:
    assert answering_action_id(text="an ordinary operator rider") is None
    assert answering_action_id(text=f"A write-up quoting {ANSWER_COMMENT_MARKER} (a, b):") is None


def test_an_answer_whose_header_is_not_closed_names_no_action_id() -> None:
    """An unreadable header must not be salvaged into a disposition.

    A disposition this reader cannot read is one it must not treat as consent,
    so the whole comment reports as "not an answer I can speak for" rather
    than yielding whatever trailing text happened to be there.
    """
    truncated = f"{ANSWER_COMMENT_MARKER} (operator:cwoolley via flag, at, resolve-blocked:x:ready"

    assert answering_action_id(text=truncated) is None
