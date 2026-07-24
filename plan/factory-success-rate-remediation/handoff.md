# Handoff — factory-success-rate-remediation

Thread goal: raise the dark-factory merge success rate (78% fleet-wide,
94% on this repo over 2026-06-11..2026-07-23) by remediating the
failure causes the 2026-07-23 telemetry investigation actually
measured — NOT by scaling the review stage, which the data cleared
(83% first-pass approve, ~2% terminal cause, zero detected misses).

Ledger epic anchor: `bd-ib-cvgjop` (this thread's status anchor).
Status is always READ from the ledger — compose it via the
`/livespec-orchestrator-beads-fabro:list-work-items` and
`/livespec-orchestrator-beads-fabro:next` operations; this file
deliberately carries no work queue of its own. (Last refreshed
2026-07-24; anything below can be re-derived from the ledger and the
files named here.)

## Read first (in this order)

1. `research/synthesis.md` — the cross-track conclusion and the
   priority ordering of the remediation targets.
2. `research/failure-telemetry-2026-07-23.md` — the failure
   distribution the priorities rest on (raw evidence: `research/data/`).
3. `research/review-fix-split-design.md` — the DECIDED design that
   resolved `bd-ib-o35rcx`, including its adversarial-review
   dispositions (see below). `research/review-fix-conflation.md` is
   the archaeology behind it.
4. `grooming-cut-2026-07-23.md` — the supervisor-approved acceptance
   criteria, routing, and drain order for the whole queue (with its
   §7 execution addendum).

## The o35rcx arc (DECIDED and mostly landed)

- Maintainer directive 2026-07-23 (supervisor-relayed): **restructure
  by splitting** — finding-disposition (accept / reject-with-rationale
  per `[BLOCKING]` finding) and fix-implementation become SEPARATE
  steps of the implement-work-item graph, each independently
  promptable and independently model-selectable.
- Design record: `research/review-fix-split-design.md` — independently
  adversarially reviewed (Codex, against the fabro engine source):
  verdict SOUND-WITH-CHANGES; ALL ten findings dispositioned in the
  record's §"Adversarial review disposition" (both blocking fixes
  folded into the design body).
