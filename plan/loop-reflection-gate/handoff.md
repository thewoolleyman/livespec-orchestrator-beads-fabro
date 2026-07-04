# loop-reflection-gate — handoff

Thread state: **LIVE** — opened 2026-07-04 to drive the
reflection-gate's remaining work; resequenced SPEC-FIRST later the
same day after a plan-accuracy review found the original next action
(groom the consumer item directly) skipped the spec lane for behavior
the spec owns. The spec-first gate AND the `.10` update pass are both
DONE: `/livespec:revise` landed SPECIFICATION v030 (2026-07-04,
accepting both proposals this thread owned), and the `.10` update pass
(2026-07-04) paired the impl item to the landed contract
(`spec_commitment_hint` + notes/description now cite Scenarios 39–40;
`origin:freeform` stamped). The thread advances to GROOMING `.10` TO
those accepted clauses.

Resume command:
`/livespec-orchestrator-beads-fabro:plan loop-reflection-gate`

A fresh session should read THIS file, then the read-first chain
below, and can then execute the next action without consulting chat
history.

## Purpose

The reflection-gate epic's built halves are landed and closed: the
mechanical loop-exit reflection stage, the telemetry pipeline
(enrich/scrub + receive planes), the out-of-band LLM reflector with
dedup issue-filing, and the lessons PROPOSER (`GitPrLessonsProposer`).
What remains is the CONSUMER half of the lessons loop plus
operational hardening. This thread owns sequencing, grooming, and
dispatch of that remainder — spec contract first, implementation TO
the accepted clauses (the `bd-ib-umno37` / SPECIFICATION v024
precedent).

## Epic anchor

