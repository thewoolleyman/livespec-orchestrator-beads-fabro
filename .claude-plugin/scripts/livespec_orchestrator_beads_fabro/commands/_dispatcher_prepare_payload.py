"""Carrying a prepare step's payload in the step's `env` table, not its script.

WHY THE PAYLOAD LEAVES THE SCRIPT. The Petri-era engine's default `compact`
fidelity renders every completed command stage into the preamble of every later
agent request as its FULL `Script:` text, and renders none of the stage's `env`
(`crates/attractor/steps/src/fidelity.rs`, `Detail::Compact`). A prepare step
that embeds a helper program, or a base64 archive, in its script therefore
re-sends those bytes on every turn of every agent node: measured on petri, 46
prepare scripts were 358,046 characters, about 241,400 tokens, 71% of the
338k-token first-request floor (`plan/factory-context-per-turn-reduction`,
research note 003). The payload is plumbing no agent turn reads.

So a payload step is split in two. The SCRIPT is a short fixed command that
writes a variable to its path; the bytes ride the step's own `env` table, which
only the step's process sees. The file the sandbox ends up with is identical
either way, which is what `payload_write_command` is for: `printf %s` of the
variable writes exactly the text the heredoc used to, with no added newline and
no expansion of the payload's own `$`, backticks or backslashes.

WHY THE VARIABLE IS CHECKED BEFORE IT IS WRITTEN. A step whose `env` the engine
did not deliver would otherwise write an EMPTY helper and succeed, and the
failure would surface minutes later as a stage reporting a program that does
nothing. `${VAR:?}` aborts the step instead, naming the variable.

WHY THE STRINGS ARE NOT ASCII-ESCAPED. `json.dumps` writes a character outside the
Basic Multilingual Plane as a SURROGATE PAIR (`\\ud83e\\udd16`), which JSON accepts and
TOML rejects as "not a Unicode scalar value": a pull-request body carrying one
emoji made the whole overlay unparseable. TOML basic strings are UTF-8, so the
text is written as itself, with the one character JSON leaves raw and TOML
forbids (DEL) escaped.

WHY EACH VALUE IS CAPPED. An environment string is bounded by the kernel's
per-string exec limit (`MAX_ARG_STRLEN`, 128 KiB), independently of the larger
total. A value over it makes `execve` fail with `E2BIG` and kills the run at
launch with no branch (`bd-ib-gnli`). The cap is deliberately under the limit,
the same margin the gh-refresh chunking already used.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

__all__: list[str] = [
    "MAX_PAYLOAD_VALUE_BYTES",
    "PAYLOAD_ENV_VAR",
    "PrepareStep",
    "payload_guard_command",
    "payload_write_command",
    "render_prepare_step",
]

PAYLOAD_ENV_VAR = "LIVESPEC_PREPARE_PAYLOAD"
MAX_PAYLOAD_VALUE_BYTES = 96000
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(frozen=True, kw_only=True)
class PrepareStep:
    """One `[[run.prepare.steps]]` entry: its script and its own env table."""

    script: str
    env: Mapping[str, str] = field(default_factory=dict[str, str])


def payload_guard_command(*, var: str = PAYLOAD_ENV_VAR) -> str:
    """The shell line that aborts the step when its payload variable is empty."""
    return f': "${{{var}:?livespec prepare payload {var} was not delivered to this step}}"'


def payload_write_command(
    *, path_word: str, var: str = PAYLOAD_ENV_VAR, append: bool = False
) -> str:
    """The shell lines that write one env payload to `path_word`, verbatim.

    `path_word` is a COMPLETE shell word the caller has already quoted (for
    example `"$root/helper.py"`), because the destination is usually built from
    an expansion this module must not re-interpret.
    """
    redirect = ">>" if append else ">"
    return f'{payload_guard_command(var=var)}\nprintf %s "${var}" {redirect} {path_word}'


def _toml_string(*, value: str) -> str:
    """One TOML basic string, with no surrogate-pair escapes."""
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def render_prepare_step(*, step: PrepareStep) -> str:
    """Render one step as TOML text, refusing a payload the kernel would reject."""
    lines = ["[[run.prepare.steps]]", f"script = {_toml_string(value=step.script)}"]
    if step.env:
        entries: list[str] = []
        for name in sorted(step.env):
            if _ENV_NAME.match(name) is None:
                msg = f"prepare-step env name {name!r} is not an upper-case shell variable name"
                raise ValueError(msg)
            size = len(step.env[name].encode())
            if size > MAX_PAYLOAD_VALUE_BYTES:
                msg = (
                    f"prepare-step env value {name} is {size} bytes, over the "
                    f"{MAX_PAYLOAD_VALUE_BYTES}-byte limit; it would fail execve "
                    "with 'argument list too long' and destroy the run"
                )
                raise ValueError(msg)
            entries.append(f"{name} = {_toml_string(value=step.env[name])}")
        lines.append("env = { " + ", ".join(entries) + " }")
    return "\n".join(lines) + "\n"
