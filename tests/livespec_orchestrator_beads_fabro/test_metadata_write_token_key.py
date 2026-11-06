"""A metadata write outside the claim-token protocol never carries the token key.

`SPECIFICATION/contracts.md`, "Dispatcher policy settings", the "Claim tokens"
bullet: an item names its current token in its metadata, and only a write of
that protocol may change the name. Every other metadata writer sends "the
whole object I read a moment ago, plus my key", and `bd update --metadata`
merges top-level keys, so a payload that carried the token id as of the
writer's own read would put an OLD token back after a claim writer had moved
it on.

Each case here runs against one tenant that answers two questions at once:
what the in-memory tenant holds after the write, and what argv the shell
client builds for that same write. The first is the outcome; the second is
what a real `bd` would have been sent.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro import _beads_client
from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsRecord,
    FakeBeadsClient,
    IssueDraft,
    ShellBeadsClient,
)
from livespec_orchestrator_beads_fabro._store_claim_token_migration import migrate_claim_tokens
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    change_claim,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import (
    dispatch_workflow_from_record,
    record_dispatch_workflow,
)
from livespec_orchestrator_beads_fabro._store_mutations import update_work_item_rank
from livespec_orchestrator_beads_fabro.store import read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ITEM_ID = "bd-ib-token-key"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


class _RecordingShell(ShellBeadsClient):
    """The shell client, recording each write's argv instead of running `bd`."""

    def __init__(self) -> None:
        super().__init__(config=_config())
        self.writes: list[list[str]] = []

    def _run_void(self, *, verb_args: list[str]) -> None:
        self.writes.append(verb_args)

    def sent_metadata(self) -> dict[str, Any]:
        """Return the `--metadata` object of the latest write."""
        argv = self.writes[-1]
        return json.loads(argv[argv.index("--metadata") + 1])


class _Tenant(FakeBeadsClient):
    """The in-memory tenant, which also hands every update to the shell client."""

    def __init__(self) -> None:
        super().__init__()
        self.shell = _RecordingShell()

    def update_issue(self, **fields: Any) -> None:
        self.shell.update_issue(**fields)
        super().update_issue(**fields)


def _empty_tenant(*, monkeypatch: pytest.MonkeyPatch) -> _Tenant:
    """Return the tenant every store call of this test reaches."""
    tenant = _Tenant()
    monkeypatch.setattr(_beads_client, "fake_singleton", lambda: tenant)
    return tenant


def _create_item(*, tenant: _Tenant, metadata: dict[str, Any]) -> None:
    _ = tenant.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="task",
            title="A ready slice",
            description="Implement the slice.",
            assignee=None,
            created_at="2026-11-06T00:00:00Z",
            metadata=metadata,
        )
    )


def _tenant(*, monkeypatch: pytest.MonkeyPatch, metadata: dict[str, Any]) -> _Tenant:
    tenant = _empty_tenant(monkeypatch=monkeypatch)
    _create_item(tenant=tenant, metadata=metadata)
    return tenant


