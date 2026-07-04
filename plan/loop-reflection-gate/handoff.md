# loop-reflection-gate — handoff

Thread state: **LIVE** — opened 2026-07-04 to drive the
reflection-gate's remaining work; resequenced SPEC-FIRST later the
same day after a plan-accuracy review found the original next action
(groom the consumer item directly) skipped the spec lane for behavior
the spec owns.

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
  `loop-reflection-gate/lessons.md` yet. Its spec contract is now the
  PENDING proposed change
  `SPECIFICATION/proposed_changes/lessons-brief-injection.md`
  (front-matter commitment `lessons-brief-injection-consumer`); the
  item implements TO those clauses once revise accepts them.
- `bd-ib-umno37` (backlog) — post-verdict fail-open stages (cost
  gate, reflection, calibration, self-update canary) ride the ambient
  `GH_TOKEN` instead of the provider accessor; wrap their runners so
  first-class remint holds across the whole dispatch lifetime. Its
  spec contract already landed (SPECIFICATION v024 §"Self-contained
  plugin dispatch"). Independent hardening; no sequencing coupling to
  `.10`; dispatches whenever admitted.
- Cross-tenant, READ-ONLY context: `livespec-dev-tooling-e60`
  (livespec-dev-tooling tenant) — the observability umbrella that
  consumes this pipeline's enriched telemetry. This thread reads its
  state for coordination only; writes belong to that tenant's own
  sessions.

## Read-first chain

1. `SPECIFICATION/proposed_changes/lessons-brief-injection.md` — the
   pending spec contract for the injection consumer (clauses +
   scenarios + the impl-followup commitment pairing `.10`).
2. `loop-reflection-gate/best-practices-and-design.md` — the gate's
   design-of-record and the epic's ratified brainstorm decisions.
3. `loop-reflection-gate/lessons.md` — the human-ratification
   contract (proposal → PR → merge) the injection consumer must
   honor: only merged content ever injects.

## Next action

From a fresh worktree (cut per Binding constraints), run
`/livespec:revise`. No `--spec-target` argument is needed (the main
spec root resolves from `.livespec.jsonc`), and no pre-reading of
the queue is needed either: revise itself enumerates and processes
whatever is pending under `SPECIFICATION/proposed_changes/`. This
thread's stake in that queue is the `lessons-brief-injection`
contract and the `claude-fable-5-critique` normative-force
correction it spawned; do not rely on any count of queued proposals
written here (a concurrent session already processed one within
hours of this handoff's first cut). The revise pass MUST co-edit
`tests/heading-coverage.json` for every `## ` heading it adds
(including the new contracts section and the new scenarios, whose
numbers are finalized at revise).

Then, in order, in later invocations of this thread:

1. **Update `.10`** — cite the accepted contracts.md section and the
   landed scenario numbers, pair it to the spec commitment via
   `spec_commitment_hint: lessons-brief-injection-consumer`, and
   stamp its missing `origin:` label (filing hygiene).
2. **Groom `.10`** via
   `/livespec-orchestrator-beads-fabro:groom livespec-impl-beads-29f.10`.
   Groomed slices land at `pending-approval`; the maintainer's
   approval is the `pending-approval → ready` transition — slices are
   NOT dispatchable straight out of grooming.
3. **Dispatch factory-side** — the Dispatcher drains `ready` items
   (or an operator runs `orchestrate`); never inline in a planning
   session.

## Hygiene and coordination notes

- `bd-ib-umno37` carries a stale pre-lifecycle `ready` LABEL while
  its authoritative STATUS is `backlog`; the 7-state lifecycle
  ignores the label. Cleanup belongs to the backlog retriage owned by
  the `lifecycle-front-end-retrofit` thread — do not let the label
  masquerade as an admission.
- Sibling origin-labeling is inconsistent (`.8` carries
  `origin:freeform`, `.4` and `.10` carry none); fix opportunistically
  when an item is next written, not as standalone churn.

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
