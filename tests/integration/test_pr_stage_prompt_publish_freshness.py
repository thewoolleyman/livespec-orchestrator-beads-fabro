"""PR-stage prompt freshness and bounded publish retry contract."""

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
# The default branch is the resolved integration-contract field, rendered by
# fabro from `inputs.default_branch`; the prompt never spells a branch name.
_FETCH = "git fetch origin {{ inputs.default_branch }} --quiet"
_REBASE = "git rebase origin/{{ inputs.default_branch }}"
_PUSH = "git push -u origin HEAD:refs/heads/feat/<work-item-id>"
_LEASE_PUSH = (
    "git push --force-with-lease="
    "refs/heads/feat/<work-item-id>:<observed-remote-tip> "
    "origin HEAD:refs/heads/feat/<work-item-id>"
)
_WORKFLOWS_PERMISSION_REJECTION = (
    "refusing to allow a GitHub App to create or update workflow "
    ".github/workflows/ci.yml without workflows permission"
)
_NON_FAST_FORWARD_REJECTION = "non-fast-forward"
# The verify query names the pull request step 5 found. The BRANCH-resolved form
# is the shape being repaired: a landed auto-merge deletes the publish branch, so
# `gh pr view` with no subject resolves from a remote that no longer exists.
_EXACT_PR_VIEW = (
    "gh pr view <number> --json number,state,mergeCommit,autoMergeRequest,mergeStateStatus"
)
_BRANCH_RESOLVED_PR_VIEW = "gh pr view --json"


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


def test_pr_stage_retries_own_feature_branch_non_fast_forward_with_lease() -> None:
    """A rewritten own feature branch is reconciled with an explicit lease."""
    prompt = _prompt_text()
    normalized_prompt = " ".join(prompt.split())

    assert _NON_FAST_FORWARD_REJECTION in normalized_prompt
    assert _LEASE_PUSH in prompt
    assert "--force-with-lease" in prompt
    assert "bare `--force` push remains forbidden" in normalized_prompt
    assert "the lease is what makes this overwrite safe" in normalized_prompt.lower()
    assert "refs/heads/feat/<work-item-id>:<observed-remote-tip>" in normalized_prompt
    assert "never the current run branch" in normalized_prompt
    assert "cannot prove the remote branch tip is this run's own prior push" in normalized_prompt
    assert "report the output verbatim and end with the needs-human protocol" in normalized_prompt
    assert "lease mismatch" in normalized_prompt


def test_pr_stage_never_instructs_bare_force_push() -> None:
    """The publish recipe allows only the leased force form."""
    prompt = _prompt_text()

    assert "--force-with-lease" in prompt
    assert " --force " not in prompt
    assert " --force\n" not in prompt


def test_pr_stage_arms_auto_merge_with_the_declared_merge_mode() -> None:
    """The merge-method flag is a projection of `dispatcher.merge_mode`, not a literal."""
    prompt = _prompt_text()

    assert "gh pr merge --{{ inputs.merge_mode }} --auto --delete-branch" in prompt
    assert "--rebase" not in prompt
    assert "--squash" not in prompt


def test_pr_stage_honors_the_per_item_merge_hold() -> None:
    """The FIRST seam of the ratified hold, asserted on the prompt the node reads.

    Four obligations, and each fails in its own direction if dropped: the hold
    is a rendered input rather than a literal or an inference; publishing is
    unchanged while it stands; nothing is armed; and the absence is VERIFIED
    rather than assumed, so an auto-merge request that exists anyway is a
    finding instead of a silent pass.
    """
    prompt = _prompt_text()
    normalized_prompt = " ".join(prompt.split())

    assert "it is `{{ inputs.merge_hold }}`" in prompt
    assert "the branch is pushed and the pull request is opened while a hold stands" in (
        normalized_prompt
    )
    assert "Arm NOTHING — do not run `gh pr merge` at all, in any form." in normalized_prompt
    assert "When the hold is `true`: `autoMergeRequest` MUST be null." in normalized_prompt
    assert "set-merge-hold:<work-item-id>:off" in prompt


def test_pr_stage_reports_the_hold_beside_the_pr_number_line() -> None:
    """`MERGE_HOLD=held` rides the same final reply as `PR_NUMBER=<n>`.

    The two markers are asserted TOGETHER and in order, because the ratified
    clause is about where the hold is reported: a reader of the reply must be
    able to tell a deliberately unarmed pull request from an arming that failed,
    and a `MERGE_HOLD=held` line anywhere else does not give them that.
    """
    prompt = _prompt_text()
    normalized_prompt = " ".join(prompt.split())

    assert prompt.count("MERGE_HOLD=held") == 1
    assert prompt.index("PR_NUMBER=<n>") < prompt.index("MERGE_HOLD=held")
    assert "report `MERGE_HOLD=held` on its own line beside that PR-number line" in (
        normalized_prompt
    )