def _tenant_naming_a_token(*, monkeypatch: pytest.MonkeyPatch) -> _Tenant:
    """Return a tenant whose item was CREATED naming an open token, with no update involved."""
    tenant = _empty_tenant(monkeypatch=monkeypatch)
    token = create_claim_token(client=tenant)
    _create_item(tenant=tenant, metadata={"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token})
    return tenant


def _move_token(*, tenant: _Tenant) -> str:
    """Win the item's current token through the protocol; return its successor."""
    outcome = change_claim(
        client=tenant,
        work_item_id=_ITEM_ID,
        writer="admission",
        intent="move-ready-to-active",
        claim_tokens=True,
        status="active",
    )
    assert outcome.outcome == "applied"
    assert outcome.successor_token_id is not None
    return outcome.successor_token_id


def _move_token_after_the_next_read(
    *, tenant: _Tenant, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    """Let the next reader see the item, then move its token before that reader writes."""
    successors: list[str] = []
    read = tenant.show_issue

    def _read_then_move(*, issue_id: str) -> BeadsRecord:
        record = read(issue_id=issue_id)
        monkeypatch.setattr(tenant, "show_issue", read)
        successors.append(_move_token(tenant=tenant))
        return record

    monkeypatch.setattr(tenant, "show_issue", _read_then_move)
    return successors


def _metadata(*, tenant: _Tenant) -> dict[str, Any]:
    return tenant.show_issue(issue_id=_ITEM_ID)["metadata"]


def test_a_stale_whole_object_write_cannot_put_an_old_token_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant_naming_a_token(monkeypatch=monkeypatch)
    read_before_the_move = _metadata(tenant=tenant)
    successor = _move_token(tenant=tenant)

    tenant.update_issue(
        issue_id=_ITEM_ID,
        metadata={**read_before_the_move, "factory_safety_recorded_at": "2026-11-06T00:00:00Z"},
    )

    assert read_before_the_move[CLAIM_TOKEN_METADATA_KEY] != successor
    assert _metadata(tenant=tenant) == {
        "rank": "a0",
        "factory_safety_recorded_at": "2026-11-06T00:00:00Z",
        CLAIM_TOKEN_METADATA_KEY: successor,
    }
    assert tenant.shell.sent_metadata() == {
        "rank": "a0",
        "factory_safety_recorded_at": "2026-11-06T00:00:00Z",
    }


def test_a_workflow_pin_racing_a_claim_write_leaves_the_new_token_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant_naming_a_token(monkeypatch=monkeypatch)
    successors = _move_token_after_the_next_read(tenant=tenant, monkeypatch=monkeypatch)

    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow="implement-fast")

    [successor] = successors
    item = tenant.show_issue(issue_id=_ITEM_ID)
    assert item["metadata"][CLAIM_TOKEN_METADATA_KEY] == successor
    assert dispatch_workflow_from_record(record=item) == "implement-fast"
    assert item["status"] == "active"
    assert CLAIM_TOKEN_METADATA_KEY not in tenant.shell.sent_metadata()


def test_a_rank_rekey_racing_a_claim_write_leaves_the_new_token_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant_naming_a_token(monkeypatch=monkeypatch)
    [projection] = list(read_work_items(path=_config()))
    successors = _move_token_after_the_next_read(tenant=tenant, monkeypatch=monkeypatch)

    update_work_item_rank(path=_config(), item=replace(projection, rank="a8"))

    [successor] = successors
    assert _metadata(tenant=tenant) == {"rank": "a8", CLAIM_TOKEN_METADATA_KEY: successor}
    assert tenant.shell.sent_metadata() == {"rank": "a8"}


def test_a_write_outside_the_protocol_cannot_name_a_token_on_an_item_that_names_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant(monkeypatch=monkeypatch, metadata={"rank": "a0"})

    tenant.update_issue(
        issue_id=_ITEM_ID, metadata={"rank": "a8", CLAIM_TOKEN_METADATA_KEY: "fake-wisp-9"}
    )

    assert _metadata(tenant=tenant) == {"rank": "a8"}
    assert tenant.shell.sent_metadata() == {"rank": "a8"}


def test_metadata_naming_no_token_is_sent_exactly_as_the_caller_built_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant(monkeypatch=monkeypatch, metadata={"rank": "a0"})
    payload = {"rank": "a8", "audit": {"commits": ["c1"], "merge_sha": "m1"}}

    tenant.update_issue(issue_id=_ITEM_ID, metadata=payload)

    assert tenant.shell.sent_metadata() == payload
    assert _metadata(tenant=tenant) == payload


def test_the_in_memory_tenant_merges_top_level_keys_and_replaces_a_nested_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant(
        monkeypatch=monkeypatch,
        metadata={
            "rank": "a0",
            "dispatch_workflow": "implement-fast",
            "audit": {"commits": ["c1"], "merge_sha": "m1"},
        },
    )

    tenant.update_issue(issue_id=_ITEM_ID, metadata={"rank": "a8", "audit": {"commits": ["c2"]}})

    assert _metadata(tenant=tenant) == {
        "rank": "a8",
        "dispatch_workflow": "implement-fast",
        "audit": {"commits": ["c2"]},
    }


def test_a_won_claim_write_names_its_successor_in_the_tenant_and_in_the_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant_naming_a_token(monkeypatch=monkeypatch)

    successor = _move_token(tenant=tenant)

    assert tenant.shell.sent_metadata() == {"rank": "a0", CLAIM_TOKEN_METADATA_KEY: successor}
    assert _metadata(tenant=tenant) == {"rank": "a0", CLAIM_TOKEN_METADATA_KEY: successor}


def test_the_migration_pass_names_its_fresh_token_in_the_tenant_and_in_the_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant(monkeypatch=monkeypatch, metadata={"rank": "a0"})

    report = migrate_claim_tokens(client=tenant, apply=True)

    [(item_id, token)] = report.named
    assert item_id == _ITEM_ID
    assert tenant.shell.sent_metadata() == {"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token}
    assert _metadata(tenant=tenant) == {"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token}
    assert tenant.show_issue(issue_id=token)["status"] != "closed"
