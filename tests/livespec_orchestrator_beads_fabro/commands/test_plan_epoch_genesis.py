"""Who may start a chain, and why nobody else may.

A transition is made safe by closing the CURRENT token, so the FIRST token has
no predecessor to close and cannot be created by an exclusion. Relay research
note 007 measured why a deterministic "create if absent" cannot stand in: a
duplicate explicit-id create is an upsert that REOPENS a closed record and
erases its close reason, exiting 0 with no warning.

So genesis happens only where one writer can exist — `create_thread`, whose
epic id no other party has yet seen, and the sanctioned plan-record migration,
a deliberate once-per-epic operator act. This module covers the primitive both
call: its refusal when a chain already stands, and the read-back that narrows
two operators migrating one epic at the same moment.

The two finding codes are spelled out here rather than imported because this
module's Red predates the constants it binds; `test_the_findings_name_both_
genesis_refusals` is what ties the literals to the exported names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_epoch_findings, _plan_epoch_genesis
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import ChainFinding
from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import create_genesis_token
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    ChainCache,
    read_chain_cache,
    write_chain_cache,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

_EPIC_ID = "bd-ib-relay1"
_GENESIS_ALREADY_NAMED = "plan-epoch-chain: genesis-already-named"
_GENESIS_UNCONFIRMED = "plan-epoch-chain: genesis-unconfirmed"


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


def _seed_epic() -> FakeBeadsClient:
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
            metadata={"rank": "a0", "plan_slug": "relay-delivery-and-progress-deadline"},
        )
    )
    return fake


def _cache() -> ChainCache | None:
    metadata = _fake().show_issue(issue_id=_EPIC_ID)["metadata"]
    assert isinstance(metadata, dict)
    return read_chain_cache(metadata=metadata)


def test_the_findings_name_both_genesis_refusals() -> None:
    """Each refusal has its own name because each has its own remedy.

    An epic that already names a chain needs nothing done; an unconfirmed
    write needs the epic re-read before anyone migrates it again. Reporting
    either as the other sends an operator to the wrong repair.
    """
    assert getattr(_plan_epoch_findings, "GENESIS_ALREADY_NAMED", None) == _GENESIS_ALREADY_NAMED
    assert getattr(_plan_epoch_findings, "GENESIS_UNCONFIRMED", None) == _GENESIS_UNCONFIRMED


def test_genesis_creates_one_token_and_records_it_as_the_chain_start() -> None:
    """The epic's chain begins at epoch 0 with nothing committed."""
    _ = _seed_epic()

    created = create_genesis_token(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(created, str)
    assert _fake().no_history_issue_ids() == (created,)
    assert _cache() == ChainCache(latest_closed=None, current=created)
    head = read_chain_head(config=_config(), epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead)
    assert head.current_token_id == created
    assert head.epoch == 0
    assert head.winning_operation_id is None
    # The epic's other metadata is untouched: `bd update --metadata` replaces a
    # nested object wholesale but merges at the top level, so a genesis write
    # that rebuilt the metadata would drop the plan's own keys.
    metadata = _fake().show_issue(issue_id=_EPIC_ID)["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["plan_slug"] == "relay-delivery-and-progress-deadline"
    assert metadata["rank"] == "a0"


def test_genesis_refuses_an_epic_that_already_names_a_chain() -> None:
    """A second genesis would give one epic two chains.

    A chain is an exclusion only while every writer closes the SAME token, so
    two chains on one epic admit two simultaneous winners — the exact failure
    the design exists to prevent. The refusal writes nothing, which is what
    makes a mistaken second migration harmless.
    """
    _ = _seed_epic()
    first = create_genesis_token(config=_config(), epic_id=_EPIC_ID)
    assert isinstance(first, str)

    refusal = create_genesis_token(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(refusal, ChainFinding)
    assert refusal.code == _GENESIS_ALREADY_NAMED
    assert first in refusal.detail
    assert _fake().no_history_issue_ids() == (first,)
    assert _cache() == ChainCache(latest_closed=None, current=first)


def test_genesis_reads_its_own_write_back_and_cleans_up_when_it_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two operators migrating one epic at once is the residual risk here.

    The read-back narrows it: a genesis whose cache write did not survive
    reports that it is unconfirmed and DELETES the token it created, so the
    epic is left naming exactly one chain rather than carrying an orphan token
    that some later reader might follow. The competing operator's write is
    injected at the cache write, which is the one instant the two can collide.
    """
    fake = _seed_epic()
    competing = create_token(client=fake)

    def _overwritten_by_a_competing_operator(
        *,
        client: BeadsClient,
        epic_id: str,
        latest_closed: str | None,
        current: str,
    ) -> None:
        _ = current
        write_chain_cache(
            client=client,
            epic_id=epic_id,
            latest_closed=latest_closed,
            current=competing,
        )

    monkeypatch.setattr(
        _plan_epoch_genesis,
        "write_chain_cache",
        _overwritten_by_a_competing_operator,
    )
    outcome = create_genesis_token(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(outcome, ChainFinding)
    assert outcome.code == _GENESIS_UNCONFIRMED
    assert competing in outcome.detail
    assert _fake().no_history_issue_ids() == (competing,)
    assert _cache() == ChainCache(latest_closed=None, current=competing)
