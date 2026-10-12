"""Every chain finding names what it observed AND a remedy somebody can take."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    CHAIN_FORK,
    CHAIN_UNREADABLE,
    MISSING_TRACKING,
    PARTIAL_WRITE,
    RECEIPT_WITHOUT_EVENT,
    chain_fork_finding,
    chain_unreadable_finding,
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
    codes = (MISSING_TRACKING, CHAIN_FORK, CHAIN_UNREADABLE, PARTIAL_WRITE, RECEIPT_WITHOUT_EVENT)

    assert len(set(codes)) == len(codes)
