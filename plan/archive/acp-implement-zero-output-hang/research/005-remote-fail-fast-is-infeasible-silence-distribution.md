# Dossier 005 — a remote-signal fail-fast is INFEASIBLE: the healthy fabro-silence distribution overlaps the hang entirely

Design-decision note for plan thread `acp-implement-zero-output-hang` (epic
`bd-ib-b5dg`), compiled 2026-09-04. It takes the qualitative finding from the
2026-09-02 live specimen (a healthy run looked identical to a hang on every
remote-observable signal, n=1) and turns it into a QUANTITATIVE basis by
measuring the distribution across 60 healthy runs. Labels **measured** /
**inferred** / **hypothesis** as before. This dossier settles the Child B
(`bd-ib-q5wxkh`) re-cut question and corrects the feasibility premise of aim 2 /
R1.

## Why this pass happened

The 2026-09-02 live catch (run `01M1HEAW523A9HVSY40AAVDFT2`, console item
`bzs6`, merged PR #942) was proven — by the console session's in-sandbox
inspection — to be a HEALTHY, productive run whose fabro event stream was frozen
for ~16 minutes after `agent.session.activated`, because the ACP-adapter → fabro
event bridge drops intra-turn notifications (the mechanism the epic's cross-repo
evidence pointer records: `fabro-acp/src/session.rs` `.otherwise_ignore()`s
`SessionUpdate::ToolCall`/`ToolCallUpdate`; `tool_time_ms` hardcoded 0). That
established, at n=1, that a healthy turn and a zero-output hang are
indistinguishable on both signals a remote watchdog can see — fabro's event
stream and `fabro ps` `status_kind`. This pass measures HOW BAD the overlap is,
because the whole feasibility of aim 2 (fail-fast BELOW the turn ceiling) turns
on it.

## Method (measured)

Sampled the 60 most-recent `succeeded` `ImplementWorkItem` runs on hp (of 572
available), via `fabro ps -a --json --server hp` then `fabro events <run>` per
run. For each run computed:

- `overall_max_gap_s` — the longest silence between any two consecutive events.
- `max_post_activation_gap_s` — the max, over every `agent.session.activated`
  event, of the gap to the immediately-following event. This is the EXACT
  "activated then fabro-silent" window a hang lives in, measured on runs that are
  known-healthy because they succeeded.

Script: `silence_gap_sampler.py` (session scratch; observe-only).

## Measured — the distribution

For all 60 runs, `max_post_activation_gap_s` EQUALS `overall_max_gap_s`: the
longest silence in a healthy run is always the intra-ACP-turn silence, and in
every case that silence runs `agent.session.activated -> agent.session.deactivated`
with no intermediate event. So the bridge is TOTALLY blind inside a turn; the
"silent window" is simply the turn's own duration.

Distribution of the healthy per-run max fabro-silence (seconds):

| stat | seconds | minutes |
|------|--------:|--------:|
| min  |   331 |  5.5 |
| p50  | 1703 | 28.4 |
| p90  | 2794 | 46.6 |
| p95  | 3132 | 52.2 |
| max  | 4001 | 66.7 |

Top offenders were all 3-turn runs: 4001s, 3903s, 3132s, 2937s, 2848s.

The 2026-09-02 healthy specimen's ~16-minute silence was, it turns out, on the
LOW side of this distribution — the MEDIAN healthy run is fabro-silent for ~28
minutes inside an ACP turn. (The long tail past 30 min is consistent with the
`ImplementWorkItem` implement node's very long configured node timeout; a healthy
implement turn can legitimately run far longer than the 30-minute figure the
original defect cited for a single ACP turn.)

## Measured — every candidate fail-fast floor false-kills the majority

Count of the 60 healthy runs whose max post-activation silence exceeds each
candidate fail-fast floor (i.e. that a watchdog keyed on fabro-event-freshness
would have WRONGLY killed):

| floor | healthy runs false-killed |
|------:|--------------------------:|
|  5 min | 60/60 (100%) |
|  8 min | 59/60 |
| 10 min | 53/60 (88%) |
| 12 min | 49/60 |
| 15 min | 48/60 (80%) |
| 20 min | 40/60 (67%) |
| 25 min | 33/60 (55%) |

There is NO floor "in minutes" (aim 2's stated goal) that avoids destroying the
majority of healthy work. A liveness guard that fails toward KILL is the
expensive direction (it deletes good work), so this is disqualifying, not a
tuning problem.

## Inferred — the only remote discriminator fires too late

Healthy turns end their fabro-silent span with `agent.session.deactivated`; the
recorded hung specimens (research/002 run `01M17P0QHRH7ZYXJ6DVTRSFAV4`; the
2026-09-01 counter-specimen `01M1ES066RHS8Y39B9WJW8WC8Q`) end theirs with
`agent.acp.timed_out`. So a remote signal that DISTINGUISHES health from hang
does exist — the turn-END event type — but by construction it only appears when
the turn is already over (deactivated) or has already burned the full ceiling
(timed_out). It cannot fire BELOW the ceiling, which is exactly what R1 requires.
The one remote avenue not yet exhausted is whether `fabro inspect` exposes a
cost/token counter that advances mid-turn; the dossier-established fact that ACP
timing fields are hardcoded/zero makes this low-probability, but it is the single
remaining thing to check before declaring the remote channel fully dead.

## Consequence for the plan (the decision)

R1 ("the orchestrator kills a zero-output/silent ACP turn below the turn ceiling")
CANNOT be met by an orchestrator-side watchdog keyed on fabro's event stream or
on `fabro ps` `status_kind`. The healthy and hung distributions overlap across
the entire usable range. This is a feasibility correction to aim 2, not a bug in
Child A's landed observability (which works — see dossier 004).

Only two mechanisms can make a real fail-fast possible; both live OUTSIDE the
orchestrator's remote-signal reach:

1. **A fabro-side intra-turn liveness signal (recommended path).** Restore the
   dropped ACP `ToolCall`/`ToolCallUpdate` notifications into the fabro event
   stream, OR emit a per-turn heartbeat event, so that a productive turn is
   VISIBLY distinct from a silent one before the ceiling. This is the plan's
   already-deferred D3 / fabro-side work. With it, the orchestrator watchdog
   becomes a thin, correct consumer of a real signal, and Child B reduces to
   wiring that consumer. Cost: upstream/fork fabro change (the fork at 8de6611
   already carries local OTLP additions, so it is a plausible carrier).

2. **In-sandbox liveness probing.** Have the dispatcher (or a sidecar) exec into
   the run's sandbox and check transcript growth / agent CPU — the exact method
   the console session used to falsify the 2026-09-02 specimen. Cost: heavy and
   cross-boundary — the dispatcher needs docker access to the factory host, which
   it does not have today (the 2026-09-02 in-sandbox capture was done by a human
   on hp). It duplicates, more fragilely, what mechanism 1 provides cleanly.

A third posture, if neither is pursued: accept that the zero-output hang cannot be
fail-fasted and invest only in DETECTION + fast human escalation (Child C's
telemetry already surfaces the outcome). That downgrades R1 rather than meeting
it, and should be an explicit maintainer decision.

**Recommended re-cut of Child B (`bd-ib-q5wxkh`):** re-scope it from "make the
orchestrator watchdog fire below the ceiling on remote signals" (infeasible, per
this note) to "consume a fabro-side intra-turn liveness signal once D3 lands" —
i.e. make Child B depend on a D3 fabro-side item and shrink its orchestrator
deliverable to the thin consumer. This is a grooming/maintainer cut, not a
worker re-write; this note is the evidence it should be made on.

## What did NOT change

- The real hang still exists (research/002; the 2026-09-01 counter-specimen:
  `active_time_ms=0` for the whole turn with NO in-sandbox transcript growth).
  Nothing here says the hang is not real — only that it cannot be discriminated
  from health via remote signals before the ceiling.
- Child D (`bd-ib-y3vnpi`, the zero-output TRIGGER) is unaffected and still needs
  a live specimen with in-sandbox access.
