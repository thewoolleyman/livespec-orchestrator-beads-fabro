## The maintainer's statement of what done means

Two disciplines named by the overseer-herdr-rewrite session (Codex, plan overseer-uzvcbn in livespec-overseer) after it stalled on 2026-10-06 and 2026-10-07, which the maintainer asked on 2026-10-07 to cover in a plan: "Checkpoint completed proof work: a replacement session should reuse exact saved inputs and outputs. Message acknowledgment must never count as delivery." and "Use a progress deadline: if a stage produces no new required result, diagnose and change the recovery approach. More handoffs and monitoring are not progress." (The proof-reuse half of the first discipline is routed by the maintainer to bd-ib-fngpwg under plan definition-and-proof-of-done; this plan covers the acknowledgment-versus-delivery half and the progress deadline.)

## Definition of Done assertions derived from that statement

- Recording a relay to another session or tenant as delivered, through the plan primitives, succeeds only when the target's own ledger, forge or repository state shows the requested result, and an acknowledgment without that state is recorded as undelivered with a deadline.
- The typed next action on an open plan epic names the one required result the action must yield and a budget, and a handoff entry that leaves that result unproduced past the budget while naming the same next action is refused unless the entry states a changed approach or routes to a person.
- A drive of a work-item whose previous dispatches each ended at or before the furthest stage any of them reached is refused, naming those runs and that stage, until a changed approach is recorded on the item.
- An open plan epic whose handoffs over a stated window record no new merged pull request, closed child or verified record is listed by needs-attention with the window, the entry count and the last required result, without the operator asking.

# Acknowledgment is not delivery, and activity is not progress: failure analysis and mechanism candidates (2026-10-07)

Status of this note: the opening research note of plan
`relay-delivery-and-progress-deadline`. It records what was measured, argues a
root cause, surveys prior art, draws the boundary against the sibling plan
`agent-session-stall-prevention`, and lays out candidate mechanisms with their
costs. It decides nothing that binds an implementer; the scoping event and the
child work-items come later, after the maintainer has confirmed or corrected the
Definition of Done above.

The Definition of Done assertions above this heading are SESSION-DERIVED. The
plan was opened by a sub-agent on the maintainer's instruction with no maintainer
present to confirm them, so they are a proposal to be confirmed, not a ruling.

All times are UTC. "The overseer session" means the Codex session
`overseer-herdr-rewrite`, driving plan `herdr-overseer` (epic `overseer-uzvcbn`)
in the `livespec-overseer` tenant from herdr pane `w1:p5`. "The orchestrator
session" means Claude Code session `b1e14094-853e-412d-aa8b-c2adb51d7461`,
driving plan `definition-and-proof-of-done` (epic `bd-ib-7sjdzv`) in this
repository. A "handoff" is one `plan-handoff-entry` comment on a plan epic; a
"relay" is a message one session sends another session, or an item it files for
another session to act on; a "required result" is the single next outcome the
work needs before anything else counts, as distinct from any activity around it.

## 1. The two disciplines, verbatim, and what this plan owns

After the overseer session stalled on 2026-10-06 and 2026-10-07 it named two
disciplines. The maintainer asked, on 2026-10-07, for a plan covering them, and
they are the charter of this plan. Quoted verbatim:

> "Checkpoint completed proof work: a replacement session should reuse exact
> saved inputs and outputs. Message acknowledgment must never count as
> delivery."

> "Use a progress deadline: if a stage produces no new required result, diagnose
> and change the recovery approach. More handoffs and monitoring are not
> progress."

The first discipline has two halves. The proof-reuse half — a replacement session
reusing exact saved inputs and outputs — is ALREADY ROUTED by the maintainer to
`bd-ib-fngpwg` (a child of plan `definition-and-proof-of-done`, epic
`bd-ib-7sjdzv`: resume a terminated run at its unfinished stage from its published
pull request). This plan does not touch it. What remains, and what this plan owns:

- **(a) Delivery.** Between agent sessions, an acknowledgment of a message is not
  evidence that the requested work was delivered. Delivery is established only
  from the TARGET'S OWN STATE: the target item's ledger status or comment, the
  forge's pull request state, a file on the target repository's default branch.
