# Handoff — factory-success-rate-remediation

Thread goal: raise the dark-factory merge success rate by remediating
the measured failure causes (2026-07-23 telemetry) — NOT by scaling the
review stage, which the data cleared. The maintainer's overriding
directive (brief-027, 2026-07-24, autonomous overnight): restore
PARALLEL FACTORY THROUGHPUT. **That goal is DELIVERED and CLOSED** —
see "The parallelism arc" below.

Ledger epic anchor: `bd-ib-cvgjop`. Status is always READ from the
ledger (`list-work-items` / `next` operations); this file carries no
work queue. Last refreshed 2026-07-24 ~12:3xZ, post-`bd-ib-sd8o`-close.

## Read first (in this order)

1. `research/synthesis.md` — the cross-track conclusion and priorities.
2. The ledger notes on `bd-ib-sd8o` (CLOSED) — the full parallelism
   evidence chain, and on `bd-ib-tyxzhv` (CLOSED) — the diagnosis it
   rests on.
3. `research/review-fix-split-design.md` — the DECIDED o35rcx design.
4. `grooming-cut-2026-07-23.md` — approved per-item acceptance criteria.
5. The track supervisor journal (below) from 07:36Z onward — tonight's
   full execution record including two live incidents and their fixes.

## The parallelism arc (DONE — context for everything else)

Serial dispatch is formally over. What shipped 2026-07-24 (~07:30-12:30Z):

- **Spec v047** (PR #909): `dispatcher.host_dispatch_cap` (positive
  integer, default **2**, no per-item override) — two-gauge in-flight
  counting (live capacity claims + observed non-terminal non-parked
  runs, each capped separately), remedy-naming refusal, parked-run
  exemption, honest crash-self-heal floor, Scenario 49.
- **Impl PR #912**: `_dispatcher_admission_mutex.py` demoted from the
  binary interim mutex to cap-N SLOT FILES
  (`tmp/fabro-dispatch-admission.slot<i>.lock`, per-slot
  claim/release/dead-pid-reclaim preserved) + the counting run gauge.
  `drive.py impl:` keeps `--budget 1 --parallel 1` (concurrency comes
  from concurrent invocations).
- **Gauge fix PR #917** (`bd-ib-3zek` P1 + `bd-ib-4cw9`, both CLOSED):
  the first live over-cap probe FAILED — call sites passed bare
  `"fabro"`, unresolvable inside the credential wrapper, so the run
  gauge had been silently fail-open-blind since the uwshxy era. Fixed
  (resolved fabro_bin threading + non-terminal/non-parked counting +
  LOUD ps-unobservable fail-open). Lesson: rule-8 negative probes are
  what caught it.
