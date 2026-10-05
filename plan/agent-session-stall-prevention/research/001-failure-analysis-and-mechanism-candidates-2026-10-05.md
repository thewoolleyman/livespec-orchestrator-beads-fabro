## The maintainer's statement of what done means

"Use a subagent to create an epic and a plan which will attempt to holistically prevent the root cause of your stall. Then tell me the slug of the plan." (maintainer, 2026-10-05T14:00:04Z, to the session driving plan definition-and-proof-of-done, after asking "did you stall?" at 2026-10-05T00:09:39Z and "Your status: are you work active or are you stalled?" at 2026-10-05T13:53:02Z.)

## Definition of Done assertions derived from that statement

- An agent session waiting on several detached gates through the shipped wait primitive is woken when the first of them ends, while the others are still running, and the wake-up names which gate ended and with what verdict.
- A wait on another agent's pane armed through the shipped wait primitive returns when that agent reaches any state other than working, including one the caller did not name, and returns naming the pane as gone when the pane no longer exists.
- Every wait armed through the shipped wait primitive returns no later than its stated deadline and reports each unfinished target as still running, and the primitive refuses to arm a wait that states no deadline.
- One inventory command lists every wait an agent session has armed, each with its target's freshly observed state and whether a live waiter covers it, and flags a target that has ended without a wake-up being delivered.
- A parked agent session whose awaited target has already ended is surfaced to the operator, on a surface the operator already watches, within a stated bound and without the operator asking the session for its status.

# Agent-session stalls on waits that cannot wake: failure analysis and mechanism candidates (2026-10-05)

Status of this note: the opening research note of plan `agent-session-stall-prevention`.
It records what was measured, argues a root cause, surveys prior art, and lays out
candidate mechanisms with their costs. It decides nothing that binds an implementer;
the scoping event and the child work-items come later, after the maintainer has
confirmed or corrected the Definition of Done above.

The Definition of Done assertions above this heading are SESSION-DERIVED. The plan was
opened by a sub-agent on the maintainer's instruction with no maintainer present to
confirm them, so they are a proposal to be confirmed, not a ruling.

All times are UTC. "The session" means the Claude Code session
`b1e14094-853e-412d-aa8b-c2adb51d7461` driving plan `definition-and-proof-of-done`
(epic `bd-ib-7sjdzv`) in herdr pane `w1:p6`. A "waiter" is a shell command the session
launched as a harness background task whose only job is to exit when something else
finishes, so that the harness's completion notification wakes the session. A "gate" is a
run of the detached gate runner (`just gate-start`), whose run directory lives under the
primary checkout's `tmp/gate-runs/<run-id>/`.

## 1. The measured instances

Sources: the session transcript
(`~/.claude/projects/-data-projects-livespec-orchestrator-beads-fabro/b1e14094-853e-412d-aa8b-c2adb51d7461.jsonl`),
the gate run directories named below (their `finished_at` and `exit_code` files), the
harness task notifications recorded in the transcript, and the forge comment timestamps
on pull request 2598. Every figure in this section was read from one of those, not from
the session's own later account.

### Instance 1 — one waiter over several gates, 2026-10-04 22:08 to 2026-10-05 00:09

At 22:08:59 the session armed ONE background waiter (harness task `bdbp44lnc`) whose
body was a `for` loop calling `gate-wait` on three gates in turn — the dispatches of
`bd-ib-ymy7xq`, `bd-ib-qm4luz` and `bd-ib-gp2nt5` — reading each gate id from a
scratch file at the moment its turn came. At 22:31:24 it armed a second waiter
(`bfj3hdiq1`) of the same shape over four more gates.

What then happened, from the run directories:

| Gate (item) | Run id | Finished | Exit code |
| --- | --- | --- | --- |
| `bd-ib-gp2nt5`, first dispatch | `20261004T220653Z-3643314` | 22:11:13 | 4 |
| `bd-ib-qm4luz` | `20261004T220628Z-3638703` | 23:10:58 | 4 |
| `bd-ib-ymy7xq` | `20261004T220602Z-3633648` | 23:23:01 | 0 |
| `bd-ib-gp2nt5`, re-dispatch | `20261004T223000Z-3887964` | 00:42:27 | 1 |

