# The released scripted-publication procedure: exercising `pr_refresh` and `pr` when the default branch advances after a draft publishes (2026-10-13)

Status of this note: the third research note of plan
`pr-stage-backgrounded-push-fault`. It records the PROCEDURE for exercising
the scripted publication stages on a RELEASED build, under the condition the
plan was opened for — a default branch that advances after a dispatch has
already published its draft pull request. It is written from this
repository's own sources, listed in §2, and it decides nothing that binds an
implementer.

This note describes a procedure, never the outcome of a particular run. A
document cannot report its own later publication outcome: whatever run
carries this file to the default branch is itself one instance of the
procedure below, and its result is readable only from that run's export,
its pull request and its ledger record — not from these pages. Every log
line quoted here is quoted as the sentinel an operator LOOKS FOR, not as
evidence that it was seen.

All times are UTC. "The engine" means the Fabro build on the selected
factory. "The released build" means the orchestrator plugin build installed
through its normal installation path, as distinct from a working tree. "The
aggregate" means the repository-declared `sandbox_check_suite`, rendered
into the publication stages as a foreground command.

## 1. Why a released build, and why this condition

Three things have to be true at once before the scripted publication stages
can be exercised at all, and each one is a precondition an operator has to
arrange rather than something a dispatch will produce on its own.

**The build must carry the scripted stages.** Release 0.195.0 is the first
release of this repository whose workflow ships `pr_refresh` and `pr` as
COMMAND stages rather than agent turns — `CHANGELOG.md` records it as
`workflow: script the implementation PR refresh and publication stages`
(`fed9105`), beside `dispatcher: render the publication title and body the
pr stage applies` (`b440324`) and `workflow: bind publication arming to the
proof-verified head` (`e73394d`). A dispatch on any earlier release
exercises the agent-turn publication leg instead, which is the leg this
plan exists because of, so a procedure aimed at the scripted stages requires
a released build at or after v0.195.0 and is not satisfied by a sandbox
whose workflow happens to be newer than its installed build.

**The default branch must advance AFTER the draft exists, not before.**
`publish_draft` refreshes its own base at the moment it runs, so a default
branch that moved before the dispatch started leaves `pr_refresh` nothing to
do and the run reports its unchanged-head outcome. The window this procedure
needs opens when `publish_draft` has pushed the publish branch and opened
the draft pull request, and closes when `pr_refresh` runs; the advance has
to land inside it. That is why the advance is a deliberate operator act
(§3, step 3) and not something to wait for.

**The run must not merge out from under the observation.** Under the default
policy the `pr` stage arms auto-merge the moment the proof-verified head is
established, which can remove the pull request before an operator has read
its records. The per-item merge hold is what keeps the published pull
request standing and readable, which is why step 1 comes first.

## 2. The sources this procedure is written from

- `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro` — the
  `publish_draft`, `pr_refresh`, `pr_refresh_head`, `pr` and `verify_pr`
  nodes, their scripts, their timeouts and the edges between them. The
  graph's own header comment states the node order.
- `SPECIFICATION/contracts.md` §"Definition-of-Done and Proof-of-Done
  stages" → "Scripted publication and proof-head integrity", which is the
  ratified duty of `pr_refresh` and `pr`; §"Proof of Done record", which is
  the record format and the requirement that a factory record name the
  publish-branch head the stage ran on; and §"Dispatcher policy settings" →
  "The per-item merge hold".
- `SPECIFICATION/scenarios.md` §"Scenario 132 — A factory-captured proof is
  captured on a draft pull request, reviewed, replayed and published", whose
  scenarios "Slow hooks after a post-draft rebase are command work",
  "Publication refuses unverifiable provenance and conflicts" and "Refresh
  is idempotent and bounded" state the behaviour this procedure observes;
  and §"Scenario 119 — A per-item merge hold publishes the pull request and
  merges only on release", which states what a held publication looks like.

## 3. The procedure, in order

### Step 1 — Set the merge hold on the item that will be dispatched

