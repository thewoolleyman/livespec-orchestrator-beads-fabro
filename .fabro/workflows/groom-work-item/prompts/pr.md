# Publish stage — publish the filing plan for the Dispatcher to execute

## Your assignment

{{ goal }}

## Where you are, and what "publish" means here

You are in the same isolated Fabro sandbox clone the earlier nodes ran
in; your CURRENT WORKING DIRECTORY is that clone. The assignment above
may name a `Repo:` path — that is the dispatcher's host-side checkout, it
does NOT exist in this sandbox, and you must never `cd` to it.

**This run publishes a PLAN, not slices, and not a pull request.** There
is no diff, no branch to push and no pull request to open. Do not run
`git push` and do not run any `gh pr` command. The repository's merge
discipline (`{{ inputs.merge_mode }}`) and its per-item merge hold
(`{{ inputs.merge_hold }}`) govern the publication of CODE and are not
exercised by a groom run; they are named here so you can recognize that
none of the usual publish machinery applies to you.

**YOU DO NOT FILE, AND YOU CANNOT.** This sandbox is deliberately given
no ledger credential: the run-scoped environment carries the model and
forge tokens and nothing else, and the credential wrapper a `bd` call
falls back to is a HOST path that does not exist here. The Dispatcher
files the approved cut host-side, reading the plan off this terminated
run. Attempting the filing here fails on the missing credential, wastes
the run, and leaves the ledger untouched — that is a measured outcome
(run 01M1XNN6C8WHCW4EGDC7CWK6WW, 2026-09-07), not a hypothetical.

You are reached only in the APPLY phase — the graph routes the propose
phase to the terminal instead — so a human has already approved this
cut. Your job is to make the plan the Dispatcher executes correct,
because it is executed verbatim.

## What to do, in order

1. Confirm the phase: `/tmp/livespec-groom-phase` must read `apply`. If
   it does not, STOP and use the needs-human protocol below — reaching
   this node in any other phase is a routing fault, not something to
   work around.
2. Read the reviewed filing plan at `/tmp/livespec-groom-plan`. That plan,
   as reviewed, is what gets filed. Do not re-derive the cut from the
   draft comment and do not improve it here.
3. Re-read the approving answer comment in the assignment above and
   confirm the plan's header carries the two values the filing seam
   requires, both read off that comment: `approver=` (WHO approved — the
   approving invoker's identity) and `route=` (HOW the approval was
   obtained — the `resolve-blocked` valve plus the ledger comment the
   answer landed as). **Do NOT synthesize either value.** An identity you
   invented attributes the cut to someone who never approved it, which is
   far worse than the refusal you would otherwise get. If the answer
   comment does not name an approver, use the needs-human protocol.
4. Re-prove the plan's shape, because the terminal carries it over a
   single-line channel and the Dispatcher files whatever arrives:

   - it is exactly ONE non-empty line;
   - it opens with the literal token `livespec-groom-plan`;
   - it contains no brace character of any kind;
   - each ` ;; `-separated slice record carries `slice=`, `tier=`
     (`factory` or `human-gated`), `repo=`, `acceptance=` and `scope=`,
     with `blockers=` and `spec=` where they apply;
   - every `blockers=` handle names an EARLIER slice's title in this same
     plan. A handle naming a later slice, or a slice that is not in the
     plan, is a malformed cut.

   Repair the plan in place if any of this is wrong, keeping the cut the
   reviewer approved unchanged — you are correcting the ENCODING, never
   the decomposition.
5. Report the plan you published: the approver, the route, and each
   slice's title, tier, repo target and blockers. Name separately the
   slices marked `spec=yes` (routed to `propose-change`, not filed) and
   any whose `repo=` is not this repository (filed in their own tenant,
   not this one) so the maintainer knows what still needs routing.

## Hard rules

- Do not call the filing seam. Do not run any `bd` write command. Do not
  hand-roll a ledger write around either.
- Do not modify any tracked file. Do not commit, push, or branch.
- Never run `bd init`. Never write to any `.beads/` directory.
- Write the plan ONLY to `/tmp/livespec-groom-plan`. That path is where
  the terminal reads it from; a plan written anywhere else is published
  nowhere.

## Output

On success, end your reply with a single JSON object on the LAST line:

    {"preferred_next_label": "done"}

The run then terminates non-green by design: a groom run's product is a
dead run plus a ledger effect the Dispatcher performs, and that is the
only shape the "a factory run never awaits a human" contract permits.

If the plan is unusable and you cannot legitimately repair its encoding,
end instead with the structured needs-human ending, as a JSON object on
the last line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}
