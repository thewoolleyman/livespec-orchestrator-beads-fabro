"""Running a rendered prepare step the way the engine does: its script, with its env.

A payload-bearing prepare step keeps its bytes in the step's own `env` table and
its script only writes them (`_dispatcher_prepare_payload`). A test that wants to
EXECUTE such a step therefore needs both halves, and a script run alone fails the
step's own payload guard rather than writing an empty helper.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import PrepareStep

__all__: list[str] = [
    "env_of",
    "runnable_script",
    "steps_in",
]


def runnable_script(*, step: PrepareStep) -> str:
    """The step's script preceded by an `export` for each env entry it carries."""
    exports = "".join(
        f"export {name}={shlex.quote(value)}\n" for name, value in sorted(step.env.items())
    )
    return exports + step.script


def steps_in(*, block: str) -> list[PrepareStep]:
    """Every `[[run.prepare.steps]]` entry of a rendered block, decoded by a TOML parser."""
    document = tomli.loads(block)
    raw = document.get("run", {}).get("prepare", {}).get("steps", [])
    return [
        PrepareStep(script=str(entry["script"]), env=_string_env(raw=entry.get("env", {})))
        for entry in raw
    ]


def env_of(*, step: PrepareStep, base: Mapping[str, str]) -> dict[str, str]:
    """`base` overlaid with the step's own env, as the engine's child process sees it."""
    return {**base, **step.env}


def _string_env(*, raw: Mapping[str, object]) -> dict[str, str]:
    return {name: str(value) for name, value in raw.items()}
