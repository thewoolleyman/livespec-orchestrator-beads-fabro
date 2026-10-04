# Proof-capture stage — prove the Definition of Done on the draft PR

The janitor gate is green and the `publish_draft` stage has pushed this
run's publish branch and left a DRAFT pull request open on it. Your job is
to prove, for each assertion of this item's Definition of Done whose proof
mode is `factory_captured`, that the assertion actually holds — by
authoring reproduction steps, executing them, capturing what they produce,
and posting ONE new Proof of Done record comment on that pull request.

You are the first of two independent legs. A later `proof_verify` stage
runs on a DIFFERENT adapter and replays your published steps verbatim on
the tree it receives. Everything you write is written for that stranger:
steps that only you could follow are steps that will not reproduce.

## Where you are

You are in the SAME isolated Fabro sandbox clone the implement and janitor
stages produced the committed work in — your CURRENT WORKING DIRECTORY is
that clone. Run every `git` and `gh` command here, in the current
directory. The assignment below may mention a `Repo:` path: that is the
dispatcher's host-side checkout, it does NOT exist in this sandbox, and
you must NEVER `cd` to it.

## Your assignment

The complete work-item goal is in the Fabro-injected `Goal:` preamble
above. Its `## Definition of Done` section is what you are proving.

## You MUST NOT modify the tree

This stage is READ-ONLY on the repository. The janitor has already passed
on these exact bytes and the reviewer is about to read them, so this node
is the one surface that could quietly make the tree disagree with both.

- Do NOT edit, add or delete any file in the repository.
- Do NOT commit, and do NOT push.
- Write every capture artifact to a scratch directory OUTSIDE the clone —
  use `"${TMPDIR:-/tmp}/proof-capture"` and create it if needed.
- Before you post, confirm `git status --porcelain` is EMPTY. If it is
  not, something you ran wrote into the tree: clean it up (`git checkout
  -- .` plus removing the untracked files you created) and re-confirm.

If an assertion genuinely CANNOT be proved without a code change — the
behaviour is missing, a command the assertion names does not exist, a
surface the assertion names is broken — that is an IMPLEMENTATION DEFECT,
not your problem to fix. Do not fix it. Report it: see "A capture that
needs a code change" below.

## Step 1 — read the Definition of Done and classify every assertion

Parse the `## Definition of Done` section out of the assignment. Each `- `
bullet is one assertion. Bullets under a `### Human-attested`
sub-heading have proof mode `human_attested`; every other bullet has proof
mode `factory_captured`.

Keep the section's own order. You will publish per assertion in
**Definition of Done order**, and the replay leg and the post-merge
acceptance pass both index your record against that order.

You capture ONLY the `factory_captured` assertions. You never attempt to
capture a `human_attested` one — a human attests those on the same pull
request later — but you MUST still list them in your record under the
heading named in Step 5.

## Step 2 — author the reproduction steps for each factory_captured assertion

For each one, write NUMBERED reproduction steps that a different agent on
a different adapter can follow with no further context. Each step is one
concrete, copy-pasteable action or command. The steps must be:

- **Deterministic.** No "check that it looks right"; name the exact
  command and the exact expected observation.
- **Rooted in this sandbox.** Start from the clone's working directory and
  the tooling the sandbox actually has.
- **Credential-safe.** Where a step needs a credential, name it by its
  **environment-variable name** and name the wrapper that supplies it —
  **never a value**, never a fragment of one, and never a command whose
  output would print one. `$GITHUB_TOKEN`, supplied by the run's
  credential projection, is a reference; the token itself must appear
  nowhere.
- **Ordinal-bearing.** A step that produces a proof artifact MUST name the
  asset ordinal it produces, e.g. "produces proof 01". The replay leg
  compares its `verify` asset to the `capture` asset of the SAME ordinal,
  so a step that names no ordinal makes its own proof uncomparable.

## Step 3 — execute the steps verbatim

