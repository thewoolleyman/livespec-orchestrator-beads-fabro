"""Scenario 28 — `append_work_item` lands a custom status in two steps.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 28 — append_work_item registers and lands a custom status in two
steps`: `bd create` cannot land directly in one of the tenant's five custom
livespec statuses, so a filing is a CREATE that lands the beads-native `open`
followed by an UPDATE that sets the real lifecycle status.

The filing is driven through the REAL store seam against the in-memory
`FakeBeadsClient`, the hermetic backend the rest of this directory uses, and
the tenant is provisioned first through the store's own
`register_custom_statuses` — the scenario's `Given`.

WHY THIS CASE OBSERVES THE SEQUENCE AND NOT ONLY THE END STATE. The end state
is already bound by
`tests/livespec_orchestrator_beads_fabro/test_store_mutations.py::test_append_lands_custom_status_via_two_step`,
and it is the same for both shapes: a one-step create that landed `backlog`
directly would leave a record indistinguishable from the one the two-step path
leaves. The scenario's two `Then` clauses are about the WRITES, so the writes
are what this case reads — through a recording overlay on the fake's two write
verbs that DELEGATES to the real implementations and records what each call
landed. Nothing is stubbed: the store seam, the mutation module and the tenant
are the production ones, and removing the overlay changes no behaviour, only
what is visible.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    register_custom_statuses,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_TENANT = "livespec-orchestrator-beads-fabro"
_PREFIX = "bd-ib"
_ITEM_ID = "bd-ib-two-step"
# The beads-native status every `bd create` lands in, custom registration
# notwithstanding — the whole reason the second write exists.
_NATIVE_CREATE_STATUS = "open"
# The custom livespec status this filing's initial state names.
_CUSTOM_BACKLOG_STATUS = "backlog"


@dataclass(frozen=True, kw_only=True)
class _Write:
    """One write the store made, and the status the tenant held after it."""

    verb: str
    issue_id: str
    requested_status: str | None
    landed_status: str | None


@pytest.fixture(autouse=True)
def _hermetic() -> Iterator[None]:
    """Drive the store onto the in-memory tenant, isolated per case."""
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_scenario28_a_file_create_lands_open_then_updates_to_the_custom_backlog_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given a tenant with the 5 custom statuses registered,
    When `append_work_item` files a new item whose initial state is backlog,
    Then `bd create` lands the issue with status open,
    And `bd update` sets the issue status to the custom backlog status."""
    register_custom_statuses(path=_config())
    assert _fake().custom_statuses_registered is True
    writes = _recorded_writes(monkeypatch=monkeypatch)

    append_work_item(path=_config(), item=_backlog_item())

    assert [write.verb for write in writes] == ["create", "update"]
    create, update = writes
    assert create.issue_id == _ITEM_ID
    # The create could not carry the custom status, so it landed the native one.
    assert create.landed_status == _NATIVE_CREATE_STATUS
    assert update.issue_id == _ITEM_ID
    assert update.requested_status == _CUSTOM_BACKLOG_STATUS
    assert update.landed_status == _CUSTOM_BACKLOG_STATUS
    assert _fake().show_issue(issue_id=_ITEM_ID)["status"] == _CUSTOM_BACKLOG_STATUS


def _recorded_writes(*, monkeypatch: pytest.MonkeyPatch) -> list[_Write]:
    """Record every create/update the store makes, delegating to the real verbs.

    The overlay is installed on the CLASS rather than on an instance because
    the store resolves its own client through `make_beads_client` per call, so
    there is no instance for a test to hand it one.
    """
    writes: list[_Write] = []
    create_issue = FakeBeadsClient.create_issue
    update_issue = FakeBeadsClient.update_issue

    def recording_create(self: FakeBeadsClient, *, draft: IssueDraft) -> str:
        issue_id = create_issue(self, draft=draft)
        writes.append(
            _Write(
                verb="create",
                issue_id=issue_id,
                requested_status=None,
                landed_status=_status_of(client=self, issue_id=issue_id),
            )
        )
        return issue_id

    def recording_update(
        self: FakeBeadsClient,
        *,
        issue_id: str,
        status: str | None = None,
        **rest: Any,
    ) -> None:
        update_issue(self, issue_id=issue_id, status=status, **rest)
        writes.append(
            _Write(
                verb="update",
                issue_id=issue_id,
                requested_status=status,
                landed_status=_status_of(client=self, issue_id=issue_id),
            )
        )

    monkeypatch.setattr(FakeBeadsClient, "create_issue", recording_create)
    monkeypatch.setattr(FakeBeadsClient, "update_issue", recording_update)
    return writes


def _status_of(*, client: FakeBeadsClient, issue_id: str) -> str | None:
    status: str | None = client.show_issue(issue_id=issue_id).get("status")
    return status


def _backlog_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=_CUSTOM_BACKLOG_STATUS,
        title="A newly filed item whose initial state is backlog",
        description="Filed to observe the two-step custom-status write.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client
