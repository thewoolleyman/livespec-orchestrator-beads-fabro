"""The dispatch leg forwards the PLAN's resolved factory environment.

`bd-ib-kyeor4`'s sibling claim. `test_dispatcher_overlay_factory_environment_
env_table.py` establishes that the renderer and the materializer key the
run-scoped env table on the factory's declared catalog environment; this
establishes that a real dispatch HANDS them that id. Without this line the
repair is inert: every dispatch materializes an overlay through
`_dispatcher_loop_overlay`, which would pass nothing and leave the table keyed
on the committed `[run.environment] id` — exactly the state the measured
incident ran in.

IT IS READ OFF THE LEG'S OWN CALL rather than driven, and that is deliberate.
The claim is about WHICH value reaches the materializer, and every other way of
observing that call needs the whole dispatch harness — a resolved plan, a
recorded dispatch, a workflow payload, a vault sink — to produce one reading.
Two builds re-create the defect while satisfying a test that merely checks the
keyword is present: one forwarding a literal, and one resolving the factory
again. The plan field is what `fabro run --environment` is rendered from, so a
second resolution can key the table away from the environment the launch
selects, and both readings are well-formed — which is the whole reason the
resolve-once-project-everywhere discipline exists.

THE FACTORY NAME IS THE CONTROL. It is forwarded off the same plan at the same
call, so a reading that found nothing at all — a renamed call, a module this
could not parse, a `**kwargs` splat — fails there first instead of reporting an
absent keyword as a finding about the environment.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_overlay


def _forwarded_keywords() -> dict[str, str]:
    """Each keyword of the leg's ONE `materialize_overlay` call, as source text."""
    source = Path(_dispatcher_loop_overlay.__file__).read_text(encoding="utf-8")
    call = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "materialize_overlay"
    )
    return {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords if keyword.arg}


def test_the_dispatch_leg_forwards_the_plans_resolved_factory_environment() -> None:
    """The leg hands the materializer the plan's field, not a second resolution."""
    forwarded = _forwarded_keywords()

    assert forwarded["factory_name"] == "plan.fabro_factory_name"
    assert forwarded["factory_environment"] == "plan.fabro_factory_environment"
