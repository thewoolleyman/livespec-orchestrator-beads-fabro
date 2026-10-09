"""Invalid runtime-ceiling policy refuses before any claim or lifecycle mutation.

Scenario 165 requires that when either runtime ceiling is configured as zero, a
negative, a boolean or a non-integer, "configuration resolution refuses before
claim or lifecycle mutation". The pre-dispatch wall is where that lands: every
refusal in it runs after selection and BEFORE admission, so a refused selection
is never claimed and no `active` row is left behind.

Both new surfaces are reached through `importlib` inside the test bodies rather
than imported at module top, so this slice's Red commit fails on a genuine
assertion — the module-existence check below — instead of dying at collection.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings import (
    COMMITTED_ONLY_RUNTIME_CEILING_KEYS,
    NO_ADOPTED_CYCLE_CEILINGS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._config_cycle_ceilings"
_WALL_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_config_cycle_ceilings.py"
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _wall() -> ModuleType:
    """Import the pre-dispatch wall, asserting the new refusal is on it first."""
    module = importlib.import_module(_WALL_NAME)
    assert hasattr(
        module, "runtime_ceiling_policy_refusal"
    ), "the pre-dispatch wall does not carry runtime_ceiling_policy_refusal yet"
    return module


def _write_config(*, repo: Path, body: str) -> None:
    (repo / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "dispatcher": {\n'
        f"{body}"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )


def test_an_absent_declaration_adopts_neither_ceiling(tmp_path: Path) -> None:
    module = _module()
    _write_config(repo=tmp_path, body='      "wip_cap": 3\n')

    assert module.resolve_adopted_cycle_ceilings(cwd=tmp_path) == NO_ADOPTED_CYCLE_CEILINGS


def test_a_committed_positive_integer_is_adopted(tmp_path: Path) -> None:
    module = _module()
    _write_config(repo=tmp_path, body='      "adopted_cycle_product_lloc_ceiling": 40\n')

    resolved = module.resolve_adopted_cycle_ceilings(cwd=tmp_path)

    assert resolved.product_lloc == 40
    assert resolved.duration_seconds is None


def test_every_invalid_value_refuses_naming_the_setting(tmp_path: Path) -> None:
    module = _module()

    for key in COMMITTED_ONLY_RUNTIME_CEILING_KEYS:
        for literal in ("0", "-1", "true", '"10"', "10.5"):
            _write_config(repo=tmp_path, body=f'      "{key}": {literal}\n')

            refusal = module.resolve_adopted_cycle_ceilings(cwd=tmp_path)

            assert isinstance(refusal, str), f"{key}={literal} must refuse"
            assert key in refusal


def test_the_pre_dispatch_wall_refuses_invalid_policy_before_admission(tmp_path: Path) -> None:
    wall = _wall()
    _write_config(repo=tmp_path, body='      "adopted_cycle_duration_seconds_ceiling": 0\n')

    refusal = wall.runtime_ceiling_policy_refusal(repo=tmp_path)

    assert refusal is not None
    assert "adopted_cycle_duration_seconds_ceiling" in refusal


def test_the_wall_passes_a_repository_with_no_adoption(tmp_path: Path) -> None:
    wall = _wall()
    _write_config(repo=tmp_path, body='      "wip_cap": 3\n')

    assert wall.runtime_ceiling_policy_refusal(repo=tmp_path) is None


def test_the_wall_exit_is_the_precondition_code(tmp_path: Path) -> None:
    wall = _wall()
    _write_config(repo=tmp_path, body='      "adopted_cycle_product_lloc_ceiling": -3\n')

    exit_code = wall.pre_dispatch_wall_exit(
        args=argparse.Namespace(workflow_name=None, workflow=None),
        repo=tmp_path,
        items=[],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        reclaim_publish_branches=False,
    )

    assert exit_code == EXIT_PRECONDITION_ERROR