- **Doctrine retired** (livespec PR #1712):
  `.ai/dispatcher-drain-operations.md` now teaches cap-governed
  concurrency. The old `--network host` premise is falsified
  (`bd-ib-tyxzhv`); the bwrap denial is a host sysctl constant
  (`bd-ib-blk3`, backlog, host-only).
- **Releases v0.46.5→v0.46.7**, rolled out and marker-verified on both
  roots (`/data/projects/livespec-orchestrator-beads-fabro`,
  `/data/projects/livespec`). Builds ≤0.46.6 have the BLIND gauge —
  never dispatch from them.
- **Live evidence** (all on `bd-ib-sd8o`): cross-track 2x green
  (pums + foreign wxq, ~10min overlap); two-of-ours 2x to merged PRs
  (mqr7wr #919, 18r #921); over-cap refusal fired live (both run ids +
  count + cap + both remedies, zero sandbox); slot terminal-release,
  dead-pid crash-reclaim, and parked-run capacity-free all observed in
  production.

## Drain state (verify from the ledger)

- CLOSED tonight with live evidence: `bd-ib-pums` (PR #915; also
  discharged qq7f's in-vivo residual — note on `bd-ib-qq7f`),
  `bd-ib-18r` (PR #921 — parked runs are now a first-class `blocked`
  outcome; two same-night live corroborations on its trail),
  `bd-ib-mqr7wr` (PR #919; manual-on-merged-evidence disposition,
  justification in its close reason; `bd-ib-w2ah` closed
  answered-by-convention), plus the parallelism items above.
- REMAINING queue (in order): `bd-ib-n7ce4n` (staleness gate — its
  landing RETIRES the interim refresh-and-verify rule) →
  `bd-ib-fe574e` (S2, depends on n7ce4n) → S3 `bd-ib-p3sjiy`
  (host-only) → `bd-ib-o35rcx` closes on S3's journaled evidence.
- `bd-ib-j4clfi` (mutex pid-reuse hardening): maintainer-directed
  ADJACENT follow-up — rescope to the slot-file structure, promote
  ready, dispatch (may pair with n7ce4n under the cap; modules are
  disjoint but verify at dispatch).
- Backlog (flagged for promotion rounds): `bd-ib-kttyks`,
  `bd-ib-gbu3k6`, `bd-ib-efjsb4`, `bd-ib-imzx24`, `bd-ib-eha3wh`
  (check the rop-sweep track's claim first), `bd-ib-blk3` (apparmor,
  host-only), `bd-ib-81l0` (reconcile valve bare-fabro — same class as
  3zek, unfixed on that surface).

## Standing operating rules (post-parallelism edition)

1. **Serialization is RETIRED.** Concurrency is governed by the shipped
   `host_dispatch_cap` (2). Do not hand-serialize; do not bypass the
   guard; raising the cap is config-only and should follow
   observed-safe operation.
2. **Refresh-and-verify before EVERY dispatch until `bd-ib-n7ce4n`
   lands** (release contains merge → `claude plugin update ... --scope
   project` in BOTH roots → cache id == release sha prefix → exact
   module marker → invoke from the new cache root). Verified commands
   in n7ce4n's notes. Beware the release-branch propagation lag (a
   refresh can land one release behind — re-check the `release` branch
   and re-run; it happened tonight).
3. **Argv-proven container ownership** before ANY container action;
   ride foreign runs untouched. Exit 137 is ambiguous; outcomes from
   artifacts (PR/journal/ledger), never exit codes or absence from
   `fabro ps`.
4. **Live probes cover EVERY acceptance criterion incl. negatives**
   (rule 8). Tonight's failed negative probe is the standing proof of
   why.
5. **Parked (`blocked`) runs**: first-class outcome since PR #921; they
   free capacity and never count toward the cap. Operator answer path:
   `echo "<KEY>" | fabro attach <run>` for the R/I/A interview, then
   `fabro steer <run> "<guidance>"` once resumed (steer is refused
   while blocked). A dead dispatcher's run needs operator-owned
   post-run (merge confirm → ledger disposition; mind `bd-ib-81l0` on
   the reconcile valve).
6. **Never background a probe/dispatch with a kill-timeout** — a
   SIGTERMed dispatcher orphans its run (happened once tonight; the
   `run_in_background` no-timeout path is the safe shape). Never use
   an inner `&` inside a backgrounded launcher.
7. **Every blocking gate names a performable remedy**; never reword an
   item to dodge a guard (inline negation declaration or the valve
   once `bd-ib-imzx24` lands).

## Epic-close preconditions (recorded on `bd-ib-cvgjop`)

1. One-shot livespec doctor LLM objective+subjective pass (deferred at
   v046 — deferred, not dropped; v047 ratification kept it deferred).
2. Journaled live evidence for every behavior-bearing drain item
   (satisfied for everything closed so far; keep the standard).

## Coordination channels

- Track journal (append milestones; questions with a recommendation):
  `/data/projects/livespec/tmp/factory-success-rate-remediation-supervisor/status.log`
- Fleet coordination (material factory moves, `date -u` stamps):
  `/data/projects/livespec/tmp/fleet-pin-propagation-supervisor/status.log`

## Next action (in order)

1. Rescope + promote `bd-ib-j4clfi`; refresh-and-verify to the release
   carrying PR #921 (≥0.46.8); dispatch `bd-ib-n7ce4n` (and pair
   j4clfi under the cap if file-disjointness holds).
2. `bd-ib-fe574e` (S2) after n7ce4n lands and a refresh; then S3
   `bd-ib-p3sjiy` host-only; close `bd-ib-o35rcx` on S3's evidence.
3. Promotion round for the backlog items with the supervisor.
4. When the epic's tracked items are closed and both epic-close
   preconditions hold, close `bd-ib-cvgjop` and archive this thread
   (`git mv plan/factory-success-rate-remediation/
   plan/archive/factory-success-rate-remediation/`).
