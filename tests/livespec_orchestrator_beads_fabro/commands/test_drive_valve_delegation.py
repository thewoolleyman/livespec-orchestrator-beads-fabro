"""The delegated valve authority verifier: its fail-closed edges and its ledger record."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    DelegationGrant,
    InvokerIdentity,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_delegation import (
    DELEGABLE_VALVES,
    record_delegated_press,
    verify_delegation,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_DELEGATE = InvokerIdentity(invoker="delegate:coordinator", invoker_source="flag")
_ACTION = "approve:bd-ib-x"
_GRANT = {"ref": "R1", "delegate": "coordinator", "grantor": "human:pat", "record": "epic e @ t"}


def _repo(*, tmp_path: Path, delegations: object, raw: str | None = None) -> Path:
    text = raw
    if text is None:
        block = {"dispatcher": {"valve_delegations": delegations}}
        text = json.dumps({"livespec-orchestrator-beads-fabro": block})
    _ = (tmp_path / ".livespec.jsonc").write_text(text, encoding="utf-8")
    return tmp_path


def test_the_allowlist_is_exactly_the_five_delegable_valves() -> None:
    assert sorted(DELEGABLE_VALVES) == [
        "accept",
        "approve",
        "reject",
        "release-spec-tier",
        "resolve-blocked",
    ]


def test_an_undelegated_press_passes_through_with_its_own_identity(tmp_path: Path) -> None:
    identity = InvokerIdentity(invoker="human:pat", invoker_source="flag")

    verdict = verify_delegation(
        repo=tmp_path, action_id=_ACTION, identity=identity, delegation="  "
    )

    assert verdict.refusal is None
    assert verdict.identity is identity


def test_a_verified_press_carries_the_committed_grant(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path, delegations=[_GRANT])

    verdict = verify_delegation(repo=repo, action_id=_ACTION, identity=_DELEGATE, delegation="R1")

    assert verdict.identity is not None
    assert verdict.identity.delegation == DelegationGrant(
        ref="R1", grantor="human:pat", record="epic e @ t"
    )


def test_a_delegate_role_with_no_name_is_not_a_delegated_role(tmp_path: Path) -> None:
    identity = InvokerIdentity(invoker="delegate:", invoker_source="flag")

    verdict = verify_delegation(
        repo=tmp_path, action_id=_ACTION, identity=identity, delegation="R1"
    )

    assert verdict.refusal is not None
    assert verdict.refusal["domain_error"] == "delegation-incomplete"


def test_a_malformed_action_id_is_not_delegable(tmp_path: Path) -> None:
    verdict = verify_delegation(
        repo=tmp_path, action_id="approve", identity=_DELEGATE, delegation="R1"
    )

    assert verdict.refusal is not None
    assert verdict.refusal["domain_error"] == "delegation-not-permitted"


@pytest.mark.parametrize(
    ("delegations", "raw"),
    [
        ({"ref": "R1"}, None),
        (["not-an-object"], None),
        ([{**_GRANT, "grantor": "human:"}], None),
        ([{**_GRANT, "record": ""}], None),
        (None, "{ not jsonc"),
    ],
)
def test_an_unreadable_setting_verifies_no_press(
    tmp_path: Path, delegations: object, raw: str | None
) -> None:
    repo = _repo(tmp_path=tmp_path, delegations=delegations, raw=raw)

    verdict = verify_delegation(repo=repo, action_id=_ACTION, identity=_DELEGATE, delegation="R1")

    assert verdict.identity is None
    assert verdict.refusal is not None
    assert verdict.refusal["domain_error"] == "delegation-unverified"
    assert "unreadable" in str(verdict.refusal["summary"])


def test_an_absent_setting_verifies_no_press(tmp_path: Path) -> None:
    verdict = verify_delegation(
        repo=tmp_path, action_id=_ACTION, identity=_DELEGATE, delegation="R1"
    )

    assert verdict.refusal is not None
    assert "no committed dispatcher.valve_delegations entry carries ref R1" in str(
        verdict.refusal["summary"]
    )


def test_a_refused_or_undelegated_result_is_recorded_nowhere() -> None:
    config = StoreConfig(
        tenant="t", prefix="bd-ib", server_user="t", database="t", bd_path="bd", fake=True
    )
    refused = {"status": "failed", "work_item_ref": "bd-ib-x"}
    granted = InvokerIdentity(
        invoker="delegate:coordinator",
        invoker_source="flag",
        delegation=DelegationGrant(ref="R1", grantor="human:pat", record="r"),
    )

    assert record_delegated_press(config=config, identity=granted, result=refused) is refused
    green = {"status": "green", "work_item_ref": "bd-ib-x"}
    assert record_delegated_press(config=config, identity=_DELEGATE, result=green) is green
