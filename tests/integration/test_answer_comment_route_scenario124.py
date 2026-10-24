"""Scenario 124 — the marked answer comment, written before the transition.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 124 — The human answer lands as a marked ledger comment before the
transition, and a poisoned answer is refused`. Its two gherkin scenarios are
the two cases below, driven through `drive.run_action` and the real store seam
against the in-memory `FakeBeadsClient`.

WHY THE CLEAN CASE OBSERVES THE WRITE SEQUENCE AND NOT ONLY THE END STATE. The
end state is the same for both orderings: a build that transitioned first and
commented second leaves a `ready` item carrying the identical comment. The
scenario's third `Then` is about the ORDER, and the order is only visible in
the writes — so a recording overlay on the fake's two write verbs DELEGATES to
the real implementations and records what each call carried. Nothing is
stubbed: removing the overlay changes no behaviour, only what is visible.

The order is load-bearing rather than tidy, which is why it is bound. A `ready`
item is selectable by `next` the instant the status write returns, so a
transition that ran first could be picked up and re-dispatched against a brief
that still lacked the answer — the exact miss this route exists to close.

WHY THE POISON CASE READS THE TENANT AND NOT THE PAYLOAD. "Refused with
nothing written" is a claim about what did not happen, and the refusal
dictionary cannot carry it: a build that wrote the comment and then refused
returns the same payload. The ledger's comment list and the item's status are
the only place the two builds differ.

The opening delimiter is built from its halves rather than written literally,
following this repository's convention for prose that discusses the token: a
ledger comment carrying one refuses every later dispatch of its item, so the
fleet keeps the literal pair out of text that merely talks about it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    fake_singleton,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_TENANT = "livespec-orchestrator-beads-fabro"
_PREFIX = "bd-ib"
_ITEM = "bd-ib-answered"
_ACTION = f"resolve-blocked:{_ITEM}:ready"
# A two-line answer, because the clause says the answer follows the marker line
# VERBATIM: a single-line answer cannot tell a verbatim copy from one the writer
# reflowed, and a reflow is what would silently drop an operator's structure.
_ANSWER = "Take option B.\nThe second provider stays out of scope for this slice."
_MARKER = "livespec-human-answer"
_EXPRESSION_OPENER = "{" + "{"
# The gate's own refusal code, spelled here rather than imported so this file
# keeps naming the record it means to read.
_POISON_REFUSED = "answer-would-poison-goal"
_OPERATOR = InvokerIdentity(invoker="human:chad", invoker_source="flag")
# The header's four fields, in the ratified order: the invoker, the source it
# was resolved from, the write instant, and the action id the press carried.
_HEADER = re.compile(
    rf"^{_MARKER} \((?P<invoker>[^ ]+) via (?P<source>[^,]+), "
    rf"(?P<at>[^,]+), (?P<aid>[^)]+)\):$"
)
_UTC_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True, kw_only=True)
class _Write:
    """One write the answer route made, and the status it requested if any.

    `status` is `None` for a write that requested none — every `add_comment`,
    and any `update_issue` reached for some other field — which is what lets
    the order assertion read the whole sequence rather than a filtered view of
    it.
    """

    verb: str
    issue_id: str
    status: str | None


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A fresh in-memory tenant per case, with the fake backend selected."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_scenario124_a_clean_answer_opens_with_the_marker_and_precedes_the_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given an operator presses resolve-blocked with an answer carrying no opener,
    When the press is applied,
    Then the comment opens with the livespec-human-answer marker line naming the
    invoker, its source, the write instant and the action id,
    And the operator's answer follows that line verbatim,
    And the comment is written before the item's status transition."""
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_parked())
    writes = _recorded_writes(monkeypatch=monkeypatch)

    result = run_action(repo=repo, action_id=_ACTION, answer=_ANSWER, identity=_OPERATOR)

    assert result["status"] == "green"
    assert result["target_status"] == "ready"
    # The ORDER, read off the writes: the comment, then the status transition,
    # with nothing between them and nothing else written at all.
    assert [(write.verb, write.status) for write in writes] == [
        ("add_comment", None),
        ("update_issue", "ready"),
    ]
    assert [write.issue_id for write in writes] == [_ITEM, _ITEM]

    marker_line, _, body = _comment_text(item_id=_ITEM).partition("\n")
    header = _HEADER.match(marker_line)

    assert header is not None
    assert header.group("invoker") == _OPERATOR.invoker
    assert header.group("source") == _OPERATOR.invoker_source
    assert _UTC_INSTANT.match(header.group("at")) is not None
    assert header.group("aid") == _ACTION
    # VERBATIM: byte-for-byte, newline included, with nothing appended.
    assert body == _ANSWER


