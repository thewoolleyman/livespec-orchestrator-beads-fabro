"""The Definition-of-Done judgement subject, delivered to the `dod_gate` node alone.

WHY A FILE AND NOT THE GOAL. From v0.310.0 the dispatch goal appended the whole
judgement subject (bd-ib-tzvtgc, measured on bd-ib-qshcwc: 24,910 to 136,040
characters). Fabro injects the goal into EVERY ACP node, so each request of each
node carried the item's referenced spec sections although only `dod_gate` grades
them. The one-rubric-one-subject rule of `contracts.md` still requires the node
and every host taking to grade BYTE-IDENTICAL subjects, and since the bounded
clause selection the node cannot rebuild the subject by reading the spec tree
itself. So the subject is rendered here, host-side, by the same
`judgement_subject` every host taking calls, and a prepare step materializes it
as a file that only the `dod_gate` prompt tells its node to read.

Four properties an editor must not invert. The subject is NOT escaped through the
MiniJinja escaper: a file is not templated, and escaping would make the node grade
different bytes from a host taking. The governing-heading verdict is the one the
pre-dispatch taking RECORDED, reused by its own reuse rule exactly as the goal's
verdict block reads it, because a second taking here would run a model per
dispatch and could disagree with the taking whose verdict the host record names.
The bytes ride the steps' `env` tables and the scripts only write them
(`_dispatcher_prepare_payload`), so the script text Fabro re-sends with every
later request stays a few hundred characters. And a subject over one env value's
cap is split across several steps that APPEND in order, on UTF-8 boundaries, so
the file the node reads is the subject exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    reusable_governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    judgement_subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    MAX_PAYLOAD_VALUE_BYTES,
    PAYLOAD_ENV_VAR,
    PrepareStep,
    payload_write_command,
    render_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DOD_GATE_SUBJECT_FILENAME",
    "DOD_GATE_SUBJECT_MARKER",
    "dod_gate_subject",
    "dod_gate_subject_path_expansion",
    "dod_gate_subject_prepare_steps_block",
]

DOD_GATE_SUBJECT_FILENAME = "livespec-dod-gate-subject.md"

# Emitted on stdout by every step, so a run's setup log says where the subject landed.
DOD_GATE_SUBJECT_MARKER = "LIVESPEC_DOD_GATE_SUBJECT_MATERIALIZED"

_UTF8_CONTINUATION_MASK = 0xC0
_UTF8_CONTINUATION_BITS = 0x80


def dod_gate_subject(*, item: WorkItem, repo: Path, comments: Sequence[str]) -> str:
    """The subject the `dod_gate` node grades: what a host taking grades for this item.

    `comments` is the item's ledger comment bodies, oldest first, exactly as the
    goal reads them.
    """
    governing = reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)
    return judgement_subject(item=item, cwd=repo, comments=comments, governing=governing)


def dod_gate_subject_path_expansion() -> str:
    """The path both the prepare steps and the `dod_gate` prompt resolve.

    One spelling, for the reason `_dispatcher_sandbox_plugins` gives: a node
    reading a different path than the step that wrote the file finds no file.
    """
    return f"{sandbox_plugins_root_expansion()}/{DOD_GATE_SUBJECT_FILENAME}"


def dod_gate_subject_prepare_steps_block(*, subject: str | None) -> str:
    """Prepare steps that materialize the subject inside the sandbox, or nothing.

    The first step creates the file and each later one appends its chunk. A
    caller rendering no subject projects no step, which is exactly the overlay
    every direct caller rendered before.
    """
    if not subject:
        return ""
    root = sandbox_plugins_root_expansion()
    steps = [
        PrepareStep(
            script="\n".join(
                [
                    "set -eu",
                    f'root="{root}"',
                    'mkdir -p "$root"',
                    payload_write_command(
                        path_word=f'"$root/{DOD_GATE_SUBJECT_FILENAME}"', append=index > 0
                    ),
                    f'echo "{DOD_GATE_SUBJECT_MARKER}: $root/{DOD_GATE_SUBJECT_FILENAME}"',
                ]
            ),
            env={PAYLOAD_ENV_VAR: chunk},
        )
        for index, chunk in enumerate(_chunks(text=subject))
    ]
    header = (
        "\n# --- Dispatcher-materialized Definition-of-Done judgement subject: only the\n"
        "# --- `dod_gate` prompt reads it, so no other node's goal carries it ---\n"
    )
    return header + "".join(render_prepare_step(step=step) for step in steps)


def _chunks(*, text: str) -> list[str]:
    """`text` split into pieces within one env value's byte cap, on character boundaries."""
    data = text.encode()
    chunks: list[str] = []
    start = 0
    while start < len(data):
        end = min(start + MAX_PAYLOAD_VALUE_BYTES, len(data))
        while end < len(data) and data[end] & _UTF8_CONTINUATION_MASK == _UTF8_CONTINUATION_BITS:
            end -= 1
        chunks.append(data[start:end].decode())
        start = end
    return chunks
