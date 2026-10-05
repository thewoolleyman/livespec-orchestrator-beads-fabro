# Taking and replaying a host-captured proof

A host-captured assertion is one whose proof needs the RELEASED build on a real
host, so the factory sandbox that implemented it cannot be the thing that proves
it. Scenario 136 of `SPECIFICATION/scenarios.md` governs; the host-leg clause of
`SPECIFICATION/contracts.md` is the ratified text. This file is the operator
procedure plus the two ways a replay has already gone wrong in this repository.

The whole point of the leg is INDEPENDENCE: the session that captures the proof
may not be the session that verifies it. Everything awkward about the procedure
below follows from that one requirement, so read a refusal as the guarantee
working rather than as a tool defect.

## The procedure, in order

### 1. Declare the assertion under `Host-captured` with a `Reason:` line

In the item's `## Definition of Done`, put the assertion under a `Host-captured`
sub-heading and give that sub-heading a `Reason:` line saying why the released
build on a host is required. The Reason is not commentary — the approve valve
refuses to move the item to `ready` while a `Host-captured` sub-heading carries
no `Reason:` line, and the refusal names the missing line. Every other assertion
stays where it was; an item normally carries a majority of `factory_captured`
assertions and one host-captured one.

Declare this at FILING time. The proof stages read the dispatch-time snapshot of
the section, so adding a `Host-captured` sub-heading to a running item changes
nothing about the run in flight.

### 2. Let the merged item rest in `acceptance`

Dispatch and merge as usual. The host-side wall does not refuse an `ai-only`
item for carrying a host-captured assertion, and the post-merge acceptance pass
reports PASS with that assertion listed under a heading stating it is pending the
host leg. The item then rests in `acceptance` with its rework counter unchanged,
and `needs-attention` surfaces the pending host leg naming the item, the pull
request and the assertion.

Do not try to clear it from here. Under `ai-then-human` the accept valve refuses
while the host leg is pending, naming the assertion and the record format, and
that refusal is correct.

### 3. Capture on the host, against the released build

Run the assertion's reproduction steps ON A HOST, against a released build that
CONTAINS THE MERGE COMMIT. A record naming a release tag that does not contain
the merge is not evidence, and the acceptance pass says so — so establish the
containment before running anything, with a content or ancestry check against the
tag rather than against a branch SHA.

Write the evidence into a JSON payload for step 4. It carries a `build` object
and an `assertions` array, and nothing else:

```json
{
  "build": {
    "release_tag": "v0.170.0",
    "installed_build": "<the installed build hash>",
    "commit": "<the commit the tag resolves>"
  },
  "assertions": [
    {
      "text": "<the assertion, verbatim from the Definition of Done>",
      "governing_scenario": "## Scenario 136",
      "steps": ["<step 1>", "<step 2>"],
      "proof": "<the verbatim output those steps produced>"
    }
  ]
}
```

The payload carries ONLY what the capturing session alone holds. It cannot carry
an identity, a timestamp, a pull-request number or a proof MODE: the primitive
computes each of those, and the mode comes from the item's own Definition of
Done, so an assertion the item does not declare is refused rather than published
under a guess. A capture's own `reproduced` field is dropped — there is nothing
yet for a first leg to have reproduced.

### 4. Publish the capture with `post-host-record`

```bash
mise exec -- <path-to-build>/dispatcher.py post-host-record \
  --repo /data/projects/livespec-orchestrator-beads-fabro \
  --item <item-id> \
  --verdict host_recorded \
  --record <payload.json> \
  --invoker <role:name>
```

The primitive resolves the target itself — the pull request of the LATEST merged
run for the item — because a record on an earlier pull request is not evidence
and a `--pull-request` flag would put that mistake one typo away. Every refusal
fires BEFORE the `gh pr comment`, so a refused post publishes nothing; that
ordering is load-bearing, because a record may not be edited after posting and a
correction is a whole new record.

The published comment's header reads
`Proof of Done — host_recorded — session <id> — <timestamp>`. That third field is
the computed publishing identity, and it is the input to the next step's refusal.

### 5. A SEPARATELY STARTED agent session replays and publishes its own verdict

The replaying session runs the same reproduction steps and publishes its own
verdict with the same primitive:

```bash
mise exec -- <path-to-build>/dispatcher.py post-host-record \
  --repo /data/projects/livespec-orchestrator-beads-fabro \
  --item <item-id> \
  --verdict host_verified \
  --record <replay-payload.json> \
  --invoker <role:name>
```

Use `--verdict host_not_reproduced` when the steps did not reproduce. That is a
real outcome, not a failure to follow the procedure: under an AI-dispositive
policy the pass reads it as FAIL for that assertion and returns the item to
`active` with the rework-pending label, which is exactly the signal rework needs.
A replay payload MAY carry `"reproduced": true` or `"reproduced": false` per
assertion; a capture's may not.

Publishing a replay verdict drives `reconcile-merged --item <id>` through the
ordinary valve, which re-runs the acceptance pass; under `ai-only` the item then
closes to `done` with its pointer carrying the `host_verified` record link. There
is one route, so driving `reconcile-merged` by hand later is the same route — it
re-runs only the acceptance pass, with no post-merge janitor.

