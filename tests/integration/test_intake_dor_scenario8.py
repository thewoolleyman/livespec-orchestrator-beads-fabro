"""Integration-tier acceptance for the intake Definition-of-Ready checklist.

Binds SPECIFICATION/scenarios.md "Scenario 8 — Intake Definition-of-Ready
triage" and the contracts.md §"Gap-detectable behavior clauses" clause:

    The `capture-work-item` and `capture-impl-gaps` capture front-ends
    MUST run the intake Definition-of-Ready checklist over the six gates
    at capture and MUST tag the resulting item `ready`, `needs-regroom`,
    or `not-yet-actionable` accordingly — a single-coherent-done,
    autonomously-verifiable, autonomy-tiered, dependency-linked,
    repo-targeted, above-floor item is tagged `ready`; an item with more
    than one coherent "done" (an epic) MUST be tagged `needs-regroom`; an
    item whose acceptance is not autonomously verifiable, or that has
    unresolved blockers, MUST be tagged `not-yet-actionable` and MUST NOT
    be filed as `ready`.

This is the top-of-pyramid behavior journey for the shared
`livespec_impl_beads.intake_dor` primitive that both capture
front-ends call: it drives `evaluate` / `apply_intake_dor` through the
REAL store/client seam against the in-memory `FakeBeadsClient` — the same
backend the hermetic CI tier and the no-live-connection runtime use, and
the same boundary every other test in this repo mocks. The three
Scenario-8 cases are each a `Scenario:` block below; the remaining cases
pin the precedence, the per-gate coverage, and the expected-error surface.
"""

from __future__ import annotations

import pytest
from livespec_impl_beads._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_impl_beads.errors import WorkItemNotFoundError
from livespec_impl_beads.intake_dor import (
    NOT_YET_ACTIONABLE_LABEL,
    READY_LABEL,
    DefinitionOfReadyChecklist,
    apply_intake_dor,
    evaluate,
)
from livespec_impl_beads.regroom import NEEDS_REGROOM_LABEL, is_needs_regroom
from livespec_impl_beads.types import StoreConfig


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


