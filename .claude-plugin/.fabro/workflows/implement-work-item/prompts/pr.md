# PR stage — mark the draft PR ready and arm auto-merge

The janitor gate is green, the review gate approved the tree, and the
Proof of Done record has been captured. A DRAFT pull request for this
item's publish branch ALREADY EXISTS — the `publish_draft` stage opened it
before the capture, because a Proof of Done record is a comment and a
comment needs a pull request to live on.

So your job is NOT to create a pull request. It is to refresh the base,
give that existing draft its real title and body, mark it READY, and arm
auto-merge. You are on a Fabro-managed run branch — its name is
run-internal and MUST NOT be published; the pull request rides the
feature branch named after the work-item instead.

## Where you are

You are in the SAME isolated Fabro sandbox clone the implement/janitor
stages produced the committed work in — your CURRENT WORKING DIRECTORY
is that clone. Run every `git` and `gh` command here, in the current
directory. Plain `git` is correct here: the sandbox's prepare chain
installed the repository's hooks and they fire on every git write —
never pass `--no-verify`. The assignment below may mention a `Repo:` path: that is the
dispatcher's host-side checkout, it does NOT exist in this sandbox, and
you must NEVER `cd` to it or treat the absence of any such path as
"no committed work". The committed work is reachable as
`git log --oneline origin/{{ inputs.default_branch }}..HEAD` from where you already are.

## Your assignment (for the PR description)

The complete work-item goal is in the Fabro-injected `Goal:` preamble above.

## What to do, in order

1. Re-enter the plugin-cache gate BEFORE anything else, and run it exactly
   as written, from this sandbox:

       python3 "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-run-plugin-gate.py"

   The run's prepare step verified the sandbox's Claude plugin registry and
   recorded the build every stage of this run resolves. THIS session started
   after that, and starting it ran a plugin update of its own, so the registry
   you are about to push under is not necessarily the one the janitor gate
   passed against. The gate reverts any build this run did not start with and
   removes any registered build whose cache never fully materialized. Both are
   silent on stdout; the exit code is the contract.
   - Exit 0: continue to the next step. Lines on stderr naming
     `LIVESPEC_PLUGIN_BUILD_ADVANCED` or `LIVESPEC_PLUGIN_CACHE_UNMATERIALIZED`
     mean it repaired something — report them in your final reply, but they do
     NOT block publishing.
   - Non-zero: STOP. The registry names a plugin build whose cache is
     incomplete and which the gate could not repair, so the repository's
     pre-push hook would fail on a plugin root this run never resolved.
     Do NOT push. Report the gate's stderr verbatim and end with the
     needs-human protocol below.
2. Confirm there is committed work: `git log --oneline
   origin/{{ inputs.default_branch }}..HEAD`. If there are zero commits, STOP — reply
   explaining that nothing was produced, and end your reply with
   `{"preferred_next_label": "done"}`.
3. Refresh the base IMMEDIATELY before publishing: run
   `git fetch origin {{ inputs.default_branch }} --quiet`, then run
   `git rebase origin/{{ inputs.default_branch }}`. If the rebase reports
   conflicts you cannot legitimately resolve, report the rebase output
   verbatim and end with the needs-human protocol below. After a
   successful rebase, re-check committed work with
   `git log --oneline origin/{{ inputs.default_branch }}..HEAD`; if there are zero commits,
   STOP as in step 2.
4. Publish under the feature branch named in your assignment (the
   "Publish branch" line — `feat/<work-item-id>`), NEVER under the
   current run branch's own name:
   `git push -u origin HEAD:refs/heads/feat/<work-item-id>`.
   NEVER `--no-verify`; if the pre-push hook fails and you cannot
   legitimately fix the cause, report its output verbatim and end with
   the needs-human protocol below.
   - If the remote rejects the push with the exact signature
     `refusing to allow a GitHub App to create or update workflow .github/workflows/ci.yml without workflows permission`
     (the workflow path is named here only as the quoted rejection
     signature; this stage must not edit files under `.github/workflows/`),
     retry EXACTLY ONCE: run
     `git fetch origin {{ inputs.default_branch }} --quiet`, then
     `git rebase origin/{{ inputs.default_branch }}`, then repeat the same
     `git push -u origin HEAD:refs/heads/feat/<work-item-id>`
     command. If that retry gets the same rejection, or if any other
     push failure occurs during this workflow-permission retry, report
     the output verbatim and end with the needs-human protocol below.
     Do NOT loop and do NOT retry on any different error signature in
     this workflow-permission arm.
   - A `non-fast-forward` rejection for the assignment feature branch is
     EXPECTED here rather than exceptional, and that is new: the
     `publish_draft` stage already pushed this run's work to that branch,
     and the rebase in step 3 has since rewritten the commits on top of a
     fresher base. So the remote tip is normally this run's OWN prior
     push. Reconcile only when you can PROVE that. Fetch the assignment
     feature branch, inspect the observed remote tip, and verify that the
     remote-only commits are this run's own prior publication. If you
     cannot prove the remote branch tip is this run's own prior push,
     report the output verbatim and end with the needs-human protocol
     below.
   - When the non-fast-forward branch is proven to be this run's own
     prior publication, retry EXACTLY ONCE with an explicit lease against
     the observed assignment feature-branch tip:
     `git push --force-with-lease=refs/heads/feat/<work-item-id>:<observed-remote-tip> origin HEAD:refs/heads/feat/<work-item-id>`.
     The retry targets only `refs/heads/feat/<work-item-id>`, never the
     current run branch. The lease is what makes this overwrite safe: if
     anyone updated the remote branch after your inspection, the lease
     mismatch rejects the push and preserves the refusal path. A bare
     `--force` push remains forbidden. If the leased retry fails with a
     lease mismatch, or if any other push failure occurs, report the
     output verbatim and end with the needs-human protocol below.
