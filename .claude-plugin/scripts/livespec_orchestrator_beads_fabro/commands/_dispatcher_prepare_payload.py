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

WHY EVERY PLAIN-TEXT PAYLOAD IS PACKED. The overlay these steps render into is
collected as the run's `workflow.toml`, and the engine caps that ONE file at
524,288 bytes (Fabro `MAX_WORKFLOW_VERSION_FILE_BYTES`, per file, not per
package). Helper programs carried as plain text pay that budget twice: once for
their bytes and again for the JSON escaping every newline and quote takes in a
TOML basic string. After v0.312.3 the livespec-dev-tooling overlay measured
524,343 bytes and every dispatch there was refused before listing
(bd-ib-p5e32s); about 185 KB of it was plain helper source, while the one payload
already packed, the gh-refresh bundle, cost a third of its raw size. So a
plain-text payload rides `pack_payload` -- gzip, then base64, one line with
nothing to escape -- and its step decodes it with `packed_payload_write_command`.
The decoder is `python3`, which the prepare chain already requires (the
gh-refresh unpack and the plugin-cache gate run under it), rather than
`base64 -d | gunzip`, which the sandbox image does not promise.

`payload_write_command` stays for a value that is ALREADY packed -- the
gh-refresh archive chunks are base64 of a gzip tarball, and packing them again
would only add bytes.
"""

from __future__ import annotations

import base64
import gzip
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

__all__: list[str] = [
    "DECODE_FAILED_CAUSE",
    "MAX_PACKABLE_CHUNK_BYTES",
    "MAX_PAYLOAD_VALUE_BYTES",
    "PAYLOAD_ENV_VAR",
    "PrepareStep",
    "pack_payload",
    "packed_payload_write_command",
    "payload_guard_command",
    "payload_write_command",
    "render_prepare_step",
]

PAYLOAD_ENV_VAR = "LIVESPEC_PREPARE_PAYLOAD"
MAX_PAYLOAD_VALUE_BYTES = 96000
# The largest plain-text piece whose PACKED form still fits one env value. Base64
# grows its input by 4/3 and gzip can grow incompressible input by a few bytes per
# block, so a piece of three quarters of the cap, less a margin for the gzip
# framing, packs under `MAX_PAYLOAD_VALUE_BYTES` whatever its content.
MAX_PACKABLE_CHUNK_BYTES = MAX_PAYLOAD_VALUE_BYTES // 4 * 3 - 1024
# The decoder every packed step runs. It reads the packed value on stdin and
# lands the decoded bytes at argv[1] (appending when argv[2] is "1"). It FAILS
# CLOSED: a base64 or gzip error (gzip checks its CRC32 and length) exits
# non-zero naming `DECODE_FAILED_CAUSE`, the file and the reason, and the bytes
# go to a temporary file in the target's directory that is renamed into place
# only after the whole value decoded, so no partial helper is ever left where a
# later stage would run it. The target keeps the mode a shell redirect gives it:
# its own when it exists, the umask's otherwise. It is terse on purpose: it rides
# in every packed step's script, inside the very file whose size it protects, and
# no single quote may appear in it because it sits in a single-quoted shell word.
DECODE_FAILED_CAUSE = "LIVESPEC_PREPARE_PAYLOAD_DECODE_FAILED"
_DECODE_PROGRAM = (
    "import base64 as b,gzip as g,os,sys,tempfile as t\n"
    "p,a=sys.argv[1:3]\n"
    "try:d=g.decompress(b.b64decode(sys.stdin.buffer.read(),validate=1))\n"
    f'except Exception as e:sys.exit("{DECODE_FAILED_CAUSE}: %s: %s"%(p,e))\n'
    "x=os.path.exists(p)\n"
    'if a=="1"and x:d=open(p,"rb").read()+d\n'
    "u=os.umask(0);os.umask(u)\n"
    'f,n=t.mkstemp(dir=os.path.dirname(p)or".");o=os.fdopen(f,"wb");o.write(d);o.close()\n'
    "os.chmod(n,os.stat(p).st_mode&4095 if x else 438&~u);os.replace(n,p)"
)
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


def pack_payload(*, text: str) -> str:
    """`text` as one line of gzip+base64, the form a plain-text payload rides in.

    The gzip header's clock is fixed, so the same text always packs to the same
    value and the rendered overlay stays deterministic.
    """
    packed = gzip.compress(text.encode("utf-8"), compresslevel=9, mtime=0)
    return base64.b64encode(packed).decode("ascii")


def packed_payload_write_command(
    *, path_word: str, var: str = PAYLOAD_ENV_VAR, append: bool = False
) -> str:
    """The shell lines that decode one packed payload into `path_word`.

    `path_word` is a complete, already-quoted shell word, as for
    `payload_write_command`; it reaches the decoder as an argument, so the
    decoder, not a shell redirect, creates the file. A payload that does not
    decode fails the step whether or not `set -e` is on, because the pipeline's
    status is the decoder's and the step's last command is that pipeline or a
    `set -e` script line.
    """
    mode = "1" if append else "0"
    return (
        f"{payload_guard_command(var=var)}\n"
        f"printf %s \"${var}\" | python3 -c '{_DECODE_PROGRAM}' {path_word} {mode}"
    )


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