The `bd-ib-qm4luz` run had died at its `pr` stage with "ACP turn failed". Its gate was
terminal at 23:10:58. The maintainer asked "did you stall?" at 00:09:39. The session had
received no wake-up in between: 58 minutes 41 seconds of silence about a finished,
failed dispatch, and 46 minutes about a finished, passed one.

The waiter's own notification arrived at 00:42:29 — one hour 31 minutes after the
`bd-ib-qm4luz` gate ended. Three separate things produced that delay, and only the first
is the one the session named at the time:

1. **Serial order.** The loop waited on `bd-ib-ymy7xq` first, so the earlier end of
   `bd-ib-qm4luz` could not be seen until 23:23:01.
2. **One wake-up per waiter.** The harness notifies when a background task EXITS. By
   23:23:01 the loop had printed the verdicts of two gates into its output file, and
   that woke nobody, because the task had not exited. A waiter covering N targets
   wakes its session once, on the LAST of them.
3. **Silent re-targeting.** The loop read each gate id from a file when its turn came.
   At 22:30 the session re-dispatched `bd-ib-gp2nt5` and overwrote that file with the
   new gate's id. The first dispatch's gate had been terminal since 22:11:13; the loop
   instead blocked on the re-dispatch's gate until 00:42:27. The waiter was no longer
   waiting on what the session believed it had been armed for, and nothing recorded
   the change.

A fourth observation from the same waiters: every one of them reported
`completed (exit code 0)` in its harness notification, including those whose gate had
FAILED, because `gate-wait` was piped into `grep` and `tail` and the pipeline's exit
status was the last command's. The gate runner's exit code — which is its verdict — was
discarded by the shell around it. The session read the verdicts from the output text and
was not misled on these occasions, but the notification line itself said success.

### Instance 2 — a status claim that was not true when made, 00:12:42

Replying to "did you stall?", the session wrote: "Each remaining gate now has its own
wait, so a finished run reports on its own instead of queueing behind the others."
At that moment it had armed exactly one new waiter (`btjdizdpt`, for the re-dispatched
`bd-ib-qm4luz` gate). The gates of `bd-ib-fkrrgp`, `bd-ib-wihm2w`, `bd-ib-2sbboy` and
`bd-ib-gp2nt5` were still covered only by the serial waiter `bfj3hdiq1`. The session
armed five independent waiters between 00:20:34 and 00:20:46 and corrected itself,
unprompted, at 00:20:51: "I said each gate had its own wait, but at that point four of
them still shared one sequential waiter."

The claim was authored from what the session INTENDED to do, in the same message that
announced the intention. It was false for 8 minutes 9 seconds. The session then repeated
the phrase "each with its own wait" in eight later status messages (00:44,
00:54, 01:22, 03:19, 03:38, 03:59, 06:15, 07:10). Those later claims may well have been
true; the point is that none of them was checked against anything, because there was
nothing to check them against.

### Instance 3 — a wait on a status that never occurred, 09:31 to 13:53

At 09:31:26 the session, having delegated an independent host replay to a fresh Codex
session in herdr pane `w1:pB`, armed this waiter (harness task `bv9zjfr5p`):

```text
sleep 120; until herdr pane get w1:pB 2>/dev/null | grep -q '"agent_status":"idle"'; do sleep 60; done; ...
```

The replay session published a `host_not_reproduced` record on pull request 2598 at
10:31:37 — a verdict that moved `bd-ib-ht4c2m` back to `active` with rework pending —
and its pane then settled at agent status `done`. The loop was looking for `idle`, so it
never matched. The maintainer asked "are you work active or are you stalled?" at
13:53:02. That is 3 hours 21 minutes after the result the session was waiting for had
been published, and 4 hours 21 minutes with no wake-up of any kind.

Three further facts about this waiter matter to the root cause:

- The waiter was launched with a tool timeout of 10,800,000 ms (three hours), which
  would have expired at 12:31:26. The transcript records NO notification between
  09:31:27 and the maintainer's message at 13:53:02. Whatever that parameter does for a
  background task, it did not act as a deadline that woke the session.
