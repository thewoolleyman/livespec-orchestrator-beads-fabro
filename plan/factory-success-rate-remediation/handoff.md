# Handoff — factory-success-rate-remediation

Thread goal: raise the dark-factory merge success rate (78% fleet-wide,
94% on this repo over 2026-06-11..2026-07-23) by remediating the
failure causes the 2026-07-23 telemetry investigation actually
measured — NOT by scaling the review stage, which the data cleared
(83% first-pass approve, ~2% terminal cause, zero detected misses).

Ledger epic anchor: `bd-ib-cvgjop`. Status is always READ from the
ledger — compose it via the
`/livespec-orchestrator-beads-fabro:list-work-items` and
`/livespec-orchestrator-beads-fabro:next` operations; this file
carries no work queue of its own. (Last refreshed 2026-07-24 ~09:5xZ,
post-pivot; re-derive anything below from the ledger and the files
named here.)

## Read first (in this order)

1. `research/synthesis.md` — the cross-track conclusion and priority
   ordering of the remediation targets.
2. `research/failure-telemetry-2026-07-23.md` — the failure
   distribution the priorities rest on.
3. `research/review-fix-split-design.md` — the DECIDED o35rcx design
   with its adversarial-review dispositions.
4. `grooming-cut-2026-07-23.md` — the approved per-item acceptance
   criteria and routing (§7 execution addendum).
5. The ledger notes on `bd-ib-tyxzhv` and `bd-ib-sd8o` — the diagnosis
   evidence the standing pivot rests on.

## THE STANDING PIVOT (maintainer-directed, in force)

Restoring PARALLEL FACTORY THROUGHPUT outranks the rest of the drain.
The diagnosis leg is DONE and reframes everything:

- `bd-ib-tyxzhv` (sd8o deliverable a) is DISCHARGED — full evidence in
  its ledger notes. Headline: **no contended host resource exists at
  2x dispatch.** (1) The "bwrap namespace denial" is a HOST CONSTANT —
  the sysctl pair `kernel.apparmor_restrict_unprivileged_userns=1` +
  `kernel.apparmor_restrict_unprivileged_unconfined=1` silently denies
  userns creation inside containers under EVERY security config,
  proven solo; historical solo "successes" never invoked bwrap (codex
  danger-full-access skips it). (2) The `--network host` doctrine is
  FALSE: the running engine (binary commit b9b63a8) maps our
  `allow_all` network mode to the DOCKER BRIDGE default — sandboxes
  already have per-run network namespaces. (3) Twin real runs
  overlapped green at the script layer AND at the LIVE ACP agent layer
  (event-verified ~14s overlap, both succeeded). Residual: the single
  x9o `active_time=0` hang (2026-07-23) is unreproduced and untied to
  any host resource — a watch item, not a blocker.
- `bd-ib-sd8o` deliverable (b) is RESCOPED on that evidence (recorded
  prominently on the item — do NOT build per-run network isolation):
  demote the admission mutex from binary to a config-keyed counting
  cap + retire/re-scope the sequential doctrine in the livespec repo's
  `.ai/dispatcher-drain-operations.md`. One small factory-safe RGR
  unit. Cap surfaces: `drive.py` `impl:` argv hardcodes
  `--budget 1 --parallel 1`; `loop --parallel` already runs a real
  `ThreadPoolExecutor` over the admitted wave INSIDE one mutex claim
  (`_dispatcher_loop_command.py:202`) — single-track parallel drains
  work TODAY with zero code change; cross-track parallelism is what
  needs the mutex-cap demotion; `wip_cap` (5) already permits it.
- **NEXT ACTION 1: obtain the supervisor/maintainer scope
  confirmation for that rescoped unit, then implement it** (shape on
  `bd-ib-sd8o`; consider sequencing `bd-ib-j4clfi`, the pid-reuse
  hardening, adjacent — the lock becomes a counting structure). The
  prior session STOPPED awaiting that confirmation — check the
  supervisor status.log (below) for a ruling posted after
  2026-07-24T09:5xZ before asking again.

## Drain state (verify from the ledger)

