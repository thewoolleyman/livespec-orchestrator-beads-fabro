"""Pin the append-only handoff contract for the future Red and Green nodes.

The workflow wiring is deliberately outside this slice.  These prompt files are
the independently shipped instruction payload that wiring will select, so this
test reads their committed bytes directly and makes every handoff requirement
observable before that sibling change lands.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "prompts"
)
_RED_PROMPT = _PROMPTS_DIR / "red.md"
_GREEN_PROMPT = _PROMPTS_DIR / "green.md"
_HANDOFF_COMMAND = "git rev-parse --git-path livespec-implement-handoff.md"


def _prompt(*, path: Path) -> str:
    """Read a prompt whose path is asserted on disk by the calling test."""
    assert path.is_file(), f"missing prompt {path}"
    return path.read_text(encoding="utf-8")


def test_red_and_green_prompts_direct_the_append_only_implement_handoff() -> None:
    """Each fresh node receives the complete, non-rewriting handoff contract."""
    red = _prompt(path=_RED_PROMPT)
    green = _prompt(path=_GREEN_PROMPT)

    for phrase in (
        "Write one failing test for one Definition of Done assertion.",
        "Run only that test and capture its failure output.",
        "Do not make a commit.",
        _HANDOFF_COMMAND,
        "## red",
        "Test file",
        "Definition of Done assertion",
        "what the test verifies and does not verify",
        "code locations for the change",
        "declared `already-satisfied` outcome",
    ):
        assert phrase in red, f"the red prompt omits {phrase!r}"

    for phrase in (
        "Read the handoff file",
        "Make the Red test pass by changing implementation files only.",
        "Run only the tests your change touches.",
        "Do not make a commit.",
        "Never change the Red test file.",
        _HANDOFF_COMMAND,
        "## green",
        "what changed",
        "which tests ran",
        "declared `test-wrong` outcome and its reason",
    ):
        assert phrase in green, f"the green prompt omits {phrase!r}"

    for prompt in (red, green):
        assert "append" in prompt, "the prompt does not direct an append"
        assert (
            "never rewrite an earlier section" in prompt
        ), "the prompt does not protect prior handoff sections"