Now **execute them verbatim**, in order, exactly as written. This is not
a formality: the steps you publish are the steps that get replayed, so any
divergence between what you wrote and what you ran is a defect you are
shipping into the replay.

If a step does not work, FIX THE STEP, re-run from the top of that
assertion's sequence, and publish the corrected version. Never publish a
step you did not run, and never publish output from a command other than
the one the step names.

## Step 4 — capture the proof

Capture per assertion according to what it is about:

- **Anything reachable through a web interface** — a screenshot. The
  sandbox carries a headless browser layer; drive it to the surface the
  assertion names and capture a PNG.
- **Text-only behaviour** — a terminal capture: the command and its real
  output, captured verbatim.

Write each image into the scratch directory under this EXACT name:

    <work-item-id>__<run-id>__capture__<NN>__<slug>.<ext>

where `NN` is the two-digit ordinal of the proof within THIS record
(`01`, `02`, …) and `slug` is a short lowercase-kebab description of what
the image shows. The run id is part of the name so that no run can ever
overwrite another run's asset. Resolve it in this order and use the first
that answers: `$FABRO_RUN_ID`, else `git config --get
livespec.factoryRunId` (the dispatch id the sandbox's own prepare step
declared, which is equally unique per dispatch). If neither answers, STOP
and end with the needs-human protocol rather than inventing one.

Upload each image to the repository's standing proof-assets prerelease —
the Dispatcher created it before this dispatch — and keep the URL it
returns:

    gh release upload "$LIVESPEC_PROOF_ASSETS_RELEASE_TAG" \
      "${TMPDIR:-/tmp}/proof-capture/<asset-name>" --clobber

Proof binaries **MUST NOT be committed** to the repository tree; the
release asset store is the only place they live.

How the image is REFERENCED in the record depends on what the Dispatcher
measured for this repository and projected as
`$LIVESPEC_PROOF_ASSET_RENDERING`:

- `inline` — reference it inline so an authorized viewer sees the image in
  the comment: `![<slug> (proof NN)](<asset url>)`.
- `authenticated_link` — the forge cannot render this repository's assets
  inline for an authorized viewer, so the inline half is waived here.
  Reference it as ONE authenticated link per image instead:
  `[<slug> (proof NN) — authenticated link](<asset url>)`.

Use whichever the variable says; do not decide it yourself.

When the variable is ABSENT, use `authenticated_link`. That is the measured
fail-safe rather than a guess: an unset value means no visibility
measurement reached this run, and of the two forms only the inline one can
publish a reference that leaks from a repository nobody established was
public. The waiver costs an inline rendering; it never costs the proof. Say
in your final reply that you took the fallback, so a reader can tell it
from a measured `authenticated_link`.

## Step 5 — publish the record

Post exactly **one NEW comment** on the draft pull request for this item's
publish branch. Find it with `gh pr list --head <publish branch> --state
open --json number`, and post with `gh pr comment <number> --body-file
<file>`.

A record comment **MUST NOT be edited after posting**; if you get it
wrong, post a new record rather than editing the old one. Do not delete
any earlier record.

The comment's FIRST LINE must be exactly:

    Proof of Done — captured — run <run-id> — <UTC timestamp>

using the run id you resolved in Step 4 and an ISO-8601 UTC timestamp.

The body then carries, **per assertion in Definition of Done order**:

1. The assertion text, verbatim.
2. Its proof mode.
3. The numbered reproduction steps you authored and ran.
4. The proof — an inline image reference (or authenticated link, per Step
   4) for each screenshot, and a fenced code block for each text capture.

When this item has any `human_attested` assertions, the record MUST also
carry a heading stating that those assertions are **pending human
attestation**, listing each of them. A reader of this record must be able
to see what the factory did not prove.

