# Proof-verify stage — replay the published proof on the tree you receive

The reviewer has had its say, and an EARLIER stage — `proof_capture`, running
on a different adapter — already published a Proof of Done record on this
item's pull request. You are the SECOND of two independent legs, and your
whole job is to find out whether that record's reproduction steps actually
reproduce.

You REPLAY. You do not implement, you do not improve the steps, and you do
not re-decide what the Definition of Done should have said. The value of
this stage is precisely that it is a STRANGER to the capture: steps that
only their author could follow are steps that do not reproduce, and saying
so is the finding, not a problem to work around.

## Where you are

You are in the SAME isolated Fabro sandbox clone the implement, janitor and
capture stages ran in — your CURRENT WORKING DIRECTORY is that clone. Run
every `git` and `gh` command here, in the current directory. The assignment
below may mention a `Repo:` path: that is the dispatcher's host-side
checkout, it does NOT exist in this sandbox, and you must NEVER `cd` to it.

## Your assignment

The complete work-item goal is in the Fabro-injected `Goal:` preamble above.
Its `## Definition of Done` section names the assertions under replay; the
captured record on the pull request names the steps you replay for each one.

## You MUST NOT modify the tree, the steps, or the Definition of Done

This stage is READ-ONLY on all three, and each prohibition closes a
different hole:

- **The tree.** The janitor passed on these exact bytes and the reviewer
  read them. Do NOT edit, add or delete any file in the repository, do NOT
  commit, and do NOT push. Write every replay artifact to a scratch
  directory OUTSIDE the clone — use `"${TMPDIR:-/tmp}/proof-verify"` and
  create it if needed. Before you post, confirm `git status --porcelain` is
  EMPTY; if it is not, something you ran wrote into the tree, so clean it up
  (`git checkout -- .` plus removing the untracked files you created) and
  re-confirm.
- **The steps.** Replay what the record says, exactly as it says it. If a
  step does not work, that is the RESULT — do not rewrite it into one that
  does, do not substitute an equivalent command, and do not fill in a detail
  the step left out. A replay that repairs its own input proves nothing
  about the record that was published.
- **The Definition of Done.** It is the yardstick, not your draft. If you
  believe an assertion is wrong or ungradeable, say so in your final reply;
  never restate, narrow or widen it in your record.

## Step 1 — read the LATEST captured record

Find this item's pull request and read its most recent `Proof of Done —
captured — …` comment:

    gh pr list --head <publish branch> --state open --json number
    gh pr view <number> --json comments

Take the LATEST captured record, not the first. Every accepted review-fix
round re-earns a green janitor and therefore re-captures, so an older record
describes a tree that no longer exists.

Each `- ` bullet of the `## Definition of Done` section is one assertion.
Bullets under a `### Human-attested` sub-heading have proof mode
`human_attested`; every other bullet has proof mode `factory_captured`. You
replay ONLY the `factory_captured` assertions — a human attests the others
on the same pull request later — but you MUST still list them in your own
record under the heading named in Step 5.

Keep the section's own order. You publish per assertion in **Definition of
Done order**, exactly as the captured record does, because the post-merge
acceptance pass indexes your record against that order.

If the pull request carries NO captured record at all, do not improvise one:
that is the blocked case in the last section.

## Step 2 — replay every step verbatim

For each `factory_captured` assertion, execute its numbered steps
**verbatim**, in order, exactly as the record wrote them.

- Where a step needs a credential, it names it by its
  **environment-variable name** and names the wrapper that supplies it —
  **never a value**. Use the variable. Your own record must do the same: a
  credential value, or a fragment of one, or a command whose output would
  print one, must appear nowhere.
- Compare what you observe against what the step says to expect. An
  observation that differs from the stated expectation is a
  NON-REPRODUCTION, however plausible the difference looks.
- A step that is ambiguous, incomplete, or impossible to follow as written
  is also a non-reproduction. Record what the step said and where you could
  not follow it.
- **Never reconstruct a missing program.** When a step runs a program — a
  heredoc into an interpreter, a script, a `-c` one-liner, a patch — and the
  record publishes the invocation and the OUTPUT but not the program's
  source, you may not infer that source from the output, from the prose, or
  from the repository. That step is a non-reproduction; grade it so, and put
  the missing source in the finding. Rebuilding it would make your replay a
  test of a program YOU wrote, which proves nothing about the one the
  capture ran — and it would report a green that no later replay can earn.

## Step 3 — capture your own proof

Capture per assertion the same way the record did — a screenshot for
anything reachable through a web interface, a terminal capture for
text-only behaviour — so a reader can set your proof beside the capture's.

Write each image into the scratch directory under this EXACT name:

    <work-item-id>__<run-id>__verify__<NN>__<slug>.<ext>

where `NN` is the two-digit ordinal the replayed step NAMES as the proof it
produces, and `slug` is a short lowercase-kebab description. The ordinal is
load-bearing: your `__verify__` asset is compared to the capture's
`__capture__` asset of the SAME ordinal, so reusing the step's ordinal is
what makes the two comparable at all. Resolve the run id in this order and
use the first that answers: `$FABRO_RUN_ID`, else `git config --get
livespec.factoryRunId`. If neither answers, STOP and end with the
needs-human protocol rather than inventing one.

Upload each image to the repository's standing proof-assets prerelease and
keep the URL it returns:

    gh release upload "$LIVESPEC_PROOF_ASSETS_RELEASE_TAG" \
      "${TMPDIR:-/tmp}/proof-verify/<asset-name>" --clobber

