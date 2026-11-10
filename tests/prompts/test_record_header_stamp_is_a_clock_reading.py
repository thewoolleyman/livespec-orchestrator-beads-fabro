"""A record header's UTC time is a clock reading taken where the header is WRITTEN.

bd-ib-yvmtrm. The `proof_verify` and `review` prompts asked only for "an
ISO-8601 UTC timestamp" and "<UTC timestamp>", so the agent wrote a time it made
up. Measured fleet-wide over 2026-11-03 to 2026-11-10: 194 of 506 `verified` and
`not_reproduced` records and 50 of 301 `Review findings` records carried a header
time more than 120 s from their own comment's creation time, nearly all ending in
`:00Z`, and three were about 20 hours in the future. The `proof_capture` prompt
computes the stamp with `date -u` in the same command that writes the header, and
its records were stamped within seconds of posting.

A prompt test because the header is authored by the agent out of this prose and
is rendered by no Python caller: the stamp is not observable until a factory run
dispatched after this change ships.
"""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

import pytest

_PROMPTS = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
)
# The clock reading the capture prompt already uses, spelled once here.
_CLOCK_READING = 'stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"'
# (prompt file, the text a command writing that prompt's header starts with)
_HEADER_WRITERS = [
    pytest.param("proof-verify.md", "printf 'Proof of Done — ", id="proof_verify"),
    pytest.param("review.md", "printf 'Review findings — ", id="review"),
]


def _text(*, prompt: str) -> str:
    return (_PROMPTS / prompt).read_text(encoding="utf-8")


def _header_command_blocks(*, prompt: str, header_write: str) -> list[list[str]]:
    """Every indented command block whose `printf` writes the prompt's header.

    BLOCKS rather than the whole prompt, because the claim is that the clock
    reading and the header write are ONE command: a `date -u` named paragraphs
    earlier is a time read before the body was composed, which is how a stale
    stamp is produced.
    """
    runs = groupby(_text(prompt=prompt).splitlines(), key=lambda line: line.startswith("    "))
    blocks = [list(lines) for indented, lines in runs if indented]
    return [one for one in blocks if any(header_write in line for line in one)]


@pytest.mark.parametrize(("prompt", "header_write"), _HEADER_WRITERS)
def test_the_header_time_is_read_from_the_clock_in_the_command_that_writes_it(
    prompt: str, header_write: str
) -> None:
    """The header's time comes from `date -u`, inside the command that writes it."""
    blocks = _header_command_blocks(prompt=prompt, header_write=header_write)

    assert len(blocks) == 1, blocks
    assert any(line.strip() == _CLOCK_READING for line in blocks[0]), blocks[0]
    assert any('"$stamp"' in line for line in blocks[0] if header_write in line), blocks[0]


@pytest.mark.parametrize("prompt", ["proof-verify.md", "review.md"])
def test_the_prompt_forbids_a_time_the_agent_composed_itself(prompt: str) -> None:
    """The prose says the time is a clock reading and never an estimate."""
    prose = " ".join(_text(prompt=prompt).split())

    assert "never a time you estimated, rounded or composed yourself" in prose, prose
    assert "no later than the instant" in prose, prose