Run the human valve action `set-merge-hold:<work-item-id>:on` through
`drive`. On beads the hold is realized as the item's `merge-hold:` label,
and setting it also disarms any auto-merge request already on a pull request
for that item; it changes no other field and never changes the item's
status. The Dispatcher renders the item's effective hold as the workflow
input `merge_hold`, resolved before the sandbox executes, so the hold must
be in place BEFORE the dispatch is created — a hold set mid-run cannot
reach the run that is already executing.

Write the action id with the work-item id braced or fully literal. An
unbraced `set-merge-hold:$item:on` is safe in `bash` and in `zsh` alike
because `on` carries no history-style modifier, but the valve family as a
whole is not: `${item}` is the form that holds for every value, and this
repository's `AGENTS.md` records the measured rewrites.

### Step 2 — Dispatch the item on a released build at or after v0.195.0

Dispatch normally. Before believing the dispatch exercised the scripted
stages, establish WHICH build executed it: a long-lived agent session binds
its plugin root once at session start, so the build a session dispatches
through is not necessarily the build its repository resolves. The
dispatcher journals a registered-install-lag warning when the executing
build is older than the target repository's registered install, and that
warning is surfaced rather than enforced, so read the dispatcher stderr the
`drive` result carries. The remedy is to bring the SESSION onto the current
build, never to invoke a build by explicit path.

Record the factory the dispatch was routed to. The scripted stages leave
their evidence in the run's export, and every `fabro` query against that run
needs the factory named explicitly.

### Step 3 — Once the draft pull request exists, advance the default branch

Watch for `publish_draft` to complete. It pushes the publish branch, records
the sha it pushed into the run's publication state, and opens the DRAFT pull
request the proof is captured on; `proof_capture` then posts the first
`captured` record against that head.

With the draft standing, advance the default branch by merging an unrelated
change that was itself being held for this purpose. Merging an unrelated
held change is what makes the advance controlled: it moves the default
branch without touching the dispatched item's tree, so the rebase
`pr_refresh` performs is a clean replay of this run's own commits onto a
base they have never seen, and nothing in the advance can conflict with the
work under observation.

### Step 4 — Read `publish_draft`'s refresh line, then `pr_refresh`'s outcome line

Two different nodes report two different things here, and the sentinels
belong to their own nodes:

- **`publish_draft`** reports its OWN base refresh as
  `LIVESPEC_PUBLISH_DRAFT_REFRESH`, naming `publish_branch`, `base_before`
  and `base_after`. It fetches the authoritative default branch, resolves
  the run's base against it, refreshes onto it — merging when the remote
  publish branch is already an ancestor of the run head, rebasing otherwise
  — and resolves the base again. The two shas on that line are therefore the
  base as the run found it and the base it published against. This line is
  emitted BEFORE the push and before any proof capture, so it reports the
  base at draft time, and it says nothing about an advance that happens
  afterwards. That is the whole reason step 3 has to land after it.
- **`pr_refresh`** reports its own outcome, and there are two happy-path
  outcome lines rather than one.
  `LIVESPEC_PR_REFRESH_CHANGED` names the branch, the base it rebased onto
  and the new head it republished, and states that the verified proof names
  the old head so fresh capture, review and replay are owed.
  `LIVESPEC_PR_REFRESH_UNCHANGED` states that the published head already
  contains the authoritative default, so no rebase is owed and the verified
  proof still names the head that will be published. An operator exercising
  this procedure is looking for the CHANGED line; the UNCHANGED line is the
  honest report that the window of step 3 was missed, and it is a reason to
  re-run the procedure rather than a fault.

`pr_refresh` is a command stage with its own timeout, which is what makes
the slow-hook condition tractable: it runs the repository-declared
`sandbox_check_suite` as a FOREGROUND command against the rebased head, then
re-checks that the sandbox plugin registry still matches the build the run
prepared with, and pushes only after both pass. Hooks run normally. The push
is a leased write against the remote head this run itself recorded — never a
bare force, never `--no-verify`, never another ref. So the CHANGED line is
not merely a claim that a rebase happened: by the time it is printed, the
aggregate has passed against the rebased tree and the new head is on origin
under a lease nobody else could have satisfied.

