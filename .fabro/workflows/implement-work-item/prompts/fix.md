# Fix stage — the janitor gate is red

The previous stage's `mise exec -- just check` run FAILED in this
worktree. Its output is in the prior stage context above.

## Your assignment (unchanged)

{{ goal }}

## What to do

1. Read the janitor failure output and diagnose the root cause.
2. Fix it IN THIS WORKTREE, honoring every rule from the implement
   stage: no `--no-verify` (if a hook fails, fix the cause or stop and
   report its output verbatim); `mise exec -- git ...` for all git
   writes; Red-Green-Replay for any product `.py` change (a test-file
   change means a fresh Red commit, never an edit under an existing
   Green); commit trailer `Co-Authored-By: Claude Fable 5
   <noreply@anthropic.com>`; never touch the primary checkout, other
   worktrees, `.beads/`, or `core.bare`.
3. Re-run `mise exec -- just check` yourself until it is green.
4. Summarize the diagnosis and the fix in your final reply.

If the failure is NOT caused by this branch's changes (e.g. an upstream
red inherited from master), say so explicitly in your final reply with
evidence — do not paper over it.
