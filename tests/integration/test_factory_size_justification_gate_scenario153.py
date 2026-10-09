"""Scenario 153: adopted assertion ceilings and attributed exceptions.

This integration journey binds the size gate through the same shared decision
that capture, groom, approval, and factory dispatch consume.  Store-facing
cases use the real in-memory beads seam; only processes outside the repository
are stood in.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    api_configurable_key_manifest,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io


def _item(*, assertion_count: int, item_id: str = "bd-size") -> WorkItem:
    bullets = "\n".join(
        f"- The product satisfies assertion {index}." for index in range(assertion_count)
    )
    return WorkItem(
        id=item_id,
        type="feature",
        status="ready",
        title="Factory size gate",
        description=(
            "## Definition of Done\n\n"
            f"{bullets}\n\n"
            "References: ## Scenario 153 — An adopted assertion ceiling requires "
            "an attributed exception without waiving other gates\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _size_gate_module() -> Any:
    return import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate")


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _ready_checklist() -> DefinitionOfReadyChecklist:
    return DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )


def _seed_capture(*, config: StoreConfig, item_id: str) -> None:
    client = make_beads_client(config=config)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="feature",
            title="Factory size gate",
            description=_item(assertion_count=1, item_id=item_id).description,
            priority=2,
            assignee=None,
            created_at="2026-10-09T00:00:00Z",
            labels=["admission:auto"],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    client.update_issue(issue_id=item_id, status="backlog")


def test_absent_ceiling_leaves_every_entry_path_on_ordinary_admission() -> None:
    """No adopted ceiling means justification presence has no gate effect."""
    module = _size_gate_module()
    valid = {
        "rationale": "This slice is cohesive despite its assertion count.",
        "author": "human:maintainer",
        "at": "2026-10-09T00:00:00Z",
    }

    decisions = [
        cast(
            "Any",
            module.factory_size_decision(
                item=_item(assertion_count=4, item_id=f"bd-{surface}-{variant}"),
                adopted_ceiling=None,
                raw_justification=raw,
            ),
        )
        for surface in ("capture", "groom", "approval", "dispatch")
        for variant, raw in (("missing", None), ("present", valid))
    ]

    assert [decision.disposition for decision in decisions] == ["proceed"] * 8
    assert all(decision.adopted_ceiling is None for decision in decisions)
    assert all(decision.assertion_count == 4 for decision in decisions)
    assert all(decision.reason is None for decision in decisions)
    assert all(decision.size_justified is False for decision in decisions)


def test_invalid_adopted_ceiling_refuses_before_lifecycle_mutation(tmp_path: Path) -> None:
    """Every non-positive or non-integer configured value fails closed."""
    invalid_values: tuple[object, ...] = (0, -1, True, False, 1.5, "3")

    for index, value in enumerate(invalid_values):
        reset_fake_singleton()
        repo = tmp_path / str(index)
        repo.mkdir()
        (repo / ".livespec.jsonc").write_text(
            json.dumps(
                {
                    "livespec-orchestrator-beads-fabro": {
                        "dispatcher": {"adopted_assertion_count_ceiling": value}
                    }
                }
            ),
            encoding="utf-8",
        )
        config = _config(repo_root=repo)
        item_id = f"bd-invalid-{index}"
        _seed_capture(config=config, item_id=item_id)

        result = apply_intake_dor(
            path=config,
            item_id=item_id,
            checklist=_ready_checklist(),
        )

        assert not is_successful(result)
        failure = unsafe_perform_io(result.failure())
        assert failure.setting == "adopted_assertion_count_ceiling"
        assert "positive integer" in failure.detail
        assert make_beads_client(config=config).show_issue(issue_id=item_id)["status"] == "backlog"

    manifest_keys = {
        entry["key"]
        for entry in cast("list[dict[str, object]]", api_configurable_key_manifest()["keys"])
    }
    assert "adopted_assertion_count_ceiling" not in manifest_keys
