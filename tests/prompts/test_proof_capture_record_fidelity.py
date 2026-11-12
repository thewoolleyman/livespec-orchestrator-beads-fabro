"""The capture prompt must reject records a fresh checkout cannot replay.

`proof_capture` authors and posts its record directly from this prompt, so the
pre-publication guard belongs in the prompt rather than a host-side parser that
would only learn about an invalid record after it was published.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
    / "proof-capture.md"
)


def _text() -> str:
    """The capture instructions that author the published record."""
    return _PROMPT.read_text(encoding="utf-8")


def test_capture_preflight_refuses_untracked_step_programs_with_step_and_path() -> None:
    """A scratch helper cannot reach the forge as an otherwise-valid record."""
    text = _text()

    for required in (
        "Before posting, validate every numbered reproduction step",
        "Refuse to publish",
        "`/tmp`",
        "recorded publish-branch head",
        "numbered step and the invoked path",
    ):
        assert required in text, required


def test_capture_requires_steps_to_print_concrete_values_without_shell_expansion() -> None:
    """A replayable command also has to show the concrete observation it proves."""
    text = _text()

    for required in (
        "Each step must print the resolved value it proves",
        "not merely the variable name, task label, or other name",
        "No reproduction-step command may contain a dollar sign (`$`) outside single quotes",
        "direct-read grammar",
    ):
        assert required in text, required


def test_capture_posts_only_through_the_head_validating_primitive() -> None:
    """A captured record without its recorded tree identity is never posted."""
    text = _text()

    for required in (
        "livespec_post_captured_record",
        "LIVESPEC_PROOF_CAPTURE_MISSING_PUBLISH_BRANCH_HEAD",
        "must post only through",
        "Publish-branch head:",
    ):
        assert required in text, required
