"""The run-from clone module's own surface, apart from the Scenario 336 journey.

`tests/integration/test_run_from_clones_scenario336.py` EXECUTES the materialized
program against local repositories; this file covers what that tier does not
discriminate: that every deployment-time token is substituted, that the rendered
program is a program, which repositories are planned, and the shape of the prepare
step and env line a dispatch renders.
"""

from __future__ import annotations

import ast
import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    SiblingClones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_from_clones import (
    RUN_FROM_CLONES_ROOT,
    RUN_FROM_PROGRAM_FILENAME,
    RUN_FROM_REPOS,
    run_from_clone_steps_block,
    run_from_clones_env_line,
    run_from_program_source,
    run_from_repos,
    sandbox_clone_fragments,
)

from tests.prepare_step_support import steps_in, unpacked


def _siblings(*, repos: tuple[str, ...]) -> SiblingClones:
    return SiblingClones(owner="thewoolleyman", repos=repos, clones_root="/livespec-siblings")


def test_the_family_runs_exactly_one_cross_repository_tool() -> None:
    """Livespec core's checker is the one tool the family executes from another checkout."""
    assert RUN_FROM_REPOS == ("livespec",)


def test_only_planned_members_get_a_run_from_clone() -> None:
    """The target is excluded from the siblings, so a target that IS livespec has none."""
    assert run_from_repos(siblings=None) == ()
    assert run_from_repos(siblings=_siblings(repos=())) == ()
    assert run_from_repos(siblings=_siblings(repos=("livespec-overseer",))) == ()
    assert run_from_repos(siblings=_siblings(repos=("livespec-overseer", "livespec"))) == (
        "livespec",
    )


def test_the_rendered_program_has_no_unsubstituted_token_and_compiles() -> None:
    """A token left in the program is a literal the sandbox would run, not a value."""
    source = run_from_program_source(
        url_base="https://github.com/thewoolleyman", root="/livespec-run-from", repos=("livespec",)
    )

    assert "@@" not in source
    assert source.endswith("\n")
    compile(source, "livespec-run-from-clones.py", "exec")
    assert '"url_base": "https://github.com/thewoolleyman"' in source


def test_the_plan_is_carried_as_data_not_spliced_into_code() -> None:
    """A hostile root or base is a JSON string the program parses, never code it runs."""
    hostile = 'x"; import os; os.system("true") #'
    source = run_from_program_source(url_base=hostile, root=hostile, repos=("livespec",))

    plan_line = next(line for line in source.splitlines() if line.startswith("PLAN = "))
    literal = ast.literal_eval(plan_line.removeprefix("PLAN = json.loads(").removesuffix(")"))
    assert json.loads(literal) == {"url_base": hostile, "root": hostile, "repos": ["livespec"]}


def test_the_prepare_step_writes_the_program_by_payload_and_runs_it() -> None:
    """The bytes ride the step's env; the script writes them where the nodes re-enter."""
    block = run_from_clone_steps_block(siblings=_siblings(repos=("livespec",)))

    (step,) = steps_in(block=block)
    assert RUN_FROM_PROGRAM_FILENAME in step.script
    assert step.script.splitlines()[-1].startswith("exec python3 ")
    assert "git clone" not in step.script
    assert RUN_FROM_CLONES_ROOT in unpacked(value=next(iter(step.env.values())))


def test_nothing_planned_renders_nothing() -> None:
    assert run_from_clone_steps_block(siblings=_siblings(repos=("livespec-overseer",))) == ""
    assert run_from_clones_env_line(siblings=_siblings(repos=("livespec-overseer",))) == ""
    assert run_from_clones_env_line(siblings=None) == ""


def test_the_fragments_pair_the_work_clones_with_the_run_from_clone_and_every_env_key() -> None:
    """Steps and env lines are rendered together, in the order the overlay appends them."""
    fragments = sandbox_clone_fragments(siblings=_siblings(repos=("livespec", "livespec-overseer")))

    assert fragments.steps.index("sibling clone skipped for livespec:") < fragments.steps.index(
        RUN_FROM_PROGRAM_FILENAME
    )
    assert fragments.env_lines.splitlines() == [
        'LIVESPEC_SIBLING_CLONES_ROOT = "/livespec-siblings"',
        'LIVESPEC_CORE_PLUGIN_ROOT = "/livespec-run-from/livespec/.claude-plugin"',
        'LIVESPEC_RUN_FROM_CLONES_ROOT = "/livespec-run-from"',
    ]


def test_no_fleet_and_a_fleet_without_livespec_render_only_what_exists() -> None:
    """No siblings at all is empty; a fleet without core still gets its sibling root."""
    empty = sandbox_clone_fragments(siblings=None)
    assert (empty.steps, empty.env_lines) == ("", "")

    no_core = sandbox_clone_fragments(siblings=_siblings(repos=("livespec-overseer",)))
    assert RUN_FROM_PROGRAM_FILENAME not in no_core.steps
    assert no_core.env_lines == 'LIVESPEC_SIBLING_CLONES_ROOT = "/livespec-siblings"\n'