- **(b) Progress deadline.** A session or supervisor that keeps producing
  handoffs, monitoring and re-dispatches without any new REQUIRED result must
  detect that, and change approach or escalate, rather than count the activity
  as progress.

### The boundary against plan `agent-session-stall-prevention`

Plan `agent-session-stall-prevention` (epic `bd-ib-jnpvh4`, research note
`plan/agent-session-stall-prevention/research/001-failure-analysis-and-mechanism-candidates-2026-10-05.md`)
is the sibling, and the two plans are DISJOINT by the state of the session they
describe:

- That plan is about a session that is WAITING and is never woken: its waits are
  unbounded, wake only on a named state, cover several targets with one
  wake-up, and are recorded nowhere a supervisor can read. Its mechanisms are a
  bounded any-of wait primitive, a wait inventory, a turn-end check, and a
  supervisor condition over that inventory. Its root-cause statement names
  "nothing bounds how long that can go on" — a bound on SILENCE.
- This plan is about a session that is ACTIVE and BUSY — writing handoffs,
  monitoring runs, re-dispatching, filing repair children — and is NOT
  PROGRESSING, and about whether a message one session sends another was
  DELIVERED. Its bound is on activity without a new required result, not on
  silence; its delivery check reads the target's state, not the waiter's.

A test for which plan owns a case: if the session would have been fine had it
simply been woken, it is the stall plan's; if the session was awake the whole
time and the problem is what it did with its turns, or what it concluded from a
message, it is this plan's. Section 3 of the stall plan's note (the overseer
daemon's `shell-prolonged`, idle nudge and pair-stall conditions) is cited here
rather than re-derived: every one of those conditions keys on ACTIVITY, which is
exactly what this plan says is not progress, so they are prior art for the
measurement problem, not solutions to it. Neither of this plan's two ideas is
covered by the stall plan: that note's section 7 lists as out of scope "stalls
that are not waits", and its mechanisms contain no delivery check and no
result-keyed deadline. Both plans therefore open.

## 2. The measured instances

Sources: the 64 comments on `overseer-uzvcbn`, read on 2026-10-07 through
`bd comments overseer-uzvcbn --json` from `/data/projects/livespec-overseer`
(bodies under the `text` key: 58 handoff entries and 6 scope events, written
between 2026-10-03T23:57Z and 2026-10-07T02:03Z); the current status of that
plan's children from `bd list --status all --limit 0 --json` in the same tenant;
this repository's dispatch journal `tmp/fabro-dispatch-journal.jsonl`; and the
orchestrator session's own handoff 17 on `bd-ib-7sjdzv`. Every figure below was
read from one of those, not from either session's later account of itself.

### Instance 1 — forty-two handoffs after the last required result moved

The herdr plan's sliced implementation is S1 `overseer-vgf6d3`, S2
`overseer-unv32k`, S3 `overseer-fatiq3`, S4 `overseer-lifebq`, then the
plan-level host proof the session calls "G". S1 closed at 2026-10-05T21:39:01Z
(its pull request 2347 merged; the session's handoff of 2026-10-06T00:42Z
records "S1 ledger closed"). The next required result on the plan's own
sequence was the dispatch of S2.

Between that closure and the last comment read (2026-10-07T02:03Z), 28 hours
and 24 minutes:

| Measure | Value |
| --- | --- |
| Comments written on the epic | 46 (42 handoff entries, 4 scope events) |
| Handoff entries on 2026-10-06 alone | 38 (plus 4 scope events); 13 on 2026-10-05; 3 on 2026-10-04 |
| Comments stating S2, S3 and S4 remain undispatched | 37 of 64 contain the word "undispatched" |
| Comments stating the final proof G has never run | 26 contain "NEVER", 15 contain "never run" |
| Movement of S2 `overseer-unv32k` | `pending-approval` to `blocked` at 2026-10-06T03:19Z; still `blocked` |
| Movement of S3, S4 | none; both `pending-approval` since 2026-10-04 |
| Repair children admitted under the epic in the window | 3: `overseer-ssjzmo` (00:42Z), `overseer-3zx456` (09:34Z), `overseer-emzwpx` (23:48Z) |
| Pull requests merged for those children | 2: 2349 (09:10Z), 2352 (shortly before 23:07Z); both items still `active` because host acceptance failed after each merge |
| Shared-tooling prerequisites opened in THIS tenant | 2: `bd-ib-mtuqxb` (plan `dispatcher-cache-lifetime`, 03:10Z) and `bd-ib-ocjy4t` (under `bd-ib-7sjdzv`, 2026-10-07T00:04Z) |
| Dispatches of `bd-ib-mtuqxb` before it closed | 4 `fabro-run` rows; 3 `needs-human-blocked` rows; 3 `human-valve-resolve-blocked-answer` rows (dispatch journal) |
| Dispatches of `bd-ib-ocjy4t` so far | 2; the first failed at a proof_capture timeout after publishing pull request 2639 |

The shape, read in order from the handoffs: dispatch a slice; the run surfaces a
defect in shared tooling or in test fixtures; file a repair child or a
prerequisite in another tenant; monitor that; it surfaces another defect; file
another. Each individual step was legitimate and was written up honestly — the
handoffs contain the phrase "no human" (as in "No human decision pending")
fourteen times and "not a maintainer decision" twice — and the plan's required next result did not move.

Two readings of this instance are both defensible, and the disagreement between
them is the design problem. Reading one: the window produced two merged pull
requests and one closed child, so there WAS progress. Reading two: the plan's
own next required result, S2's dispatch, moved only backwards (to `blocked`),
and every merged pull request was a repair of a repair, so there was NOT. The
session held reading one; the maintainer's discipline states reading two. No
mechanism in either repository can tell them apart today, because nothing
records WHICH result is the required one. That is why section 5 puts a declared
required result ahead of any detector.

### Instance 2 — the record-rate guard fired at least five times and changed nothing

This repository already ships the closest existing mechanism: the plan
operation's record-rate guard (`commands/_plan_record_rate.py`, threshold 6
records per author-day), whose own docstring was written for this shape: "A
blocked session writes records instead of making progress: one wrote 15
handoff entries and about 12 research notes in a single day while it was stuck.
Nothing noticed." It only warns, by design, and the prose instructs the session
to surface the warning and carry on.

The overseer session did exactly that. Five handoffs record the warning being
surfaced before the write, with the running count: 34 entries on 2026-10-06 at
20:42Z, 35 at 21:23Z, 36 at 22:21Z, 38 at 23:07Z, 39 at 23:29Z, against the
threshold of 6 (and 12 on 2026-10-05, also past threshold). Each time the
session explained why this particular write was warranted ("this records new
canary input and actual commit boundary, not a routine wait") and wrote it. The
guard measured the right thing — records per day — and had no teeth, and it
asked no question about results. The question the prose says the warning should
prompt ("whether the thread is blocked on something that a handoff entry cannot
fix") was not asked in any of the five entries, which is consistent with
`bd-ib-40vz`'s observation that a warning with no required response is read as
permission.

### Instance 3 — acknowledgments that were not delivery, inside one run

The overseer session steered its factory workers through queued messages, and
its handoffs are a catalogue of the difference between a message being queued,
acknowledged, delivered, and acted on. Seventeen of the 64 comments mention a
queued message. Specific measured cases:

- 2026-10-04T01:35Z: "queued steer messages required subsequent clean-boundary
  interrupts to deliver HOLD" — the hold was queued and did not arrive until a
  separate mechanism forced it.
- 2026-10-05T19:11Z: "The two previously queued native layout review findings
  have NOT yet been observed in the worker transcript."
- 2026-10-06T06:10Z: "Three queued review notes were not delivered in the timed-out
  fix stage or in the new proof initial prompt; persistence/delivery remains
  under audit, not assumed."
- 2026-10-06T13:43Z, correcting its own 13:11Z entry: "the 13:05:32 injection
  delivered an older queued concise A5-failure note, not the newer combined
  note" — a delivery was recorded as the wrong message.
- 2026-10-06T18:01Z: a capture-completion continuation "was injected into review
  17:48:11, where reviewer 6a3b3fb5 treated it as closeout and returned an
  outcome of captured instead of performing review. This was a coordination
  failure" — the message was delivered to the wrong stage, the recipient
  acknowledged and acted, and the run failed closed.
- 2026-10-06T20:42Z: "Normal NON-interrupt steer queued requesting same-PR
  inclusion; queue receipt is not delivery evidence." 21:23Z: "First queued note
  actually injected 21:18:37.791Z / native user 21:18:37.874Z. Other three notes
  still pending at last observation."
- 2026-10-06T07:43Z: "Exact normal steering receipt audited, not inferred from
  ack."

The session KNEW the rule — it wrote "queue receipt is not delivery evidence" in
its own words a day before the maintainer's statement — and still had to
establish delivery by hand, by reading the worker transcript, every time,
because the only mechanical signal available was the queue's receipt. The same
pattern appears for success claims: at 2026-10-06T05:30Z, "Root initially
described a passed post-implementation gate from the checkpoint name alone, then
corrected that claim immediately upon the actual failure report; checkpoint
names alone do not establish success"; and at 09:24Z, "Correction: 65536-char
publication limit was an actor assumption, not an observed GitHub rejection;
GitHub accepted the 66680-char verification record." Twenty-three of the 64
comments contain the word "Correction" or "correction". Each correction was
honest and prompt. Each was also a hand-run delivery check that a mechanism
could have run first.

### Instance 4 — cross-session relays, and where delivery was and was not established

Between the two sessions and their tenants, three relays in the same window show
the three possible outcomes:

- **Delivered and verified by the sender from the target's state.** At
  2026-10-06T03:01Z the overseer session asked, in a handoff, that "the
  definition-and-proof owner track this shared-tooling incident". By 03:19Z its
  next handoff recorded that plan `dispatcher-cache-lifetime` (epic
  `bd-ib-fjw7fs`) and child `bd-ib-mtuqxb` existed in this tenant, read from
  this tenant's ledger. At 05:59Z it recorded a finding "posted/read back on
  original owner bd-ib-7sjdzv comment 01a10fc8-... at 05:55:29Z after dedup".
  Both are delivery established from the target's own state, by hand.
- **Delivered, and recorded on both sides.** The orchestrator session's handoff
  17 on `bd-ib-7sjdzv` records "R9: the hold on plan overseer-herdr-rewrite
  (epic overseer-uzvcbn) was released 2026-10-05T04:02Z with a written brief
  ... That session resumed and is dispatching." The overseer epic's handoff at
  2026-10-05T04:02:05Z records "Resume authorized by definition-and-proof-of-done
  relay on 2026-10-05. Read the supplied A-G brief in full." The claim was true;
  it was also authored from the sender's side, and nothing but a later reader
  comparing the two epics could have shown it.
- **Not delivered, and the sender concluded it was.** The closed item
  `bd-ib-q5qm4e` records the measured case from 2026-08-22: a fleet dispatch
  hold was sent to foreman seats that could not act on it, the announcing seat
  "sees no bounce and concludes the hold landed", and a plan session with no
  signal dispatched into the maintenance window. Its own words: "No bounce is not
  evidence of receipt." The remedy chosen there was an admission valve at the
  chokepoint — the right fix for that case, and not a general delivery check.

## 3. The root cause

### (a) Every existing confirmation is produced by the channel, not by the target

An acknowledgment is produced by the thing that carried the message: a queue
receipt, a pane echo, a comment id returned by `bd comments add`, a peer's
"received". Delivery is a change in the thing the message was about: the item
moved status, the comment is on the target item, the pull request exists on the
forge, the file is on the target's default branch. The two are produced by
different systems and nothing today requires a session to read the second
before recording the first as done.

The fleet's strongest existing rule is the supervisor obligation schema shipped
in `.ai/supervisor-protocol.md` in this repository and in `livespec-overseer`
(`overseer-uc4l5e`, closed 2026-07-30): a cross-track handoff keeps
`holder: me` until BOTH `receipt_ack` and `peer_recorded` are set, and its
filing note says outright "Filing is not delivery." That rule is one step short
of the maintainer's discipline, and the step matters: `peer_recorded` is the
PEER'S record of the obligation, which is still a statement by a party to the
relay, not the state of the thing the relay was about. And the schema lives in a
`tmp/` YAML file read by the overseer daemon for freshness, not by any
orchestrator primitive that records a relay as done — on this repository's side
it is prose. `overseer-ow7c.3` (backlog) names the adjacent gap: a relayed claim
cannot express its provenance or measured-at, so a claim whose content is fine
and whose source or age is wrong is undetectable by reading. That item is about
the ENVELOPE of a claim; this plan is about whether the claim's SUBJECT changed.

So the root cause of (a) is stated here as:

> Nothing in the orchestrator's record-keeping distinguishes "I sent it and
> something acknowledged it" from "the target now shows the result I asked for",
> so a session can — and, as instance 3 shows, must — treat the two as the same
> unless it does a hand check, and a hand check is exactly the activity instance
> 1 counts as work.

### (b) Every existing progress signal measures activity, and the one that measures records only warns

Surveyed for this note, every signal in both repositories that could flag the
instance-1 shape keys on something other than a required result:

| Signal | Where | What it measures | Why instance 1 passes it |
| --- | --- | --- | --- |
| `progress_now` (pair-stall detector, Lane D of `overseer-4xfmez`) | `livespec-overseer/overseer/_supervisor_progress.py` | agent status busy, or context percentage moved, or (Codex) pane looks busy | the session was busy the whole day |
| `shell-prolonged`, idle nudge | `livespec-overseer/overseer/_supervisor_config.py` (8 h, 1 h) | a background shell held, or continuous idleness | the session was neither parked nor idle |
| stall and dead-watch condition (`overseer-h4ziqc`) | overseer daemon | pane content unchanged for a bound | pane content changed constantly |
| plan record-rate guard | this repository, `_plan_record_rate.py` | records per author-day, threshold 6 | fired at least five times; warn-only; no required response |
| fix-loop cap, review-fix cap, non-convergence bounce (`bd-ib-tbgxm4`, Scenario 11) | this repository, Dispatcher | retries INSIDE one run; bounces the item to `backlog` at the cap | each re-dispatch is a fresh run with a fresh cap; `bd-ib-mtuqxb` ran four times |
| `acceptance_rework_cap` | this repository, `_dispatcher_completion.py` | rework rounds after a failed acceptance | not reached: the host janitor failures left items `active` with no rework marker |
| `plan_completion` (`overseer-9gfh`) | livespec-overseer | child set closed | measures exhaustion by absence, which that item's own filing calls "actively wrong" |

The common property: each signal fails toward "working". That is the correct
direction for a signal that AUTHORIZES AN ACT against a session (Lane D states
the directional-evidence principle explicitly), and it is the wrong direction for
a signal meant to DETECT that a busy session is not progressing. A busy,
honest, well-documented session is invisible to every one of them. So the root
cause of (b):

> No record in either repository names the one result a session's current work
> is required to produce next, so no mechanism can measure whether it has been
> produced, and every proxy that exists measures activity instead — which a
> stuck session produces in abundance.

The typed `next_action` on a plan epic is the nearest thing to that record and it
is not it: its `kind: impl` names an item to dispatch, not what the dispatch must
yield, and the overseer epic's pointer at the end of the window read `kind: none`
with the text "Finish the shared repair through normal recovery, independent
proof and release, update and rebind the plugin, then resolve and dispatch
overseer-emzwpx" — five results in one sentence, none of them checkable by a
primitive.

### Why both halves are one plan

A delivery check and a progress deadline share one primitive: READ THE TARGET.
Delivery of a relay is the target item or forge object showing the requested
change. Progress against a required result is the target item, forge object or
ledger showing the declared result. The same reader, pointed at a ledger id, a
pull request number, or a path on a default branch, answers both. Building them
apart would produce two readers of the same three surfaces.

## 4. Prior art in both ledgers

Surveyed 2026-10-07 with `bd list --status all --limit 0 --json` in this
repository (1172 records) and in `livespec-overseer` (1117 records), searching
titles and descriptions for progress, record rate, acknowledgment, delivery,
relay, two-sided, non-convergence, bounce, nudge, ladder, thrash, handoff count
and retry budget, then reading the description of each overlap. The items below
are the ones that bear on this plan. `livespec-dev-tooling` and other fleet
tenants were not searched.

**Closest, and NOT to be duplicated:**

- `overseer-uc4l5e` (closed) — cross-track obligation handoff with two-sided
  confirmation (`receipt_ack` and `peer_recorded`); "Filing is not delivery."
  Shipped as the supervisor-protocol schema in both repositories. This plan's
  delivery check is the third leg that schema lacks: a read of the target's
  state. Any mechanism here must extend that schema, not shadow it.
- `bd-ib-q5qm4e` (closed) — a fleet dispatch hold with no delivery path; "No
  bounce is not evidence of receipt." Closed by the admission valve. The general
  delivery-check gap it names in passing ("a broadcast primitive that ... reports
  who was NOT reached") was not built and is in scope here.
- `overseer-ow7c.3` (backlog) and `overseer-tdfe.18` (closed) — a relayed claim
  carries no provenance or measured-at. Envelope, not subject; complementary.
- `overseer-4xfmez` (closed epic) and `overseer-4xfmez.6` (closed) — control-plane
  supervision liveness; Lane D's content-immune `progress_now` and pair-stall
  detector. This is the overseer's definition of progress, and it is activity.
  Section 3(b) is the argument for a second, result-keyed definition beside it,
  not a replacement: Lane D must keep failing toward "working" because it gates
  a nudge.
- `bd-ib-40vz` (ready) — ledger comments concatenated into the dispatch goal.
  Names the record-rate guard as "the identical hazard, already recognised,
  already guarded — for PLAN records" and proposes a warn-at-assembly guard on
  the same warn-only contract. Instance 2 is evidence that the warn-only contract
  does not change behaviour; the design here should say so when it decides
  whether the deadline warns or refuses.
- `bd-ib-z2y4ca` (pending-approval), `bd-ib-tbgxm4` (closed, 2026-10-06),
  `livespec-impl-beads-n5kina` (closed), `bd-ib-rfgr` (backlog) — the
  non-convergence bounce family: Red progress per cycle inside a run, the
  fix-loop cap, the bounce to `backlog`, and the fact that a bounced item reaches
  no attention surface. All are WITHIN-RUN. This plan's mechanism C is
  ACROSS dispatches of one item and must compose with the bounce, not re-implement
  it; `bd-ib-rfgr` is the surfacing gap that mechanism D would also close if its
  fact class covers a bounced item.
- `overseer-9gfh` (closed) — plan completion inferred from the child set is
  "actively wrong" for a plan whose scope lives elsewhere. The same warning
  applies to any detector here that infers "no progress" from child state alone.
- `overseer-h4ziqc` (closed), `overseer-w2nwx5` (closed) — the daemon's stall
  condition and the idle-escalation ladder's false positives against a healthy
  foreman. A result-keyed detector sidesteps the second: a foreman between
  ticks has no required result due.
- `overseer-au3pt3.2` (closed), `overseer-7ranbh.5` (closed) — the foreman's relay
  and escalation discipline (evidence-carrying relays, verbatim quotes, published
  wait states on the governed epic). Relay CONTENT discipline; delivery is not
  among its five rules.
- `bd-ib-fngpwg` (ready) — the proof-reuse half of the first discipline, routed
  there by the maintainer. Out of scope here.
- `bd-ib-jnpvh4` (backlog epic) — the sibling stall plan; boundary in section 1.

**Not found:** no item, open or closed, in either tenant proposes a required
next result declared on an item or epic, a handoff-count or wall-clock budget
after which a same-shape attempt is refused, a delivery check that reads the
target's state before a relay is recorded as done, or an attention fact keyed on
an epic's handoffs recording no new merged pull request, closed child or verified
record. That absence is stated with its scope: two tenants, all statuses, the
terms above.

## 5. Candidate mechanisms

Ordered from most mechanical to least. Costs are estimates for scoping, not
commitments. "Owner" names the repository whose code would change; anything in
`livespec-overseer` goes through a referral, never a direct edit from this plan.

### A. A delivery check before a relay is recorded as done (plan primitives)

A relay recorded on a plan epic names its TARGET as a typed reference — a ledger
item id with the expected status or an expected comment marker, a pull request
number with the expected state, or a path expected on a named branch of a
repository — and the primitive that records the relay READS that target before
it will write "delivered". If the target does not show the result, the relay is
recorded as `relayed, undelivered` with a deadline, and the sender keeps the
obligation. An acknowledgment, however it arrived, is recorded as an
acknowledgment and nothing more.

- Where: `append_handoff` grows an optional `relays` tuple, or a sibling
  `record_relay(...)` primitive; the reader is one function over the three
  surfaces (ledger via the existing `BeadsClient`, forge via `gh`, repository
  via `git ls-remote` / `git cat-file` on the named ref). The
  `.ai/supervisor-protocol.md` schema in both repositories gains a `delivered`
  leg beside `receipt_ack` and `peer_recorded`, and the rule that `holder`
  changes only when it is set.
- Cost: small to medium. The reader is a few adapters over clients that exist.
  The hard part is the vocabulary of "expected result", which mechanism B
  shares.
- What it does not do: it cannot verify delivery of a message with no durable
  target (a pane paste with no record). Those stay undelivered until the
  recipient produces a durable effect, which is the correct answer.

### B. A declared required next result and a budget on the typed next action

The epic's `next_action` grows a `required_result` — a typed reference of the
same shape as A's target, naming the ONE result the next action must yield
(`merged_pr`, `closed_item`, `item_at_status`, `verified_record`,
`file_on_branch`) — and a `budget`: a handoff count, a wall-clock bound, or
both. `append_handoff` reads the previous pointer's `required_result`, checks it
against the target, and:

- if the result is now present, the entry is ordinary and the new pointer may
  name the next required result;
- if it is absent and the budget is not exhausted, the entry is ordinary and the
  count advances;
- if it is absent and the budget IS exhausted, the primitive REFUSES an entry
  whose `next_action` has the same kind and ref as before, unless the body
  carries an `approach:` line stating what changes, or the pointer becomes
  `kind: human` naming the question. The refusal names the required result, the
  budget, and how many entries were written against it.

This is the progress deadline. Instance 2 is why it refuses rather than warns:
the warn-only guard was surfaced five times and read as permission each time.
It also makes instance 1's two readings decidable, because the session declares
at each handoff which result counts, and the next session inherits that
declaration rather than re-deriving it.

- Where: `_plan_next_action.py` (the `NextAction` shape), `append_handoff`,
  `set_next_action`, `resume_directive` (which must surface an exhausted
  budget as a finding), and the plan prose.
- Cost: medium. The `next_action` object is fixed-shape epic metadata under
  §"Typed `next_action` and `last_session`" and §"Planning Lane restraint
  budget" of `SPECIFICATION/contracts.md`, so adding keys is a `propose-change`
  decision, not a free edit. The restraint budget's own wording ("bounded,
  fixed-shape metadata KEYS on that same epic") admits two more keys; the
  scoping session must say so in the proposal.
- Open: whether a budget has a default or is refused when absent. This note
  leans the same way the stall plan did for deadlines: refuse, because a default
  is a budget nobody chose.

### C. Refuse an N-th same-shape dispatch of one item (Dispatcher)

Before dispatching an item, `drive` / `dispatcher.py dispatch` reads the item's
rows in the dispatch journal (`fabro-run`, `needs-human-blocked`,
`human-valve-resolve-blocked-answer`, `preserve-by-reference`, and the terminal
stage of each run) and computes the furthest stage any previous dispatch
reached. If the last N dispatches each ended at or before that stage, the
dispatch is refused until the item carries a changed-approach record — a
`resolve-blocked` answer that names what is different, or a comment of a fixed
first-line shape — and the refusal names each prior run, its terminal stage, and
the best stage ever reached.

- Measured input exists today: `bd-ib-mtuqxb` shows 4 `fabro-run` rows and 3
  `needs-human-blocked` rows in `tmp/fabro-dispatch-journal.jsonl`; the
  `human-valve-resolve-blocked-answer` rows are the natural carrier of the
  changed approach, and are already written by the valve.
- Composition: the non-convergence bounce (Scenario 11) acts INSIDE a run at the
  fix-loop cap; this acts BETWEEN runs. Neither replaces the other. The bounce's
  `backlog` return is one of the terminal shapes this reads.
- Cost: medium. The pre-dispatch sequence in `_dispatcher_run_checks.py` is where
  it inserts; the journal reader exists in several attention lanes. N is a
  committed `dispatcher.*` key, never a constant.
- Risk: a run that fails for a factory-host reason (ENOSPC, a stale build,
  a credential outage) ends at the same stage through no property of the item,
  and AGENTS.md says such a failure is waited out and retried on the normal
  path. The refusal must therefore classify the terminal cause the way the
  attention lanes already do, and count only item-attributable terminals.

### D. An attention fact for an epic whose handoffs record no new required result

A `needs-attention` lane that, for every open plan epic with a live
`plan/<slug>/` directory, reads its handoff timeline over a window and the
ledger and forge state its entries name, and surfaces the epic when the window
holds more than K entries and no new merged pull request, closed child, or
verified record attributable to the epic — naming the window, the entry count,
the last required result and when it last moved. Report-only, on the surface the
operator already reads.

- With B in place this lane reads `required_result` directly and needs no
  inference. Without B it infers from the three surfaces and must say that it
  is inferring — `overseer-9gfh` is the warning against inferring exhaustion
  from one surface.
- The overseer daemon consumes the orchestrator's `needs-attention` envelope
  already (§"The needs-attention machine envelope"), so a daemon-side surface
  for the same fact is a referral to `livespec-overseer`, filed once this fact
  class is stable, and would let that daemon catch the overseer session itself.
- Cost: small to medium; one lane in the existing composition, one fixture.

### E. Guidance (AGENTS.md, plan prose, supervisor protocol)

The two disciplines as a verification-discipline rule: a relay is recorded as
delivered only from the target's state; a status entry names the required
result it is measured against; and the record-rate warning's prescribed
question ("is the thread blocked on something a handoff cannot fix") is answered
in the entry that surfaces it, not merely acknowledged.

- Cost: trivial. Value alone: low — the overseer session already knew and wrote
  the rule, which is the whole point of instance 3. Guidance is the pointer to
  the mechanisms, not the fix.

### Recommended combination (a proposal, not a ruling)

B and D first, in one design, because they share the one definition of "required
result" and D without B is inference. A beside them, because its reader is the
same one B needs and it is small once that reader exists. E in the same change.
C after B's vocabulary exists, so that the changed-approach record C demands is
the same thing B records. The referral to `livespec-overseer` for a daemon-side
surface last, once D's fact class has been exercised on this repository.

## 6. Open questions the scoping event must settle

1. The shape of a typed target reference shared by A, B and D: ledger id plus
   expected status or comment marker; pull request number plus state; path plus
   ref plus repository. Whether a fourth kind (a verified Proof of Done record
   on a named run) is its own kind or the comment-marker kind.
2. Whether B's budget is counted in handoff entries, wall-clock hours, or both,
   and whether it is refused when absent.
3. Whether B's refusal is absolute or whether an unattended resume
   (`LIVESPEC_PLAN_UNATTENDED`) converts it to `kind: human`, which is the only
   thing an unattended session can safely do with a refusal.
4. Whether A and B require a specification change. B touches fixed-shape epic
   metadata and so almost certainly does; A may be realizable in the plan prose
   and primitives without one. That is a `propose-change` decision for the
   scoping session, and the Scenario that would govern B does not exist yet.
5. For C, the terminal-cause classification that separates an item-attributable
   same-stage failure from a host-side one, and its relation to the existing
   needs-human classification in the valves.
6. What "attributable to the epic" means for D's three surfaces, given the
   child-enumeration trap recorded in AGENTS.md (neither the id-prefix form nor
   the `parent` field is complete; use `client.children()`).
7. Whether the `.ai/supervisor-protocol.md` schema change is this plan's or a
   referral: the file exists in both repositories with the same schema, and the
   overseer daemon reads it.

## 7. Explicitly out of scope

- Reusing a terminated run's saved inputs and outputs in a replacement session.
  That is `bd-ib-fngpwg` under plan `definition-and-proof-of-done`.
- A session that is parked on a wait and never woken, bounded waits, the wait
  inventory, and the supervisor condition over it. That is plan
  `agent-session-stall-prevention` (`bd-ib-jnpvh4`).
- The content of the overseer session's repairs: the herdr fixtures, the shell
  alias guard, the idle canary, the dispatcher cache lifetime, the host-mode
  prompts. Those belong to their own items and plans; this note cites them only
  as measurements.
- The within-run non-convergence bounce, the fix-loop cap and their calibration
  (`bd-ib-z2y4ca`, `bd-ib-tbgxm4`). Mechanism C composes with them and does not
  change them.
- The provenance and measured-at envelope of a relayed claim
  (`overseer-ow7c.3`). Complementary, not duplicated.
- Changes to the overseer daemon. This plan defines a fact the daemon can
  consume and files a referral; it does not edit `livespec-overseer`.
- The overseer session's own privacy incidents and TDD-chronology disclosures
  recorded in its handoffs. Noted as read; not this plan's subject.
