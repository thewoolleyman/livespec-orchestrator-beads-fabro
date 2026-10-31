"""A resume refusal on an `active` item names a remedy that changes that item.

Scenario 221 of `SPECIFICATION/scenarios.md`, and the first refusal bullet of
`contracts.md` section "Resume from a published pull request (`resume --item`)":
the named remedy "MUST be one that changes that item's state; a refusal MUST NOT
name a remedy that would leave the item unchanged."

THE DEFECT IS A REMEDY THAT CANNOT FIRE. `reconcile-runs` releases a stranded
claim whose run FAILED or is absent, and holds one whose run SUCCEEDED
(`run-succeeded`), so an operator told to run it for a succeeded run's claim
runs a valve that reports `reconciled: []` and leaves the item exactly as it was.
Measured 2026-10-16 on `bd-ib-3hpdvm` and again 2026-10-29 on `bd-ib-sufca7`.

EVERY CASE HAS A CONTROL THAT RETURNS THE OTHER ANSWER. The default observation
keeps naming `reconcile-runs`, so a ladder that had simply stopped naming it for
every `active` item could not satisfy the control; and the open and merged
pull-request cases are each other's control, since the two remedies differ.

THE NEW OBSERVATION FIELDS ARE REACHED THROUGH AN ASSERTION RATHER THAN A
CONSTRUCTOR CALL, because this Red predates them: a `TypeError` from an unknown
keyword proves only that the field is absent, while the field-set assertion fails
as a genuine assertion first.
"""

from __future__ import annotations

import dataclasses

from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    ResumeObservation,
    resume_refusals,
)

_ITEM_ID = "bd-ib-sufca7"
_PULL_REQUEST = 3913


def _require_new_fields() -> None:
    names = {one.name for one in dataclasses.fields(ResumeObservation)}
    assert {"earlier_run_succeeded", "own_route"} <= names


def _active(
    *,
    succeeded: bool = True,
    state: str | None = "OPEN",
    forge_observed: bool = True,
    lock_age_seconds: float | None = None,
    own_route: str | None = None,
) -> ResumeObservation:
    _require_new_fields()
    return ResumeObservation(
        work_item_id=_ITEM_ID,
        status="active",
        anchor_head="a" * 40,
        forge_observed=forge_observed,
        pull_request=_PULL_REQUEST if forge_observed else None,
        pull_request_state=state if forge_observed else None,
        pull_request_head="a" * 40,
        liveness_observed=True,
        lock_age_seconds=lock_age_seconds,
        earlier_run_succeeded=succeeded,
        own_route=own_route,
    )


def _status_refusal(*, observation: ResumeObservation) -> str:
    return resume_refusals(observation=observation)[0]


def test_a_succeeded_run_with_an_open_pull_request_is_offered_the_release_move() -> None:
    refusal = _status_refusal(observation=_active())

    assert f"move:{_ITEM_ID}:ready" in refusal
    assert "reconcile-runs" not in refusal


def test_a_succeeded_run_with_a_merged_pull_request_is_offered_reconcile_merged() -> None:
    refusal = _status_refusal(observation=_active(state="MERGED"))

    assert "reconcile-merged" in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal
    assert "reconcile-runs" not in refusal


def test_a_succeeded_run_with_a_closed_pull_request_is_offered_the_release_move() -> None:
    refusal = _status_refusal(observation=_active(state="CLOSED"))

    assert f"move:{_ITEM_ID}:ready" in refusal
    assert "reconcile-runs" not in refusal


def test_a_live_ownership_lock_withholds_every_status_move() -> None:
    refusal = _status_refusal(observation=_active(lock_age_seconds=42.0))

    assert "ownership lock" in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal
    assert "reconcile-merged" not in refusal
    assert "reconcile-runs" not in refusal


def test_an_item_keeping_its_own_route_is_not_offered_the_release_move() -> None:
    refusal = _status_refusal(observation=_active(own_route="merge-hold"))

    assert "merge-hold" in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal
    assert "reconcile-runs" not in refusal


def test_an_unreadable_forge_withholds_every_status_move_and_names_the_failed_read() -> None:
    refusal = _status_refusal(observation=_active(forge_observed=False))

    assert "forge" in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal
    assert "reconcile-merged" not in refusal
    assert "reconcile-runs" not in refusal


def test_a_claim_whose_run_did_not_succeed_still_names_reconcile_runs() -> None:
    """The control: `reconcile-runs` IS the release for a failed run's claim."""
    refusal = _status_refusal(observation=_active(succeeded=False))

    assert "reconcile-runs" in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal
