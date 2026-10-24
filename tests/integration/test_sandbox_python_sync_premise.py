"""The sandbox's Python dependency-sync step is a declared premise, not a constant.

Covers work-item bd-ib-xti6q. Its Definition of Done names
`SPECIFICATION/scenarios.md` "Scenario 32 -- Adopter-target dispatch
compatibility", whose second block requires that "no fleet-toolchain prepare
constant (uv / lefthook / livespec_dev_tooling) is assumed for the target", and
the `SPECIFICATION/contracts.md` factory-sandbox-toolchain-disposition clause,
which requires every factory-sandbox prepare premise assuming the fleet
toolchain to be EITHER a declared-and-validated integration point OR a ratified
no-op, never a silent degrade. The heading bindings themselves stay exactly as
`tests/heading-coverage.json` records them; nothing here claims one.

WHAT WAS MEASURED. The third `[[run.prepare.steps]]` entry of the committed run
configs ran the fleet's Python dependency sync UNCONDITIONALLY, while its two
neighbours -- the version-manager install and the hook-manager install -- were
already `dispatcher.prepare_toolchain` premises that run nothing for a
repository declaring nothing. A governed repository with no `pyproject.toml` and
no target-local workflow therefore died in preparation, before any agent turn,
with `error: No pyproject.toml found in current directory or any parent
directory` and exit 2. Measured 2026-10-24 01:19Z on run 01M5NQVKAENN, a
dispatch of the JavaScript repository `resume` (package.json, mise.toml, no
pyproject.toml), which failed at prepare step 4 with category `deterministic`.
Every dispatch of every such adopter failed identically.

WHY THESE CASES EXECUTE THE STEP RATHER THAN MATCH ITS TEXT. The property under
grade is whether the fleet's sync tool is INVOKED, and no reading of a command
line establishes that: the premise idiom is `set -- <word-list>; test $# -eq 0
|| "$@"`, so whether anything runs is decided by the word-list the Dispatcher
substitutes into it rather than by the step's own shape. A text assertion would
read a correctly-templated step as correct while the resolved word-list still
carried a command, and would read an EMPTY word-list as a step that runs
nothing even if the idiom around it were broken. So each case resolves the
contract from a real `.livespec.jsonc`, substitutes the token exactly as the
Dispatcher's overlay does, and runs the result under `/bin/sh`.

HOW THE SYNC INVOCATION IS OBSERVED. A shim bearing the fleet tool's own name,
first on the child `PATH`, appends its argv to a log and then behaves the way
the real tool behaves for the measured failure: with no `pyproject.toml` at or
above the working directory it prints that same message and exits 2, and
otherwise it exits 0. The walk is CEILINGED at the fixture root, for the reason
`test_sandbox_history_preparation._child_env` records about `git`: this suite's
own tree carries a `pyproject.toml`, so an unbounded walk out of the fixture
would report a project the case was not about and the measured failure could
never be reproduced.

THE MEASURED FAILURE IS ITSELF A CASE. The retired command line is held as a
constant and run against the same no-project fixture, which is what makes the
adopter leg's silence evidence of the repair rather than of a dead shim or a
fixture that could never have shown the defect -- the "instrument incapable of
returning a hit" failure this repository's own `AGENTS.md` catalogues.

AND THE MEMBER LEG IS THE OTHER HALF OF THAT CONTROL. A build that templated
the step and resolved every repository to the no-op would satisfy the adopter
leg exactly as well while silently stopping this fleet's own sandboxes from
having a populated virtual environment -- which every later prepare step and
every check node then runs through. So the member leg asserts the resolved step
INVOKES the sync with its declared arguments, at the same chain position the
constant occupied, named by its two premise neighbours rather than by an index
alone.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_input_tokens import (
    substitute_input_tokens,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    resolve_repo_integration_contract,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_RUN_CONFIG = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)
_GROOM_RUN_CONFIG = _REPO_ROOT / ".fabro" / "workflows" / "groom-work-item" / "workflow.toml"
_MEMBER_CONFIG = _REPO_ROOT / ".livespec.jsonc"

# Every committed run config a dispatch of THIS repository can reach: the
# bundled reserved workflow and the one variant it registers. Both carried the
# constant, so both are held to the premise.
_RUN_CONFIGS: tuple[Path, ...] = (_BUNDLED_RUN_CONFIG, _GROOM_RUN_CONFIG)

# The chain position the constant occupied, and the two premises that bracket it.
# Asserted together rather than as a bare index, because an index alone says
# nothing about WHICH steps a move would have reordered.
_PYTHON_SYNC_STEP_INDEX = 2
_PRECEDING_PREMISE_INPUT = "prepare_toolchain_mise"
_FOLLOWING_PREMISE_INPUT = "prepare_toolchain_lefthook"
_PYTHON_SYNC_INPUT = "prepare_toolchain_python_sync"

# The command line the step carried before this repair, measured failing live.
# Held as a constant rather than read from a payload so the control keeps
# reproducing the defect after no payload carries it.
_RETIRED_UNCONDITIONAL_SYNC = "uv sync --all-groups"
_SYNC_TOOL = "uv"
_NO_PROJECT_MESSAGE = "No pyproject.toml found in current directory or any parent directory"
_NO_PROJECT_EXIT = 2
# What this fleet member declares, read back off its own committed declaration
# rather than spelled here, so the member leg cannot pass by matching a literal
# that has drifted from the configuration a dispatch actually resolves.
_PREPARE_TOOLCHAIN_PATH = ("livespec-orchestrator-beads-fabro", "dispatcher", "prepare_toolchain")
_PYTHON_SYNC_KEY = "python_sync"

_SYNC_SHIM = """#!/bin/sh
printf '%s\\n' "$*" >> "$LIVESPEC_RECORDED_SYNC_ARGV"
dir="$PWD"
while :; do
    if test -f "$dir/pyproject.toml"; then exit 0; fi
    if test "$dir" = "$LIVESPEC_PROJECT_SEARCH_CEILING"; then break; fi
    dir="$(dirname "$dir")"
done
echo 'error: {message}' >&2
exit {exit_code}
"""


@pytest.mark.parametrize("run_config", _RUN_CONFIGS, ids=lambda path: path.parent.name)
def test_a_repository_declaring_no_python_sync_premise_runs_no_sync_at_all(
    run_config: Path, tmp_path: Path
) -> None:
    """Assertion 1: exit 0, and the fleet's sync tool was never invoked.

    Both halves are asserted because either alone passes against a build that is
    still broken: a step that exits 0 may have invoked the tool in a directory
    that happened to resolve a project, and a step that invoked nothing may have
    exited non-zero on a malformed word-list idiom. The declaration is the
    committed member one with ONLY the Python-sync premise removed, so the leg
    differs from the member leg in exactly the fact under grade.
    """
    fixture = _provision(tmp_path=tmp_path)
    script = _resolved_python_sync_step(
        run_config=run_config, config_text=_declaration_without_python_sync()
    )

    completed = _run_script(script=script, fixture=fixture)

    assert completed.returncode == 0, completed.stderr
    assert _recorded_sync_argv(fixture=fixture) == []


def test_the_retired_unconditional_sync_still_refuses_that_same_project_less_clone(
    tmp_path: Path,
) -> None:
    """The measured failure, reproduced: the control for the case above.

    Identical fixture; the ONE thing varied is which command line runs in it.
    The exit code, the provider's own message and the recorded invocation are all
    asserted, because the invocation alone would not say the sync was REFUSED for
    finding no project, and the exit code alone would not say the tool was
    reached at all -- which is exactly the distinction the case above rests on.
    """
    fixture = _provision(tmp_path=tmp_path)

    completed = _run_script(script=_RETIRED_UNCONDITIONAL_SYNC, fixture=fixture)

    assert completed.returncode == _NO_PROJECT_EXIT, completed.stderr
    assert _NO_PROJECT_MESSAGE in completed.stderr, completed.stderr
    assert _recorded_sync_argv(fixture=fixture) == ["sync --all-groups"]


@pytest.mark.parametrize("run_config", _RUN_CONFIGS, ids=lambda path: path.parent.name)
def test_a_repository_declaring_the_premise_runs_its_sync_at_the_same_chain_position(
    run_config: Path, tmp_path: Path
) -> None:
    """Assertion 2: this member's declared sync runs, bracketed by its neighbours.

    The invoked argv is compared against the member's OWN committed declaration
    rather than against a literal, so a declaration that drifted from the
    measured command would fail here instead of being echoed back. The position
    is read as the two premises the step still sits between, which is what an
    index cannot say: a chain whose steps were reordered keeps every index.
    """
    fixture = _provision(tmp_path=tmp_path, with_project=True)
    scripts = _prepare_scripts(run_config=run_config)
    script = _resolved_python_sync_step(
        run_config=run_config, config_text=_MEMBER_CONFIG.read_text(encoding="utf-8")
    )

    completed = _run_script(script=script, fixture=fixture)

    assert completed.returncode == 0, completed.stderr
    assert _recorded_sync_argv(fixture=fixture) == [
        " ".join(_declared_python_sync()[1:]),
    ]
    assert _PRECEDING_PREMISE_INPUT in scripts[_PYTHON_SYNC_STEP_INDEX - 1]
    assert _FOLLOWING_PREMISE_INPUT in scripts[_PYTHON_SYNC_STEP_INDEX + 1]


@dataclass(frozen=True, kw_only=True)
class _Fixture:
    """A provisioned working directory, its child environment, and the argv log."""

    workdir: Path
    env: dict[str, str]
    recorded_sync_argv: Path


def _prepare_scripts(*, run_config: Path) -> tuple[str, ...]:
    """Every `[[run.prepare.steps]]` script a committed run config declares.

    Parsed with `tomli` rather than grepped, for the reason
    `test_sandbox_history_preparation._history_preparation_script` records: the
    property under grade is the value the engine resolves, and a line-shaped
    read would happily return a commented-out declaration.
    """
    document: dict[str, Any] = tomli.loads(run_config.read_text(encoding="utf-8"))
    steps: list[dict[str, Any]] = document["run"]["prepare"]["steps"]
    return tuple(str(step["script"]) for step in steps)


def _resolved_python_sync_step(*, run_config: Path, config_text: str) -> str:
    """The Python-sync step as a dispatch of one declaration would RUN it.

    Resolved through the production contract resolver and substituted through the
    production overlay substituter, because the engine leaves `run.prepare`
    verbatim and the Dispatcher renders those tokens host-side -- so this IS the
    text that reaches the sandbox shell. The step is asserted to carry no
    unresolved token afterwards: one left standing would run as whatever the
    shell made of the literal rather than as what a dispatch runs.
    """
    resolved = resolve_repo_integration_contract(config_text=config_text, default_branch=None)
    rendered = substitute_input_tokens(
        text=_prepare_scripts(run_config=run_config)[_PYTHON_SYNC_STEP_INDEX],
        prepare_inputs=contract_prompt_variables(resolved=resolved),
    )
    assert "inputs." not in rendered, rendered
    return rendered


def _declared_python_sync() -> list[str]:
    """This member's own committed `dispatcher.prepare_toolchain.python_sync` argv."""
    document: dict[str, Any] = json.loads(
        _jsonc_stripped(text=_MEMBER_CONFIG.read_text(encoding="utf-8"))
    )
    block: dict[str, Any] = document
    for key in _PREPARE_TOOLCHAIN_PATH:
        block = block[key]
    return [str(token) for token in block[_PYTHON_SYNC_KEY]]


def _declaration_without_python_sync() -> str:
    """The committed member declaration with ONLY the Python-sync premise removed.

    Varying one key of the real declaration rather than hand-writing a second
    repository is what keeps this leg an adopter that declares nothing HERE
    while declaring everything else exactly as the member does -- so the two
    legs differ in the fact under grade and in nothing else.
    """
    document: dict[str, Any] = json.loads(
        _jsonc_stripped(text=_MEMBER_CONFIG.read_text(encoding="utf-8"))
    )
    block: dict[str, Any] = document
    for key in _PREPARE_TOOLCHAIN_PATH:
        block = block[key]
    _ = block.pop(_PYTHON_SYNC_KEY, None)
    return json.dumps(document, indent=2)


def _jsonc_stripped(*, text: str) -> str:
    """The committed JSONC with its `//` line comments removed, string-safe."""
    return re.sub(r'("(?:\\.|[^"\\])*")|(//[^\n]*)', lambda m: m.group(1) or "", text)


def _provision(*, tmp_path: Path, with_project: bool = False) -> _Fixture:
    """A working directory with the sync shim first on `PATH`.

    `with_project` writes the minimal `pyproject.toml` the shim looks for, which
    is what lets the member leg reach the tool's success arm; without it the
    fixture is the measured adopter shape -- a repository the sync tool finds no
    project in. The state is asserted before returning, because a fixture that
    silently came out the other way would make its case pass against the defect
    fully present.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / _SYNC_TOOL
    _ = shim.write_text(
        _SYNC_SHIM.format(message=_NO_PROJECT_MESSAGE, exit_code=_NO_PROJECT_EXIT),
        encoding="utf-8",
    )
    shim.chmod(0o755)
    workdir = tmp_path / "clone"
    workdir.mkdir()
    if with_project:
        _ = (workdir / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    assert (workdir / "pyproject.toml").is_file() == with_project
    return _Fixture(
        workdir=workdir,
        env={
            "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(tmp_path),
            "LIVESPEC_RECORDED_SYNC_ARGV": str(tmp_path / "recorded-sync-argv.txt"),
            "LIVESPEC_PROJECT_SEARCH_CEILING": str(tmp_path),
        },
        recorded_sync_argv=tmp_path / "recorded-sync-argv.txt",
    )


def _run_script(*, script: str, fixture: _Fixture) -> subprocess.CompletedProcess[str]:
    """Run one prepare-step script under `/bin/sh`, as the engine runs it."""
    return subprocess.run(
        ["/bin/sh", "-c", script],
        cwd=str(fixture.workdir),
        env=fixture.env,
        capture_output=True,
        text=True,
        check=False,
        input="",
    )


def _recorded_sync_argv(*, fixture: _Fixture) -> list[str]:
    """Every argv the sync shim was invoked with, in order; empty when unreached.

    An absent log IS the empty recording here, unlike the `git` shim one module
    over: the whole claim of the adopter leg is that the tool was not reached, so
    a log the shim never created is the expected shape rather than a broken
    instrument -- and the retired-command control is what proves the shim can
    still record.
    """
    if not fixture.recorded_sync_argv.is_file():
        return []
    return fixture.recorded_sync_argv.read_text(encoding="utf-8").splitlines()