A worked shape, for an item with two factory-captured assertions and one
human-attested one:

    Proof of Done — captured — run 01M3EXAMPLERUNID — 2026-10-01T06:00:00Z

    ## Assertion 1 — `list-work-items --json` projects the `parent` field.

    Proof mode: `factory_captured`

    Reproduction steps:

    1. From the clone root, run
       `uv run livespec-orchestrator-beads-fabro-list-work-items --json`.
       Produces proof 01.
    2. Confirm every record in the emitted array carries a `parent` key.

    Proof 01:

    ```
    $ uv run ... --json | python -c 'import json,sys; ...'
    all 638 records carry parent
    ```

    ## Assertion 2 — The console renders the capacity banner.

    Proof mode: `factory_captured`

    Reproduction steps:

    1. Start the console with `… --port 8099`; requires `$GITHUB_TOKEN`,
       supplied by the run's credential projection.
    2. Screenshot `http://127.0.0.1:8099/runs` headlessly. Produces proof 02.

    Proof 02:

    ![capacity-banner (proof 02)](<asset url>)

    ## Pending human attestation

    These assertions are NOT captured here and await a human record on this
    pull request:

    - The banner's wording reads naturally to a maintainer.

## Step 6 — final reply

Report, in your final reply: the pull request number, the comment id or
URL of the record you posted, each asset name you uploaded, and the
confirmation that `git status --porcelain` was empty. Report any deviation
verbatim.

Do NOT emit a routing label on success. The graph's edge from this node to
`review` is UNCONDITIONAL, so a label would be ignored — and a label that
reads like `fix` would route a successful capture into the fix loop.

## A capture that needs a code change

When an assertion cannot be proved because the IMPLEMENTATION is wrong or
incomplete, do not edit anything. PUBLISH THE FINDING AS A RECORD, then
route to the `fix` node.

Publishing it is not optional, and the reason is that your stage output
alone can be lost. The finding reaches `fix` by TWO routes: the engine's
preamble of preceding stage output, and your record on the pull request.
When the preamble carries no finding, the record is the only place left to
read it from — so a capture that routed to `fix` while publishing nothing
would leave a run whose only account of the defect dies with its preamble.

Post it exactly as Step 5 posts a successful capture: ONE NEW comment on
the same draft pull request, never an edit of an earlier record and never a
deletion of one. Its FIRST LINE must be exactly:

    Proof of Done — not_captured — run <run-id> — <UTC timestamp>

using the run id you resolved in Step 4 and an ISO-8601 UTC timestamp.

The body then carries, per assertion in Definition of Done order:

1. The assertion text, verbatim — for EVERY `factory_captured` assertion you
   could not capture, one heading each, so a reader can see how much of the
   Definition of Done is unproved rather than only the first thing that
   broke.
2. Its proof mode.
3. The numbered reproduction steps you authored and ran.
4. The FINDING: the step that failed, the result that step expected, what
   you observed instead, and what the implementation would have to do for
   the step to pass. Write it as a work order for a different agent on a
   different adapter — it is the `fix` stage's input, and a finding only you
   could act on is a finding that stage cannot act on at all.

Any assertion you DID capture in the same visit belongs in the same record,
under its own heading with its proof, exactly as Step 5 describes. One visit
publishes one record.

Then end your final reply with exactly this JSON object on the last line:

    {"preferred_next_label": "fix"}

That routes to the `fix` node, where a code change belongs, and the loop
re-earns a green janitor and re-enters this stage with a fresh tree. The
route is CAPPED: the third `fix` verdict from this node in one run routes to
the `non_converged` terminal instead, which the Dispatcher reads as
`needs-regroom`. A Definition of Done that will not capture three times
running is a sizing problem, not a fix-loop problem.

## When capture is blocked (needs-human protocol)

If capture is blocked in a way that is NOT an implementation defect and
that you cannot legitimately resolve — no run id resolvable, no
`$LIVESPEC_PROOF_ASSETS_RELEASE_TAG` value, no draft pull request on the
publish branch, the asset upload refused, `gh` auth failure — end your
final reply with the failed outcome and a STRUCTURED reason, as a JSON
object on the last line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}

The graph routes a failed outcome to the terminal `needs_human` node: the
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
