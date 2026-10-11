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

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import build_plan
from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_GRADE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_factory_environment"
_CANDIDATE_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32278"
_CATALOG_ENVIRONMENT = "livespec-ci"
_WORK_ITEM_ID = "bd-ib-fgre25"


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


def _write_config(*, cwd: Path, factories: dict[str, object]) -> None:
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {"factories": factories}}}),
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
