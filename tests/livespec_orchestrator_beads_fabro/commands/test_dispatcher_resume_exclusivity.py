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

HOW THE EXCLUSIVITY IS NOW STRUCTURED, which is what this file asserts. The
reclaim used to close `pre_dispatch_wall_exit`, so a resume had to decline it
through a `reclaim_publish_branches=False` parameter — and the resume was the only
caller that passed anything but the default. Under `bd-ib-huoyk7` the reclaim moved
PAST the capacity decision, to `post_admission_publish_branch_reclaim`, which each
LAUNCH path calls for the items it is about to launch. So the shared wall reclaims
for nobody at all, and a path reaches the reclaim only by calling it itself. The
resume does not; the two dispatch paths do.

WHY THIS FILE NEEDS A CONTROL ELSEWHERE. A structure in which NOBODY could reach
the reclaim satisfies every STRUCTURAL assertion here, because holding an entry
point is not performing the act. So the behavioural control is the launched-item
half of `test_dispatcher_publish_branch_reclaim_after_capacity.py`, which drives
both dispatch paths and reads the reclaim they actually perform; this file asserts
only which routes can reach it at all.
"""

from __future__ import annotations

import argparse
import inspect
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_wave as loop_wave
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_resume_command as resume_command,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_launch as run_launch
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)

_RECLAIM = "post_admission_publish_branch_reclaim"


def test_the_wall_carries_no_reclaim_opt_out_because_it_reclaims_for_nobody() -> None:
    """The parameter is gone: there is nothing left for a resume to decline.

    Its absence is asserted rather than merely unused, because a parameter that
    still existed would leave the destructive pre-admission call one argument
    away from returning.
    """
    signature = inspect.signature(pre_dispatch_wall_exit)
    assert "reclaim_publish_branches" not in signature.parameters


def test_the_shared_wall_reclaims_for_nobody(monkeypatch: Any) -> None:
    """The one act that mutates a remote ref is not taken by the wall, for anyone."""
    calls: list[str] = []
    # A lambda rather than a `def`, because this stub must NEVER be entered: a
    # function body nothing reaches is an uncovered line, and "nothing reaches
    # it" is precisely what this case asserts.
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "reclaim_stale_publish_branches",
        lambda **kwargs: calls.append(str(kwargs)),
    )
    # Every refusing arm is stubbed to pass, so this exercises the wall's own
    # reclaim decision and nothing else: a refusal returning early would make the
    # absent call prove the wrong thing.
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

    plain = pre_dispatch_wall_exit(
        args=args,
        repo=_dispatcher_pre_dispatch_wall.Path("."),
        items=[],
        journal=None,
    )

    assert plain is None
    assert calls == []


def test_only_the_two_launch_paths_can_reach_the_reclaim() -> None:
    """Both dispatch paths hold the entry point; the resume module does not.

    A module's namespace holds an imported name only if that module uses it, so
    this is the structural form of "which routes can reach the reclaim at all" —
    and it is the whole of the resume's exclusivity now that the shared wall
    reclaims for nobody. The two launch paths are named individually because
    they are two separate call sites: a reclaim wired into only one of them would
    satisfy a weaker assertion while leaving the other path's recovery stuck.
    """
    assert hasattr(_dispatcher_pre_dispatch_wall, _RECLAIM)
    assert hasattr(loop_wave, _RECLAIM)
    # The targeted dispatch's reclaim moved with its admit-and-launch step into
    # `_dispatcher_run_launch`; the entry point still belongs to a LAUNCH path,
    # which is the whole of what this assertion is about.
    assert hasattr(run_launch, _RECLAIM)
    assert not hasattr(resume_command, _RECLAIM)
