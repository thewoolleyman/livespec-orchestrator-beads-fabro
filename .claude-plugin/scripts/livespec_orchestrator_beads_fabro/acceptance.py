"""Golden-master acceptance harness for the Beads/Fabro tier."""

import runpy
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "AcceptanceConfig",
    "AcceptanceResult",
    "GreetDiscoveryError",
    "LiveAcceptanceConfig",
    "run_acceptance",
    "run_live_acceptance",
]

_ORCHESTRATOR_TIER = "beads-fabro-hermetic"
_LIVE_ORCHESTRATOR_TIER = "beads-fabro-live"
_GREET_SYMBOL = "greet"
# Directories under a fresh repo checkout that never carry the generated
# program: VCS/CI metadata, byte-cache, the throwaway ledger, and the
# seed SPECIFICATION itself (a `.py` there is a fixture decoy, never the
# generated program). Skipping them keeps `greet` discovery unambiguous
# and avoids importing stale or fixture modules.
_SKIP_DIRS = frozenset({".git", ".github", "__pycache__", ".beads", "SPECIFICATION"})
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
class LiveAcceptanceConfig:
    """Inputs for one LIVE Beads/Fabro greeting assertion.

    `checkout` is a working tree of the throwaway repo at its default
    branch AFTER the Fabro-generated PR has merged; `name` is the single
    supplied greeting name (the fixture scenario uses `Ada`).
    """

    checkout: Path
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
    # The fixture contract is `greet(name: str) -> str` — a generator may make
    # the parameter positional OR keyword-only (`def greet(*, name)`, the
    # livespec family discipline). Call faithfully for either: try positional,
    # and on a TypeError that signals a keyword-only signature, retry by keyword.
    positional = attempt(action=lambda: greet(name), exceptions=(TypeError,))
    if not isinstance(positional, AttemptFailure):
        return positional
    greet_kw = cast(Callable[..., str], greet)
    return greet_kw(name=name)


def run_live_acceptance(*, config: LiveAcceptanceConfig) -> AcceptanceResult:
    """Assert the greeting produced by a merged LIVE Beads/Fabro run.

    `config.checkout` is a working tree of the throwaway repo at its
    default branch AFTER the Fabro-generated PR merged. This discovers the
    generated program (the single `.py` exposing a callable `greet`),
    calls `greet(config.name)`, and returns an `AcceptanceResult` carrying
    `orchestrator_tier="beads-fabro-live"`. A discovery failure (no
    `greet`, more than one candidate) raises a built-in exception: it is a
    factory bug, never an expected/retryable condition, so it propagates
    to the operator-facing live runner rather than being papered over.

    The returned `greeting` is asserted (== `Hello, <name>!`) by the live
    runner and the live pytest binding; this function performs the
    discovery + invocation and never weakens or fakes the comparison.
    """
    generated_program = _discover_greet_module(checkout=config.checkout)
    greeting = _generated_greeting(generated_program=generated_program, name=config.name)
    fixture_name = _fixture_name(spec_root=config.checkout / "SPECIFICATION")
    return AcceptanceResult(
        fixture_name=fixture_name,
        generated_program=generated_program,
        greeting=greeting,
        orchestrator_tier=_LIVE_ORCHESTRATOR_TIER,
    )


class GreetDiscoveryError(Exception):
    """A merged LIVE checkout did not expose exactly one callable `greet`.

    A factory bug, not an expected/retryable condition: the operator-facing
    live runner surfaces it rather than asserting on a fabricated greeting.
    """

    def __init__(self, *, detail: str) -> None:
        super().__init__(detail)


def _discover_greet_module(*, checkout: Path) -> Path:
    """Find the single `.py` under `checkout` exposing a callable `greet`.

    Walks every `.py` outside `_SKIP_DIRS`, importing each that statically
    mentions the symbol and keeping those whose module namespace binds a
    callable `greet`. Raises `GreetDiscoveryError` when none or more than
    one qualifies — both are factory bugs the operator must see.
    """
    candidates = [
        path for path in _python_files(checkout=checkout) if _module_exposes_greet(program=path)
    ]
    if not candidates:
        raise GreetDiscoveryError(
            detail=f"no module exposing a callable {_GREET_SYMBOL!r} found under {checkout}"
        )
    if len(candidates) > 1:
        joined = ", ".join(sorted(str(path) for path in candidates))
        detail = (
            f"expected exactly one module exposing {_GREET_SYMBOL!r} under "
            f"{checkout}; found {len(candidates)}: {joined}"
        )
        raise GreetDiscoveryError(detail=detail)
    return candidates[0]


def _python_files(*, checkout: Path) -> list[Path]:
    """Every `.py` under `checkout` whose path skips no `_SKIP_DIRS` segment."""
    return [
        path
        for path in sorted(checkout.rglob("*.py"))
        if _SKIP_DIRS.isdisjoint(path.relative_to(checkout).parts)
    ]


def _module_exposes_greet(*, program: Path) -> bool:
    """True iff running `program` binds a callable named `greet`.

    A `.py` that raises on import, or whose `greet` is not callable, does
    not qualify; such a file is simply not the generated program.
    """
    if _GREET_SYMBOL not in program.read_text(encoding="utf-8"):
        return False
    namespace = attempt(
        action=lambda: runpy.run_path(str(program)),
        exceptions=(
            ImportError,
            NameError,
            OSError,
            RuntimeError,
            SyntaxError,
            TypeError,
            ValueError,
        ),
    )
    if isinstance(namespace, AttemptFailure):
        return False
    return callable(namespace.get(_GREET_SYMBOL))
