"""Integration-tier acceptance for the intake Definition-of-Ready checklist.

Binds SPECIFICATION/scenarios.md "Scenario 8 — Intake Definition-of-Ready
triage" and the contracts.md clause:

    The `capture-work-item` and `capture-impl-gaps` capture front-ends
    MUST run the intake Definition-of-Ready checklist over the six gates
    at capture and MUST route the resulting item into its lifecycle state
    accordingly — a single-coherent-done, autonomously-verifiable,
    autonomy-tiered, dependency-linked, repo-targeted, above-floor item
    lands in `pending-approval` (approved on into `ready` when its
    effective `admission_policy` is `auto`); an item with more than one
    coherent "done" (an epic) MUST land in `backlog`; an item whose
    acceptance is not autonomously verifiable MUST land in `blocked` with
    `blocked_reason: needs-human`; an item with unresolved blockers is
    filed with its dependency edges linked and MUST NOT land directly in
    `ready`.

This is the top-of-pyramid behavior journey for the shared
`livespec_orchestrator_beads_fabro.intake_dor` primitive that both capture
front-ends call: it drives `evaluate` / `apply_intake_dor` through the
REAL store/client seam against the in-memory `FakeBeadsClient` — the same
backend the hermetic CI tier and the no-live-connection runtime use, and
the same boundary every other test in this repo mocks. The three
Scenario-8 cases are each a `Scenario:` block below; the remaining cases
pin the precedence, the per-gate coverage, and the expected-error surface.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
    evaluate,
)
from livespec_orchestrator_beads_fabro.store import (
    INTAKE_TRIAGED_LABEL,
    materialize_work_items,
    read_intake_triage_records,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


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


def _config(*, repo_root: Path | None = None) -> StoreConfig:
    """A hermetic connection descriptor — `fake=True` selects the in-memory backend."""
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _seed_issue(
    *, issue_id: str, labels: list[str] | None = None, spec_id: str | None = None
) -> None:
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
            labels=list(labels) if labels is not None else [],
            metadata={},
            spec_id=spec_id,
            parent_id=None,
        )
    )


def _item(*, issue_id: str) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[issue_id]


def _write_dispatcher_config(*, repo_root: Path, setting: str) -> None:
    _ = (repo_root / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {' + setting + "}}}",
        encoding="utf-8",
    )


def _link_dependency(*, item_id: str, blocker_id: str) -> None:
    make_beads_client(config=_config()).add_dependency(
        from_id=item_id,
        to_id=blocker_id,
        edge_type=EDGE_BLOCKS,
    )


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
# Scenario: A single-acceptance item lands pending-approval.
# --------------------------------------------------------------------------


def test_single_acceptance_item_lands_pending_approval(tmp_path: Path) -> None:
    _seed_issue(issue_id="li-pending")

    verdict = apply_intake_dor(
        path=_config(repo_root=tmp_path), item_id="li-pending", checklist=_ready_checklist()
    )

    assert verdict == "pending-approval"
    item = _item(issue_id="li-pending")
    assert item.status == "pending-approval"
    assert item.blocked_reason is None


def test_pending_item_without_repo_root_fails_loudly() -> None:
    _seed_issue(issue_id="li-no-root")

    with pytest.raises(TypeError, match="repo_root is required"):
        apply_intake_dor(path=_config(), item_id="li-no-root", checklist=_ready_checklist())


def test_auto_admission_single_acceptance_item_lands_ready(tmp_path: Path) -> None:
    _seed_issue(issue_id="li-ready", labels=["admission:auto"])

    verdict = apply_intake_dor(
        path=_config(repo_root=tmp_path), item_id="li-ready", checklist=_ready_checklist()
    )

    assert verdict == "ready"
    assert _item(issue_id="li-ready").status == "ready"


def test_global_auto_approve_single_acceptance_item_lands_ready(tmp_path: Path) -> None:
    _write_dispatcher_config(repo_root=tmp_path, setting='"auto_approve_ready": true')
    _seed_issue(issue_id="li-global-ready")

    verdict = apply_intake_dor(
        path=_config(repo_root=tmp_path),
        item_id="li-global-ready",
        checklist=_ready_checklist(),
    )

    assert verdict == "ready"
    assert _item(issue_id="li-global-ready").status == "ready"


def test_manual_label_holds_pending_despite_global_auto_approve(tmp_path: Path) -> None:
    _write_dispatcher_config(repo_root=tmp_path, setting='"auto_approve_ready": true')
    _seed_issue(issue_id="li-manual", labels=["admission:manual"])

    verdict = apply_intake_dor(
        path=_config(repo_root=tmp_path), item_id="li-manual", checklist=_ready_checklist()
    )

    assert verdict == "pending-approval"
    assert _item(issue_id="li-manual").status == "pending-approval"


def test_spec_change_tier_holds_pending_despite_auto_label_and_global_auto(
    tmp_path: Path,
) -> None:
    _write_dispatcher_config(repo_root=tmp_path, setting='"auto_approve_ready": true')
    _seed_issue(issue_id="li-spec", labels=["admission:auto"], spec_id="SC-1")

    verdict = apply_intake_dor(
        path=_config(repo_root=tmp_path), item_id="li-spec", checklist=_ready_checklist()
    )

    assert verdict == "pending-approval"
    assert _item(issue_id="li-spec").status == "pending-approval"


# --------------------------------------------------------------------------
# Scenario: An epic lands backlog.
# --------------------------------------------------------------------------


def test_epic_lands_backlog() -> None:
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

    assert verdict == "backlog"
    assert _item(issue_id="li-epic").status == "backlog"


# --------------------------------------------------------------------------
# Scenario: A non-autonomously-verifiable item is blocked for human input.
# --------------------------------------------------------------------------


def test_non_autonomously_verifiable_item_is_blocked_needs_human() -> None:
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

    assert verdict == "blocked"
    item = _item(issue_id="li-judgement")
    assert item.status == "blocked"
    assert item.blocked_reason == "needs-human"


def test_linked_dependency_item_keeps_edges_and_does_not_land_ready() -> None:
    _seed_issue(issue_id="li-blocker")
    _seed_issue(issue_id="li-dependent", labels=["admission:auto"])
    _link_dependency(item_id="li-dependent", blocker_id="li-blocker")

    verdict = apply_intake_dor(
        path=_config(),
        item_id="li-dependent",
        # The blocker is unresolved, but its dependency edge is linked.
        checklist=_ready_checklist(),
    )

    item = _item(issue_id="li-dependent")
    assert verdict == "pending-approval"
    assert item.status == "pending-approval"
    assert item.depends_on == ({"kind": "local", "work_item_id": "li-blocker"},)


# --------------------------------------------------------------------------
# The triage marker: stamped for EVERY verdict, so "the gate saw this item"
# is observable — the discriminator a `backlog` item otherwise lacks.
# --------------------------------------------------------------------------


def _triaged(*, issue_id: str) -> bool:
    records = {record.id: record for record in read_intake_triage_records(path=_config())}
    return records[issue_id].triaged


@pytest.mark.parametrize(
    ("issue_id", "checklist", "expected_status"),
    [
        ("li-mark-pending", _ready_checklist(), "pending-approval"),
        (
            "li-mark-backlog",
            replace(_ready_checklist(), single_coherent_done=False),
            "backlog",
        ),
        (
            "li-mark-blocked",
            replace(_ready_checklist(), autonomously_verifiable=False),
            "blocked",
        ),
    ],
)
def test_every_verdict_stamps_the_intake_triage_marker(
    issue_id: str,
    checklist: DefinitionOfReadyChecklist,
    expected_status: str,
    tmp_path: Path,
) -> None:
    """Routing an item — anywhere — records that the gate ran on it.

    The `backlog` row is the load-bearing one (livespec-h95t): without the
    marker, an epic the gate deliberately parked is indistinguishable from an
    item filed with a raw `bd create` that will never move, because both sit
    in `backlog`, both are refused by dispatch, and neither was reported.
    """
    _seed_issue(issue_id=issue_id)

    verdict = apply_intake_dor(
        path=_config(repo_root=tmp_path), item_id=issue_id, checklist=checklist
    )

    assert verdict == expected_status
    assert _triaged(issue_id=issue_id)


def test_auto_admitted_ready_item_is_also_marked_triaged(tmp_path: Path) -> None:
    """The onward `ready` approval keeps the marker rather than dropping it."""
    _seed_issue(issue_id="li-mark-ready", labels=["admission:auto"])

    verdict = apply_intake_dor(
        path=_config(repo_root=tmp_path), item_id="li-mark-ready", checklist=_ready_checklist()
    )

    assert verdict == "ready"
    assert _triaged(issue_id="li-mark-ready")


def test_a_raw_created_item_the_gate_never_saw_carries_no_marker() -> None:
    """The complement: filing outside the gate leaves the item unmarked.

    `_seed_issue` is the raw `bd create` path — no `apply_intake_dor` call —
    which is exactly how an agent or script files today. The absence of the
    marker is what the un-triaged-backlog attention lane keys on.
    """
    _seed_issue(issue_id="li-never-gated")

    assert not _triaged(issue_id="li-never-gated")
    assert INTAKE_TRIAGED_LABEL == "intake:triaged"


# --------------------------------------------------------------------------
# Pure-verdict precedence + per-gate coverage (the `evaluate` function).
# --------------------------------------------------------------------------


def test_evaluate_all_gates_pass_is_ready() -> None:
    assert evaluate(checklist=_ready_checklist()) == "pending-approval"


@pytest.mark.parametrize(
    ("gate", "expected"),
    [
        # An epic short-circuits to backlog even if other gates also fail.
        ("single_coherent_done", "backlog"),
        # Each remaining ready-gate failure, on its own, blocks `ready`.
        ("autonomously_verifiable", "blocked"),
        ("dependency_linked", "blocked"),
        ("autonomy_tiered", "blocked"),
        ("repo_targeted", "blocked"),
        ("above_floor", "blocked"),
    ],
)
def test_evaluate_each_failing_gate_blocks_ready(gate: str, expected: str) -> None:
    """No single gate failure ever yields `ready`; the contract names the bucket."""
    checklist = replace(_ready_checklist(), **{gate: False})
    assert evaluate(checklist=checklist) == expected


def test_evaluate_epic_precedes_blocked() -> None:
    """An epic that is ALSO non-verifiable surfaces for decomposition, not as blocked."""
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=False,
        autonomously_verifiable=False,
        autonomy_tiered=False,
        dependency_linked=False,
        repo_targeted=False,
        above_floor=False,
    )
    assert evaluate(checklist=checklist) == "backlog"


# --------------------------------------------------------------------------
# Expected-error surface: stamping a phantom id is surfaced, not silent.
# --------------------------------------------------------------------------


def test_apply_intake_dor_unknown_item_raises_not_found() -> None:
    with pytest.raises(WorkItemNotFoundError) as excinfo:
        apply_intake_dor(path=_config(), item_id="li-ghost", checklist=_ready_checklist())
    assert excinfo.value.item_id == "li-ghost"
