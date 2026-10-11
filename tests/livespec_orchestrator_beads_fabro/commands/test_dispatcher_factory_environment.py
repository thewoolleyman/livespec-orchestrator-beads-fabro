"""Tests for grading a factory's declared sandbox environment (bd-ib-fgre25).

`_factory_environment` reads the `dispatcher.factories` entry's optional
`environment` key; this module covers the GRADE of that reading — the id the
`fabro run` argv carries, and the pre-claim refusal of a declaration that
names no usable id.

The argv arms are asserted END TO END, from a committed `.livespec.jsonc`
through the resolved factory, the dispatch plan and the port, down to the
argv a recording runner receives. A unit assertion on the argv builder alone
would pass while any one link of that chain dropped the id, and the chain is
where this is easiest to get wrong: the environment is a property of the
FACTORY, so it has to survive the same hand-off the factory's server and its
client binary already make.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import build_plan
from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_GRADE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_factory_environment"
_CANDIDATE_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32278"
_CATALOG_ENVIRONMENT = "livespec-ci"
_WORK_ITEM_ID = "bd-ib-fgre25"
_EXIT_PRECONDITION_ERROR = 3


@dataclass(kw_only=True)
class _Runner:
    """Records every argv the launch hands the CLI."""

    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        return CommandResult(exit_code=0, stdout="Run: 01LAUNCHED\n", stderr="")


def _write_config(
    *,
    cwd: Path,
    factories: dict[str, object],
    default_factory: str | None = None,
) -> None:
    dispatcher: dict[str, object] = {"factories": factories}
    if default_factory is not None:
        dispatcher["default_factory"] = default_factory
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _grade_module() -> Any:
    """The grade module, imported inside the test body.

    The module path is asserted FIRST so the Red is a genuine assertion
    failure rather than a collection error — at Red the module does not exist,
    and a top-level import of it would die before any assertion ran.
    """
    assert (_COMMANDS_DIR / "_dispatcher_factory_environment.py").is_file()
    return importlib.import_module(_GRADE_MODULE)


def _run_argv(*, cwd: Path, factory: str) -> list[str]:
    """The `fabro run` argv one dispatch to `factory` actually produces."""
    grade = _grade_module()
    target = resolve_fabro_factory(cwd=cwd, factory=factory)
    plan = build_plan(
        repo=cwd,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=cwd / "workflow.toml",
        goal_file=cwd / "goal.md",
        fabro_bin="/opt/fabro",
        fabro_factory_name=target.name,
        fabro_factory_server=target.server,
        fabro_factory_environment=grade.factory_environment_id(factory=target),
        janitor=None,
        janitor_checkout=cwd / "janitor",
    )
    runner = _Runner()
    port = fabro_port_for_plan(plan=plan, runner=runner)
    _ = port.run(
        workflow_toml=plan.workflow_toml,
        goal_file=plan.goal_file,
        inputs=(),
        timeout_seconds=42.0,
    )
    return next(argv for argv in runner.argvs if argv[1] == "run")


def test_the_run_argv_carries_the_environment_a_factory_declares(tmp_path: Path) -> None:
    """A declaring factory's id reaches `fabro run --environment`.

    Asserted as adjacent argv TOKENS rather than by substring: the engine
    reads the flag and its operand as two tokens, so an id spliced onto the
    flag would satisfy a substring probe and be rejected by the engine.

    The `--server` position is asserted beside it because the pinned engine
    requires `--server` to stay LAST on the subcommand: an operand inserted
    after it is a dispatch that cannot launch at all.

    The projection is asserted FIRST, before the chain that carries it, so a
    failure says which of the two it was: an id the grade never produced, or
    an id the hand-off dropped.
    """
    _write_config(
        cwd=tmp_path,
        factories={
            "hp-candidate": {"server": _CANDIDATE_SERVER, "environment": _CATALOG_ENVIRONMENT}
        },
    )

    assert (
        _grade_module().factory_environment_id(
            factory=resolve_fabro_factory(cwd=tmp_path, factory="hp-candidate")
        )
        == _CATALOG_ENVIRONMENT
    )

    argv = _run_argv(cwd=tmp_path, factory="hp-candidate")

    assert argv[argv.index("--environment") + 1] == _CATALOG_ENVIRONMENT
    assert argv.index("--environment") < argv.index("--server")
    assert argv[-2:] == ["--server", _CANDIDATE_SERVER]


def test_the_run_argv_carries_no_environment_when_a_factory_declares_none(
    tmp_path: Path,
) -> None:
    """A factory declaring no `environment` emits no flag at all.

    This is NOT the cosmetic complement of the arm above. The key is opt-in
    precisely because the pinned 0.254 engine has no `--environment` flag:
    emitting one unconditionally — even carrying the `default` id the server
    would have selected anyway — makes every dispatch to that engine die at
    argument parsing, before any run exists. So "no id" has to mean "no
    flag", not "the default id spelled out".
    """
    _write_config(cwd=tmp_path, factories={"hp": {"server": _CANDIDATE_SERVER}})

    assert (
        _grade_module().factory_environment_id(
            factory=resolve_fabro_factory(cwd=tmp_path, factory="hp")
        )
        is None
    )

    argv = _run_argv(cwd=tmp_path, factory="hp")

    assert "--environment" not in argv
    assert argv[-2:] == ["--server", _CANDIDATE_SERVER]


@pytest.mark.parametrize("declared", ["", 7, None, [], {}])
def test_an_unusable_declared_environment_is_refused_before_claim_naming_the_factory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    declared: object,
) -> None:
    """A declaration naming no usable id refuses the dispatch, and says whose.

    Every unusable shape is parameterized because they have ONE remedy and
    must not have several messages: an empty string, a number, an explicit
    null, and the two container shapes a JSONC author can reach by accident.

    The refusal is taken off `dispatch_preamble`, which is the whole claim it
    has to land before: the preamble runs ahead of admission, so an
    unobserved fault here admits the item `ready -> active` with an assignee
    and then places its run in the server's default environment — a failure
    that reads as the work-item's, in a sandbox with no `mise` on PATH.

    The message must name the FACTORY as well as the key. A dispatch resolves
    its factory from `default_factory`, `LIVESPEC_FABRO_FACTORY` or a per-item
    pin, so "some factory declares an unusable environment" does not say which
    entry of `dispatcher.factories` to edit.
    """
    _write_config(
        cwd=tmp_path,
        factories={
            "hp-candidate": {"server": _CANDIDATE_SERVER, "environment": declared},
            "hp": {"server": _CANDIDATE_SERVER},
        },
        default_factory="hp-candidate",
    )
    args = argparse.Namespace(fabro_bin=None, janitor=None, journal=None)

    result = dispatch_preamble(args=args, repo=tmp_path)

    refusal = capsys.readouterr().err
    assert "dispatcher.factories.hp-candidate.environment" in refusal
    assert result == (None, _EXIT_PRECONDITION_ERROR)


def test_a_usable_declared_environment_is_not_refused(tmp_path: Path) -> None:
    """The positive control for the refusal above, and it is load-bearing.

    A refusal that convicted EVERY declared `environment` would satisfy every
    unusable case above while making the key impossible to use — and the two
    are indistinguishable at the only surface that reports either, since both
    read as "the dispatch was refused naming this factory's environment". The
    absent arm cannot stand in for this one: it proves the refusal tolerates a
    factory that declares nothing, not that it admits one that declares well.
    """
    _write_config(
        cwd=tmp_path,
        factories={
            "hp-candidate": {"server": _CANDIDATE_SERVER, "environment": _CATALOG_ENVIRONMENT}
        },
    )
    target = resolve_fabro_factory(cwd=tmp_path, factory="hp-candidate")
    grade = _grade_module()

    assert grade.factory_environment_refusal(factory=target) is None
    assert grade.factory_declaration_refusal(factory=target) is None


def test_a_caller_holding_no_factory_target_has_no_environment_to_refuse() -> None:
    """No resolved target is an answer, not a fault.

    The needs-attention and standalone reconcile surfaces build their own
    arguments and never run a dispatch preamble, so they hold no factory. That
    is the pre-key behaviour — the same reason `factory_bin_refusal` tolerates
    it — and a refusal there would reject surfaces that dispatch nothing.
    """
    grade = _grade_module()

    assert grade.factory_environment_refusal(factory=None) is None
    assert grade.factory_declaration_refusal(factory=None) is None