- S1 (spec): RATIFIED as `SPECIFICATION/history/v046/` via a selective
  revise (other threads' pending proposals untouched), merged as
  PR #892; ledger slice `bd-ib-t5u62i` CLOSED.
- S2 (implementation): `bd-ib-fe574e` — queued at the drain tail,
  AFTER `bd-ib-n7ce4n` (supervisor ordering: once the staleness gate
  is live, S2's own live-verification is trustworthy by construction).
- S3 (live evidence): `bd-ib-p3sjiy` — supervised, after S2.
- `bd-ib-o35rcx` itself stays OPEN until S3's journaled live-exercise
  evidence exists. Do NOT close it on S2's merge.

## Drain state (2026-07-24; re-verify from the ledger)

- DONE with live evidence: `bd-ib-nga9` (PR #889; positive refusal +
  negative no-over-match probes journaled on the item — read its notes
  for the merged-but-not-live finding they exposed).
- CLOSED on verified evidence: `bd-ib-4sy` (the bd-ib-2nq token arc
  fixed it; evidence journaled on the item).
- OPEN, narrowed: `bd-ib-6vu` — fork-track reconnect-path credential
  threading (`github_app: None` on attach-resume; fabro #568 finding
  #2); host-only, never drained.
- REMAINING DRAIN ORDER (ranks a3..aA; dispatch via
  `drive --action impl:<id>`, strictly sequential):
  `bd-ib-lgv` → `bd-ib-qq7f` → `bd-ib-pums` → `bd-ib-uwshxy` (sd8o-c
  mutex) → `bd-ib-18r` → `bd-ib-mqr7wr` (w2ah convention doc) →
  `bd-ib-n7ce4n` (staleness gate) → `bd-ib-fe574e` (S2).
  Every queued item already carries: groomed acceptance criteria, a
  named LIVE PROBE PLAN with a negative no-over-match case (in notes),
  a brace-token sweep (clean), and a description under the ~1500-char
  sizing threshold (verbatim originals parked in notes).

## Standing operating rules a successor MUST inherit

1. **Cross-track serialization**: before ANY dispatch, claim the host
   factory slot with an ordered line in
   `/data/projects/livespec/tmp/fleet-pin-propagation-supervisor/status.log`
   and release when done; RE-READ the log immediately before claiming
   (a TOCTOU collision happened when a zero-container check passed
   while another track was still preflighting).
2. **Argv-proven container ownership**: never kill/stop/touch a fabro
   container without proving ownership from the dispatcher argv
   (`ps -eo pid,args` → `fabro-run-config-<item>.toml` +
   `dispatch --item <id>`); never identify by image, timing, or
   elimination — this session killed a foreign run that way.
3. **Exit 137 is ambiguous** (kill vs normal teardown): establish run
   outcome from the independent artifact — merged PR, journal
   `outcome` record, ledger state — never from exit codes.
4. **Refresh-and-verify before EVERY dispatch until `bd-ib-n7ce4n`
   lands** (verified commands in that item's notes): confirm
   `origin/release` contains the relevant merge
   (`git merge-base --is-ancestor`), `claude plugin update
   livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro
   --scope project`, assert the new cache dir id equals the release
   HEAD sha prefix, grep the new cache for the item's distinctive
   symbol, and invoke every surface from the NEW cache root. The
   self-update layer is skipped ENTIRELY in the read-only plugin-cache
   mode this host runs.
5. **Live probes are part of done**: every behavior-bearing item needs
   journaled live-exercise evidence WITH a negative no-over-match case
   before it counts (maintainer rule 2026-07-04: done = rolled out and
   exercised live; the negative case is what catches a fix that
   silently disarms adjacent work).
6. **Every blocking gate must name a remedy the blocked party can
   perform** (fleet-pin Slice-3 precedent; the n7ce4n release-target
   redesign is the worked example).
7. **Never reword an item's text merely to flip an automatic guard's
   decision** (verb-avoidance is retired): a guard-dodging rewrite
   erases the fact that a safety guard objected and generalizes to
   items that genuinely warrant the block — the same defect family as
   hand-editing `admission:*` labels instead of using the valve. For a
   citation-only false positive of the workflow-edit heuristic, use
   the shipped negation declaration (an inline line stating the item
   ships no files under the workflows dir) and journal the substantive
   verification from the item's actual deliverables; the recorded
   valve override that mechanically clears the block is
   `bd-ib-imzx24`'s deliverable (the shipped message's valve remedy
   does not yet clear it).

## Epic-close preconditions (recorded on `bd-ib-cvgjop`)

1. One-shot livespec doctor LLM objective+subjective pass over the
   accumulated spec state (deferred at the v046 revise — deferred, not
   dropped).
2. Journaled live evidence for every behavior-bearing drain item.

## Items filed by this thread (beyond the original epic set)

`bd-ib-t5u62i` (S1, closed), `bd-ib-fe574e` (S2), `bd-ib-p3sjiy` (S3),
`bd-ib-uwshxy` (sd8o-c mutex), `bd-ib-tyxzhv` (sd8o-a diagnosis,
host-only), `bd-ib-js4t57` (fork-track engine seam for pums' root
defect, host-only), `bd-ib-mqr7wr` (w2ah execution-mirror convention
doc), `bd-ib-n7ce4n` (staleness gate, release-target design),
`bd-ib-kttyks` (4sy-residual work-loss hardening, backlog),
`bd-ib-gbu3k6` (container ownership-attribution surface, backlog),
`bd-ib-efjsb4` (exit-137 / outcome-from-artifact doctrine chore,
backlog).

## Next action

1. Resume the drain under ALL the standing rules above: the queue
   order and per-item probe plans are on the items; the supervisor
   coordination channel is
   `/data/projects/livespec/tmp/factory-success-rate-remediation-supervisor/status.log`
   (journal dispatch-start / dispatch-end / blockers / questions
   there).
2. After `bd-ib-fe574e` (S2) merges and a refreshed build carries it:
   drive `bd-ib-p3sjiy` (S3) — capture the first blocking-review
   dispatch's `fabro events` showing the disposition routing, journal
   on `bd-ib-o35rcx`, then close `bd-ib-o35rcx`.
3. When the epic's tracked items are closed and both epic-close
   preconditions hold, close `bd-ib-cvgjop` and archive this thread
   (`git mv plan/factory-success-rate-remediation/
   plan/archive/factory-success-rate-remediation/`).