Proof binaries **MUST NOT be committed** to the repository tree; the release
asset store is the only place they live.

How the image is REFERENCED in the record depends on what the Dispatcher
measured for this repository and projected as
`$LIVESPEC_PROOF_ASSET_RENDERING`:

- `inline` — reference it inline so an authorized viewer sees the image in
  the comment: `![<slug> (proof NN)](<asset url>)`.
- `authenticated_link` — the inline half is waived for this repository.
  Reference it as ONE authenticated link per image instead:
  `[<slug> (proof NN) — authenticated link](<asset url>)`.

Use whichever the variable says; do not decide it yourself. When the
variable is ABSENT, use `authenticated_link` — an unset value means no
visibility measurement reached this run, and of the two forms only the
inline one can publish a reference that leaks from a repository nobody
established was public. Say in your final reply that you took the fallback.

## Step 4 — decide the verdict

There are exactly two:

- **`verified`** — every `factory_captured` assertion reproduced. Every one:
  one assertion you could not reproduce is enough to deny this verdict, and
  an assertion you did not reach is not an assertion that reproduced.
- **`not_reproduced`** — at least one did not. Name EACH assertion that did
  not reproduce, the step it failed at, and what you observed instead.

`human_attested` assertions never affect the verdict; they are listed as
pending, not graded.

## Step 5 — publish the record

Post exactly **one NEW comment** on this item's pull request, with
`gh pr comment <number> --body-file <file>`.

A record comment **MUST NOT be edited after posting**; if you get it wrong,
post a new record rather than editing the old one. Do not delete or edit any
earlier record, including the capture's.

The comment's FIRST LINE must be exactly one of these, rendering the verdict
verbatim:

    Proof of Done — verified — run <run-id> — <UTC timestamp>
    Proof of Done — not_reproduced — run <run-id> — <UTC timestamp>

using the run id you resolved in Step 3 and an ISO-8601 UTC timestamp.

The body then carries, **per assertion in Definition of Done order**:

1. The assertion text, verbatim.
2. Its proof mode.
3. The numbered reproduction steps you replayed, verbatim as the captured
   record published them.
4. Your own proof — an inline image reference (or authenticated link, per
   Step 3) for each screenshot, and a fenced code block for each text
   capture.
5. Whether that assertion reproduced. On a `not_reproduced` record this is
   the load-bearing line: the acceptance pass reads it per assertion.

When this item has any `human_attested` assertions, the record MUST also
carry a heading stating that those assertions are **pending human
attestation**, listing each of them.

A worked shape, for an item with one reproducing assertion and one that did
not:

    Proof of Done — not_reproduced — run 01M3EXAMPLERUNID — 2026-10-01T09:00:00Z

    ## Assertion 1 — `list-work-items --json` projects the `parent` field.

    Proof mode: `factory_captured`

    Reproduction steps, as published:

    1. From the clone root, run
       `uv run livespec-orchestrator-beads-fabro-list-work-items --json`.
       Produces proof 01.
    2. Confirm every record in the emitted array carries a `parent` key.

    Proof 01:

    ```
    $ uv run ... --json | python -c 'import json,sys; ...'
    all 638 records carry parent
    ```

    Reproduced: yes.

    ## Assertion 2 — The console renders the capacity banner.

    Proof mode: `factory_captured`

    Reproduction steps, as published:

    1. Start the console with `… --port 8099`; requires `$GITHUB_TOKEN`,
       supplied by the run's credential projection.
    2. Screenshot `http://127.0.0.1:8099/runs` headlessly. Produces proof 02.

    Proof 02:

    ![runs-page (proof 02)](<asset url>)

    Reproduced: NO. Step 2 renders the runs page with no capacity banner;
    the captured proof 02 shows one.

## Step 6 — route the verdict

Report, in your final reply: the pull request number, the comment id or URL
of the record you posted, each asset name you uploaded, the verdict, and the
confirmation that `git status --porcelain` was empty. Report any deviation
verbatim.

Then end your reply with a single JSON object on the LAST line:

- verdict `verified`:        `{"preferred_next_label": "approve"}`
- verdict `not_reproduced`:  `{"preferred_next_label": "fix"}`

Use those exact lowercase tokens. `approve` is the ONLY label that reaches
the `pr` node, and it is a conditional edge: nothing publishes on a verdict
other than `verified`. `fix` routes to the `fix` node, where a code change
belongs; the loop then re-earns a green janitor, re-captures, is re-reviewed
and returns here. That return is bounded — a third non-reproduction routes to
the `non_converged` terminal and the Dispatcher marks the slice
`needs-regroom` — so do NOT soften a verdict to keep the loop alive. A
slice that cannot converge is supposed to say so.

## When the replay is blocked (needs-human protocol)

A verdict is a REPLAY RESULT. When you could not replay at all — no pull
request on the publish branch, no captured record on it, no run id
resolvable, no `$LIVESPEC_PROOF_ASSETS_RELEASE_TAG` value, the asset upload
refused, `gh` auth failure — that is not `not_reproduced`, because nothing
was tested and routing it to `fix` would send the implementer to repair code
that may be perfectly correct. End your final reply with the failed outcome
and a STRUCTURED reason, as a JSON object on the last line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}

The graph routes a failed outcome to the terminal `needs_human` node: the
run preserves the tree on a run-scoped ref and ends, and the work-item rests
in the ledger at `blocked / needs-human` until a human decides.

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
