"""Running a rendered prepare step the way the engine does: its script, with its env.

A payload-bearing prepare step keeps its bytes in the step's own `env` table and
its script only writes them (`_dispatcher_prepare_payload`). A test that wants to
EXECUTE such a step therefore needs both halves, and a script run alone fails the
step's own payload guard rather than writing an empty helper.
"""

from __future__ import annotations

import base64
import gzip
import re
import shlex
import zlib
from collections.abc import Mapping

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import PrepareStep

__all__: list[str] = [
    "env_of",
    "readable",
    "readable_block",
    "runnable_script",
    "steps_in",
    "unpacked",
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


def unpacked(*, value: str) -> str:
    """A packed payload value's text, decoded here rather than by the module under test."""
    return gzip.decompress(base64.b64decode(value)).decode("utf-8")


_BASE64_LINE = re.compile(r"[A-Za-z0-9+/]+={0,2}")
_GZIP_MAGIC = b"\x1f\x8b"


def readable(*, value: str) -> str:
    """An env value as a reader searches it: a packed payload decoded, anything else as is.

    A value that is base64 of a gzip stream is decoded TOLERANTLY, so a chunk cut
    from the middle of a larger archive yields what it can rather than raising;
    a value that is not one is returned unchanged.
    """
    raw = base64.b64decode(value) if _BASE64_LINE.fullmatch(value) else b""
    if not raw.startswith(_GZIP_MAGIC):
        return value
    inflated = zlib.decompressobj(wbits=zlib.MAX_WBITS | 16).decompress(raw)
    return inflated.decode("utf-8", errors="replace")


def readable_block(*, block: str) -> str:
    """A rendered block's text with every step's env values made readable beside its script."""
    return "\n".join(
        "\n".join([step.script, *(readable(value=value) for value in step.env.values())])
        for step in steps_in(block=block)
    )