def test_scenario124_a_poisoned_answer_is_refused_with_nothing_written_and_no_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given an operator presses resolve-blocked with an answer carrying an opener,
    When the press is evaluated,
    Then the answer is refused with nothing written,
    And the item stays blocked with no status transition.

    Read three ways, because each alone can pass a wrong build: the refusal
    payload names the cause, NO write of either verb was made, and the tenant
    still holds a `blocked` item with an empty comment list. A build that wrote
    the comment and refused afterwards fails the second and third; one that
    transitioned and refused fails them too.
    """
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_parked())
    writes = _recorded_writes(monkeypatch=monkeypatch)
    poisoned = f"Take option B, then render {_EXPRESSION_OPENER} item.id }}}} in the brief."

    result = run_action(repo=repo, action_id=_ACTION, answer=poisoned, identity=_OPERATOR)

    assert result["status"] == "failed"
    assert result["domain_error"] == _POISON_REFUSED
    assert _EXPRESSION_OPENER in str(result["summary"])
    assert writes == []
    stored = materialize_work_items(records=read_work_items(path=_config()))[_ITEM]
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")
    assert list(fake_singleton().list_comments(issue_id=_ITEM)) == []


def _recorded_writes(*, monkeypatch: pytest.MonkeyPatch) -> list[_Write]:
    """Record the route's comment and status writes, delegating to the real verbs.

    The overlay is installed on the CLASS rather than on an instance because
    the store resolves its own client through `make_beads_client` per call, so
    there is no instance for a test to hand it one.

    EVERY call of either verb is recorded, unfiltered. A recorder that kept only
    the status-bearing `update_issue` calls would read the same way on a build
    that slipped an unrelated write between the comment and the transition,
    which is the one thing a sequence assertion is for; recording all of them
    makes "exactly these two writes, in this order" the claim.
    """
    writes: list[_Write] = []
    add_comment = FakeBeadsClient.add_comment
    update_issue = FakeBeadsClient.update_issue

    def recording_add_comment(self: FakeBeadsClient, *, issue_id: str, body: str) -> None:
        writes.append(_Write(verb="add_comment", issue_id=issue_id, status=None))
        add_comment(self, issue_id=issue_id, body=body)

    def recording_update_issue(
        self: FakeBeadsClient,
        *,
        issue_id: str,
        status: str | None = None,
        **rest: Any,
    ) -> None:
        writes.append(_Write(verb="update_issue", issue_id=issue_id, status=status))
        update_issue(self, issue_id=issue_id, status=status, **rest)

    monkeypatch.setattr(FakeBeadsClient, "add_comment", recording_add_comment)
    monkeypatch.setattr(FakeBeadsClient, "update_issue", recording_update_issue)
    return writes


def _comment_text(*, item_id: str) -> str:
    """The one ledger comment this item carries, read off `text`.

    `text` is the key beads returns, and `body` is the one this repository's
    agent instructions record two sessions reaching for: it yields an empty
    string per comment, which is the identical observation to a lost write.
    """
    comments = list(fake_singleton().list_comments(issue_id=item_id))
    assert len(comments) == 1
    return str(comments[0]["text"])


def _parked() -> WorkItem:
    """A work-item resting at `blocked` with `blocked_reason: needs-human`."""
    return WorkItem(
        id=_ITEM,
        type="task",
        status="blocked",
        title="Parked on a question",
        description="It could not be finished without a decision.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )


def _repo(*, tmp_path: Path) -> Path:
    """A governed clone with no configured disposition — the documented default.

    `human` is what an absent `answer_disposition` key resolves to, so an
    operator's press is admitted here on the ordinary fleet configuration
    rather than on one this case arranged.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"' + _PLUGIN_BLOCK + '": {"connection": {"prefix": "' + _PREFIX + '"}}}',
        encoding="utf-8",
    )
    return repo


def _config() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )
