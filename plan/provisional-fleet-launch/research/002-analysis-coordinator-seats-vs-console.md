## Analysis — coordinator-and-seats workflow versus the livespec console

Written by an independently commissioned analyst who had no role in building or operating either workflow.

### The short answer

The two workflows answer different questions. The coordinator-and-seats workflow is a working fleet scheduler. Its scheduling rules live in agent sessions and in untracked shell scripts, so it costs a great deal of human and interactive-token attention to keep it correct. The console is a well-specified cockpit for one repository at a time. By design it decides nothing. It assumes the orchestrator already runs the factory unattended, and today the orchestrator does not do that at fleet scale. Neither workflow, as it stands, would run the homelab and Kubernetes work cheaply.

On 2026-10-24 the main human cost was not pressing buttons. It was correcting the coordinator: about thirteen recorded maintainer interventions in one day, most of them asking "why is this stalled?". The main machine cost was the coordination itself. By my sum of the coordinator's own hourly reports, interactive sessions spent about as much Claude budget as the factory did. My recommendation is a hybrid. Move the coordinator's scheduling rules into committed, tested code. Replace the tick loop with push alerts. Make "ready" mean "launchable". Use the console as the only human surface. Keep at most one small coordinator, woken by alerts, for genuine judgement calls.

### What I read, and how far to trust the numbers

- **The coordinator's running log:** ledger item `livespec-dev-tooling-dfixhe`, which holds 2,928 comments written between 2026-10-13 and 2026-10-24 (about 3.1 MB of text). I read every comment header for 2026-10-24 and the full text of about 30 comments. I counted faults, maintainer rulings, handoffs and cap changes by pattern over 2026-10-22 to 2026-10-24.
- **The seat plan timeline:** item `bd-ib-fyozyd`, 305 comments.
- **The launcher directory:** `tmp/petri-canary/` holds 824 files, 114 of them shell scripts totalling 10,481 lines. I read the head of `dispatch-dual-r681b.sh`.
- **The dispatch journal:** `tmp/fabro-dispatch-journal.jsonl`, 310 MB and 502,673 rows. It covers only this orchestrator repository, so it is a sample of one repository out of fourteen, not the whole fleet.
- **The console repository:** its README, `SPECIFICATION/spec.md`, the relevant parts of `contracts.md`, the user docs, the open plan's research note on plans, and its ledger (462 items, 47 not closed).
- **This repository's `AGENTS.md`:** the sections on decision authority, stopping the line, and the three dispatch-admission conditions the Dispatcher owns.

Caveats. The dollar figures are the coordinator's own Claude-only estimates. They undercount factory tokens while runs are still in flight, which the log itself notes as the "R330 undercount". I did not measure fleet-wide throughput directly. Where I give a per-dispatch or per-day figure for the whole fleet, I say that it is inferred. I judge the console on its specification, because it was not used to operate the factory during this period: none of the 16 mentions of "needs-attention" in the coordinator log refers to the console's screen.

---

### Workflow 1: coordinator-and-seats

**How it works.** One coordinator Claude session runs a "TICK" loop on its own schedule. On each tick it reads the factory boards, the in-flight markers, the launch queue and the fleet cap, then writes rulings to the ledger. Specialist "seat" sessions each own one plan, for example `petri-factory-on-gmktec`, `fabro-currency` and `kubernetes-sandbox-backend`; on 2026-10-24 I count about eleven named sessions in the log. Seats talk to each other through cross-session messages and ledger comments. They launch every factory run through seat-run shell scripts. The current script is `dispatch-dual-r681b.sh`, which enforces several controls:

- a fleet cap kept in a plain file;
- a FIFO (first in, first out) ticket directory for queue order;
- a mutex, plus in-flight marker files;
- a hold file that pauses launches;
- readers for each factory's board;
- a Definition-of-Done pre-screen at launch, called "R316". A Definition of Done is the list of checkable assertions an item must satisfy.

The rules behind all of this are numbered rulings written to the ledger. They reached R680 by 2026-10-22, up from R131 on 2026-10-17. The script's 60-line header comment is itself a stack of ruling numbers.

**Where a human must look, decide or press.**

- *Corrections.* On 2026-10-24 the log records the maintainer's words verbatim about thirteen times. Most were course corrections, not approvals:
  - 00:4x: "You're blocking the whole … upgrade because you don't want to kill a run".
  - 01:0x: "Why are you still blocking anything on slots? We have tons of quota and tons of compute."
  - 01:1x: "So we're still not on Kubernetes. Why did you let this stall so long?"
  - ~15:4x: "this is not worthy of my attention".
  - ~18:2x: a question about why ready work was not handled autonomously.
  - ~18:4x: a prompt that produced the finding about commit-time gates.
- *Faults.* The coordinator logged about 20 "COORDINATOR FAULT" records between 2026-10-22 and 2026-10-24. Several of them were found by the maintainer, not by the coordinator.
- *Valve presses.* Releasing an item from `blocked` is a human-only valve. On 2026-10-24 the coordinator pressed such valves itself, with `--invoker human:thewoolleyman`, under a standing mandate (15:52Z, 17:11Z). That saved the maintainer's attention. It also means the journal now records agent decisions as human ones, which defeats the valve's purpose as evidence.
- *Unavoidable maintainer items.* These were few and real: granting a GitHub App permission, putting a credential into 1Password, and running one spec revise.

**What stalls silently, and how long until someone notices.** These durations come from the log:

| Stall | Duration | How it was found |
|---|---|---|
| Every launcher still read the board of the retired hp factory. An unreadable board made the fleet count "unknown", so no launch passed the gate. | 13:07Z to about 14:37Z on 10-24, about 90 minutes, with 4 runs live against a cap of 6 | When the coordinator restarted its loop. Its own fault note says "the loop was started only at 14:3xZ". |
| The fleet was held at cap 0 to let runs end naturally before an upgrade | about 1 h 50 min (22:5x to 00:4x, 10-23 into 10-24) | The maintainer |
| Kubernetes was ordered last in the rules | hours. At 01:10Z, 1 of 14 repositories was on Kubernetes. | The maintainer |
| A hung test went unnoticed | 19:35Z to about 21:2xZ on 10-23 | The coordinator, late |
| A cross-tenant dependency edge refused every dispatch in one repository | about 40 minutes on 10-22 | A seat |
| The account-rotation seat hit its own usage limit and skipped rotations | 02:13Z to 03:21Z on 10-24 | Inferred afterwards |
| A drain monitor's search matched the text "No running processes" | 16 minutes on 10-23 | The coordinator |

The pattern is consistent. A broken script or rule produces a plausible "nothing to do" state, not an error, and only a reader who happens to be looking finds it. When the coordinator restarts, the reader is gone. The coordinator restarted at 50% context about every five to nine hours: there were 11 handoffs from 10-22 to 10-24, each 2 to 8 KB long.

**What it costs in interactive token spend.** Summing the coordinator's hourly capacity reports from 23:43Z on 10-23 to 17:43Z on 10-24 gives about **$1,100 interactive against about $1,060 factory**, roughly half each. The interactive share swung from 14% to 87% by hour. It was 62% at 17:43Z, when an interactive spike of $110/h triggered a cap cut from 6 to 5 and a launch hold. The coordinator's own note at 17:45Z says that "interactive spend includes the coordination sessions themselves". So the coordination layer competes with the factory for the same Claude windows. It throttles the factory in order to pay for watching the factory. The write volume alone was 194 to 308 coordinator comments per day, roughly 180 to 350 KB.

**How it scales.** Badly, and the evidence is already in. The work is spread over one coordinator, around ten seats and 114 scripts. Rules accumulate faster than any session can hold them in context, which is why there are handoffs and fault records. Every new factory or repository adds board readers, wrapper scripts and rulings by hand. The hp retirement shows the cost: removing one server stalled every launcher, because nothing listed who reads that board. The launcher edit that fixed the stall then introduced a second defect. It swallowed a statement into a comment, `bash -n` passed it, and only a reviewing coordinator caught it.

**Main failure modes.**

1. Untested, uncommitted scheduler code. It lives in `tmp/`, carries no tests, and is replaced by hand with `mv`.
2. Supervision by polling, which disappears whenever the supervisor restarts or runs out of quota.
3. The coordinator's mistakes are confident and system-wide. One wrong cap value or ordering rule binds the whole fleet.
4. Relay hazards between sessions. Examples: a keystroke sent into a seat's pane was read as the seat's user interrupting (10-23), and agents pressing human valves under a human identity.
5. "Ready" is not launchable. Of 17 ready candidates, 11 failed the launch-time Definition-of-Done screen. The launch-time screen and the Dispatcher's own judgement also disagree: one item passed the screen, then was refused 39 minutes later after the slow pre-launch phase, which burned a whole launch slot. On top of that, every launch spends 20 to 39 minutes in pre-launch, and serial pre-screening left slots idle.

**Pros.**

- It works. It cut the fleet over to a new factory, put 14 of 14 repositories on Kubernetes-backed environments in about a day, and kept runs flowing.
- It is the only thing in the system that understands the real binding resource, which is Claude token budget spread across rotating accounts. Neither the Fabro scheduler nor the Kubernetes quota knows about that budget.
- It adapts fast. A new constraint, such as a homelab namespace, leaked pods or a quota 403 error, gets a rule within minutes.
- It produces a complete, auditable narrative in the ledger.

**Cons.**

- High maintainer correction load and an interactive spend roughly equal to the factory's.
- Silent stalls of 40 to 110 minutes that end only when someone looks.
- Untested scheduler code, with knowledge that lives in context windows and handoffs.
- Human-valve provenance is blurred.
- It does not scale linearly with the number of repositories or factories.

---

### Workflow 2: the livespec console

**What it is meant to do.** According to `spec.md`, the console is a single Rust program with a terminal user interface (TUI). It pulls facts from LiveSpec, the work-item ledger, the Dispatcher journal, Fabro, GitHub and the orchestrator's `needs-attention` surface. It stores them as events in SQLite and renders an inbox, lanes, plans, events, repositories and settings. Every operator action is a recorded command, with an outcome event and a resolved operator identity. Its design choices bear directly on attention:

- It **must not host a resident deciding agent**. It "surfaces facts and executes the operator's explicit commands".
- It must not drive agent sessions through a terminal multiplexer.
- Autonomy is meant to come from the orchestrator's `dispatcher.*` policy settings, such as auto-approve-ready, acceptance mode, rework caps and the work-in-progress cap. The console edits these settings, and flags any setting that lets the factory act without a human as "dangerous / use with caution". Only escalations the orchestrator could not settle reach the inbox.
- The header must distinguish a "cockpit-blind" screen, where sources are unreachable, from an idle factory.

**What is built and what is not.** Version 0.4.0 is released. The single-repository read path, the lanes, the valves, the settings and the per-item dispatch exist, and were acceptance-tested on one host. The following is unbuilt or unfinished:

- The **plan roster** is partly built. Its first slice sits in `acceptance`. Three follow-ups sit in `pending-approval`. One is blocked on the orchestrator publishing plan fields.
- **Account rotation** is promised in the spec only as "rendering of orchestrator surfaces", and no such surface exists.
- **Push notification** appears in the spec only as "notification-ready alert semantics" and "notification policy". Nothing pushes.
- There is **no fleet view**. The console runs against one repository path at a time (`LIVESPEC_CONSOLE_REPO_PATH`). Its "Repos observed" view only counts repositories that appear in its own event log.
- Its **drain** is `dispatcher.py loop --repo <one repo>`, which has no notion of a cross-repository token budget.

The ledger also shows the console has its own backlog: 32 backlog items, 6 blocked and 1 priority-1 red pre-push check.

**Where a human must look, decide or press.** The console's design asks the human for exactly the decisions the orchestrator escalates: approve, accept, reject, release from blocked, and the policy dials. The spec states this precisely, down to which verbs are offered in which lifecycle state. That is the right shape for attention. In the 10-24 evidence, however, most human attention went to things the console never sees: cap levels, ordering, holds around account windows, launcher defects, and Definition-of-Done triage. The console would not have cut those corrections. It would only have given the remaining valve presses a cleaner, correctly attributed home.

**What stalls silently.** The console is a pull surface. A stall is visible only while someone has the screen open. Its health header would expose a source outage. It would not have exposed the hp-board stall, because the stuck component was a seat script and not an orchestrator surface. With no push alerting, the console's time-to-notice equals the time until the human next looks. For an absent maintainer, that is worse than a polling coordinator.

**What it costs in interactive token spend.** Close to nothing. It is a Rust program with no language model in the loop; an assistant is allowed only as an operator-invoked add-on. This is its strongest property for the question being asked.

**How it scales.** Per-repository state scales well, because the event store and projections are cheap. Multi-repository operation does not scale yet. Fourteen repositories means fourteen console instances, or switching the repository path, and there is no cross-repository budget or queue. Fourteen independent per-repository drains, each under its own work-in-progress cap, would oversubscribe the shared Claude accounts. That is exactly the failure the coordinator's fleet cap exists to prevent. `AGENTS.md` puts host concurrency with the Fabro scheduler and lets a launch loop add capacity and spacing gates. Nothing committed owns the token budget.

**Main failure modes.**

1. It relies on autonomy that does not yet exist at fleet scale.
2. It is blind when nobody looks.
3. Plan-level work (the "uber-plan" layer) is not yet visible.
4. Its own build and maintenance load: a Rust workspace with 100% coverage, fuzzing, mutation testing and end-to-end TUI tests.

**Pros.**

- Near-zero interactive spend.
- Every human decision is recorded with the correct identity.
- Its "decides nothing" boundary means policy changes are explicit, recorded settings writes, not context that has to be carried forward.
- The honest-outcome rules stop it from reporting dispatches that did not happen.
- The inbox is exactly the set of escalations, which is the right attention model.

**Cons.**

- Single-repository.
- No push alerts.
- No knowledge of the token budget.
- Depends on orchestrator surfaces that are still missing (plan fields, account rotation, question surfaces).
- Silently useless when the factory stalls somewhere upstream of the orchestrator's surfaces.

---

### Side by side

| Measure | Coordinator-and-seats | Console (as specified) |
|---|---|---|
| Human corrections per day | about 13 recorded maintainer interventions on 10-24 (measured) | unknown; it is not in use. By design only escalations reach it. |
| Silent-stall time to notice | 16 to 110 minutes in measured instances | until the next human look; no push alerts |
| Interactive spend | about 50% of Claude spend on 10-24 (measured from hourly reports) | about 0 |
| Fleet token-budget control | yes, by hand-tuned rules | none |
| Multi-repository | yes, through scripts | no |
| Correctness of the controls | untested scripts and ledger rulings | specified and tested, but narrower |
| Human-valve provenance | blurred (agents press as the human) | exact |

### The underlying point

Almost all of the attention cost in workflow 1 goes to decisions that should be **deterministic policy in committed code**:

- the cap is already a formula. The log records triggers of "line below 2.5, so set the cap to 3", applied hourly;
- account holds already have an automatic release gate;
- the release of failures the host caused, such as a usage-limit death, has already been ruled to need no human;
- the Definition-of-Done screening is mechanical in five of twelve cases.

Once those run as code, the coordinator has little left to decide. The console's design is correct that a human should only see true escalations. It is missing the fleet-level autonomy that would make the inbox short, and it is missing push alerts. So the plan is not a choice between the two workflows. Turn workflow 1's rules into the orchestrator autonomy that workflow 2 assumes, then retire most of workflow 1.

### Recommendation for the homelab and Kubernetes conversion

Use a **hybrid**: committed automation does the scheduling, alerts do the watching, the console is the human surface, and one thin coordinator handles judgement calls. Make the changes in this order, because each one removes attention that the next one would otherwise absorb.

1. **Make "ready" mean "launchable" before filing any homelab or Kubernetes work.**
   - Make the filing-time Definition-of-Done check blocking instead of advisory.
   - Bind the launch-time screen's verdict to the description digest, so the Dispatcher does not re-judge the same text differently (the work item that binds the verdict to the digest [`bd-ib-8zyan`]).
   - Fix the 20-to-39-minute pre-launch (the pre-launch slowness item [`bd-ib-6bbcda`]).

   This alone removes the largest measured waste: 11 of 17 ready items failing, and a 39-minute slot lost per divergence.

2. **Commit the launcher as one supervised launch-loop service** (the plan now open as `provisional-fleet-launch` [`bd-ib-klkbxp`]).
   - Run it under systemd or as a Kubernetes workload, not from seat sessions.
   - Read factories from the GitOps-rendered registry (`/etc/livespec/fabro-factories.json`), not from hard-coded URLs, so that retiring a server cannot strand it.
   - Run one continuous loop per repository behind the shared budget gate.
   - Give it tests and treat its edits as reviewed code. A launcher change is proven by executing it, not by `bash -n`.

3. **Turn the capacity rules into a deterministic job.**
   - The token-spend line and its pre-committed triggers write the cap file every hour.
   - Account rotation runs as a host service whose own usage limit cannot stop it.
   - The in-flight session-limit release (the item that releases runs killed by a session limit [`bd-ib-3ozwp2`]) and the "release host-caused needs-human automatically" ruling become Dispatcher behaviour. Agents must stop pressing human valves under the maintainer's name.

4. **Replace the tick loop with push alerts.** Build on the Kubernetes node observability that the maintainer already made part of the Definition of Done. Add Honeycomb triggers for:
   - launch queue non-empty with free slots for more than 15 minutes;
   - any launcher reporting an unknown fleet count;
   - quota-exceeded (403) errors at sandbox acquisition;
   - pods that belong to no live run;
   - runs past their wall budget;
   - an account window below its floor.

   Route each alert to the maintainer and to the coordinator's inbox. The measured 90-minute stall becomes a 15-minute page.

5. **Shrink the agent layer.**
   - Keep one coordinator, woken by alerts and by escalations, not by a clock.
   - Keep seats only for host-routed infrastructure work that cannot go through the factory: Ansible and GitOps changes to cluster quota and namespaces, and node changes. Use one infrastructure seat for homelab and Kubernetes.
   - Send all factory-safe changes through the committed loop.
   - Move standing mandates from ledger rulings (R1 to R680) into committed policy, either `dispatcher.*` settings or spec text, so they survive restarts without being re-read.

6. **Make the console the single human surface, and extend it only along published surfaces.**
   - Have the orchestrator publish a fleet-level needs-attention surface and the budget and cap state.
   - The console renders that surface across repositories, alongside the plan roster that is already in flight.
   - Keep the console's "decides nothing" rule. Scheduling belongs in step 2's service, not in the user interface.

7. **Track the right metric from day one of the conversion.** Track maintainer interventions per merged pull request, and the interactive share of Claude spend. A reasonable target is an interactive share under 20% and no "why is this stalled" corrections in a normal day. Both are already computable from the hourly capacity reports and the ledger.

If time forces a shorter list, do steps 1, 2 and 4 before starting the homelab and Kubernetes work. They address the three largest measured costs: unlaunchable "ready" work, a scheduler that breaks silently, and stalls that last until someone looks.
