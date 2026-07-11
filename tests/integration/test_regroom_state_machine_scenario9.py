"""Integration-tier acceptance for backlog-based groom target disposition.

Binds SPECIFICATION/scenarios.md "Scenario 9" and the contracts.md clause:

    An item MUST enter `backlog` on an intake Definition-of-Ready epic failure
    and MUST enter `backlog` on a Dispatcher non-convergence bounce; groom
    approval MUST transition the `backlog` item out by filing `ready` slices
    (the original item is regroomed-out, never silently dropped).

The seven-state lifecycle has no separate regroom label or status. These tests
drive the `livespec_orchestrator_beads_fabro.regroom` helper through the real
store/client seam against the in-memory FakeBeadsClient.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro import regroom
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._beads_client_argv import build_update_argv
from livespec_orchestrator_beads_fabro.errors import (
    GroomExitRefusedError,
    GroomTargetNotBacklogError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.regroom import close_regroomed_out, require_backlog_target
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
    """Reset the process-singleton fake tenant before and after each case."""
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    """A hermetic connection descriptor — `fake=True` selects the in-memory backend."""
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed_issue(*, issue_id: str, status: str) -> None:
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="epic",
            title=issue_id,
            description="",
            priority=2,
            assignee=None,
            created_at="2026-06-19T00:00:00Z",
            labels=[],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    client.update_issue(issue_id=issue_id, status=status)


def _item_status(*, issue_id: str) -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[issue_id].status


# --------------------------------------------------------------------------
# Scenario: backlog is the regroom target state.
# --------------------------------------------------------------------------


def test_backlog_item_is_a_valid_groom_target() -> None:
    _seed_issue(issue_id="li-epic", status="backlog")

    require_backlog_target(path=_config(), item_id="li-epic")


def test_ready_item_is_not_a_valid_groom_target() -> None:
    _seed_issue(issue_id="li-ready", status="ready")

    with pytest.raises(GroomTargetNotBacklogError) as excinfo:
        require_backlog_target(path=_config(), item_id="li-ready")

    assert excinfo.value.item_id == "li-ready"


def test_unknown_groom_target_raises_not_found() -> None:
    with pytest.raises(WorkItemNotFoundError):
        require_backlog_target(path=_config(), item_id="li-ghost")


# --------------------------------------------------------------------------
# Scenario: groom approval explicitly disposes the original backlog item.
# --------------------------------------------------------------------------


def test_close_regroomed_out_closes_backlog_item_with_replacement_reason() -> None:
    _seed_issue(issue_id="li-epic", status="backlog")

    close_regroomed_out(
        path=_config(),
        item_id="li-epic",
        replacement_slice_ids=["li-slice-a", "li-slice-b"],
    )

    item = materialize_work_items(records=read_work_items(path=_config()))["li-epic"]
    assert item.status == "done"
    assert item.resolution == "no-longer-applicable"
    assert item.reason == "regroomed out into replacement slices: li-slice-a, li-slice-b"


def test_close_regroomed_out_refuses_empty_replacements_and_leaves_backlog() -> None:
    _seed_issue(issue_id="li-epic", status="backlog")

    with pytest.raises(GroomExitRefusedError) as excinfo:
        close_regroomed_out(path=_config(), item_id="li-epic", replacement_slice_ids=[])

    assert excinfo.value.item_id == "li-epic"
    assert _item_status(issue_id="li-epic") == "backlog"


def test_close_regroomed_out_refuses_non_backlog_original() -> None:
    _seed_issue(issue_id="li-ready", status="ready")

    with pytest.raises(GroomTargetNotBacklogError):
        close_regroomed_out(path=_config(), item_id="li-ready", replacement_slice_ids=["li-slice"])


def test_retired_label_state_machine_surface_is_not_exported() -> None:
    assert not hasattr(regroom, "enter")
    assert not hasattr(regroom, "exit_regroom")
    assert not hasattr(regroom, "is_needs_regroom")
    assert not hasattr(regroom, "READY_LABEL")
    assert not hasattr(regroom, "NEEDS_REGROOM_LABEL")


# --------------------------------------------------------------------------
# Seam coverage: lifecycle routing still uses the Shell `--remove-label` branch.
# --------------------------------------------------------------------------


def test_build_update_argv_emits_remove_label_flag_for_lifecycle_cleanup() -> None:
    argv = build_update_argv(
        issue_id="li-a",
        status=None,
        parent_id=None,
        add_labels=None,
        metadata=None,
        remove_labels=["blocked-reason:needs-human", "not-yet-actionable"],
    )

    assert argv.count("--remove-label") == 2
    assert "blocked-reason:needs-human" in argv
    assert "not-yet-actionable" in argv