def _seed_issue(*, issue_id: str) -> None:
    """Create an issue directly through the client seam (the capture front-end's filing).

    The intake checklist stamps a verdict on an ALREADY-filed item, so each
    case seeds the item the front-end just filed, then runs `apply_intake_dor`.
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
            labels=[],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )


def _labels_of(*, issue_id: str) -> list[str]:
    record = make_beads_client(config=_config()).show_issue(issue_id=issue_id)
    raw = record["labels"]
    assert isinstance(raw, list)
    return [label for label in raw if isinstance(label, str)]


def _ready_checklist() -> DefinitionOfReadyChecklist:
    """All six gates passing — the canonical `ready` shape."""
    return DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )


# --------------------------------------------------------------------------
# Scenario: A single-acceptance item is tagged ready.
# --------------------------------------------------------------------------


def test_single_acceptance_item_is_tagged_ready() -> None:
    _seed_issue(issue_id="li-ready")

    verdict = apply_intake_dor(path=_config(), item_id="li-ready", checklist=_ready_checklist())

    assert verdict == "ready"
    labels = _labels_of(issue_id="li-ready")
    assert READY_LABEL in labels
    assert NEEDS_REGROOM_LABEL not in labels
    assert NOT_YET_ACTIONABLE_LABEL not in labels


# --------------------------------------------------------------------------
# Scenario: An epic is tagged needs-regroom.
# --------------------------------------------------------------------------


def test_epic_is_tagged_needs_regroom() -> None:
    _seed_issue(issue_id="li-epic")

    verdict = apply_intake_dor(
        path=_config(),
        item_id="li-epic",
        # More than one coherent "done" — an epic.
        checklist=DefinitionOfReadyChecklist(
            single_coherent_done=False,
            autonomously_verifiable=True,
            autonomy_tiered=True,
            dependency_linked=True,
            repo_targeted=True,
            above_floor=True,
        ),
    )

    assert verdict == "needs-regroom"
    # Entry is via the SHARED regroom.enter verb — the `needs-regroom` label.
    assert is_needs_regroom(path=_config(), item_id="li-epic") is True
    labels = _labels_of(issue_id="li-epic")
    assert NEEDS_REGROOM_LABEL in labels
    assert READY_LABEL not in labels


# --------------------------------------------------------------------------
# Scenario: A non-autonomously-verifiable or blocked item is not-yet-actionable.
# --------------------------------------------------------------------------


def test_non_autonomously_verifiable_item_is_not_yet_actionable() -> None:
    _seed_issue(issue_id="li-judgement")

    verdict = apply_intake_dor(
        path=_config(),
        item_id="li-judgement",
        # Acceptance needs a human judgement call.
        checklist=DefinitionOfReadyChecklist(
            single_coherent_done=True,
            autonomously_verifiable=False,
            autonomy_tiered=True,
            dependency_linked=True,
            repo_targeted=True,
            above_floor=True,
        ),
    )

    assert verdict == "not-yet-actionable"
    labels = _labels_of(issue_id="li-judgement")
    assert NOT_YET_ACTIONABLE_LABEL in labels
    # The hard invariant: a not-yet-actionable item is NEVER filed `ready`.
    assert READY_LABEL not in labels


def test_blocked_item_is_not_yet_actionable() -> None:
    _seed_issue(issue_id="li-blocked")

    verdict = apply_intake_dor(
        path=_config(),
        item_id="li-blocked",
        # Has an unresolved blocker (dependencies not linked).
        checklist=DefinitionOfReadyChecklist(
            single_coherent_done=True,
            autonomously_verifiable=True,
            autonomy_tiered=True,
            dependency_linked=False,
            repo_targeted=True,
            above_floor=True,
        ),
    )

    assert verdict == "not-yet-actionable"
    assert NOT_YET_ACTIONABLE_LABEL in _labels_of(issue_id="li-blocked")
    assert READY_LABEL not in _labels_of(issue_id="li-blocked")


# --------------------------------------------------------------------------
# Pure-verdict precedence + per-gate coverage (the `evaluate` function).
# --------------------------------------------------------------------------


def test_evaluate_all_gates_pass_is_ready() -> None:
    assert evaluate(checklist=_ready_checklist()) == "ready"


@pytest.mark.parametrize(
    ("gate", "expected"),
    [
        # An epic short-circuits to needs-regroom even if other gates also fail.
        ("single_coherent_done", "needs-regroom"),
        # Each remaining ready-gate failure, on its own, blocks `ready`.
        ("autonomously_verifiable", "not-yet-actionable"),
        ("dependency_linked", "not-yet-actionable"),
        ("autonomy_tiered", "not-yet-actionable"),
        ("repo_targeted", "not-yet-actionable"),
        ("above_floor", "not-yet-actionable"),
    ],
)
def test_evaluate_each_failing_gate_blocks_ready(gate: str, expected: str) -> None:
    """No single gate failure ever yields `ready`; the contract names the bucket."""
    from dataclasses import replace

    checklist = replace(_ready_checklist(), **{gate: False})
    assert evaluate(checklist=checklist) == expected


def test_evaluate_epic_precedes_not_yet_actionable() -> None:
    """An epic that is ALSO non-verifiable surfaces for grooming, not as blocked."""
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=False,
        autonomously_verifiable=False,
        autonomy_tiered=False,
        dependency_linked=False,
        repo_targeted=False,
        above_floor=False,
    )
    assert evaluate(checklist=checklist) == "needs-regroom"


# --------------------------------------------------------------------------
# Expected-error surface: stamping a phantom id is surfaced, not silent.
# --------------------------------------------------------------------------


def test_apply_intake_dor_unknown_item_raises_not_found() -> None:
    with pytest.raises(WorkItemNotFoundError) as excinfo:
        apply_intake_dor(path=_config(), item_id="li-ghost", checklist=_ready_checklist())
    assert excinfo.value.item_id == "li-ghost"
