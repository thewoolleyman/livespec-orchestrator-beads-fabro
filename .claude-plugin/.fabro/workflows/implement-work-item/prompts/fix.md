# Fix stage — repair the incoming gate or proof finding

The loop routed here after a red janitor check, a code-change finding from
`proof_capture` or `proof_verify`, or an operator-requested retry. A proof
stage can SUCCEED at reporting a defect while requesting `fix`: its status
does not mean the implementation passed. A green janitor does not discharge
a semantic proof finding.

This node uses `summary:high` fidelity so the preamble includes prior
agents' source-labelled responses, not just their status and changed files.
Read the most recent incoming stage and its full response (or open the
referenced response artifact). Do not choose an older green proof record
over that stage's current finding. When several rounds are visible, use
the incoming stage's latest response, not an earlier round's disposition.

## When the preamble carries no finding, read the pull request

A proof finding reaches you by TWO routes, and the second exists because
the first can be lost: every proof stage also publishes its finding as a
record comment on this item's pull request. So a preamble with no readable
finding is not yet a blocker — it is an instruction to read the other
route.

Find the pull request for this run's publish branch with `gh pr list --head
<publish branch> --state open --json number`, read its comments (`gh pr
view <number> --comments`, or `gh api` for the full bodies), and take the
LATEST comment whose first line opens `Proof of Done — ` and whose verdict
field is `not_captured` (from `proof_capture`) or `not_reproduced` (from
`proof_verify`). Its body names the assertion, the step that failed, what
was observed and what the proof needs: that is your work order. An older
`captured` or `verified` record is NOT a discharge of it.

Only when the preamble carries no finding AND the pull request carries no such record
is the finding missing or unreadable. Then use the failed outcome below and
name BOTH routes you checked. Never infer completion from green checks, an
unchanged tree, or the absence of a PR comment.

## A proof finding is discharged by a tree change or by the needs-human ending

A visit entered on a proof finding MUST end in exactly one of two ways:

- with a TREE CHANGE addressing the finding, committed on this branch; or
- through the structured needs-human ending below, stating why the finding
  is wrong.

It MUST NOT end succeeded with an unchanged tree. Suite success, a green
janitor, and an older passing record are none of them a discharge — the
proof stage SUCCEEDED at reporting a defect while requesting `fix`, so its
status says nothing about whether the implementation passed. Before you
end, run `git status --porcelain` and `git log --oneline
origin/{{ inputs.default_branch }}..HEAD`: if neither shows a change of
yours and you are not taking the needs-human ending, you have not finished.

## Your assignment (unchanged)

The complete work-item goal is in the Fabro-injected `Goal:` preamble above.

## What to do

1. Identify the incoming source and quote its actionable finding. For a red
   gate, read the janitor failure output and diagnose the root cause. For
   `proof_capture` or `proof_verify`, identify the assertion, reproduction
   step, expected result and observed failure in its response; reproduce
   that failure before editing. Proof stages remain read-only: this node
   owns the code change, and must not weaken the assertion to make it pass.
2. Fix it IN THIS CLONE, honoring every rule from the implement
   stage: no `--no-verify` (if a hook fails, fix the cause or end with
   the needs-human protocol below, reporting its output verbatim);
   plain `git` for all writes (the installed hooks fire on their own);
   Red-Green-Replay for any
   product `.py` change (a test-file change means a fresh Red commit,
   never an edit under an existing Green); commit trailer
   `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`; never
   create or switch branches, never touch `.beads/` or `core.bare`.
3. Re-run the repository's check suite (`{{ inputs.sandbox_check_suite }}`) yourself until it is green.
4. Re-run the failed reproduction and report the before/after result,
   naming the source stage and assertion alongside the diagnosis and fix.
   Suite success alone is not evidence that the semantic finding is fixed.
   The graph still re-earns janitor, capture, review and independent replay;
   do not claim their downstream approval on their behalf.

## When the failure is not auto-resolvable (needs-human protocol)

If the failure needs a human decision, is NOT caused by this branch's
changes (e.g. an upstream red inherited from {{ inputs.default_branch }} — say so with
evidence), or you have proven you cannot legitimately fix it, do NOT go
quiet and do NOT paper over it. End your final reply with the failed
outcome and a STRUCTURED reason, as a JSON object on the last line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}

When the fix loop's budget exhausts, the graph terminates the run at the
`needs_human` node and rests the work-item at `blocked / needs-human` in
the ledger; your structured reason is what the human reads first — make
it actionable.

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
