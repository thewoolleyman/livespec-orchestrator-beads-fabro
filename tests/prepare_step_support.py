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
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_materialize import materialize
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import (
    PLUGINS_ROOT,
    Helper,
    helper_manifest_text,
    helper_registry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    PLUGIN_GATE_PROGRAM_FILENAME,
    plugin_cache_gate_prepare_step,
    plugin_cache_gate_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import PrepareStep
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

__all__: list[str] = [
    "env_of",
    "fetch_helpers",
    "land_helpers",
    "land_plugin_helpers",
    "plugin_gate_installer_script",
    "plugins_helper",
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


def land_helpers(*, roots: Mapping[str, Path]) -> list[Path]:
    """Write every helper program under the named sandbox roots given, as the fetch step does.

    The helper-fetch setup step lands each helper from the installed build's own
    commit (`_dispatcher_helper_fetch`); a test that runs a consuming step or a
    helper itself needs those files where that step would have put them. Only
    the roots named here are written, so a test about the plugins root does not
    write the gh-refresh bundle.
    """
    landed: list[Path] = []
    for helper in helper_registry():
        root = roots.get(helper.root)
        if root is None:
            continue
        target = root / helper.path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_bytes(helper.compose())
        target.chmod(helper.mode)
        landed.append(target)
    return landed


def land_plugin_helpers(*, env: Mapping[str, str]) -> Path:
    """Land every plugins-root helper where a step run under `env` resolves that root.

    The same resolution the steps' shell expansion performs: the override when it
    is set and non-empty, else `$HOME/.claude/plugins`.
    """
    override = env.get(SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR, "")
    root = Path(override) if override else Path(env["HOME"]) / ".claude" / "plugins"
    _ = land_helpers(roots={PLUGINS_ROOT: root})
    return root


_GATE_PROGRAM_END = "LIVESPEC_TEST_GATE_PROGRAM_END"


def plugin_gate_installer_script() -> str:
    """The plugin-cache gate's own step, preceded by the write the helper fetch performs.

    The gate program is a helper program the helper-fetch setup step lands below
    the plugins root before the gate's step runs; a test that runs the gate's
    shipped step body needs that file first, at the root the step itself resolves.
    """
    step = plugin_cache_gate_prepare_step()
    root = step.script.splitlines()[1]
    assert root.startswith('root="')
    program = plugin_cache_gate_program_source()
    assert _GATE_PROGRAM_END not in program
    return (
        f"{root}\n"
        'mkdir -p "$root"\n'
        f"cat > \"$root/{PLUGIN_GATE_PROGRAM_FILENAME}\" <<'{_GATE_PROGRAM_END}'\n"
        f"{program}{_GATE_PROGRAM_END}\n" + runnable_script(step=step)
    )


def plugins_helper(*, path: str) -> Helper:
    """The registered helper the fetch step writes at `path` below the plugins root."""
    [helper] = [h for h in helper_registry() if (h.root, h.path) == (PLUGINS_ROOT, path)]
    return helper


_FETCH_REPOSITORY = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"
_FETCH_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def fetch_helpers(*, roots: Mapping[str, Path]) -> int:
    """Run the helper fetch's materializer in-process against `roots`, every root named.

    The same call the setup step makes from its checkout, minus the fetch: the
    manifest is this tree's own, so every digest verifies, and any root inside a
    git worktree has its helpers named in that worktree's exclude file first.
    """
    written = materialize(
        manifest_text=helper_manifest_text(repository=_FETCH_REPOSITORY, commit=_FETCH_COMMIT),
        roots=roots,
    )
    assert isinstance(written, int), written
    return written
