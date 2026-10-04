"""The archive leg's own module, split out of `plan.py` by cohesion.

`plan.py` had accreted two concerns: AUTHORING a plan (create, handoff, scope
event) and ARCHIVING one (the child-disposition gate, the working-tree sweep,
the completeness-review evidence resolution, the epic close and the directory
move). The archive half belongs beside its own neighbourhood —
`_plan_archive_gates.py` and `_plan_archive_review.py` already live there —
and the split is what gives `plan.py` the room the plan-level Definition of
Done needs.

The comment-header RENDER moves too, into `_plan_timeline.py`, which already
owns the PARSE of that same header. Both halves of one format now live in one
module and are structurally incapable of drifting apart; the alternative was a
cross-module private import, which pyright strict and the `private_calls`
check both reject.
"""

from __future__ import annotations

import importlib
from pathlib import Path

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)


def test_the_archive_leg_moved_into_its_own_cohesive_module() -> None:
    module_path = _COMMANDS / "_plan_archive.py"

    assert module_path.is_file()

    archive = importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_archive")
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")

    # The public entry point lives in the new module and is re-exported by the
    # source module, so every existing caller of `plan.archive_thread` is
    # unaffected by the move.
    assert "archive_thread" in archive.__all__
    assert plan.archive_thread is archive.archive_thread
    assert "archive_thread" in plan.__all__

    # The private helpers that ONLY the archive leg used moved WITH it and are
    # gone from the source module. A helper left behind and imported back would
    # be exactly the cross-module private import the split exists to avoid.
    assert not hasattr(plan, "_resolve_completeness_review_evidence")
    assert not hasattr(plan, "_utc_now_iso")


def test_the_plan_comment_header_render_lives_beside_its_parse() -> None:
    timeline = importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_timeline")
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")

    assert "plan_comment_body" in timeline.__all__
    # The render composes the exact three-line header the module's own
    # `read_timeline` parses back: prefix, author, timestamp, blank line, body.
    assert timeline.plan_comment_body(
        prefix=timeline.PLAN_SCOPE_PREFIX,
        author="factory-test",
        now="2026-10-04T00:00:00Z",
        body="Requirement carriers:\n- one",
    ) == (
        "plan-scope-event\nauthor: factory-test\ntimestamp: 2026-10-04T00:00:00Z\n\n"
        "Requirement carriers:\n- one"
    )
    assert not hasattr(plan, "_comment_body")
