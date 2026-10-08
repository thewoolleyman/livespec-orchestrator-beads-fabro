"""The head declaration's grammar, and the stage fallback's default.

Three arms of `_dispatcher_resume_anchor` that the anchor's own scenarios do not
reach, each asserted here because each is the fail-closed direction of a reading
that would otherwise look correct.

A NESTED FENCE. A record legitimately carries one fence inside another — a proof
that prints part of a Markdown file prints that file's own fences, and an excerpt
can carry one half of a pair. The fence tracker therefore carries the OPEN
delimiter rather than a boolean, and this file asserts the inner delimiter does
NOT close the outer one. A boolean would invert on that line and stay inverted,
after which every remaining line reads as fenced and a genuine head declaration
BELOW the proof is never seen — so a record that does name its head would be read
as naming none, and a resume that should proceed would refuse.

A LABEL LINE THAT IS NOT A SHA. The label is prose a capture agent writes, so it
can carry an abbreviated sha, a branch name, or a sentence. None of those is a
head a resume can hold a pull request to, and treating one as a head would send
the head-moved refusal after a value the forge can never equal — which refuses
every resume while reporting a mismatch that does not exist.

AN UNRECOGNISED VERDICT. The clause's fallback table names four verdicts and
`proof_capture` for "no such record". A verdict outside the table is the same
situation: nothing a later stage could build on was published, so capture is the
first stage with work left. The table's `.get` default is what says so, and
without this assertion a future verdict word would silently resume at whichever
stage a `KeyError` handler happened to pick.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_resume_anchor.py"
)

_HEAD = "c" * 40


def _anchor_module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def test_an_inner_fence_delimiter_does_not_close_the_outer_fence() -> None:
    """A head line between a nested delimiter and the real close stays fenced."""
    module = _anchor_module()
    body = "\n".join(
        (
            "Proof of Done — verified — run run-1 — 2026-10-08T00:00:00Z",
            "```",
            "~~~",
            f"{module.PUBLISH_HEAD_LABEL}: {'d' * 40}",
            "~~~",
            "```",
            f"{module.PUBLISH_HEAD_LABEL}: {_HEAD}",
        )
    )
    assert module.published_head(body=body) == _HEAD


def test_a_label_line_carrying_no_full_sha_declares_no_head() -> None:
    """An abbreviated sha, a branch name and prose are each not a head."""
    module = _anchor_module()
    for value in ("c" * 7, "feat/bd-ib-fngpwg", "the branch tip"):
        body = f"{module.PUBLISH_HEAD_LABEL}: {value}\n"
        assert module.published_head(body=body) is None


def test_a_verdict_outside_the_table_falls_back_to_proof_capture() -> None:
    """An unknown verdict published nothing a later stage could build on."""
    module = _anchor_module()
    assert (
        module.resumed_at_for_verdict(verdict="a_word_no_stage_publishes")
        == module.RESUMED_AT_PROOF_CAPTURE
    )
