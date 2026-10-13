"""Every chain finding names what it observed AND a remedy somebody can take."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    CHAIN_FORK,
    CHAIN_UNREADABLE,
    GENESIS_ALREADY_NAMED,
    GENESIS_UNCONFIRMED,
    MISSING_TRACKING,
    PARTIAL_WRITE,
    RECEIPT_WITHOUT_EVENT,
    chain_fork_finding,
    chain_unreadable_finding,
    genesis_already_named_finding,
    genesis_unconfirmed_finding,
    missing_tracking_finding,
    partial_write_finding,
    receipt_without_event_finding,
)


def test_the_missing_tracking_finding_names_the_migration_that_creates_a_genesis() -> None:
    """No other writer may create one, so the remedy has to name the migration.

    A finding whose remedy read "create the chain" would invite the very write
    the design forbids: two writers minting their own genesis tokens give one
    epic two chains, and a chain is an exclusion only while every writer closes
    the same token.
    """
    finding = missing_tracking_finding(epic_id="bd-ib-relay1")

    assert finding.code == MISSING_TRACKING
    assert "bd-ib-relay1" in finding.detail
    assert "legacy pointer" in finding.detail
    assert "migration" in finding.remedy


def test_the_fork_finding_names_both_the_claimed_and_the_walked_predecessor() -> None:
    forked = "wisp-4"
    finding = chain_fork_finding(
        epic_id="bd-ib-relay1",
        token_id=forked,
        claimed_prior="wisp-2",
        walked_from=forked,
    )

    assert finding.code == CHAIN_FORK
    assert forked in finding.detail
    assert "wisp-2" in finding.detail
    assert "before any further transition or dispatch" in finding.remedy


def test_the_unreadable_finding_names_where_the_walk_stopped() -> None:
    stopped = "wisp-7"
    finding = chain_unreadable_finding(
        epic_id="bd-ib-relay1",
        token_id=stopped,
        detail="the token record could not be read",
    )

    assert finding.code == CHAIN_UNREADABLE
    assert stopped in finding.detail
    assert "could not be read" in finding.detail
    assert finding.remedy != ""


def test_the_partial_write_finding_withholds_the_dispatch_in_its_remedy() -> None:
    finding = partial_write_finding(epic_id="bd-ib-relay1", detail="the cache names wisp-2")

    assert finding.code == PARTIAL_WRITE
    assert finding.detail == "bd-ib-relay1: the cache names wisp-2"
    assert "before authorizing a dispatch" in finding.remedy


def test_the_receipt_without_event_finding_refuses_to_invent_the_original() -> None:
    finding = receipt_without_event_finding(epic_id="bd-ib-relay1", operation_id="op-3")

    assert finding.code == RECEIPT_WITHOUT_EVENT
    assert "op-3" in finding.detail
    assert "receipt" in finding.detail
    assert "recover" in finding.remedy


def test_every_finding_code_is_distinct() -> None:
    """A shared code would make two conditions with different remedies one fact."""
    codes = (
        MISSING_TRACKING,
        CHAIN_FORK,
        CHAIN_UNREADABLE,
        PARTIAL_WRITE,
        RECEIPT_WITHOUT_EVENT,
        GENESIS_ALREADY_NAMED,
        GENESIS_UNCONFIRMED,
    )

    assert len(set(codes)) == len(codes)


def test_the_genesis_already_named_finding_asks_for_nothing_to_be_done() -> None:
    """Its remedy is deliberately empty of repair work.

    A second migration of an already-migrated epic is an ordinary operator
    mistake. A remedy that asked for a repair would invite the very second
    chain the refusal had just prevented.
    """
    standing = "wisp-1"
    finding = genesis_already_named_finding(epic_id="bd-ib-relay1", token_id=standing)

    assert finding.code == GENESIS_ALREADY_NAMED
    assert standing in finding.detail
    assert "no genesis was created" in finding.detail
    assert "nothing to do" in finding.remedy


def test_the_genesis_unconfirmed_finding_names_what_stands_instead() -> None:
    """Both outcomes are reported, because they mean different things.

    A rival token standing in the cache is another operator's successful
    migration; no chain at all is a cache write that went missing, and only
    the second leaves the epic still owing a genesis.
    """
    lost = "wisp-mine"
    overwritten = genesis_unconfirmed_finding(
        epic_id="bd-ib-relay1",
        token_id=lost,
        observed="wisp-theirs",
    )
    vanished = genesis_unconfirmed_finding(epic_id="bd-ib-relay1", token_id=lost, observed=None)

    assert overwritten.code == GENESIS_UNCONFIRMED == vanished.code
    assert "wisp-theirs" in overwritten.detail
    assert "no chain at all" in vanished.detail
    assert lost in overwritten.detail
    assert lost in vanished.detail
    assert "re-read the epic" in vanished.remedy
