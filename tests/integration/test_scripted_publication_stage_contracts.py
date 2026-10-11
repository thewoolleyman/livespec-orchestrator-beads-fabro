"""The scripted publication stages' freshness, lease and merge-hold contract.

THIS MODULE REPLACES A PROMPT TEST, AND THE REPLACEMENT IS A STRENGTHENING.
Until v121 these obligations lived in `prompts/pr.md` and were asserted against
its prose, so every case graded what an agent was ASKED to do. Publication is
now the command stages `pr_refresh` and `pr`
(`SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
stages" -> "Scripted publication and proof-head integrity"), so the same
obligations are asserted against the bytes that RUN. A prose needle could be
satisfied by a paragraph the model skipped; a script needle cannot.

WHY THIS MODULE READS WHILE ITS COMPANION EXECUTES. These focused assertions
make every required and forbidden recipe byte easy to diagnose. The companion
`test_scripted_publication_execution.py` hands the graph through the production
renderer and parser, executes the resulting scripts against real temporary Git
repositories and a controlled forge transport, and advances the default branch
between publication and refresh. The released-factory journey remains the
HOST-CAPTURED assertion of `bd-ib-c3txja`; it is not a substitute for the
hermetic command-path controls. The forbidden halves here still matter:
`--force-with-lease` beside a surviving bare `--force` would be no guarantee.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    publication_push_program_source,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

# The default branch and the merge method are resolved integration-contract
# fields rendered by the engine from their inputs; the scripts never spell a
# branch name or a merge method of their own.
_DEFAULT_BRANCH_TOKEN = "{{ inputs.default_branch }}"
_MERGE_METHOD_TOKEN = "--{{ inputs.merge_mode }}"
_MERGE_HOLD_TOKEN = "{{ inputs.merge_hold }}"
_CHECK_SUITE_TOKEN = "{{ inputs.sandbox_check_suite }}"

# The workflow path appears nowhere in these stages: a factory branch never
# creates or updates a file under it, and publication has no business naming one.
_WORKFLOW_PATH = ".github/workflows/"


def _node_script(*, node: str) -> str:
    """One COMMAND node's `script` attribute, as the engine will run it.

    Scoped to the node's own block so a needle cannot be satisfied by a
    neighbouring node's script in the same graph -- which, with three publication
    stages whose recipes share vocabulary, is the mistake most available to make
    here.

    THE BLOCK IS BOUNDED BY ITS CLOSING BRACKET ON ITS OWN LINE, not by the first
    `]` in the text, and that distinction is a measured one: `--jq '.[0].number'`
    puts a bracket INSIDE a script value, and a `[^\\]]*` body scan truncates
    there -- silently, in the middle of the recipe, so every needle after the jq
    reads as absent. The production renderer survives it only because every node
    declares its `timeout` before its `script`; a reader of the script cannot
    rely on that.
    """
    lines = _GRAPH.read_text(encoding="utf-8").splitlines()
    opens = [index for index, line in enumerate(lines) if line.strip() == f"{node} ["]
    assert len(opens) == 1, f"expected exactly one {node} declaration, got {len(opens)}"
    start = opens[0]
    closes = [index for index, line in enumerate(lines[start:], start=start) if line.strip() == "]"]
    assert closes, f"{node}'s declaration is unterminated"
    body = lines[start + 1 : closes[0]]
    declared = [line.strip() for line in body if line.strip().startswith('script="')]
    assert len(declared) == 1, f"{node} declares {len(declared)} script attributes"
    return declared[0].removeprefix('script="').removesuffix('"')


def test_the_refresh_establishes_the_published_head_from_provenance() -> None:
    """The head leased against comes from the run's record, never a tracking ref.

    This is the clause's own distinction -- "from its recorded publication or
    validated resume provenance, never from a stale local tracking ref" -- and it
    is load-bearing rather than pedantic: the refresh FETCHES before it compares,
    so `refs/remotes/origin/<branch>` has by then been overwritten with the very
    value the ownership test exists to compare against. Asserted in both
    directions, because reading provenance while ALSO falling back to the
    tracking ref would satisfy a containment check on the provenance read.
    """
    script = _node_script(node="pr_refresh")

    assert "/tmp/livespec-publish-head" in script
    assert "LIVESPEC_RESUME_PUBLISHED_HEAD" in script
    assert "LIVESPEC_PR_REFRESH_NO_PROVENANCE" in script
    assert "refs/remotes/origin/$branch" not in script


def test_the_refresh_fetches_the_authoritative_default_before_comparing() -> None:
    """A stale base is refreshed from origin, not read out of the clone.

    The ORDER is the assertion. A comparison performed before the fetch grades
    whatever the sandbox was cloned at, which for a long run is exactly the
    stale base the refresh exists to retire.
    """
    script = _node_script(node="pr_refresh")

    fetch = script.index("git fetch --no-tags origin")
    base = script.index('base=$(git rev-parse \\"refs/remotes/origin/')
    ancestor = script.index("git merge-base --is-ancestor")

    assert fetch < base < ancestor
    assert _DEFAULT_BRANCH_TOKEN in script


def test_the_refresh_gates_the_rebase_before_it_pushes() -> None:
    """The declared check suite runs against the rebased head, and push follows.

    Both the presence and the ORDER are the assertion: a suite run after the
    push would prove the gate ran and would have published the ungated tree
    anyway, which is the one sequence the clause forbids ("push only after that
    gate passes").
    """
    script = _node_script(node="pr_refresh")

    rebase = script.index('git rebase \\"$base\\"')
    gate = script.index(_CHECK_SUITE_TOKEN)
    push = script.index('if ! \\"$push_program\\"')

    assert rebase < gate < push
    assert "LIVESPEC_PR_REFRESH_GATE_FAILED" in script


def test_the_refresh_rewrites_only_its_own_ref_and_only_under_a_lease() -> None:
    """One leased push, against the recorded remote head, of one ref.

    Four obligations in one case because each is a different way the same push
    goes wrong: a bare force ignores the remote's state, an unleased
    `--force-with-lease` with no value leases against the tracking ref the clause
    already forbids trusting, a second refspec rewrites something that is not
    this run's, and `--no-verify` skips the hooks the clause requires to run
    normally.
    """
    script = _node_script(node="pr_refresh")
    push = publication_push_program_source()

    assert "livespec-push-exact-head" in script
    assert '"$push_program" "$branch" "$remote"' in script.replace("\\", "")
    assert '--force-with-lease="refs/heads/$branch:$expected"' in push
    assert push.count("git push") == 1
    assert 'origin "HEAD:refs/heads/$branch"' in push
    assert "--force " not in push
    assert "--no-verify" not in push
    assert "git push" not in script
    assert "LIVESPEC_PR_REFRESH_LEASE_FAILED" in script
    assert "LIVESPEC_PR_REFRESH_PUSH_PROGRAM_ABSENT" in script


def test_the_refresh_fails_closed_on_every_cause_it_cannot_act_on() -> None:
    """Each named cause is its own sentinel, so "we could not look" is legible.

    The clause requires "a named cause and recovery artifact pointer" for a
    missing or unobservable remote, a foreign or unexpectedly changed publish
    head, and a conflicted rebase. One shared sentinel would satisfy a
    containment check while making the three indistinguishable in the run record,
    which is the discrimination an operator needs before clearing a branch by
    hand.
    """
    script = _node_script(node="pr_refresh")

    for sentinel in (
        "LIVESPEC_PR_REFRESH_NO_BRANCH",
        "LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE",
        "LIVESPEC_PR_REFRESH_REMOTE_REF_UNKNOWN",
        "LIVESPEC_PR_REFRESH_FOREIGN_HEAD",
        "LIVESPEC_PR_REFRESH_CONFLICT",
        "LIVESPEC_PR_REFRESH_NON_CONVERGED",
    ):
        assert sentinel in script, sentinel
    # A conflict chooses NEITHER side: the rebase is aborted and the published
    # head is left exactly as it stood.
    assert "git rebase --abort" in script


def test_the_refresh_is_bounded_to_three_and_resets_per_sandbox() -> None:
    """Three refreshes per run, counted where a new run cannot inherit the count.

    The counter lives in the sandbox's own `/tmp`, which is per run, so "the
    three-refresh bound starts at zero for each resumed run" is a property of the
    container rather than a rule something has to remember to reset. The
    comparison is asserted as `-ge 3` rather than merely present, because an
    off-by-one here is the difference between the ratified bound and a fourth
    refresh.
    """
    script = _node_script(node="pr_refresh")

    assert "/tmp/livespec-pr-refresh-count" in script
    assert '\\"$count\\" -ge 3' in script
    assert "LIVESPEC_PR_REFRESH_NON_CONVERGED" in script


def test_a_changed_head_is_reported_by_the_breaker_and_cleared_each_entry() -> None:
    """The marker is written by the refresh and CLEARED at the top of every entry.

    The clear is the half that is easy to omit and impossible to notice: a marker
    left behind by an earlier refresh would route an unchanged head back through
    capture on every later pass, so the run would never reach publication while
    every stage reported success.
    """
    refresh = _node_script(node="pr_refresh")
    breaker = _node_script(node="pr_refresh_head")

    assert "rm -f /tmp/livespec-pr-refresh-changed" in refresh
    assert ": > /tmp/livespec-pr-refresh-changed" in refresh
    assert refresh.index("rm -f /tmp/livespec-pr-refresh-changed") < refresh.index(
        ": > /tmp/livespec-pr-refresh-changed"
    )
    assert "test -f /tmp/livespec-pr-refresh-changed" in breaker
    assert "LIVESPEC_PR_REFRESH_HEAD_CHANGED" in breaker
    assert "LIVESPEC_PR_REFRESH_HEAD_UNCHANGED" in breaker


def test_publication_establishes_proof_identity_through_the_one_reader() -> None:
    """The gate is the head a RECORD names, not the head this run pushed.

    This is the obligation a pushed-head marker cannot discharge. The clause
    requires `pr` to "verify its current head against the head whose proof was
    verified" and forbids reusing "a verified record from before that change", so
    the comparison has to reach the proof artifact. It reaches it through the
    Dispatcher-materialized publication-head program -- the ONE reader of the
    record format -- and requires BOTH `captured` and `verified` to name the same
    head, because a verified record alone can post-date a capture of a different
    tree and a captured record alone was never replayed.

    The ABSENT-program arm is asserted beside it: a sandbox the prepare step did
    not reach must fail closed rather than fall through to the pushed-head check,
    which would be the weaker guarantee wearing the stronger one's clothes.
    """
    script = _node_script(node="pr")

    assert "livespec-publication-head.py" in script
    assert "--require captured --require verified" in script
    assert "LIVESPEC_PR_PROOF_PROGRAM_ABSENT" in script
    assert "LIVESPEC_PR_PROOF_IDENTITY_UNESTABLISHED" in script
    assert "LIVESPEC_PR_PROOF_HEAD_MISMATCH" in script


def test_publication_also_verifies_the_head_this_run_pushed() -> None:
    """The pushed head is a SECOND, separately-named check, not the proof gate.

    It answers a different question -- did this run put this tree on the branch
    -- and it carries its own cause so a divergence between what was pushed and
    what the proof names is legible as that rather than as a proof failure. The
    ORDER is asserted: the proof gate runs first, so the weaker check can never
    stand in for it.
    """
    script = _node_script(node="pr")

    assert script.index("LIVESPEC_PR_PROOF_HEAD_MISMATCH") < script.index(
        "LIVESPEC_PR_UNEXPECTED_HEAD"
    )
    assert "LIVESPEC_PR_NO_PROVENANCE" in script


def test_publication_resolves_the_pull_request_across_every_state() -> None:
    """The open one if there is one, else the newest in any state.

    The all-states fallback is load-bearing: a landed auto-merge deletes the
    publish branch, so an open-only query finds nothing at all for a fully
    successful publish and the stage would report it as absent.
    """
    script = _node_script(node="pr")

    assert "--state open" in script
    assert "--state all" in script
    assert "LIVESPEC_PR_ABSENT" in script


def test_publication_readies_the_standing_draft_and_creates_nothing() -> None:
    """`gh pr ready`, and no creation verb anywhere in the stage.

    Asserted in BOTH directions: the presence of `gh pr ready` alone would pass
    for a stage that readied a pull request it had just created, which is the
    double-publication the draft-first flow removed.
    """
    script = _node_script(node="pr")

    assert "gh pr ready" in script
    assert "gh pr create" not in script


def test_the_finalizer_is_idempotent_across_draft_ready_and_merged() -> None:
    """`gh pr ready` is issued only for a pull request that IS a draft.

    The clause requires finalization to be "idempotent for existing draft, ready
    or already-merged", and `gh pr ready` on an already-ready pull request
    commonly exits NON-ZERO -- so a stage that ran it unconditionally and treated
    every non-zero exit as a failure would fail closed on the second entry of a
    perfectly healthy publish. The draft state is therefore QUERIED and the ready
    is conditional; the already-ready case gets its own stated outcome rather
    than silence, so a reader of the run log can tell it from a ready that was
    skipped by accident.

    The already-MERGED arm is the third state, and it returns before the edit:
    there is nothing left to ready or arm, and the clause calls it a recorded
    success.
    """
    script = _node_script(node="pr")

    assert "--json isDraft" in script
    assert '\\"$draft\\" = \\"true\\"' in script
    assert "LIVESPEC_PR_ALREADY_READY" in script
    assert "LIVESPEC_PR_READY_FAILED" in script
    # The merged arm returns before the title/body edit and the ready, which is
    # what makes the merged state idempotent rather than merely tolerated.
    assert script.index("LIVESPEC_PR_ALREADY_MERGED") < script.index("gh pr edit")
    assert script.index("LIVESPEC_PR_ALREADY_MERGED") < script.index("gh pr ready")


def test_publication_passes_the_title_and_body_as_data() -> None:
    """Metadata rides the environment and a file, never shell syntax.

    The clause's own wording is "passed as data, not interpolated as shell
    syntax", and the BODY is the half that matters: a title is one line, while a
    pull-request body routinely carries backticks and `$(...)` from a diff it
    quotes. `--body-file` is what makes those bytes text; `--body` with an
    interpolated value is what makes them a command.
    """
    script = _node_script(node="pr")

    assert "LIVESPEC_PR_TITLE" in script
    assert "LIVESPEC_PR_BODY_FILE" in script
    assert "--body-file" in script
    assert "--body " not in script


def test_publication_arms_auto_merge_with_the_declared_merge_method() -> None:
    """The merge-method flag is a projection of `dispatcher.merge_mode`.

    The forbidden half is the literal: a hardcoded `--rebase` or `--squash` would
    arm correctly for this repository and silently wrongly for every adopter that
    declared the other one.
    """
    script = _node_script(node="pr")

    assert f"gh pr merge {_MERGE_METHOD_TOKEN} --auto --delete-branch" in script
    assert "--rebase" not in script
    assert "--squash" not in script


def test_publication_honors_the_per_item_merge_hold() -> None:
    """Four obligations, each failing in its own direction if dropped.

    The hold is a rendered input rather than a literal or an inference;
    publication up to and including `gh pr ready` is unchanged while it stands;
    nothing is armed; and the absence of an arming is VERIFIED rather than
    assumed, so an auto-merge request that exists anyway is a finding instead of
    a silent pass. The ORDER assertion is what carries the second of those: the
    hold is read AFTER the ready, so a held item still gets a ready pull request.
    """
    script = _node_script(node="pr")

    ready = script.index("gh pr ready")
    hold = script.index(_MERGE_HOLD_TOKEN)
    arm = script.index("gh pr merge")

    assert ready < hold < arm
    assert "autoMergeRequest" in script
    assert "LIVESPEC_PR_HOLD_ARMED" in script


def test_publication_reports_its_markers_on_stdout_beside_the_pr_number() -> None:
    """`PR_NUMBER`, `MERGE_HOLD` and `MERGE_LANDED` are stdout, not stderr.

    The host's PR discovery and auto-merge journaling read these lines, so the
    STREAM is part of the contract: a marker written to stderr beside the
    diagnostics is a marker the host does not see. Asserted as `echo "<marker>`
    with no redirect, which is what separates them from every sentinel in the
    same script.
    """
    script = _node_script(node="pr")

    for marker in ('echo \\"PR_NUMBER=', 'echo \\"MERGE_HOLD=held', 'echo \\"MERGE_LANDED='):
        assert marker in script, marker
    # Every diagnostic goes the other way, so the two streams stay separable.
    assert "LIVESPEC_PR_READY_AND_ARMED" in script
    assert script.count(">&2") > 1


def test_publication_treats_a_merged_pull_request_as_a_recorded_success() -> None:
    """A merge that beat the stage to the pull request is the outcome, not a fault.

    Both races are covered because they arrive at different commands: the forge
    can have merged BEFORE the stage looked (the state read), and it can merge
    between `gh pr ready` and the arming (the arm's own failure). A stage that
    handled only the first would route a fully successful publish to needs_human
    on the second, which is the measured failure this arm exists for.
    """
    script = _node_script(node="pr")

    assert "LIVESPEC_PR_ALREADY_MERGED" in script
    assert "LIVESPEC_PR_MERGED_WHILE_ARMING" in script
    assert "mergeCommit" in script


def test_publication_fails_closed_on_a_closed_unmerged_pull_request() -> None:
    """A publication a human closed is not reopened by a script.

    This is the control on the merged-as-success arm above: a stage that widened
    "not open" into "already landed" would satisfy every merged assertion while
    reporting a deliberately closed pull request as a clean publish.
    """
    script = _node_script(node="pr")

    assert "LIVESPEC_PR_CLOSED_UNMERGED" in script
    assert '"$state" != \\"OPEN\\"' in script or '\\"$state\\" != \\"OPEN\\"' in script


def test_no_publication_stage_names_the_workflow_path() -> None:
    """The factory-branch boundary, asserted on the stages that push.

    A factory branch never creates or updates a file under the workflow path, and
    publication has no business naming one; the retired prompt carried the path
    only as a quoted remote-rejection signature, and the scripted stages carry it
    not at all.
    """
    for node in ("pr_refresh", "pr_refresh_head", "pr"):
        assert _WORKFLOW_PATH not in _node_script(node=node), node
