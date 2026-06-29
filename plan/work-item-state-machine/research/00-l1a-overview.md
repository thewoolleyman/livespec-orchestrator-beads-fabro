# L1a — overview and read-first chain

This is the `livespec-orchestrator-beads-fabro` (L1a) track of the
fleet-wide **work-item-lifecycle** epic — the deterministic work-item
state machine. L1a consumes the L0 runtime artifact and realizes the
orchestrator-side contract + code: the Dispatcher valves + per-repo WIP
cap, the beads custom-status encoding, lane emission, rank ordering, and
the `rebalance-ranks` command.

- **Ledger anchor (this repo's tenant):** epic **`bd-ib-vvrxcb`**
  (`livespec-orch-beads-fabro` beads tenant).
- **Fleet anchor (prose reference, NOT a typed cross-tenant
  `depends_on`):** `livespec-35s3zo` in the livespec core tenant
  (decisions 41/44/45 — a cross-tenant id would dangle in the flat
  same-tenant id list and pollute the `blocked:dependency` derivation).
- **L0 dependency (SATISFIED):** `livespec-runtime` **v0.5.0** (released;
  tag `dda6a40`) — the artifact this track vendors
  (`livespec_runtime.work_items.{types,lifecycle,rank}`).

## The reframe (load-bearing finding)

This redesign is **overwhelmingly a `livespec-runtime` + orchestrator
change; livespec CORE's own spec is barely touched** (decision 44).
CORE's `SPECIFICATION/` explicitly delegates the entire lifecycle /
schema / Dispatcher / acceptance surface to the orchestrators as
NON-normative. So the L1a contract lands in **THIS repo's
`SPECIFICATION/contracts.md`**, not in CORE. The epic stays *anchored* in
core (prose ref `livespec-35s3zo`), but core is the anchor, not the work
site.

## Read-first chain (cold-start)

Read in order, then execute the next action in `../handoff.md`:

1. **This file** — the slice, the anchor, the reframe.
2. `01-spec-deltas.md` — the exact `SPECIFICATION/contracts.md` deltas
   (the propose-change payload, human-readable) + the scenarios + the
   heading-coverage reasoning. The `revise` gate ratifies this
   (AUTO-RATIFY — design LOCKED, decisions 1-46).
3. `02-propose-change-findings.json` — the ready-to-feed
   `/livespec:propose-change` findings payload for `01`.
4. `03-code-slices.md` — the code-slice breakdown. The `groom` gate cuts
   this into ready children of `bd-ib-vvrxcb` (AUTO-CUT).
5. Cross-repo design of record (already on disk, authoritative):
   - `/data/projects/livespec/plan/work-item-state-machine/research/02-design.md`
     (§2 states, §3 `lane_of`, §4 valves, §5 `rank`, §6 schema)
   - `/data/projects/livespec/plan/work-item-state-machine/research/03-decision-log.md`
     (decisions 1-46; authoritative on any conflict)
   - `/data/projects/livespec/plan/work-item-state-machine/research/04-slice-plan.md`
     (the "L1a — livespec-orchestrator-beads-fabro" section)
   - L0 worked example (full propose-change→revise→groom→implement→release):
     `/data/projects/livespec-runtime/plan/work-item-state-machine/`

## The L1a slice (what lands in this repo)

**Spec** (propose-change → `SPECIFICATION/contracts.md`; see `01`):
- `## Work-item beads-issue mapping` — the 7-state `status` maps to **5
  custom statuses** (`backlog`, `pending-approval`, `ready:active`,
  `active:wip`, `acceptance:wip`) + **2 built-in reuses** (`blocked`
  name-matched; `done`→`closed`); per-tenant custom-status registration;
  the **2-step `append_work_item`** (`bd create` lands `open`, then `bd
  update --status <state>`); `rank` → `metadata.rank` (legacy lines read
  the shared bottom-sentinel); `priority` dropped as a logical field;
  `admission_policy`/`acceptance_policy`/`blocked_reason` → labels;
  `assignee` native + the `active ⟹ assignee` invariant.
- new `## Dispatcher admission, WIP cap, and post-merge acceptance` — the
  admission valve (`admission_policy` replaces the `host-only` /
  `human-gated` text markers; the Dispatcher is the sole enforcer, sets
  `assignee` on `admit`), the **per-repo WIP cap** (`.livespec.jsonc`,
  default 5), and **post-merge acceptance** (`complete` = merge-on-green
  → `acceptance`; `accept` = post-ship confirm per `acceptance_policy`;
  `reject` = revert/fix-forward). `just check` stays the hard pre-merge
  floor.
- `#### list-work-items` — emit flat `lane` + `lane_reason` (consume the
  runtime's `lane_of`, never re-derive) + the auto-emitted new fields;
  filters track the new lane vocabulary.
- `#### next` — rank by `rank` then `id`; the old `priority → origin →
  captured_at` heuristic retired.
- `### Open realization choices` — RESOLVED: `needs-regroom` is a bounce
  to the `backlog` state (decision 32), not a label-vs-status open
  question; the groom front-end is its own skill (already shipped).

**Code** (this repo; gates on the L0 release — satisfied; see `03`):
re-vendor `livespec_runtime` v0.5.0; shrink `_cross_repo.py` (lifecycle
logic moves to the runtime; inject status-lookups; keep
`load_manifest`/`parse_entry`); custom-status registration (bootstrap) +
2-step create→update + `done↔closed` in `store.py`/`_beads_client.py`;
Dispatcher WIP + valves + post-merge acceptance; `lane`/`lane_reason`
emission; `next` rank order; the new `rebalance-ranks` command (+ a
legacy-seed entry path for L2's backfill); doctor checks
(non-sentinel-`rank`, rank-key-length warning, `active⟹assignee`,
`blocked⟹reason`).

**Gate:** cut a `livespec-orchestrator-beads-fabro` release — the
artifact the L2 migration + console consume.

## Autonomy posture (this track)

The design is LOCKED (decisions 1-46). Per the track kickoff, this track
**AUTO-PROCEEDS** through its `revise` (ratify) and `groom` (cut) gates
per the locked design — it does NOT pause for maintainer approval. It
halts + reports ONLY on a genuine blocker or a new decision the design
does not resolve. Discipline is non-negotiable: worktree → PR →
rebase-merge; `mise exec -- git`; never `--no-verify`; halt + report on
any hook failure; product `.py` follows red-green-replay; co-edit
`tests/heading-coverage.json` for any `## `-heading change.

## The live-tenant migration is L2, not here

L1a ships the CODE (custom-status registration bootstrap, the
`rebalance-ranks` command + its legacy-seed backfill path, the 2-step
append) but does NOT migrate this tenant's live data. The epic + its
children are filed under the CURRENT pre-migration schema (status=open,
priority, no rank); the 7-state shape + `rank` backfill land at the L2
migration (decisions 37/46), driven after the L1 releases.