5. Find the EXISTING draft pull request for the publish branch and give it
   its real title and body, then mark it ready. Do NOT create a pull
   request, by any command or in any form — one already exists, and
   creating a second would either fail outright or open a duplicate that
   no reviewer and no proof record is attached to:

       gh pr list --head feat/<work-item-id> --state open --json number,isDraft

   - If that returns NO pull request, something upstream of you went
     wrong: the `publish_draft` stage is the only thing that opens it and
     the graph cannot reach you without passing through it. Report what
     you observed and end with the needs-human protocol below rather than
     creating one yourself.
   - Set the real title and body with
     `gh pr edit <number> --title ... --body ...` — title from the
     work-item, body drafted from the work-item acceptance criteria in
     the assignment above, and including the work-item id. The
     `publish_draft` stage titled it with the branch name as a
     placeholder, so this step is what makes it readable.
     The body MUST end with the line:

     🤖 Generated with [Claude Code](https://claude.com/claude-code)

   - Mark it ready for review: `gh pr ready <number>`. This is what
     releases it to the repository's merge automation; while it was a
     draft, auto-merge could not take it, which is exactly why the proof
     could be captured on it first. If it is already not a draft, that is
     fine — `gh pr ready` is idempotent in the direction you want.

6. Read the merge hold for this item: it is `{{ inputs.merge_hold }}`.
   Everything above this step is the same either way — the branch is
   pushed and the pull request is opened while a hold stands. What the
   hold changes is only whether auto-merge is armed.
   - When it is `false`, arm auto-merge with the repository's declared
     merge mode:
     `gh pr merge --{{ inputs.merge_mode }} --auto --delete-branch <pr-url-or-number>`.
   - When it is `true`, the item is under a per-item MERGE HOLD: a
     maintainer wants it implemented now and merged in a window they
     choose. Arm NOTHING — do not run `gh pr merge` at all, in any form.
     The hold is released later by an operator through the
     `set-merge-hold:<work-item-id>:off` valve, which arms the merge from
     the host; it is not yours to release and not yours to work around.
7. VERIFY the pull request is in the state the hold implies:
   `gh pr view --json number,autoMergeRequest,mergeStateStatus`.
   - When the hold is `false`: if `autoMergeRequest` is null, retry the
     arming once and re-verify.
   - When the hold is `true`: `autoMergeRequest` MUST be null. If it is
     NOT null, an auto-merge request exists that must not — report that
     verbatim and end with the needs-human protocol below rather than
     disarming it yourself.
   - If `mergeStateStatus` is `BEHIND`, the repo automation updates the
     branch; if it stays `BEHIND` for more than 10 minutes, report it —
     do NOT attempt a manual update.
8. Do NOT wait for the merge (it lands server-side after CI, or after
   the hold is released), do NOT clean anything up, and do NOT switch
   branches — the Dispatcher owns merge confirmation and the post-merge
   janitor, and Fabro owns this sandbox's lifecycle.
9. Final reply: report the PR number on its own line in exactly this
   form — `PR_NUMBER=<n>` — plus whether auto-merge is armed, and any
   deviation verbatim. When the hold is `true`, report `MERGE_HOLD=held`
   on its own line beside that PR-number line, so a reader of the reply
   can tell a deliberately unarmed pull request from an arming that
   failed.

## When publishing is blocked (needs-human protocol)

If the push or PR flow is blocked in a way you cannot legitimately
resolve (hook rejection you must not bypass, gh/auth failure, branch
protection surprise), end your final reply with the failed outcome and
a STRUCTURED reason, as a JSON object on the last line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}

The graph routes a failed outcome to a terminal `needs_human` node: the
run preserves the tree on a run-scoped ref and ends, and the work-item
rests in the ledger at `blocked / needs-human` until a human decides.

## Ending the turn — leave nothing running in the background

The ACP turn this stage runs inside cannot COMPLETE while the agent
session still has work outstanding, so anything you leave running holds
the turn open until the node's own timeout kills it — and work that had
already finished is then recorded as a timed-out stage instead of the
green result it was. Measured repeatedly on this factory: stages that had
already emitted their final message sat idle for 28, 75 and 89 minutes
before the ceiling fired, and four further runs were lost in one night to
a single backgrounded command.

So, in this stage:

- NEVER background a tool call. Do not pass `run_in_background` (or any
  other detach flag) to a shell tool, and do not start a poller, a
  watcher, a `tail -f`, or a loop that waits for a condition.
- Run a long command in the FOREGROUND and raise THAT call's own timeout
  instead. A full check suite, a dependency install, or a long
  verification wait belongs in ONE blocking call whose output you read,
  never in a background job you poll.
- If something IS still running when you are ready to finish, STOP it
  before your final message (`TaskStop`, `KillShell`, or whatever kills
  what you started) and confirm it is gone.
- Your final message must be the LAST thing the turn does. Do not start
  any new tool call, probe, or cleanup after it.