- CLOSED with live evidence (rule 5: every criterion, negatives
  included): `bd-ib-nga9` (PR #889), `bd-ib-lgv` (PR #898),
  `bd-ib-qq7f` (PR #905; its IN-VIVO rebase observation still pends —
  bind it to the next real dispatch that publishes, expected pums).
- `bd-ib-uwshxy` (interim mutex): MERGED (PR #902) and live-verified —
  positive refusal PASS, terminal release PASS, crash-release PASS
  (POSIX reasoning + synthetic dead-pid reclaim probe). Close
  residuals on the item: parked-run exemption (bind to 18r's probe
  window), AC1 run-id-naming branch (partial discharge recorded),
  fleet root re-verification. This mutex is what the rescoped sd8o-b
  DEMOTES.
- Verify-first outcomes: `bd-ib-4sy` closed on evidence; `bd-ib-6vu`
  narrowed to fork reconnect-path credential threading (host-only).
- o35rcx arc: S1 `bd-ib-t5u62i` CLOSED (spec v046, PR #892); S2
  `bd-ib-fe574e` queued behind `bd-ib-n7ce4n`; S3 `bd-ib-p3sjiy`
  after S2; `bd-ib-o35rcx` closes only on S3's journaled evidence.
- **NEXT ACTION 2 (after the parallelism ruling): resume the drain** —
  `bd-ib-pums` → `bd-ib-18r` → `bd-ib-mqr7wr` → `bd-ib-n7ce4n` →
  `bd-ib-fe574e` → S3. Every queued item carries groomed acceptance
  criteria, a full-criteria probe plan (in its notes), a clean
  brace-token sweep, and a sized description.
- Backlog items filed by this thread, flagged for promotion rounds:
  `bd-ib-kttyks` (work-loss hardening), `bd-ib-gbu3k6` (container
  ownership surface), `bd-ib-efjsb4` (exit-137 doctrine chore),
  `bd-ib-imzx24` (cite-only override that actually unblocks),
  `bd-ib-j4clfi` (mutex pid-reuse), `bd-ib-eha3wh` (E2BIG telemetry
  argv — the rop-sweep track claimed a fleet-wide sweep of this class
  at 02:19Z; check their claim before working it).

## Standing operating rules a successor MUST inherit

1. **Cross-track serialization** (until the rescoped sd8o-b lands AND
   the supervisors rule to de-serialize): claim/release the factory in
   `/data/projects/livespec/tmp/fleet-pin-propagation-supervisor/status.log`;
   RE-READ the log immediately before claiming (TOCTOU);
   LAUNCH-FIRST-ANNOUNCE-SECOND — post the LAUNCHING line only after
   your container is visible; release on the prior run's
   ARTIFACT-VERIFIED terminal state (merged PR / journal outcome, with
   a transparency line) when its owner is a non-participant session.
2. **Argv-proven container ownership** before ANY container action
   (`ps -eo pid,args` → `fabro-run-config-<item>.toml`); never
   image/timing/elimination — this track killed a foreign run that
   way once.
3. **Exit 137 is ambiguous** (kill vs teardown): outcome comes from
   the artifact, never the exit code.
4. **Refresh-and-verify before EVERY dispatch until `bd-ib-n7ce4n`
   lands** (verified commands in that item's notes): release must
   contain the merge (`git merge-base --is-ancestor`), then
   `claude plugin update livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro --scope project`,
   assert the new cache dir id == the release HEAD sha prefix,
   marker-grep the item's symbol, and invoke every surface from the
   NEW cache root. Self-update is skipped ENTIRELY in the read-only
   plugin-cache mode this host runs.
5. **Live probes are part of done** — every acceptance criterion,
   explicitly the override/carve-out/escape-hatch ones, each with a
   negative no-over-match case (nga9's criterion 3 shipped broken
   because only the headline was probed).
6. **Every blocking gate must name a remedy the blocked party can
   perform** (three same-class instances in one night: n7ce4n's
   original design, nga9's valve route, fleet-pin Slice-3).
7. **Never reword an item merely to flip an automatic guard** — use
   the inline negation declaration + substantive verification from the
   item's actual deliverables, or the recorded valve once
   `bd-ib-imzx24` makes it mechanically real.
8. **Probes never use foreign runs as test subjects**; sanctioned
   concurrency is your own argv-proven runs only, announced in the
   serialization log with clean teardown and a findings line.

## Epic-close preconditions (recorded on `bd-ib-cvgjop`)

1. One-shot livespec doctor LLM objective+subjective pass (deferred at
   the v046 revise — deferred, not dropped).
2. Journaled live evidence for every behavior-bearing drain item.

## Coordination channels

- This track's supervisor journal (append milestones; questions with a
  recommendation, then wait):
  `/data/projects/livespec/tmp/factory-success-rate-remediation-supervisor/status.log`
- Cross-track factory serialization:
  `/data/projects/livespec/tmp/fleet-pin-propagation-supervisor/status.log`

## Next action (in order)

1. Read both status.logs for rulings posted after 2026-07-24T09:5xZ
   (especially the sd8o-b scope confirmation and any de-serialization
   ruling on the tyxzhv evidence).
2. Execute NEXT ACTION 1 (the rescoped sd8o-b) once confirmed; then
   close `bd-ib-tyxzhv` (its evidence is complete) and dispose
   `bd-ib-sd8o` per its rescope.
3. Execute NEXT ACTION 2 (drain resume) under the standing rules;
   pums' dispatch also delivers qq7f's pending in-vivo evidence, and
   18r's probe window also carries uwshxy's parked-run residual.
4. When the epic's tracked items are closed and both epic-close
   preconditions hold, close `bd-ib-cvgjop` and archive this thread
   (`git mv plan/factory-success-rate-remediation/
   plan/archive/factory-success-rate-remediation/`).
