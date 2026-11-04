"""`SPECIFICATION/scenarios.md` Scenario 176 — refresh repair rebases and commits via the runner.

WHAT THIS BINDS. `SPECIFICATION/contracts.md` "Self-contained plugin dispatch"
and the refresh-repair route of Scenario 176 send a run whose `publish_draft`
refresh conflicts with a moved default branch to the `fix` node. Work-item
`bd-ib-xuo54m`: the `fix` prompt's refresh-repair steps MUST integrate the default
branch by REBASING the run's own commits onto it, and MUST direct every commit
the integration creates through the sandbox commit runner's `start` and bounded
`wait`, never through a foreground `git merge`, `git rebase --continue` or
`git commit`.

WHY THE MEASUREMENT MATTERS. Run 01M6HXXA4JGG465V5JWX03NC7K (petri, 0.282.0,
item bd-ib-uq2ocd, 2026-11-04): `fix@1` followed "rebase or merge" and ran a
foreground `git merge origin/master --no-edit`. The merge commit's hook was
killed at the ten-minute tool-call limit (exit 143), the retry through the runner
was still running when the 3600 second turn expired, and the run ended
`needs_human`. A scratch `git rebase origin/master` of the preserved merge
commit reproduced both original conflicts, because `publish_draft` refreshes by
rebase, which drops a merge and replays the run's own commit.

A PROMPT TEST because the choice is made by the AGENT out of this prose; nothing
host-side observes which integration a turn chose. Needles are matched over
whitespace-normalised prose, since the prompts are hard-wrapped, and are asserted
POSITIVELY as the sentences that grant or forbid. The groom twin carries no
refresh-repair steps today; its case holds it to the same rules the moment it
gains them.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPLEMENT_FIX = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
    / "fix.md"
)
_GROOM_FIX = _REPO_ROOT / ".fabro" / "workflows" / "groom-work-item" / "prompts" / "fix.md"

_SECTION_HEADING = "## When the incoming finding is a refresh-repair brief"
_RUNNER = "livespec-commit-runner.py"

_REBASE_DIRECTIVE = "REBASE this run's own commits onto `origin/{{ inputs.default_branch }}`"
_NO_MERGE_COMMIT = "so the repaired head carries no merge commit"
_NEVER_MERGE = "Never integrate with `git merge`"
_RUNNER_START = f'{_RUNNER}" start -- git commit'
_RUNNER_WAIT = f'{_RUNNER}" wait <run-id> --timeout-seconds 300'
_NEVER_FOREGROUND = (
    "Never run a foreground `git merge`, a foreground `git commit`, or a foreground "
    "`git rebase --continue` while a resolution is staged"
)
_CONTINUATION_THROUGH_RUNNER = "including the commit that records a conflict resolution"


def _normalised(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _repair_section(*, prose: str) -> str:
    start = prose.index(_SECTION_HEADING)
    end = prose.find(" ## ", start + len(_SECTION_HEADING))
    return prose[start:] if end == -1 else prose[start:end]


def test_the_implement_fix_prompt_integrates_by_rebase_not_merge() -> None:
    section = _repair_section(prose=_normalised(_IMPLEMENT_FIX))

    assert _REBASE_DIRECTIVE in section
    assert _NO_MERGE_COMMIT in section
    assert _NEVER_MERGE in section
    assert "rebase or merge this" not in section


def test_the_implement_fix_prompt_sends_every_integration_commit_through_the_runner() -> None:
    section = _repair_section(prose=_normalised(_IMPLEMENT_FIX))

    assert _CONTINUATION_THROUGH_RUNNER in section
    assert _RUNNER_START in section
    assert _RUNNER_WAIT in section
    assert _NEVER_FOREGROUND in section


def test_the_groom_fix_prompt_carrying_refresh_repair_steps_states_the_same_rules() -> None:
    prose = _normalised(_GROOM_FIX)
    if _SECTION_HEADING not in prose:
        assert "refresh-repair" not in prose
        return
    section = _repair_section(prose=prose)

    assert _REBASE_DIRECTIVE in section
    assert _NEVER_MERGE in section
    assert _RUNNER_START in section
    assert _RUNNER_WAIT in section
    assert _NEVER_FOREGROUND in section
