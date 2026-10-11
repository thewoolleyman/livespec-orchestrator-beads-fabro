"""The shared pre-claim refusal wall and credential-bound derivation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    WorkflowFaultDeferral,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure
from livespec_orchestrator_beads_fabro.errors import ConnectionPrefixMissingError
from livespec_orchestrator_beads_fabro.types import WorkItem


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


class _CapResult:
    def __init__(self, *, value: int | None) -> None:
        self.value = value

    def value_or(self, default: int) -> int:
        return default if self.value is None else self.value


def _item(*, item_id: str = "bd-ib-wall") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title=item_id,
        description="wall fixture",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _args() -> argparse.Namespace:
    return argparse.Namespace(workflow_name=None, workflow=None)


def _green_dependencies(*, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    reclaimed: list[str] = []
    monkeypatch.setattr(wall, "implementation_pr_override_refusal", lambda **_: None)
    monkeypatch.setattr(wall, "pre_dispatch_criteria_refusal", lambda **_: None)
    monkeypatch.setattr(wall, "proof_assets_refusal_for_items", lambda **_: None)
    monkeypatch.setattr(wall, "proof_credentials_refusal_for_items", lambda **_: None)
    monkeypatch.setattr(wall, "credential_wrapper_text", lambda **_: "wrapper")
    monkeypatch.setattr(wall, "selection_credential_requirement", lambda **_: "requirement")
    monkeypatch.setattr(wall, "codex_credential_refusal_for_items", lambda **_: None)
    monkeypatch.setattr(
        wall,
        "reclaim_stale_publish_branches",
        lambda **_: reclaimed.append("reclaimed"),
    )
    monkeypatch.setattr(wall, "write_stderr", lambda **_: None)
    return reclaimed


@pytest.mark.parametrize(
    ("dependency", "expected"),
    [
        ("implementation_pr_override_refusal", EXIT_PRECONDITION_ERROR),
        ("pre_dispatch_criteria_refusal", EXIT_UNGRADEABLE_CRITERIA),
        ("proof_assets_refusal_for_items", EXIT_PRECONDITION_ERROR),
        ("proof_credentials_refusal_for_items", EXIT_PRECONDITION_ERROR),
        ("codex_credential_refusal_for_items", EXIT_PRECONDITION_ERROR),
    ],
)
def test_each_refusal_returns_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dependency: str,
    expected: int,
) -> None:
    reclaimed = _green_dependencies(monkeypatch=monkeypatch)
    journal = _Journal()

    def refuse(**kwargs: object) -> str:
        if dependency == "implementation_pr_override_refusal":
            assert kwargs["journal"] is journal
            journal.append(record={"stage": dependency})
        return f"{dependency} refused"

    monkeypatch.setattr(wall, dependency, refuse)
    result = wall.pre_dispatch_wall_exit(
        args=_args(),
        repo=tmp_path,
        items=(_item(),),
        journal=journal,
    )
    assert result == expected
    assert reclaimed == []
    assert journal.records == (
        [{"stage": dependency}] if dependency == "implementation_pr_override_refusal" else []
    )


def test_success_reclaims_only_for_a_fresh_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reclaimed = _green_dependencies(monkeypatch=monkeypatch)
    assert (
        wall.pre_dispatch_wall_exit(
            args=_args(),
            repo=tmp_path,
            items=(_item(),),
            journal=_Journal(),
        )
        is None
    )
    assert reclaimed == ["reclaimed"]
    assert (
        wall.pre_dispatch_wall_exit(
            args=_args(),
            repo=tmp_path,
            items=(_item(),),
            journal=_Journal(),
            reclaim_publish_branches=False,
        )
        is None
    )
    assert reclaimed == ["reclaimed"]


def test_workflow_fault_defers_the_codex_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _green_dependencies(monkeypatch=monkeypatch)
    monkeypatch.setattr(
        wall,
        "selection_credential_requirement",
        lambda **_: WorkflowFaultDeferral(message="owned later"),
    )
    called: list[str] = []
    monkeypatch.setattr(
        wall,
        "codex_credential_refusal_for_items",
        lambda **_: called.append("codex"),
    )
    assert (
        wall.pre_dispatch_wall_exit(
            args=_args(),
            repo=tmp_path,
            items=(_item(),),
            journal=_Journal(),
        )
        is None
    )
    assert called == []


def test_selection_requirement_uses_the_widest_effective_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(wall, "attempt", lambda **_: ("review-fix-cap:9",))
    monkeypatch.setattr(
        wall,
        "effective_review_fix_cap",
        lambda **_: _CapResult(value=9),
    )
    monkeypatch.setattr(wall, "unsafe_perform_io", lambda value: value)
    monkeypatch.setattr(
        wall,
        "effective_policy_inputs",
        lambda *, review_fix_cap: {"cap": review_fix_cap},
    )

    def resolve(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "resolved"

    monkeypatch.setattr(wall, "resolve_credential_lifetime_requirement", resolve)
    args = argparse.Namespace(workflow="custom.toml", workflow_name="named")
    assert (
        wall.selection_credential_requirement(
            args=args,
            repo=tmp_path,
            items=(_item(),),
        )
        == "resolved"
    )
    assert captured == {
        "repo": tmp_path,
        "workflow_override": "custom.toml",
        "workflow_name": "named",
        "policy_inputs": {"cap": 9},
    }
    assert (
        wall.selection_credential_requirement(
            args=argparse.Namespace(),
            repo=tmp_path,
            items=(),
        )
        == "resolved"
    )


def test_widest_cap_and_label_failure_degrade_to_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wall, "effective_policy_inputs", lambda *, review_fix_cap: review_fix_cap)
    monkeypatch.setattr(
        wall,
        "resolve_credential_lifetime_requirement",
        lambda *, policy_inputs, **_: policy_inputs,
    )
    monkeypatch.setattr(wall, "unsafe_perform_io", lambda value: value)
    assert (
        wall.selection_credential_requirement(args=argparse.Namespace(), repo=tmp_path, items=())
        == wall.DEFAULT_REVIEW_FIX_CAP
    )
    monkeypatch.setattr(
        wall,
        "attempt",
        lambda **_: AttemptFailure(error=ConnectionPrefixMissingError()),
    )
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        wall,
        "effective_review_fix_cap",
        lambda *, raw_labels, **_: seen.append(raw_labels) or _CapResult(value=None),
    )
    assert (
        wall.selection_credential_requirement(
            args=argparse.Namespace(), repo=tmp_path, items=(_item(),)
        )
        == wall.DEFAULT_REVIEW_FIX_CAP
    )
    monkeypatch.setattr(wall, "attempt", lambda **_: "unreadable")
    assert (
        wall.selection_credential_requirement(
            args=argparse.Namespace(), repo=tmp_path, items=(_item(),)
        )
        == wall.DEFAULT_REVIEW_FIX_CAP
    )
    monkeypatch.setattr(wall, "attempt", lambda **_: ("review-fix-cap:8",))
    monkeypatch.setattr(
        wall,
        "effective_review_fix_cap",
        lambda *, raw_labels, **_: seen.append(raw_labels) or _CapResult(value=8),
    )
    assert (
        wall.selection_credential_requirement(
            args=argparse.Namespace(), repo=tmp_path, items=(_item(),)
        )
        == 8
    )
    assert seen == [(), (), ("review-fix-cap:8",)]
