"""A packed payload that does not decode refuses the run by name and leaves no file (bd-ib-p5e32s).

Compression must never change what the factory is told to do. A packed embed
that was altered in transit fails its gzip check, and the step that decodes it
must then stop the run with a NAMED cause, rather than land a truncated or empty
helper that a later stage executes. The target path must not exist afterwards,
not even as a partial file, because a later stage cannot tell a partial file
from a valid one.
"""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PAYLOAD_ENV_VAR,
    PrepareStep,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_guard import (
    REVIEW_GUARD_PROGRAM_FILENAME,
    review_guard_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

from tests.prepare_step_support import env_of, steps_in


def _flipped(*, value: str) -> str:
    """`value` with one byte of its compressed body inverted, still valid base64."""
    raw = bytearray(base64.b64decode(value))
    raw[len(raw) // 2] ^= 0xFF
    return base64.b64encode(bytes(raw)).decode("ascii")


def test_a_flipped_byte_in_a_packed_embed_refuses_by_name_and_leaves_no_file(
    tmp_path: Path,
) -> None:
    [step] = steps_in(block=review_guard_prepare_steps_block())
    tampered = PrepareStep(
        script=step.script, env={PAYLOAD_ENV_VAR: _flipped(value=step.env[PAYLOAD_ENV_VAR])}
    )
    plugins_root = tmp_path / "plugins"
    base = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
    }

    completed = subprocess.run(
        ["sh", "-c", tampered.script],
        cwd=tmp_path,
        env=env_of(step=tampered, base=base),
        capture_output=True,
        text=True,
        check=False,
    )

    facts = [
        completed.returncode != 0,
        "LIVESPEC_PREPARE_PAYLOAD_DECODE_FAILED:" in completed.stderr,
        REVIEW_GUARD_PROGRAM_FILENAME in completed.stderr,
        not (plugins_root / REVIEW_GUARD_PROGRAM_FILENAME).exists(),
        sorted(path.name for path in plugins_root.iterdir()) == [],
    ]
    assert all(facts), (facts, completed.returncode, completed.stderr)
