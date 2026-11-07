"""`SPECIFICATION/scenarios.md` Scenario 176 — refresh repair preserves publication ancestry.

WHAT THIS BINDS. `SPECIFICATION/contracts.md` "Self-contained plugin dispatch"
and the refresh-repair route of Scenario 176 send a run whose `publish_draft`
refresh conflicts with a moved default branch to the `fix` node. Work-item
`bd-ib-diiztk`: the `fix` prompt's refresh-repair steps MUST merge the default
branch when the already-published branch tip is an ancestor of the run head, so
that publication ancestry survives repair.  When no publish branch exists, the
prompt MUST retain the rebase path.  Every integration commit still goes through
the sandbox commit runner's `start` and bounded `wait`.

WHY THE MEASUREMENT MATTERS. Run 01M6SPM6J3HDMVGXBAM43Y9AZX (petri, 0.298.0,
item livespec-dev-tooling-wou75w, 2026-11-07) had already published a draft.
Its refresh-repair turn rebased and dropped that published head from its
ancestry. The next refresh and publication correctly refused the divergent
remote tip. A no-commit merge preserves the remote tip as an ancestor while the
runner still owns the commit hook.

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

_PUBLISHED_BRANCH = "`origin/$LIVESPEC_PUBLISH_BRANCH` exists and its tip is an ancestor of `HEAD`"
_MERGE_DIRECTIVE = "MERGE `origin/{{ inputs.default_branch }}` into `HEAD`"
_MERGE_COMMAND = "git merge --no-commit --no-ff `origin/{{ inputs.default_branch }}`"
_PRESERVE_ANCESTRY = "so the origin tip remains an ancestor of the repaired head"
_NO_PUBLISHED_BRANCH = "When the publish branch does not exist on origin"
_REBASE_DIRECTIVE = "REBASE this run's own commits onto `origin/{{ inputs.default_branch }}`"
_NO_DIRECT_MERGE_COMMIT = "Do NOT use `git merge --no-edit`"
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


def test_the_implement_fix_prompt_merges_when_the_published_tip_is_an_ancestor() -> None:
    section = _repair_section(prose=_normalised(_IMPLEMENT_FIX))

    assert _PUBLISHED_BRANCH in section
    assert _MERGE_DIRECTIVE in section
    assert _MERGE_COMMAND in section
    assert _PRESERVE_ANCESTRY in section
    assert _NO_DIRECT_MERGE_COMMIT in section


def test_the_implement_fix_prompt_rebases_when_no_publish_branch_exists() -> None:
    section = _repair_section(prose=_normalised(_IMPLEMENT_FIX))

    assert _NO_PUBLISHED_BRANCH in section
    assert _REBASE_DIRECTIVE in section


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
    assert _RUNNER_START in section
    assert _RUNNER_WAIT in section
    assert _NEVER_FOREGROUND in section
