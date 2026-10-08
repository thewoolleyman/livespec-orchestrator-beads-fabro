"""A resume and the stale publish-branch reclaim are exclusive per dispatch.

Two clauses meet here. The reclaim's own section says "An operator who wants to
KEEP that work drives the resume below instead of a plain dispatch; the two routes
are exclusive per dispatch and the journal shows which one ran." The resume's
section says it "MUST NOT run the stale publish-branch reclaim above: the
surviving publish branch is the branch the run resumes on, and no preservation
ref is created." Scenario 142's last arm asserts the journal carries NEITHER a
`publish-branch-reclaim` nor a `publish-branch-reclaim-held` record for a resume;
Scenario 144 asserts a plain re-dispatch still reclaims.

WHY RUNNING BOTH IS WORSE THAN RUNNING NEITHER, which is what makes this
assertion load-bearing rather than tidy. The reclaim preserves the surviving head
to a run-scoped ref and then DELETES the publish branch. A resume that also ran it
would delete the branch its own prepare step is about to fetch, so the run would
die in prepare — and the journal would carry a healthy-looking reclaim record
saying the recovery had worked.

WHY BOTH DIRECTIONS ARE ASSERTED. A wall that reclaimed for nobody would satisfy
the resume half perfectly well, so the plain-dispatch half is its control; and a
wall that reclaimed for everybody would satisfy the plain-dispatch half, so the
resume half is that one's control. The parameter default is asserted too, because
every existing caller relies on it and a flipped default would silently stop
reclaiming for the whole fleet.
"""

from __future__ import annotations

import argparse
import inspect
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)


def test_the_wall_takes_a_reclaim_opt_out() -> None:
    """The parameter exists at all — the resume has no other way to decline it."""
    signature = inspect.signature(pre_dispatch_wall_exit)
    assert "reclaim_publish_branches" in signature.parameters


def test_the_reclaim_runs_by_default() -> None:
    """A plain dispatch still reclaims; a flipped default would stop the fleet's."""
    signature = inspect.signature(pre_dispatch_wall_exit)
    assert signature.parameters["reclaim_publish_branches"].default is True


def test_a_resume_declines_the_reclaim_and_a_plain_dispatch_does_not(
    monkeypatch: Any,
) -> None:
    """The one act that mutates a remote ref, taken for one route and not the other."""
    calls: list[str] = []

    def _record(**kwargs: Any) -> None:
        calls.append("reclaimed")
        _ = kwargs

    monkeypatch.setattr(_dispatcher_pre_dispatch_wall, "reclaim_stale_publish_branches", _record)
    # Every refusing arm above the reclaim is stubbed to pass, so this exercises
    # the reclaim decision and nothing else: a refusal returning early would make
    # the absent call prove the wrong thing.
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall, "pre_dispatch_criteria_refusal", lambda **_: None
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall, "proof_assets_refusal_for_items", lambda **_: None
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall, "proof_credentials_refusal_for_items", lambda **_: None
    )
    monkeypatch.setattr(_dispatcher_pre_dispatch_wall, "credential_wrapper_text", lambda **_: "")
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "selection_credential_requirement",
        lambda **_: _dispatcher_pre_dispatch_wall.WorkflowFaultDeferral(
            message="stubbed: this wall arm is not under test here"
        ),
    )
    args = argparse.Namespace(workflow_name=None)

    resumed = pre_dispatch_wall_exit(
        args=args,
        repo=_dispatcher_pre_dispatch_wall.Path("."),
        items=[],
        journal=None,
        reclaim_publish_branches=False,
    )
    assert resumed is None
    assert calls == []

    plain = pre_dispatch_wall_exit(
        args=args,
        repo=_dispatcher_pre_dispatch_wall.Path("."),
        items=[],
        journal=None,
    )
    assert plain is None
    assert calls == ["reclaimed"]