Read all of this from the run's export rather than from a console. The
sentinels go to stderr, and the stage status files do not carry them:

```
fabro dump <run-id> --server <factory-url> -o <export-dir>
```

Then read each stage's own output and `events.jsonl` in that export. A
stage's `status.json` carries an outcome and a generic failure label, not a
cause, so a sentinel is found in the stage output and the event stream.

### Step 5 — Check that the proof stages produced FRESH records naming the changed head

A changed head invalidates the proof that was verified before the rebase,
and the graph enforces that rather than trusting it: `pr_refresh_head` asks
whether `pr_refresh` republished the branch, and a changed head routes back
to `proof_capture`, then `review`, then `proof_verify`. The procedure's
observation is that this loop actually ran and produced NEW records.

A factory Proof of Done record is one new comment on the pull request whose
first line carries its verdict, the run or session identity, and a UTC
timestamp, and whose body names, once, the full commit sha of the
publish-branch head the stage ran on. Records are never edited; a correction
is a new record. So the comparison an operator performs is mechanical:

- take the publish-branch head that `LIVESPEC_PR_REFRESH_CHANGED` reports as
  republished;
- read the LATEST `captured` record and the LATEST `verified` record on the
  pull request;
- confirm both name THAT sha, and that both are newer than the records
  posted against the pre-rebase head.

A pair of records naming the old head is the failure this check exists to
catch, and it is the same comparison the `pr` stage then makes for itself
through the Dispatcher-materialized publication-head program: `pr` asks that
program for the head whose proof is both captured AND verified, and refuses
rather than readying the pull request when that sha differs from the head
the pull request actually carries, or when the pull request carries a head
this run did not push.

### Step 6 — Check the pull request is ready with auto-merge deliberately unarmed

Under the hold, `pr` does everything publication normally does except arm
the merge. It applies the Dispatcher-rendered title and body — passed as
data, never interpolated as shell syntax — marks the draft ready for review,
reads the pull request's auto-merge state, and verifies that NO auto-merge
request exists. It reports `PR_NUMBER=` and `MERGE_HOLD=held` on stdout,
with `LIVESPEC_PR_HELD` naming the pull request and the release valve. If an
auto-merge request is present while the hold stands, the stage fails closed
for a human rather than disarming it, because a script must not reverse a
human's arming.

The run then terminates GREEN with the pull request standing. The item
remains `active`, its green terminal run is reclaimed so it holds no
capacity slot, reconciliation does not treat it as an orphan or as stranded,
and `needs-attention` surfaces exactly one hygiene row for the hold naming
the pull request and the release valve. That row is how the hold stays
visible until it is released.

### Step 7 — Release the hold to merge

Run `set-merge-hold:<work-item-id>:off`. Against an item whose pull request
is open and unmerged, that arms auto-merge from the host using the merge
method journaled with the dispatch that opened the pull request — never
re-derived from configuration — and creates NO new dispatch. The merge then
lands server-side, and the existing post-merge path proceeds unchanged: the
post-merge janitor, `reconcile-merged` for that item, and acceptance. The
hold's attention row disappears from the next snapshot.

## 4. What this procedure does and does not establish

It establishes that, on a released build, a dispatch whose base moves after
its draft is published reaches a ready pull request through command stages
alone — no agent turn in the publish leg — with the aggregate run in the
foreground against the rebased head, the republish leased against the head
the run recorded, and fresh captured and verified records naming the head
that is finally published.

It does NOT establish the fail-closed behaviour of those stages. The
foreign-head, unobservable-origin, conflicted-rebase and
three-refresh-non-convergence causes each have their own sentinel and their
own recovery, and none of them is on this path; Scenario 132's
refusal and bounding scenarios govern them, and exercising them needs
conditions this procedure deliberately avoids creating. Nor does it
establish anything about the agent-turn publication leg that the plan's
note 001 analysed: a dispatch on a build at or after v0.195.0 does not
execute that leg at all.
