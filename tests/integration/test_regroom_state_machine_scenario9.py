"""Integration-tier acceptance for the `needs-regroom` state machine.

Binds SPECIFICATION/scenarios.md "Scenario 9 — needs-regroom state and
transitions" and the contracts.md clause:

    An item MUST enter `needs-regroom` on an intake Definition-of-Ready
    failure and MUST enter `needs-regroom` on a Dispatcher non-convergence
    bounce; groom approval MUST transition the `needs-regroom` item out by
    filing `ready` slices (the original item is regroomed-out, never silently
    dropped).

This is the top-of-pyramid behavior journey for the shared
`livespec_orchestrator_beads_fabro.regroom` primitive: it drives `enter` / `exit_regroom` /
`is_needs_regroom` through the REAL store/client seam against the in-memory
`FakeBeadsClient` — the same backend the hermetic CI tier and the
no-live-connection runtime use, and the same boundary every other test in this
repo mocks. The three Scenario-9 transitions are each a `Scenario:` block
below; the remaining cases pin the refuse-don't-drop guarantee and the
expected-error surface.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    _build_update_argv,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.errors import RegroomExitRefusedError, WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.regroom import (
    NEEDS_REGROOM_LABEL,
    READY_LABEL,
    enter,
    exit_regroom,
    is_needs_regroom,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
    """Reset the process-singleton fake tenant before and after each case.

    This directory has no shared conftest, so the test owns its backend
    isolation: every case starts against an empty in-memory tenant and the
    singleton is dropped afterwards so nothing leaks between cases.
    """
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


def _seed_issue(
    *,
    issue_id: str,
    labels: list[str] | None = None,
    status: str = "open",
) -> None:
    """Create an issue directly through the client seam (the test's `bd create`).

    The regroom primitive operates on already-filed items, so each case seeds
    the item(s) it acts on. `status` lets a case stage a closed slice to prove
    a closed replacement cannot satisfy the exit gate.
    """
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title=issue_id,
            description="",
            priority=2,
            assignee=None,
            created_at="2026-06-19T00:00:00Z",
            labels=list(labels) if labels is not None else [],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    if status != "open":
        client.update_issue(issue_id=issue_id, status=status)


# --------------------------------------------------------------------------
# Scenario: An intake Definition-of-Ready failure enters needs-regroom.
# --------------------------------------------------------------------------


def test_intake_dor_failure_enters_needs_regroom() -> None:
    _seed_issue(issue_id="li-epic")

    enter(path=_config(), item_id="li-epic")

    assert is_needs_regroom(path=_config(), item_id="li-epic") is True
    record = make_beads_client(config=_config()).show_issue(issue_id="li-epic")
    assert NEEDS_REGROOM_LABEL in record["labels"]


# --------------------------------------------------------------------------
# Scenario: A non-converging dispatched slice enters needs-regroom.
# --------------------------------------------------------------------------


def test_non_convergence_bounce_enters_needs_regroom() -> None:
    _seed_issue(issue_id="li-slice")

    # The Dispatcher non-convergence bounce drives the SAME entry verb as the
    # intake path — every path into the state is the one observable mutation.
    enter(path=_config(), item_id="li-slice")

    assert is_needs_regroom(path=_config(), item_id="li-slice") is True


def test_enter_is_idempotent() -> None:
    _seed_issue(issue_id="li-epic")
    enter(path=_config(), item_id="li-epic")
    enter(path=_config(), item_id="li-epic")
    record = make_beads_client(config=_config()).show_issue(issue_id="li-epic")
    assert record["labels"].count(NEEDS_REGROOM_LABEL) == 1


# --------------------------------------------------------------------------
# Scenario: A groomed-and-approved item transitions out of needs-regroom.
# --------------------------------------------------------------------------


def test_groom_approval_exits_needs_regroom_by_filing_ready_slices() -> None:
    _seed_issue(issue_id="li-epic")
    enter(path=_config(), item_id="li-epic")
    # Groom approval filed two `ready` replacement slices.
    _seed_issue(issue_id="li-slice-a", labels=[READY_LABEL])
    _seed_issue(issue_id="li-slice-b", labels=[READY_LABEL])

    exit_regroom(
        path=_config(),
        item_id="li-epic",
        ready_slice_ids=["li-slice-a", "li-slice-b"],
    )

    assert is_needs_regroom(path=_config(), item_id="li-epic") is False
    record = make_beads_client(config=_config()).show_issue(issue_id="li-epic")
    assert NEEDS_REGROOM_LABEL not in record["labels"]


# --------------------------------------------------------------------------
# Refuse-don't-drop: exit is refused unless real `ready` slices were filed.
# --------------------------------------------------------------------------


def test_exit_refused_when_no_replacement_slices_named() -> None:
    _seed_issue(issue_id="li-epic")
    enter(path=_config(), item_id="li-epic")

    with pytest.raises(RegroomExitRefusedError) as excinfo:
        exit_regroom(path=_config(), item_id="li-epic", ready_slice_ids=[])

    assert excinfo.value.item_id == "li-epic"
    # The label is untouched — the item is not silently dropped.
    assert is_needs_regroom(path=_config(), item_id="li-epic") is True


def test_exit_refused_when_named_slice_is_absent() -> None:
    _seed_issue(issue_id="li-epic")
    enter(path=_config(), item_id="li-epic")

    with pytest.raises(RegroomExitRefusedError) as excinfo:
        exit_regroom(path=_config(), item_id="li-epic", ready_slice_ids=["li-ghost"])

    assert "li-ghost" in excinfo.value.detail
    assert is_needs_regroom(path=_config(), item_id="li-epic") is True


def test_exit_refused_when_named_slice_is_not_ready_labelled() -> None:
    _seed_issue(issue_id="li-epic")
    enter(path=_config(), item_id="li-epic")
    # Filed, but never tagged `ready` (e.g. still needs-regroom itself).
    _seed_issue(issue_id="li-slice-a", labels=[])

    with pytest.raises(RegroomExitRefusedError):
        exit_regroom(path=_config(), item_id="li-epic", ready_slice_ids=["li-slice-a"])

    assert is_needs_regroom(path=_config(), item_id="li-epic") is True


def test_exit_refused_when_ready_slice_is_already_closed() -> None:
    _seed_issue(issue_id="li-epic")
    enter(path=_config(), item_id="li-epic")
    # Carries `ready` but is closed — a closed slice is not a live replacement.
    _seed_issue(issue_id="li-slice-a", labels=[READY_LABEL], status="closed")

    with pytest.raises(RegroomExitRefusedError):
        exit_regroom(path=_config(), item_id="li-epic", ready_slice_ids=["li-slice-a"])

    assert is_needs_regroom(path=_config(), item_id="li-epic") is True


# --------------------------------------------------------------------------
# Expected-error surface: transitions against a phantom id are surfaced.
# --------------------------------------------------------------------------


def test_enter_unknown_item_raises_not_found() -> None:
    with pytest.raises(WorkItemNotFoundError) as excinfo:
        enter(path=_config(), item_id="li-ghost")
    assert excinfo.value.item_id == "li-ghost"


def test_exit_unknown_item_raises_not_found() -> None:
    with pytest.raises(WorkItemNotFoundError):
        exit_regroom(path=_config(), item_id="li-ghost", ready_slice_ids=["li-x"])


def test_is_needs_regroom_unknown_item_raises_not_found() -> None:
    with pytest.raises(WorkItemNotFoundError):
        is_needs_regroom(path=_config(), item_id="li-ghost")


def test_is_needs_regroom_false_for_item_without_the_label() -> None:
    _seed_issue(issue_id="li-ready", labels=[READY_LABEL])
    assert is_needs_regroom(path=_config(), item_id="li-ready") is False


# --------------------------------------------------------------------------
# Seam coverage: the Shell `--remove-label` argv branch the exit path needs.
# --------------------------------------------------------------------------


def test_build_update_argv_emits_remove_label_flag() -> None:
    """The clear-label path maps to a repeated `--remove-label` flag (bd v1.0.5)."""
    argv = _build_update_argv(
        issue_id="li-a",
        status=None,
        parent_id=None,
        add_labels=None,
        metadata=None,
        remove_labels=[NEEDS_REGROOM_LABEL, "ready"],
    )
    assert argv.count("--remove-label") == 2
    assert NEEDS_REGROOM_LABEL in argv
    assert "ready" in argv


# --------------------------------------------------------------------------
# Fail-soft: a record whose `labels` is not a list reads as label-less rather
# than crashing the query — a malformed shape the fake's public surface never
# produces, so it is injected via a small read-only stub (the same technique
# `test_store.py` uses for its identical guard).
# --------------------------------------------------------------------------


class _NonListLabelsStub:
    """A read-only `BeadsClient` stand-in whose record carries non-list labels."""

    def exists(self, *, issue_id: str) -> bool:  # noqa: ARG002
        return True

    def show_issue(self, *, issue_id: str) -> dict[str, object]:
        return {"id": issue_id, "labels": "not-a-list"}


def test_is_needs_regroom_treats_non_list_labels_as_label_less(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _NonListLabelsStub()
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.regroom.make_beads_client",
        lambda *, config: stub,  # noqa: ARG005
    )
    assert is_needs_regroom(path=_config(), item_id="li-malformed") is False
