"""The genesis outcome a competing operator cannot produce: a vanished write.

`create_genesis_token`'s read-back has two failing shapes, and they are not
interchangeable. A RIVAL token standing in the cache is another operator's
successful migration, and the epic is migrated. NO chain at all is a cache
write that went missing, and the epic still owes a genesis. Only the first is
reachable by racing two operators, so the second gets its own case here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_epoch_genesis
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    GENESIS_UNCONFIRMED,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import create_genesis_token
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

_EPIC_ID = "bd-ib-relay1"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def test_a_genesis_whose_cache_write_vanished_reports_it_and_leaves_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write that silently did nothing must not read as a chain that stands.

    The token is deleted either way, because an orphan nothing names is worse
    than none: it is invisible to every list surface, so nothing would ever
    reconcile it.
    """
    reset_fake_singleton()
    fake = _fake()
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC_ID,
            issue_type="epic",
            title="plan",
            description="anchor",
            assignee=None,
            created_at="2026-10-12T08:00:00Z",
            metadata={"rank": "a0"},
        )
    )

    def _write_nothing(
        *,
        client: BeadsClient,
        epic_id: str,
        latest_closed: str | None,
        current: str,
    ) -> None:
        _ = (client, epic_id, latest_closed, current)

    monkeypatch.setattr(_plan_epoch_genesis, "write_chain_cache", _write_nothing)
    outcome = create_genesis_token(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(outcome, ChainFinding)
    assert outcome.code == GENESIS_UNCONFIRMED
    assert "no chain at all" in outcome.detail
    assert _fake().no_history_issue_ids() == ()