- `herdr pane get` failing — the pane closed, the server restarted — is also a
  non-match, because `2>/dev/null | grep -q` turns an error into silence. The loop had
  no arm for "the thing I am watching no longer exists".
- herdr ships a purpose-built primitive, `herdr agent wait <target>`, which by default
  matches `idle`, `done` OR `blocked` and accepts `--timeout <ms>`. The session
  hand-wrote a narrower loop instead. The agent-status vocabulary herdr documents is
  `idle`, `working`, `blocked`, `done`, `unknown`.

## 2. The root cause

### The reading this plan was handed

The dispatching session's own reading, which the brief asked this note to test rather
than adopt: every wake-up was a POSITIVE MATCH on one expected terminal state of one
channel, with no deadline, no heartbeat, and no arm for "ended in a state I did not
name"; and there is no inventory of what the session believes it is waiting on that
could be checked against reality.

### What the measurements support, and where they disagree

That reading is right about instance 3 and about the missing inventory. It is
incomplete about instance 1, and it mislocates instance 2.

**Instance 1 was not a wrong-state match.** `gate-wait` classifies every terminal
state correctly — it returns on anything that is not `RUNNING`, including
`DIED_WITHOUT_VERDICT`. Nothing ended in an unnamed state. What failed was the
COMPOSITION around a sound primitive: a serial join where a select-any was needed, one
exit notification standing for three events, and a target resolved late from a file
that had since been rewritten. A wait primitive that merely "treats every unrecognised
terminal state as terminal" would not have fixed instance 1 at all.

**The common factor is narrower and more general than "positive match".** In all three
instances the session's ONLY source of wake-ups was the exit of a shell program it had
written a moment earlier, and that program was never tested. Each was a small piece of
unreviewed concurrent code — a serial loop, a grep on a JSON field, a pipeline that ate
an exit code — and each had a path on which it never exits, or exits late, or exits
saying the wrong thing. An agent session between turns is not running: it has no clock
and no loop of its own. If its one wake-up source is wrong, there is nothing behind it.
So the root cause is stated here as:

> A session parks its entire liveness on a hand-written, untested waiter whose exit is
> the only event that can wake it, and nothing — not the waiter, not the session, not
> any supervisor — bounds how long that can go on or compares what the session thinks
> it is waiting for with the state of the things themselves.

Three properties follow from that statement, and each instance violates at least two:

| Property a wait must have | Instance 1 | Instance 3 |
| --- | --- | --- |
| **Complement classification.** It returns on any state that is NOT a named still-running state — including "the target is gone" and "I cannot read the target" — rather than on a named finished state. | held (inside `gate-wait`) | violated (`idle` only; errors swallowed) |
| **First-event wake-up.** Over several targets, it returns on the first one to end, and says which. | violated (serial; one exit for three events) | not applicable (one target) |
| **Bounded silence.** It returns no later than a stated deadline, reporting "still running" for whatever has not ended, so the session re-observes on a schedule even when nothing matches. | violated (ran to 00:42) | violated (no wake-up for 4 h 21 min) |

Bounded silence is the one property that would have limited the damage in BOTH
instances with no other change, which is why this note treats the deadline as the
load-bearing part and the richer state matching as the second line. A deadline does not
need to understand the target. It converts every failure of the other two properties —
including the ones nobody has thought of yet — from an unbounded stall into a bounded
one.

**Instance 2 is the same absence seen from the other side, not a separate honesty
defect.** The session did not set out to misreport. It had no record of its own waits
other than its recollection of what it had typed, so a status line about monitoring
could only ever be authored from intent. The repository's verification discipline
already says a next-action line must be authored "from evidence, not from status"
(AGENTS.md, Verification discipline, rule 5); a monitoring claim has the same
structure and today has no evidence to be authored from. The fix for the honesty half
and the fix for the stall half are therefore the same artifact: an inventory of armed
waits that is written by the act of arming one, and that can be compared with the
targets' own current state on demand.

