# PR stage — publish the branch and arm rebase auto-merge

The janitor gate is green. Publish this worktree's branch as a PR per
the family merge discipline.

## Your assignment (for the PR description)

{{ goal }}

## What to do, in order

1. Confirm there is committed work: `git log --oneline
   origin/master..HEAD`. If there are zero commits, STOP — reply
   explaining that nothing was produced, and end your reply with
   `{"preferred_next_label": "done"}`.
2. Push the branch: `mise exec -- git push -u origin HEAD`. NEVER
   `--no-verify`; if the pre-push hook fails, stop and report its
   output verbatim.
3. Open the PR against master with `gh pr create` — title from the
   work-item, body summarizing the change and naming the work-item id.
   The body MUST end with the line:

   🤖 Generated with [Claude Code](https://claude.com/claude-code)

4. Arm auto-merge: `gh pr merge --rebase --auto --delete-branch <pr-url-or-number>`.
5. VERIFY it armed: `gh pr view --json number,autoMergeRequest,mergeStateStatus`.
   - If `autoMergeRequest` is null, retry the arming once and re-verify.
   - If `mergeStateStatus` is `BEHIND`, the repo automation updates the
     branch; if it stays `BEHIND` for more than 10 minutes, report it —
     do NOT attempt a manual update.
6. Do NOT wait for the merge (it lands server-side after CI), do NOT
   delete or clean up this worktree, and do NOT switch branches — the
   Dispatcher owns merge confirmation, the post-merge janitor, and
   worktree reaping.
7. Final reply: report the PR number on its own line in exactly this
   form — `PR_NUMBER=<n>` — plus whether auto-merge is armed, and any
   deviation verbatim.
