"""The token record seam: server-assigned creates, verdict-free closes, reads back."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    TOKEN_DESCRIPTION,
    TOKEN_TITLE,
    attempt_close,
    create_token,
    delete_token,
    discard_token,
    token_reading,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError, BeadsMappingError


def test_a_created_token_is_open_and_invisible_to_the_list_surfaces() -> None:
    fake = FakeBeadsClient()

    token = create_token(client=fake)

    reading = token_reading(client=fake, token_id=token)
    assert reading.present is True
    assert reading.closed is False
    assert reading.close_reason is None
    assert fake.list_issues() == []
    assert fake.show_issue(issue_id=token)["title"] == TOKEN_TITLE
    assert "Not a work item" in TOKEN_DESCRIPTION


def test_two_creates_never_share_an_id() -> None:
    """Nothing derives a token id, so no later create can land on an existing one."""
    fake = FakeBeadsClient()

    assert create_token(client=fake) != create_token(client=fake)


def test_a_close_is_conditional_and_the_reading_is_the_only_verdict() -> None:
    fake = FakeBeadsClient()
    token = create_token(client=fake)

    attempt_close(client=fake, token_id=token, reason="winner")
    attempt_close(client=fake, token_id=token, reason="loser")

    reading = token_reading(client=fake, token_id=token)
    assert reading.closed is True
    assert reading.close_reason == "winner"


def test_reading_an_absent_token_reports_absence_rather_than_raising() -> None:
    """A deleted predecessor is an ordinary state of a chain that has moved on."""
    fake = FakeBeadsClient()
    absent = "wisp-gone"

    reading = token_reading(client=fake, token_id=absent)

    assert reading.present is False
    assert reading.closed is False
    assert reading.close_reason is None


def test_a_non_string_close_reason_reads_as_no_reason() -> None:
    """A record whose reason is not text carries no readable transition."""
    fake = FakeBeadsClient()
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id="li-odd",
            issue_type="task",
            title="t",
            description="d",
            assignee=None,
            created_at="2026-10-12T00:00:00Z",
        )
    )
    fake.update_issue(issue_id="li-odd", status="closed")
    odd = "li-odd"

    reading = token_reading(client=fake, token_id=odd)

    assert reading.closed is True
    assert reading.close_reason is None


def test_delete_token_raises_on_an_absent_record_and_discard_does_not() -> None:
    """The two differ ON PURPOSE, and the difference is where each is called.

    `discard_token` runs after a transition has already committed, where a
    concurrent reconciler may have removed the same predecessor; failing a
    durable transition there would turn a benign outcome into a refusal.
    """
    fake = FakeBeadsClient()
    token = create_token(client=fake)

    delete_token(client=fake, token_id=token)

    assert fake.no_history_issue_ids() == ()
    with pytest.raises(BeadsMappingError):
        delete_token(client=fake, token_id=token)
    discard_token(client=fake, token_id=token)


def test_discard_token_also_tolerates_a_command_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delete that failed leaves an invisible record, never an unfinished transition."""
    client = FakeBeadsClient()
    token = create_token(client=client)

    def _refuse(*, issue_id: str) -> None:
        raise BeadsCommandError(command=f"delete {issue_id}", exit_code=1, stderr="refused")

    monkeypatch.setattr(client, "delete_issue", _refuse)
    discard_token(client=client, token_id=token)

    assert client.no_history_issue_ids() == (token,)
