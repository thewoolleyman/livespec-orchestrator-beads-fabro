"""The run-from clone module's own surface, apart from the Scenario 336 journey.

`tests/integration/test_run_from_clones_scenario336.py` EXECUTES the materialized
program against local repositories; this file covers what that tier does not
discriminate: that every deployment-time token is substituted, that the rendered
program is a program, which repositories are planned, and the shape of the prepare
step and env line a dispatch renders.

The program is a fetched helper program (bd-ib-jrawlp, research note 004
decision 6): the helper-fetch setup step lands it below the plugins root from the
installed build's own commit, so its bytes are a pure function of the plugin tree
and carry no dispatch input. The dispatch's PLAN -- which repositories, from
where, under which root -- is per-dispatch data: the prepare step writes it beside
the program as a JSON file, and every run of the program reads it from there.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_from_clones as run_from
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import (
    PLUGINS_ROOT,
    helper_registry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    SiblingClones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_from_clones import (
    RUN_FROM_CLONES_ROOT,
    RUN_FROM_PROGRAM_FILENAME,
    RUN_FROM_REPOS,
    run_from_clone_steps_block,
    run_from_clones_env_line,
    run_from_repos,
    sandbox_clone_fragments,
)

from tests.prepare_step_support import plugins_helper, steps_in


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


def test_the_program_is_a_fetched_helper_landed_below_the_plugins_root() -> None:
    """The helper fetch composes the program; no prepare step carries its bytes."""
    landed = {(helper.root, helper.path) for helper in helper_registry()}
    assert (PLUGINS_ROOT, RUN_FROM_PROGRAM_FILENAME) in landed

    helper = plugins_helper(path=RUN_FROM_PROGRAM_FILENAME)

    assert helper.compose() == run_from.run_from_program_source().encode("utf-8")
    assert helper.mode == 0o644


def test_the_program_has_no_unsubstituted_token_compiles_and_carries_no_plan() -> None:
    """A token left in the program is a literal the sandbox would run, not a value."""
    source = run_from.run_from_program_source()

    assert "@@" not in source
    assert source.endswith("\n")
    compile(source, RUN_FROM_PROGRAM_FILENAME, "exec")
    assert "url_base" in source
    assert "https://github.com" not in source
    assert RUN_FROM_CLONES_ROOT not in source
    assert run_from.RUN_FROM_PLAN_FILENAME in source


def test_the_plan_is_carried_as_data_not_spliced_into_code() -> None:
    """A hostile root or base is a JSON string the program parses, never code it runs."""
    hostile = 'x"; import os; os.system("true") #'
    plan = run_from.run_from_plan_text(url_base=hostile, root=hostile, repos=("livespec",))

    assert json.loads(plan) == {"url_base": hostile, "root": hostile, "repos": ["livespec"]}


def test_the_prepare_step_writes_the_plan_beside_the_fetched_program_and_runs_it() -> None:
    """The plan rides the step's env as plain data; the script writes it, then runs."""
    block = run_from_clone_steps_block(siblings=_siblings(repos=("livespec",)))

    (step,) = steps_in(block=block)
    assert step.env == {
        run_from.RUN_FROM_PLAN_ENV: run_from.run_from_plan_text(
            url_base="https://github.com/thewoolleyman",
            root=RUN_FROM_CLONES_ROOT,
            repos=("livespec",),
        )
    }
    assert f'"$root/{run_from.RUN_FROM_PLAN_FILENAME}"' in step.script
    assert step.script.splitlines()[-1] == f'exec python3 "$root/{RUN_FROM_PROGRAM_FILENAME}"'
    assert "git clone" not in step.script
    assert "def ensure" not in step.script


def test_the_program_with_no_plan_beside_it_has_nothing_to_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every refreshing node runs the fetched program; a dispatch that planned none is a no-op."""
    program = tmp_path / RUN_FROM_PROGRAM_FILENAME
    program.write_text(run_from.run_from_program_source(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(program), run_name="__main__")

    assert (exited.value.code, capsys.readouterr().err) == (0, "")
    assert sorted(path.name for path in tmp_path.iterdir()) == [RUN_FROM_PROGRAM_FILENAME]


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