**This is the "instrument that cannot return a hit" trap, pointed at time.** AGENTS.md
catalogues queries that could not have returned the other answer. A waiter that can
only fire on `idle` is the same failure with a clock attached: its silence was read as
"still working" when it was equally consistent with "finished some other way", "pane
gone" and "my loop is wrong". The existing rule for a surprising empty result — ask
what the instrument would show if it were pointed correctly — has no analogue for a
wait, because a wait's negative result is the absence of an event, and an absent event
prompts nobody to ask anything.

### Two contributing conditions

**The existing guidance covers the gate, not the waiter.** AGENTS.md prescribes
`gate-start` plus `gate-wait` and says a dead background task is not the dispatch's
verdict. The user-level rule "Don't poll background tasks you spawned" says to wait for
the harness notification instead of building a second polling layer. Both are correct,
and both are silent about the case the three instances share: waiting on something that
is NOT a harness background task (a detached gate, another agent's pane), where the
session has to bring its own waiter and that waiter IS the notification. Followed
faithfully, the two rules lead to exactly one unbacked wake-up source per wait.

**No supervisor was in a position to notice.** See section 3: the overseer daemon was
not tracking this session at all, and for a session it does track, a live waiter makes
the session read as busy.

## 3. Is stall detection already somebody's job?

Partly, in the sibling repository `livespec-overseer` — and the part that exists is
disarmed by this very failure. Read from that repository's source and ledger on
2026-10-05:

- The overseer daemon classifies each tracked session per tick. For a Claude Code
  session it trusts the session registry's own status, where `shell` means "at the
  prompt with a live background command" and is counted as BUSY
  (`overseer/_supervisor_observe.py`). A session parked on a waiter that will never
  fire therefore reads `working`, note `background shell` — the healthy state.
- The keep-going nudge needs a continuously idle, not-busy session for
  `IDLE_NUDGE_AFTER` (one hour). A session with a live waiter is never idle, so the
  nudge cannot fire.
- The one condition aimed at this shape is `shell-prolonged`, with
  `SHELL_PROLONGED_AFTER` set to eight hours by a recorded ruling. It is report-only.
  Both stalls here were noticed by the maintainer in one to four hours; an eight-hour
  floor would have reported neither.
- **The session was not tracked.** The daemon's published snapshot
  (`~/.livespec-overseer-status.json`, read 2026-10-05 about 14:03) lists topic
  `definition-and-proof-of-done` with status `unassigned` and no managed pane. The
  session runs in a herdr pane, and herdr support in the overseer is the unfinished
  work of plan `herdr-overseer` (epic `overseer-uzvcbn`). So even the eight-hour
  condition could not have fired.

The overseer's ledger shows this class has been found before from the supervisor's
side, twice, with longer stalls than these:

- `overseer-4xfmez` (closed epic, control-plane supervision liveness): a dead
  `gh pr checks` poller held a session's status at `shell` for about 39 hours.
- `overseer-94fs` (in `acceptance`): a monitor loop that never surfaced an event
  shielded a session for THREE DAYS; the session had concluded the monitor failed to
  launch. Its fix persists the shell-only episode start so the upper bound survives a
  daemon restart.
- `overseer-h4ziqc` (closed): a stall and dead-watch attention condition, including
  "a monitor/watch is only a mechanism if its TARGET is still alive".
- `overseer-tdfe.13` / `overseer-au3pt3.6` (closed): the `wait-target-missing`
  condition, which re-verifies that a run a session declared it is waiting on still
  exists.
- `overseer-vyjkzw` (closed), `overseer-3zbwi3` (closed epic), `overseer-tlrc73`
  (closed epic, unattended-stall-hardening).

What that history shows: the supervisor side has been hardened repeatedly and still
sees a waiter as a black box. It can bound how long a background shell may shield a
session; it cannot tell a waiter that is correctly waiting on a four-hour factory run
from one that is waiting on a state that will never occur, because the difference is
in what the waiter is waiting FOR, and that is recorded nowhere the daemon can read.
A wait inventory (section 5, mechanism C) is the missing input, not a competing design.

## 4. Prior art in this repository's ledger and its siblings

Surveyed 2026-10-05 with `bd list --status all --limit 0 --json` in three tenants
(this repository, 1159 records; `livespec-overseer`, 1114; `livespec-dev-tooling`,
764), searching titles and descriptions for stall, waiter, watchdog, liveness, silent,
idle, heartbeat, gate-wait, the died-without-verdict state name, and background task,
then reading the description and comments of each overlap. The bare word match on
"stall" is dominated by "install"; the items below are the ones that actually bear on
this plan. Live plan directories and `plan/archive/` names were checked too; none
covers session-side waits.

**Adjacent, and NOT to be duplicated:**

- `bd-ib-6nrnxu` (closed) — a `drive` launched as a harness background task is killed
  mid post-merge. It produced the AGENTS.md rule to launch through `gate-start`. It
  fixed the lifetime of the GATE. It did not consider the waiter, and the three
  instances here all used the gate runner correctly.
- `bd-ib-5qlr` (closed), `bd-ib-b5dg.1` (closed) — inside a factory sandbox, a
  backgrounded poller keeps the agent's turn open until the node ceiling. This is the
  opposite failure in a different place (the waiter outlives its usefulness and holds
  the turn), and it is a hard constraint on this plan: whatever wait primitive ships
  MUST NOT be prescribed inside a Fabro sandbox as a long blocking call.
- `livespec-dev-tooling-klj2at` (ready) — the background guard prescribes `gate-wait`
  inside the sandbox, where it kills runs. Same constraint, already owned there.
- `livespec-dev-tooling-zh4c` (backlog) — the gate runner's liveness probe counts an
  unreaped zombie as alive, so a killed gate reads `RUNNING` forever. A `gate-wait` on
  such a gate never returns; a deadline (mechanism A) bounds it without fixing it.
- `livespec-dev-tooling-3bqy` (backlog) — `gate-wait` reports an unknown run for a
  live gate started in a worktree.
- `livespec-impl-beads-oyg`, `bd-ib-o3cpko`, `bd-ib-q5wxkh`, `bd-ib-n6cobe`,
  `bd-ib-tec5sz` (all closed) — the Dispatcher's stall watchdog over a Fabro RUN. It
  watches the factory, not the session driving it.
- `bd-ib-tk6e` (ready) — a ledger outage kills the dispatcher while its remote run
  lives. A session waiting on that gate is told `FAILED` about live work; relevant to
  what a "terminal" gate state licenses a session to conclude, not to whether it wakes.
- `bd-ib-zlpeyg` (closed epic, idle-factory visibility) — idleness of the FACTORY
  surfaced through `needs-attention`. A precedent for surfacing a quiet condition on an
  operator surface rather than leaving it to be asked about.
- `bd-ib-dk3u2p` (closed) — the three AGENTS.md traps recorded earlier on 2026-10-05
  from the same session. None concerns waiting.
- The plan operation's own record-rate guard (plan prose, "Record rate") — a
  precedent for a guard that detects a blocked session by what it does instead of
  progressing. It is warn-only.

**Not found:** no item, open or closed, in any of the three tenants proposes a
multi-target wait, a mandatory deadline on a wait, or a session-side inventory of
waits. That absence is stated with its scope: three tenants, all statuses, the search
terms listed above. Other fleet tenants were not searched.

## 5. Candidate mechanisms

Ordered from most mechanical to least. Costs are estimates for scoping, not
commitments. "Owner" names the repository whose code would change; anything outside
this repository goes through the cross-tenant execution-mirror convention or a
referral, never a direct edit from this plan.

### A. A bounded, any-of wait primitive (tooling)

One command that takes one or more targets and a REQUIRED deadline, and returns as soon
as ANY target is no longer in a named still-running state, or when the deadline
expires — whichever comes first. Its output names every target with its observed state;
its exit code distinguishes "something ended" from "deadline reached, everything still
running" from "a target could not be read or does not exist".

- Target kinds worth supporting first: a gate run id; a herdr agent pane; a Fabro run
  on a named factory; a pull request's checks. Each kind supplies only a
  still-running predicate — the complement is terminal by construction, so a state the
  author never anticipated (`done`, a vanished pane, an unreadable run directory) ends
  the wait instead of extending it.
- Targets are resolved to concrete identities when the wait is ARMED and recorded, so a
  rewritten pointer file cannot re-target a live waiter (instance 1, cause 3).
- The command is the last element of its own invocation, so its exit code survives.
- Owner: the gate-run half belongs to the worktree pack in `livespec-dev-tooling`
  (`gate-run.sh` is installed from there; this repository only imports it). A
  multi-kind primitive could instead live in this repository's plugin, calling
  `gate-status` for gate targets. That placement is the first open design question.
- Cost: small to medium. The gate-only form is a loop over `derive_state` that
  already exists. The multi-kind form needs one adapter per target kind and tests
  against fakes of each.
- What it does not do: it does not make a session USE it. See D and F.

### B. A heartbeat that does not depend on any waiter (session-side)

A wake-up the session gets on a fixed cadence while it has anything outstanding,
independent of every waiter — the harness's own scheduled wake-up or recurring-prompt
facility where the runtime has one. On each beat the session re-observes its
outstanding targets directly.

- This is bounded silence without trusting the waiter at all, and it is the only
  candidate that also covers a waiter that was never armed.
- Cost: recurring model turns while idle (tokens and context on every beat); it is
  runtime-specific (Claude Code, Codex and pi differ); and a beat that fires while the
  session is mid-turn has to be harmless.
- Mechanism A with a deadline gives most of the benefit at near-zero cost, because a
  deadline-expired return IS a heartbeat for the waits that exist. B is the stronger
  form to reach for if A's adoption cannot be enforced.

### C. A wait inventory (tooling, and the honesty half)

Arming a wait through A writes a record: target identity, kind, armed-at, deadline,
the owning session's identity, the waiter's process id. One read command lists every
record with the target's CURRENT state, read fresh, and whether a live waiter covers
it, and flags each mismatch: a target that has ended with no wake-up delivered; a
target still running with no live waiter; a wait past its deadline.

- A status claim about monitoring then has something to be derived from: the session
  quotes the inventory's output instead of asserting. Instance 2 becomes checkable by
  the session, by the maintainer, and by a daemon.
- It is also the input the overseer has lacked (section 3): a daemon that can read
  "this session is waiting on gate X, which ended 40 minutes ago" needs no eight-hour
  floor.
- Where it lives: beside the gate runs under the primary checkout's `tmp/`, which
  already outlives worktrees and is already where gate evidence is read from.
- Cost: small on top of A. The discipline risk is the usual one for a declared
  inventory — a wait armed outside the primitive is absent from it, and absence reads
  as "nothing outstanding". D addresses that.

### D. Refuse the hand-rolled shapes (hook)

A pre-tool-use guard that denies a BACKGROUND shell command whose body is an unbounded
polling loop or a serial chain of waits, and names primitive A in the denial. The
existing `pretooluse_background_guard` in `livespec-dev-tooling` is the precedent, and
its history is the warning: `livespec-dev-tooling-k169` (substring false positive),
`livespec-dev-tooling-a9xp` and `-h7qp` (a denial that prescribed a remedy six of seven
repositories did not ship), `livespec-dev-tooling-klj2at` (a prescription that kills
sandbox runs).

- Cost: medium, mostly in false-positive control. Shell is not parseable by regular
  expression in general; the guard has to target a few literal shapes (`until ...; do
  sleep`, `while true`, `for ... gate-wait`) and accept that it is a net, not a proof.
- It must ship only after A exists everywhere the guard is armed, and it must not fire
  inside a factory sandbox.

### E. A turn-end check against the inventory (hook)

When the session is about to end a turn and go quiet, a stop-time hook reads the
inventory (C). If a registered target has already ended and the session has not been
told, or an outstanding target has no live waiter, the hook says so before the session
parks.

- This catches the instance-2 shape at the moment it matters — the session announcing
  a monitoring state and going idle — and it needs no cadence and no daemon.
- Cost: small once C exists; runtime-specific (the hook surface differs across Claude
  Code, Codex and pi, and Codex's equivalent has to be established, not assumed).
- It cannot help once the session is already parked. It complements A's deadline; it
  does not replace it.

### F. A supervisor-level watchdog (livespec-overseer)

The overseer reads the inventory (C) each tick and raises an attention condition —
and, where its acting rules allow, pastes a nudge — for a tracked session with a wait
past its deadline or a target that ended without a wake-up.

- This is the only candidate that works when the session is fully parked AND its own
  tooling has failed, and it is the natural home: the overseer already owns
  `shell-prolonged`, `wait-target-missing` and the idle nudge.
- It is NOT this repository's to build. It belongs in `livespec-overseer`, under that
  repository's architecture invariants (one daemon; conditions inside the existing
  evaluate machinery), and it depends on two things outside this plan: the inventory
  format being stable, and the overseer tracking herdr-hosted sessions at all, which
  is plan `herdr-overseer` (epic `overseer-uzvcbn`), currently in flight.
- This plan's part is to define the inventory so that a daemon can consume it, and to
  file the referral. Cost here: a document and a ledger item in the sibling tenant.

### G. Guidance (AGENTS.md)

A trap-catalogue entry: the three properties in section 2, the instruction to use the
primitive, and the rule that a monitoring claim is quoted from the inventory.

- Cost: trivial. Value alone: low. The session that stalled had read the gate-runner
  guidance and followed it; the failure was in the space between two correct rules.
  Guidance is the interim measure and the pointer to the mechanisms, not the fix.
- It should also correct the gap named in section 2: say explicitly that for something
  the harness did not spawn, the waiter is the notification, and so it must be bounded.

### Recommended combination (a proposal, not a ruling)

A plus C first, in one design, because C is nearly free once A arms the waits and A
without C leaves instance 2 untouched. G in the same change, since the primitive needs
a pointer. Then E, as the cheapest enforcement that does not depend on parsing shell.
Then the referral for F. D last and only if measured need remains, given its
false-positive history. B held in reserve as the fallback if A cannot be made the
default path.

## 6. Open questions the scoping event must settle

1. Where primitive A lives: the worktree pack in `livespec-dev-tooling` (every fleet
   repository gets it; cross-tenant delivery through the execution mirror) or this
   repository's plugin (one repository; reachable from the build a session is bound
   to, with the stale-build caveats AGENTS.md records).
