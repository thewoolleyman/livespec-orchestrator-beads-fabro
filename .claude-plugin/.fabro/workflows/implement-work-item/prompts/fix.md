# Fix stage — repair the incoming gate, proof or refresh finding

The loop routed here after a red janitor check, a code-change finding from
`proof_capture` or `proof_verify`, a REFRESH-REPAIR brief from `publish_draft`
or `pr_refresh`, or an operator-requested retry. A proof
stage can SUCCEED at reporting a defect while requesting `fix`: its status
does not mean the implementation passed. A green janitor does not discharge
a semantic proof finding.

## When the incoming finding is a refresh-repair brief

A refreshing stage could not bring this run onto the default branch — the
rebase conflicted, or the refreshed head was refused by the repository's own
gate — so it RESTORED the head it held before the refresh and routed here
rather than ending the run. The preceding stage's output opens
`LIVESPEC_REFRESH_REPAIR` and carries the brief; the brief is also written to
the file `livespec-refresh-repair-brief` inside the publication state
directory (`git rev-parse --git-path livespec-publication`), which is the
durable second route when the preamble carries none. Read it with `cat`.

The brief names the stage, the pre-refresh head, the default-branch commit the
refresh targeted, and either each conflicted path together with the run commit
that was being applied, or each failed gate target. Your job is to INTEGRATE
the default branch into this run's work inside this turn and resolve the
conflict or the gate failure:

1. `git fetch origin {{ inputs.default_branch }}`, then rebase or merge this
   run's work onto it yourself, resolving each conflicted path on its merits.
   Do NOT resolve by taking one side wholesale — a conflict means both sides
   changed something, and discarding either loses work somebody shipped.
2. Re-run the repository's check suite (`{{ inputs.sandbox_check_suite }}`)
   against the integrated tree and fix what the integration broke. A gate
   target the brief names failed on the REFRESHED tree, so a green suite on
   the pre-refresh tree is not evidence.
3. Leave the branch at the integrated, green head. The graph re-enters
   janitor, then `publish_draft`, then `proof_capture`, so publication is
   re-earned on the repaired head rather than claimed here.

Hooks run normally in this turn, exactly as everywhere else. Never pass
`--no-verify`, never use bare force, and rewrite no ref at all — not even
this run's own publish branch. The `publish_draft` visit the graph re-enters
after this repair owns the one republication the contract permits, under an
explicit lease against the head this run itself published; a branch you
rewrote here would move it to a head no janitor had passed and no proof had
been captured on. A run may take at most two
refresh-repair rounds in total, so a turn that leaves the conflict unresolved
spends a budget nothing replaces.

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

## Every commit goes through the sandbox commit runner

This repository's commit gate runs INSIDE your `git commit`. On a loaded
factory host that gate can run longer than one of your tool calls, and
when the limit ends the call you are left with nothing: no exit status,
no hook output, no verdict. That kill is indistinguishable from a hook
REFUSAL, so a commit that was fine reads exactly like one that was
refused, and the run ends with verified work unpublished. Measured on
this factory: two `git commit --amend --no-edit` calls ended at about
1202 seconds with the gate still running, and the same amend took 41
minutes when a human finished it by hand on that host.

So EVERY git commit you make — the Red commit, the Green amend, and any
later commit — goes through the sandbox commit runner at

    "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-sandbox-commit"

It runs the argv you give it UNCHANGED, with this repository's hooks
firing exactly as they fire for a foreground commit, in a session that
outlives the tool call that started it. Three steps:

1. START it, in the FOREGROUND. It prints a commit run id and returns in
   well under a second, before the hook has finished:

       runner="${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-sandbox-commit"
       run_id=$("$runner" start -- <the git commit argv you would have run>)

2. WAIT on it, with a bound in whole seconds, in as many later tool calls
   as it takes. Each wait blocks for AT MOST that bound, reports the
   state, and leaves the commit run untouched:

       "$runner" wait "$run_id" 600

3. READ the `state:` line of that report. It is the verdict:

   - `running` — the commit has not finished. Wait again.
   - `passed` — the commit happened. The report carries `exit_status: 0`
     and `head:`, the resulting commit id.
   - `failed` — a hook refused it. The report carries the commit
     process's own exit status and the final lines of its output, and
     HEAD is unchanged. A failed commit run IS NOT A COMMIT: fix the
     cause its output names, then start a new commit run.
   - `no-verdict` — the commit was ended by a signal, or its process is
     gone without having recorded an exit status. This IS NOT A COMMIT
     either, and it is NOT a refusal: nothing is known about the gate.
     Start a new commit run.

Also:

- `"$runner" status "$run_id"` reports the same thing without blocking.
- `"$runner" stop "$run_id"` ends a commit run that must not finish. A
  stopped run reports `no-verdict`, so it can never read as a commit.
- Only ONE commit run may be in flight in this sandbox. A start while
  another is `running` is refused and names the running commit run.
- NEVER pass `--no-verify` and never set a variable that skips or
  relaxes a check. The runner changes nothing about which hooks run or
  how severely they fail; it only stops the verdict from depending on
  one tool call.
- If the runner is not at that path this sandbox was not provisioned
  with it. Do NOT commit around it — report that absent path through the
  needs-human protocol below.

THE COMMIT RUN AND ITS BOUNDED WAITS ARE THE ONE EXCEPTION to the rule
below against backgrounding a tool call, and the turn-end obligation is
UNCHANGED: before your final message every commit run you started must
be terminal — `passed`, `failed` or `no-verdict` — or stopped. Confirm
that with a last `wait` or `status` on each commit run id you hold.

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
