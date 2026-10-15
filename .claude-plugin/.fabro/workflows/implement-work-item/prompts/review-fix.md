# Review-fix stage — implement accepted review findings

The disposition stage adjudicated the review stage's BLOCKING findings.
Your job is to implement ONLY the findings that the disposition record
marks ACCEPTED. Rejected findings are out of bounds. You have no
adjudication authority in this stage.

## Your assignment (unchanged)

The complete work-item goal is in the Fabro-injected `Goal:` preamble above.

## What to do

1. Read the disposition record from the prior stage context, including any
   visible `finding_dispositions_r<N>` run-context keys and the prior stage
   transcript. Identify every finding marked ACCEPTED.
2. Fix each ACCEPTED finding in this clone, strictly within the work-item
   scope. Do NOT implement rejected findings, advisories, unrelated cleanup,
   new features, broad refactors, or speculative abstractions.
3. If an ACCEPTED finding cannot be implemented honestly within scope, that
   is a needs-human `failed` outcome. Do not silently skip it and do not
   reclassify it as rejected here.
4. Honor every rule from the implement stage: no `--no-verify` (if a hook
   fails, fix the cause or end with the needs-human protocol below,
   reporting its output verbatim); plain `git` for all git writes (the
   installed hooks fire on their own); Red-Green-Replay for any product `.py` change (a test-file
   change means a fresh Red commit, never an edit under an existing
   Green); commit trailer `Co-Authored-By: Claude Fable 5
   <noreply@anthropic.com>`; never create or switch branches, never touch
   `.beads/` or `core.bare`.
5. Re-run the repository's check suite (`{{ inputs.sandbox_check_suite }}`) yourself until it is green — the
   janitor re-validates this clone after this stage.
6. In your final reply, summarize each ACCEPTED finding as
   `FIXED — <what you changed>`. Mention rejected findings only to say
   they were intentionally left untouched per the disposition record.

## HONEST checks — no detector evasion (non-negotiable)

Make every check pass HONESTLY — by satisfying the condition it exists
to enforce, never by hiding the violation from its detector. A green
tree obtained by evasion is a FAILED outcome, not a success. This stage
is where such dodges have been authored under pressure from a
`[BLOCKING]` finding; resolving a finding by evasion is itself a
failure. Specifically FORBIDDEN:

- Forking or repointing a shared, externally-owned check (the fleet's
  dev-tooling Verifiers the prepare chain installed) to a weaker local copy;
  editing `dev-tooling/checks/**` or changing a `check-*` justfile recipe to
  invoke anything other than the pinned shared check module.
- Rewriting a banned call into a form the matcher doesn't recognize but
  that does the same thing (e.g. `sys.stdout.write`/`sys.stderr.write`
  -> `.buffer.write`).
- Constructing a class dynamically (`type(name, (Base,), ...)`) or
  otherwise restructuring code to hide a disallowed inheritance/pattern
  from an AST check.
- Silencing a check with `: Any`, `# type: ignore`, `# noqa`, symbol
  renames, or getattr/indirection instead of satisfying it.

If a check genuinely conflicts with a LEGITIMATE, required pattern —
i.e. the check over-applies (a domain exception that must subclass a
stdlib error; a launcher that can't carry `__all__`; a module correctly
invoked via `python -m`) — that is NOT yours to resolve by evasion or by
weakening the check. SURFACE it via the needs-human protocol: end with
`{"outcome":"failed","failure_reason":"check <name> over-applies to <legitimate pattern> at <file>; needs an upstream gate decision"}` so a
maintainer fixes the check upstream. Reserve this for a genuine
check-vs-legitimate-pattern conflict, not a check you simply find
inconvenient to satisfy.

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

## When you cannot proceed (needs-human protocol)

If an accepted finding needs a human decision, is NOT caused by this
branch's changes, or you have proven you cannot legitimately resolve it,
do NOT go quiet and do NOT paper over it. End your final reply with the
failed outcome and a STRUCTURED reason, as a JSON object on the last line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}

When the loop's budget exhausts, the graph terminates the run at the
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
