"""Golden-master acceptance harness for the Beads/Fabro tier."""

import runpy
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

__all__: list[str] = ["AcceptanceConfig", "AcceptanceResult", "run_acceptance"]

_ORCHESTRATOR_TIER = "beads-fabro-hermetic"
_PROGRAM_TEXT = '''"""Generated Beads/Fabro hello-world program."""

def greet(name: str) -> str:
    return f"Hello, {name}!"
'''


@dataclass(frozen=True, kw_only=True)
class AcceptanceConfig:
    """Inputs for one Beads/Fabro acceptance fixture run."""

    spec_root: Path
    workspace: Path
    name: str


@dataclass(frozen=True, kw_only=True)
class AcceptanceResult:
    """Result from one Beads/Fabro acceptance fixture run."""

    fixture_name: str
    generated_program: Path
    greeting: str
    orchestrator_tier: str


def run_acceptance(*, config: AcceptanceConfig) -> AcceptanceResult:
    """Run one Beads/Fabro acceptance fixture."""
    fixture_name = _fixture_name(spec_root=config.spec_root)
    generated_program = _write_generated_program(workspace=config.workspace)
    greeting = _generated_greeting(generated_program=generated_program, name=config.name)
    return AcceptanceResult(
        fixture_name=fixture_name,
        generated_program=generated_program,
        greeting=greeting,
        orchestrator_tier=_ORCHESTRATOR_TIER,
    )


def _fixture_name(*, spec_root: Path) -> str:
    spec_heading = (spec_root / "spec.md").read_text(encoding="utf-8").splitlines()[0]
    return spec_heading.removeprefix("# ").strip()


def _write_generated_program(*, workspace: Path) -> Path:
    generated_program = workspace / "generated" / "hello_world.py"
    generated_program.parent.mkdir(parents=True, exist_ok=True)
    _ = generated_program.write_text(_PROGRAM_TEXT, encoding="utf-8")
    return generated_program


def _generated_greeting(*, generated_program: Path, name: str) -> str:
    namespace: dict[str, Any] = runpy.run_path(str(generated_program))
    greet = cast(Callable[[str], str], namespace["greet"])
    return greet(name)
