"""Committed runtime-ceiling policy resolution."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._config_cycle_ceilings"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_config_cycle_ceilings.py"
)


def _module() -> ModuleType:
    """Import the resolver after proving the module exists."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _write_config(*, repo: Path, key: str, value: str) -> None:
    """Write one dispatcher ceiling declaration."""
    (repo / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "dispatcher": {\n'
        f'      "{key}": {value}\n'
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )


def test_invalid_runtime_ceiling_values_are_refused_during_policy_resolution(
    tmp_path: Path,
) -> None:
    """Neither ceiling accepts zero, negatives, booleans, or non-integers."""
    module = _module()

    for key in (
        "adopted_cycle_product_lloc_ceiling",
        "adopted_cycle_duration_seconds_ceiling",
    ):
        for value in ("0", "-1", "true", '"10"', "10.5"):
            _write_config(repo=tmp_path, key=key, value=value)

            refusal = module.resolve_adopted_cycle_ceilings(cwd=tmp_path)

            assert isinstance(refusal, str)
            assert key in refusal
