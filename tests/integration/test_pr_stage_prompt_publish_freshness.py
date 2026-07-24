"""PR-stage prompt freshness and bounded workflow-permission retry contract."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PR_PROMPT = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
    / "pr.md"
)
_FETCH = "mise exec -- git fetch origin master --quiet"
_REBASE = "mise exec -- git rebase origin/master"
_PUSH = "mise exec -- git push -u origin HEAD:refs/heads/feat/<work-item-id>"
_WORKFLOWS_PERMISSION_REJECTION = (
    "refusing to allow a GitHub App to create or update workflow "
    ".github/workflows/ci.yml without workflows permission"
)


def _prompt_text() -> str:
    return _PR_PROMPT.read_text(encoding="utf-8")


def test_pr_stage_rebases_current_master_immediately_before_first_push() -> None:
    """A stale-base sandbox is refreshed before the publish branch is created."""
    prompt = _prompt_text()

    fetch_index = prompt.index(_FETCH)
    rebase_index = prompt.index(_REBASE)
    push_index = prompt.index(_PUSH)

    assert fetch_index < rebase_index < push_index
    assert "After a" in prompt
    assert "successful rebase, re-check committed work" in prompt


def test_pr_stage_retries_once_only_for_exact_workflows_permission_rejection() -> None:
    """The stale-base App-token failure is recovered once, without overmatching."""
    prompt = _prompt_text()

    assert _WORKFLOWS_PERMISSION_REJECTION in prompt
    assert prompt.count(_FETCH) == 2
    assert prompt.count(_REBASE) == 2
    assert prompt.count(_PUSH) == 2
    assert "retry EXACTLY ONCE" in prompt
    assert "If that retry gets the same rejection" in prompt
    assert "Do NOT loop and do NOT retry on any" in prompt
    assert "different error signature" in prompt


def test_pr_stage_does_not_authorize_workflow_file_edits() -> None:
    """The workflow path appears only as the remote rejection signature."""
    prompt = _prompt_text()

    assert "this stage must not edit files under `.github/workflows/`" in prompt
