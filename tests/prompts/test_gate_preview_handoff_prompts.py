"""Prompt contract for recording the last implement gate-preview verdict."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS = _ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "prompts"


def test_red_and_green_prompts_require_gate_preview_repair_and_handoff_verdicts() -> None:
    """A later command node receives the gate facts, never an assumed clean tree."""
    for stage in ("red", "green"):
        prompt = (_PROMPTS / f"{stage}.md").read_text(encoding="utf-8")
        normalized = " ".join(prompt.split())
        assert "livespec-implement-gate-preview.py" in prompt
        assert f'gate-preview.py" {stage}' in prompt
        assert "Fix every failed target the preview names" in normalized
        assert "run the preview again after each fix" in normalized
        assert "exit status and failed target names of the last gate preview run" in normalized
        assert "If no preview ran, state that and why." in prompt


def test_red_prompt_names_the_test_file_to_the_preview() -> None:
    """The Red preview is told which test file commit_red will stage."""
    prompt = (_PROMPTS / "red.md").read_text(encoding="utf-8")
    assert 'gate-preview.py" red <path of the test file you wrote>' in prompt