Epic `livespec-impl-beads-29f` (this repo's tenant) — "Reflection
gate realization — Honeycomb-backed eval/audit loop for the
dispatcher". Its eight original children are complete; the epic stays
OPEN because this thread added a ninth child (`.10`, below).

Anchor deviation, consciously accepted: this thread ADOPTED the
existing implementation epic as its anchor instead of filing a
dedicated planning epic through `capture-work-item` (the letter of
contracts.md §"The `plan` front-end"). Consequence: the thread
archives exactly when the real remaining work closes, which is the
behavior this thread wants; revisit only if the thread outlives the
epic's scope.

Status is DERIVED, never stored here — verify live via the
`list-work-items` operation
(`/livespec-orchestrator-beads-fabro:list-work-items --json`), or the
equivalent raw read from the repo root:

```bash
cd /data/projects/livespec-orchestrator-beads-fabro
/data/projects/1password-env-wrapper/with-livespec-env.sh \
  bd show livespec-impl-beads-29f livespec-impl-beads-29f.10 bd-ib-umno37 --json
```

## Work this thread drives

- `livespec-impl-beads-29f.10` (backlog) — Lessons brief-injection
  consumer (epic decision 7). The proposer half opens the
  ratification PR; NO code reads the merged
  `loop-reflection-gate/lessons.md` yet. Its spec contract LANDED in
  SPECIFICATION v030: `contracts.md` §"Dispatch-brief lessons
  injection" plus Scenarios 39–40 in `scenarios.md`. The item is now
  PAIRED to that contract (`spec_commitment_hint:
  lessons-brief-injection-consumer` — surfaced on the beads-native
  record as `spec_id`; its notes + description cite the landed clauses;
  `origin:freeform` stamped) and awaits grooming TO those accepted
  clauses.
- `bd-ib-umno37` (ready) — post-verdict fail-open stages (cost
  gate, reflection, calibration, self-update canary) ride the ambient
  `GH_TOKEN` instead of the provider accessor; wrap their runners so
  first-class remint holds across the whole dispatch lifetime. Its
  spec contract already landed (SPECIFICATION v024 §"Self-contained
  plugin dispatch"). Independent hardening; no sequencing coupling to
  `.10`; it is already `ready`, so the factory drains it on its own —
  this thread owes it nothing.
- Cross-tenant, READ-ONLY context: `livespec-dev-tooling-e60`
  (livespec-dev-tooling tenant) — the observability umbrella that
  consumes this pipeline's enriched telemetry. This thread reads its
  state for coordination only; writes belong to that tenant's own
  sessions.

## Read-first chain

All paths below are repo-root-relative (from
`/data/projects/livespec-orchestrator-beads-fabro/`), NOT relative to
this handoff's directory — the `loop-reflection-gate/` entries live at
the repo TOP LEVEL, not under `plan/`.

1. `SPECIFICATION/contracts.md` §"Dispatch-brief lessons injection"
   and `SPECIFICATION/scenarios.md` Scenarios 39–40 — the LANDED spec
   contract for the injection consumer (clauses + scenarios). The
   accept record (decision + rationale + resulting files) is
   `SPECIFICATION/history/v030/proposed_changes/lessons-brief-injection-revision.md`;
   the impl-followup commitment `lessons-brief-injection-consumer`
   pairing `.10` is the front-matter
   `spec_commitments.impl_followups[].id_hint` of the paired original
   proposal
   `SPECIFICATION/history/v030/proposed_changes/lessons-brief-injection.md`.
2. `loop-reflection-gate/best-practices-and-design.md` — the gate's
   design-of-record and the epic's ratified brainstorm decisions.
3. `loop-reflection-gate/lessons.md` — the human-ratification
   contract (proposal → PR → merge) the injection consumer must
   honor: only merged content ever injects.

## Next action

The spec-first gate AND the `.10` update pass are both complete:

- `/livespec:revise` landed SPECIFICATION v030 (2026-07-04), accepting
  BOTH proposals this thread owned: `lessons-brief-injection` →
  `contracts.md` §"Dispatch-brief lessons injection" + Scenarios 39
  (ratified lesson injects) and 40 (unratified / absent / unmerged /
  unreadable never alter briefs); `claude-fable-5-critique` → BCP14
  restatement of the no-root-research-tree invariant in `contracts.md`
  §"The `plan/<topic>/` thread store" + Scenario 41.
- The `.10` update pass (2026-07-04) paired
  `livespec-impl-beads-29f.10` to the landed contract:
  `spec_commitment_hint: lessons-brief-injection-consumer`, its notes +
  description now cite `contracts.md` §"Dispatch-brief lessons
  injection" and Scenarios 39–40, and the missing `origin:freeform`
  label is stamped. The epic-description sketch no longer stands in for
  the contract.

The out-of-scope `orchestrate-plan-surfaces-unarchived-plan-threads`
proposal remains pending, untouched, for its own thread (it still
claims a Scenario 39 provisionally — that renumbers when IT lands,
since 39–41 are now taken).

**The next action is to groom `.10`** via
`/livespec-orchestrator-beads-fabro:groom livespec-impl-beads-29f.10`.
Groom TO the landed clauses — Scenarios 39–40 are the authoritative
acceptance. Groomed slices land at `pending-approval`; the maintainer's
approval is the `pending-approval → ready` transition — slices are NOT
dispatchable straight out of grooming.

Scope the grooming pass to `.10` ALONE: do NOT dispatch (that is the
sequenced later step below), and do NOT touch `bd-ib-umno37` or any
sibling item beyond opportunistic origin-label hygiene. One action per
pass keeps the thread auditable.

Then, in a later invocation of this thread:

1. **Dispatch factory-side** — once the maintainer approves the groomed
   `.10` slices to `ready`, the Dispatcher drains them (or an operator
   runs `orchestrate`); never inline in a planning session.

## Hygiene and coordination notes

- `bd-ib-umno37` is now at status `ready` and its `ready` label
  agrees — the earlier pre-lifecycle STATUS-vs-label discrepancy has
  resolved, so the backlog-retriage caveat this note once carried is
  obsolete. It is independent hardening the factory drains on its own;
  no action owed by this thread.
- Sibling origin-labeling is inconsistent (`.8` and `.10` carry
  `origin:freeform`, `.4` carries none); fix opportunistically when an
  item is next written, not as standalone churn.

## Close-out condition

When `livespec-impl-beads-29f.10` (and any slices groomed from it)
land and close, and epic `livespec-impl-beads-29f` closes, archive
this thread via a docs-only PR
(`git mv plan/loop-reflection-gate/ plan/archive/loop-reflection-gate/`)
with a final handoff note recording the outcome.

## Binding constraints

- Repo mutations: worktree → PR → rebase-merge; worktrees only under
  `~/.worktrees/livespec-orchestrator-beads-fabro/<branch>`; always
  `mise exec -- git …`; never `--no-verify`.
- Beads only via the wrapper
  `/data/projects/1password-env-wrapper/with-livespec-env.sh`;
  secrets probe-only; new items file at lifecycle status `backlog`.
- The `loop-reflection-gate/` paths are LOAD-BEARING (see
  `loop-reflection-gate/CLAUDE.md`): the reflector's default lessons
  path and the telemetry modules' design-of-record citations point
  there — never move or archive that directory without a coordinated
  code change.