**"Separately started" is the whole requirement, and it is not satisfiable from
inside the recording session.** `computed_publishing_identity` reads
`CLAUDE_CODE_SESSION_ID`, then `CODEX_SESSION_ID`, then `PI_SESSION_ID`, and
falls through to the forge login only when none is set. Every one of those is
INHERITED — by a subshell, a background job, a sub-agent, a `codex exec`, a
second pane of the same session — so any process launched from the recording
session recomputes the recording identity and is refused as a self-replay. Only
a session started afresh, or a human at a terminal with no agent-session variable
set, computes a different one. Re-running the command inside the recording
session can never pass, because the inherited variable is the input.

A `host_verified` record carrying the recording identity, posted by any other
route, does not rescue it either: the assertion stays pending and is reported as
not independent.

## The two ways a replay goes wrong

Both of these were measured on 2026-10-05 while taking the first host record
this repository has ever had, for `bd-ib-ht4c2m`. Neither announced itself:
each produced a plausible observation at the surface the operator was watching,
and each cost a whole attempt at the proof.

### A publish branch seeded at an ancestor of master demonstrates nothing

When the assertion under proof is about the publish-branch reclaim — that a
dispatch finding a surviving publish branch preserves it to a run-scoped ref and
clears it from origin — the capture has to SEED that surviving branch by hand,
because an ordinary dispatch leaves none behind. The seed is where the proof is
lost.

**A publish branch seeded at a commit that is an ancestor of master is
fast-forwarded by the next run, and therefore cannot demonstrate a
non-fast-forward refusal or the need for a reclaim.** The run's HEAD is built on
master, so the remote branch head being an ancestor of it is exactly the
fast-forward case: the push is ACCEPTED, with no refusal and no warning. The
capture then records a "publish accepted" observation that is perfectly true and
carries no information — it is equally consistent with "the reclaim worked" and
with "there was never anything to reclaim", and nothing in the output
distinguishes them. This is the instrument-aim failure the trap catalogue in
AGENTS.md §"Beads runtime prerequisites" describes, arriving through a seed
rather than through a typo.

**A seeded branch has to point at a commit master does not contain.** That is
the only seed a push cannot fast-forward, so it is the only seed under which the
refusal can fire and the reclaim has anything to do. Commit something off
master — or seed at a dropped or reverted head — and verify the divergence
before capturing, with `git merge-base --is-ancestor <seed> origin/master`
expecting a NON-zero exit.

Two further facts from that instance, because each is a separate way the attempt
was lost:

- The reclaim acts only for an item that has an EARLIER JOURNALED DISPATCH and
  no live run, so on a FIRST dispatch it journals neither
  `publish-branch-reclaim` nor `publish-branch-reclaim-held` and leaves a
  surviving branch standing. The absence of both rows is a third, silent
  outcome; on a first dispatch it is the designed behaviour, not a fault. Read
  the held row's `reason` before clearing a publish branch by hand — see
  AGENTS.md §"Proof-of-Done, publish-branch reclaim, and drive action-id traps".
- Do not re-seed the SAME branch for a second attempt against a DIFFERENT item.
  The independent replay for `bd-ib-ht4c2m` hit the seed left at
  `refs/heads/feat/bd-ib-andmpe` with `bd-ib-dk3u2p`, whose first run
  fast-forwarded the branch, published its pull request and closed the item —
  leaving nothing to re-dispatch and consuming the item as proof material.

### A `herdr` agent pane finishes at agent status `done`, not `idle`

Step 5 needs a separately started session, and the natural way to get one is a
fresh agent session in its own `herdr` pane. The trap is in WAITING for it.

**A `herdr` agent pane finishes with agent status `done` rather than `idle`, so
a wait on such a pane has to accept either word.** herdr's documented
agent-status vocabulary is `idle`, `working`, `blocked`, `done` and `unknown`;
a session that has completed its delegated work settles at `done` and stays
there. A hand-written loop polling for `idle` therefore never matches, and it
fails SILENTLY — there is no error, no timeout and no notification, just a wait
that outlives the result it was waiting for.

Measured on 2026-10-05: a waiter armed at 09:31:26 as

```text
sleep 120; until herdr pane get w1:pB 2>/dev/null | grep -q '"agent_status":"idle"'; do sleep 60; done
```

was still looping at 13:53. The replay session it watched had published its
`host_not_reproduced` record on the pull request at 10:31:37 and settled at
`done`. That is three hours and twenty-one minutes of waiting for a state that
had already been passed, ended by the maintainer asking whether the session was
stalled.

Two more defects in that one line, both of which the remedy below also fixes:

- `2>/dev/null | grep -q` turns a FAILURE of `herdr pane get` — the pane closed,
  the server restarted — into a non-match, so the loop had no arm for "the thing
  I am watching no longer exists".
- It carried no deadline. A tool-level timeout on the backgrounded call did not
  act as one.

**Use the purpose-built primitive instead of hand-writing the loop.**
`herdr agent wait <target>` matches `idle`, `done` OR `blocked` by default and
accepts `--timeout <ms>`, so it covers the terminal state this trap is about,
the blocked state a replay can genuinely reach, and the deadline a hand-written
`until` loop has no way to express. If you do write a condition by hand, accept
either word and give it an arm for the target disappearing.