2. Whether the deadline has a default or is refused when absent. This note leans to
   refusal: a default is a deadline nobody chose.
3. Which target kinds are in the first slice. Gate runs and herdr agent panes are the
   two the measured instances need.
4. What "the session was woken" means mechanically for the inventory to flag an
   undelivered wake-up — the waiter's exit is observable; the session having read it
   is not, short of the session acknowledging the record.
5. Whether E is buildable on Codex and pi, or is Claude-only at first.
6. Whether this plan needs a specification change. The gate runner is unspecified
   tooling today; a wait primitive that agents are REQUIRED to use, and a hook that
   enforces it, may warrant a contract. That is a `propose-change` decision for the
   scoping session.
7. The harness behaviour measured in instance 3 — a background task launched with a
   three-hour tool timeout produced no notification for over four hours — is recorded,
   not explained. It should be reproduced deliberately before any design relies on a
   harness timeout for anything.

## 7. Explicitly out of scope

- The Dispatcher's stall watchdog over Fabro runs, and anything about how a factory
  run is detected as hung. That is closed work (`livespec-impl-beads-oyg` and its
  successors).
- Background tasks holding a factory sandbox agent's turn open (`bd-ib-5qlr`,
  `livespec-dev-tooling-klj2at`). This plan must respect that constraint; it does not
  own the defect.
- The gate runner's own liveness defects (`livespec-dev-tooling-zh4c`, `-3bqy`).
  Mechanism A bounds their effect on a waiting session; fixing them stays with their
  items.
- Changes to the overseer daemon. This plan files a referral for mechanism F and
  defines an inventory a daemon can read; it does not edit `livespec-overseer`.
- Why the harness killed two background tasks on 2026-09-10 (`bd-ib-6nrnxu`), and the
  unexplained timeout behaviour in open question 7 beyond reproducing it.
- The substance of what the stalled session was waiting for — the
  `host_not_reproduced` verdict on `bd-ib-ht4c2m` and its rework. That belongs to plan
  `definition-and-proof-of-done`.
- Stalls that are not waits: a session blocked on a human, a session out of context, a
  session at a picker. The overseer's existing conditions cover those.
- Retroactive audit of other sessions' historical waits.
