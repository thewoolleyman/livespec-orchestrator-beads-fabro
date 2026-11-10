"""The prepare-step payload carrier: rendering, writing and refusing (bd-ib-coxsfu).

A payload rides a step's `env`, and the step's script only writes it. Every claim
here is made by EXECUTING the written step under `sh`, because a substring check
on the script cannot tell a verbatim write from one that expands the payload's
own `$`, backticks and backslashes, or one that silently writes nothing.
"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    MAX_PACKABLE_CHUNK_BYTES,
    MAX_PAYLOAD_VALUE_BYTES,
    PAYLOAD_ENV_VAR,
    PrepareStep,
    pack_payload,
    packed_payload_decode_command,
    packed_payload_write_command,
    payload_guard_command,
    payload_write_command,
    render_prepare_step,
)

from tests.prepare_step_support import env_of, steps_in, unpacked

_HOSTILE = (
    "line one $(touch /tmp/never) `date` \\n 'quoted' \"double\" ${HOME}\nno trailing newline"
)


def _run(*, step: PrepareStep, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", step.script],
        cwd=cwd,
        env=env_of(step=step, base={"PATH": "/usr/bin:/bin"}),
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_rendered_step_round_trips_through_a_toml_parser() -> None:
    step = PrepareStep(script="echo hi\n", env={PAYLOAD_ENV_VAR: _HOSTILE})

    [parsed] = steps_in(block=render_prepare_step(step=step))

    assert parsed == step


def test_a_step_without_env_renders_no_env_key() -> None:
    assert "env" not in render_prepare_step(step=PrepareStep(script="true")).replace("[[", "")


def test_the_write_lands_the_payload_byte_for_byte(tmp_path: Path) -> None:
    step = PrepareStep(
        script=payload_write_command(path_word='"out.txt"'),
        env={PAYLOAD_ENV_VAR: _HOSTILE},
    )

    completed = _run(step=step, cwd=tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == _HOSTILE


def test_append_adds_to_the_file_rather_than_replacing_it(tmp_path: Path) -> None:
    first = PrepareStep(
        script=payload_write_command(path_word="out.txt"), env={PAYLOAD_ENV_VAR: "ab"}
    )
    second = PrepareStep(
        script=payload_write_command(path_word="out.txt", append=True), env={PAYLOAD_ENV_VAR: "cd"}
    )

    assert _run(step=first, cwd=tmp_path).returncode == 0
    assert _run(step=second, cwd=tmp_path).returncode == 0

    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "abcd"


def test_a_step_whose_env_was_not_delivered_fails_instead_of_writing_an_empty_file(
    tmp_path: Path,
) -> None:
    undelivered = PrepareStep(script=payload_write_command(path_word="out.txt"))

    completed = _run(step=undelivered, cwd=tmp_path)

    assert completed.returncode != 0
    assert PAYLOAD_ENV_VAR in completed.stderr
    assert "was not delivered" in completed.stderr
    assert not (tmp_path / "out.txt").exists()


def test_the_guard_names_a_custom_variable() -> None:
    assert "LIVESPEC_X" in payload_guard_command(var="LIVESPEC_X")


def test_a_value_over_the_cap_is_refused_before_a_run_exists() -> None:
    at_cap = PrepareStep(script="true", env={PAYLOAD_ENV_VAR: "x" * MAX_PAYLOAD_VALUE_BYTES})
    over_cap = PrepareStep(
        script="true", env={PAYLOAD_ENV_VAR: "x" * (MAX_PAYLOAD_VALUE_BYTES + 1)}
    )

    assert render_prepare_step(step=at_cap)
    with pytest.raises(ValueError, match="argument list too long") as excinfo:
        _ = render_prepare_step(step=over_cap)
    assert str(MAX_PAYLOAD_VALUE_BYTES + 1) in str(excinfo.value)


def test_a_value_is_measured_in_bytes_not_characters() -> None:
    wide = PrepareStep(script="true", env={PAYLOAD_ENV_VAR: "é" * MAX_PAYLOAD_VALUE_BYTES})

    with pytest.raises(ValueError, match="argument list too long"):
        _ = render_prepare_step(step=wide)


def test_an_env_name_that_is_not_a_shell_variable_is_refused() -> None:
    with pytest.raises(ValueError, match="not an upper-case shell variable name"):
        _ = render_prepare_step(step=PrepareStep(script="true", env={"bad name": "v"}))


# A packed payload must survive everything a plain one did, plus the two kinds of
# text the packing itself could mangle: a non-BMP character and DEL.
_PACKED_HOSTILE = _HOSTILE + " \U0001f916 é \x7f"


def test_a_packed_payload_round_trips_byte_for_byte() -> None:
    packed = pack_payload(text=_PACKED_HOSTILE)

    assert "\n" not in packed
    assert unpacked(value=packed) == _PACKED_HOSTILE
    assert pack_payload(text=_PACKED_HOSTILE) == packed


def test_the_packed_write_lands_the_source_byte_for_byte(tmp_path: Path) -> None:
    step = PrepareStep(
        script=packed_payload_write_command(path_word='"out.txt"'),
        env={PAYLOAD_ENV_VAR: pack_payload(text=_PACKED_HOSTILE)},
    )

    completed = _run(step=step, cwd=tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "out.txt").read_bytes() == _PACKED_HOSTILE.encode("utf-8")


def test_a_packed_append_adds_to_the_file_rather_than_replacing_it(tmp_path: Path) -> None:
    first = PrepareStep(
        script=packed_payload_write_command(path_word="out.txt"),
        env={PAYLOAD_ENV_VAR: pack_payload(text="ab")},
    )
    second = PrepareStep(
        script=packed_payload_write_command(path_word="out.txt", append=True),
        env={PAYLOAD_ENV_VAR: pack_payload(text="cd")},
    )

    assert _run(step=first, cwd=tmp_path).returncode == 0
    assert _run(step=second, cwd=tmp_path).returncode == 0

    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "abcd"


def test_a_value_that_does_not_decode_fails_the_step(tmp_path: Path) -> None:
    step = PrepareStep(
        script="set -eu\n" + packed_payload_write_command(path_word="out.txt"),
        env={PAYLOAD_ENV_VAR: "plain text, never packed"},
    )

    assert _run(step=step, cwd=tmp_path).returncode != 0


def test_an_undelivered_packed_payload_fails_naming_its_variable(tmp_path: Path) -> None:
    completed = _run(
        step=PrepareStep(script=packed_payload_decode_command(var="LIVESPEC_X")), cwd=tmp_path
    )

    assert completed.returncode != 0
    assert "LIVESPEC_X" in completed.stderr


def test_a_chunk_of_the_packable_size_packs_under_the_value_cap() -> None:
    # Random bytes rendered as text barely compress, so packing them is close to
    # the worst growth a packed chunk can see.
    noise = base64.b85encode(os.urandom(MAX_PACKABLE_CHUNK_BYTES)).decode("ascii")
    chunk = noise[:MAX_PACKABLE_CHUNK_BYTES]

    assert len(pack_payload(text=chunk).encode()) <= MAX_PAYLOAD_VALUE_BYTES