def test_pr_stage_verifies_the_exact_pull_request_with_state_and_merge_commit() -> None:
    """The verify query names its subject and asks for what makes a merge legible.

    Three obligations, each failing in its own direction if dropped. The NUMBER
    must be named, because a landed auto-merge DELETES the publish branch and a
    branch-resolved view then resolves nothing at all. `state` and `mergeCommit`
    must be requested, because a null `autoMergeRequest` has two causes — an
    arming that never took, and a merge that consumed the request — which the
    pre-repair query could not separate. And the branch-resolved form must be
    GONE rather than merely joined: a query that appended the two fields while
    still resolving from the current branch satisfies a containment check on the
    field names just as well, and is exactly the shape being repaired.
    """
    prompt = _prompt_text()
    normalized_prompt = " ".join(prompt.split())

    assert _EXACT_PR_VIEW in prompt
    assert _BRANCH_RESOLVED_PR_VIEW not in prompt
    assert prompt.index("by the number step 5 found") < prompt.index(_EXACT_PR_VIEW)
    assert "a landed auto-merge DELETES the publish branch" in normalized_prompt
    assert "a null `autoMergeRequest` has TWO causes" in normalized_prompt


def test_pr_stage_reports_a_merged_pull_request_as_a_landed_publish() -> None:
    """A MERGED pull request with a merge commit ends the stage as a success.

    The arm is keyed on BOTH observations the query added, because `state` alone
    would read a merge queue's intermediate state as a landing. The two negative
    duties are asserted explicitly: the run must not spend its one arming retry
    on a pull request that has nothing left to arm, and must not route a fully
    successful publish to `needs_human`, which is the measured failure this item
    was filed for. The reply marker is asserted BESIDE `PR_NUMBER=<n>` and in
    order, since a landed-merge line reported anywhere else does not let a reader
    of the reply tell merged work from an arming still pending.
    """
    prompt = _prompt_text()
    normalized_prompt = " ".join(prompt.split())

    assert (
        "When the hold is `false` and `state` is `MERGED` with a non-null `mergeCommit`"
        in normalized_prompt
    )
    assert "the publish LANDED" in normalized_prompt
    assert (
        "Report the merge as a landed publish, naming the pull request number and the"
        " `mergeCommit`." in normalized_prompt
    )
    assert "Do NOT retry the arming, and do NOT enter the needs-human protocol" in normalized_prompt
    assert prompt.count("MERGE_LANDED=<merge-commit-sha>") == 1
    assert prompt.index("PR_NUMBER=<n>") < prompt.index("MERGE_LANDED=<merge-commit-sha>")


def test_pr_stage_preserves_the_open_unarmed_retry_and_its_needs_human_exit() -> None:
    """The genuine arming failure keeps its one retry and its needs-human exit.

    This is the control on the landed-publish arm above: without it, a prompt
    that simply stopped treating a null `autoMergeRequest` as a finding would
    satisfy the MERGED case while silently passing every run whose arming really
    did fail. The arm is now keyed on `OPEN`, so it cannot fire on a merge.
    """
    prompt = _prompt_text()
    normalized_prompt = " ".join(prompt.split())

    assert (
        "When the hold is `false` and `state` is `OPEN` with a null `autoMergeRequest`"
        in normalized_prompt
    )
    assert "Retry the arming exactly once, then re-verify by number" in normalized_prompt
    assert (
        "If the retry leaves `autoMergeRequest` null, report that verbatim and end with the"
        " needs-human protocol" in normalized_prompt
    )


def test_pr_stage_treats_an_already_merged_arming_failure_as_a_landed_merge() -> None:
    """`gh pr merge` losing the race to the merge is a landing, not a failure.

    The arming command can fail for the same reason the verify query now reads as
    success, and a stage that reported that exit status as an arming failure
    would reach the needs-human protocol before step 7 ever ran. The last needle
    is what binds the clause to the RETRY as well as the first attempt: an
    already-merged pull request fails the retry identically, so an arm scoped to
    the first attempt alone leaves the measured failure reachable.
    """
    prompt = _prompt_text()
    normalized_prompt = " ".join(prompt.split())

    assert "If an arming attempt FAILS because the pull request is ALREADY MERGED" in (
        normalized_prompt
    )
    assert "that is a LANDED MERGE and not an arming failure" in normalized_prompt
    assert "re-verify the exact pull request by its number in step 7" in normalized_prompt
    assert "This holds for the retry in step 7 as much as for this first attempt." in (
        normalized_prompt
    )


def test_pr_stage_merge_hold_arm_survives_the_landed_publish_repair() -> None:
    """A hold is never satisfied by a merge, so the landed-publish arm must not reach it.

    The hold's own requirements are re-asserted here rather than left to the
    sibling cases above, because the landed-publish arm is the first thing in
    this prompt that treats a merge as a SUCCESS: a build that widened it to the
    hold would still satisfy every hold assertion written before it, and would
    report a merge that happened under a hold as a clean publish.
    """
    prompt = _prompt_text()
    normalized_prompt = " ".join(prompt.split())

    assert "When the hold is `true`: `autoMergeRequest` MUST be null." in normalized_prompt
    assert prompt.count("MERGE_HOLD=held") == 1
    assert (
        "If `state` is `MERGED`, the pull request merged while the hold stood — report that"
        " verbatim and end with the needs-human protocol below as well." in normalized_prompt
    )
    assert "the landed-publish arm above does NOT apply under a hold" in normalized_prompt


def test_pr_stage_does_not_authorize_workflow_file_edits() -> None:
    """The workflow path appears only as the remote rejection signature."""
    prompt = _prompt_text()

    assert "this stage must not edit files under `.github/workflows/`" in prompt
