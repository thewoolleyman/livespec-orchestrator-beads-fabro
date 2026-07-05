# loop-reflection-gate — handoff

Thread state: **LIVE** — opened 2026-07-04 to drive the
reflection-gate's remaining work; resequenced SPEC-FIRST later that day
after a plan-accuracy review found the original next action (groom the
consumer item directly) skipped the spec lane for behavior the spec
owns. Spec-first gate, `.10` update, and grooming are all DONE:
`/livespec:revise` landed SPECIFICATION v030 (2026-07-04); the `.10`
update paired the impl item to the landed contract; and grooming
(2026-07-05) decomposed `.10` into two factory slices (S1 reader → S2
inject) and regroomed the original out. The thread advances to
DISPATCHING that groomed factory work.

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
dispatcher". Its eight original children are complete; the ninth child
`.10` was groomed into two slices (S1 `bd-ib-nznswb`, S2
`bd-ib-zwl7w3`, both linked under the epic) and regroomed out. The epic
stays OPEN until those two slices land and close.

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
  bd show livespec-impl-beads-29f bd-ib-nznswb bd-ib-zwl7w3 bd-ib-umno37 --json
```

## Work this thread drives

- `bd-ib-nznswb` — **Lessons consumer S1: ratified-lessons reader**
  (layer 0). A pure extractor over the committed
  `loop-reflection-gate/lessons.md` (extract ratified text under
  `## Lessons`; return empty for absent / placeholder-only /
  unreadable — fail-open). Child of epic `livespec-impl-beads-29f`;
  `origin:freeform`. Status is DERIVED — as of grooming it auto-readied
  to `ready` (see Next action). No blocking dependency (the epic edge is
  parent-child, which the store does not treat as blocking).
- `bd-ib-zwl7w3` — **Lessons consumer S2: inject into the dispatch
  brief** (layer 1). Wires the S1 reader into `render_goal`
  (`_dispatcher_plan.py`), reading lessons from the DISPATCHER'S OWN
  working tree (not `render_goal`'s target `repo`) and injecting a
  delimited lessons section into the pre-escape assembly; brief is
  byte-identical when there are no ratified lessons. Child of the epic;
  `origin:freeform`; carries `spec_commitment_hint:
  lessons-brief-injection-consumer` (the v030 pairing, moved here from
  the regroomed-out `.10`). Has a `blocks` edge to S1, so it stays
  gated until S1 closes. Acceptance: Scenarios 39–40.
- `bd-ib-umno37` (ready) — post-verdict fail-open stages (cost
  gate, reflection, calibration, self-update canary) ride the ambient
  `GH_TOKEN` instead of the provider accessor; wrap their runners so
  first-class remint holds across the whole dispatch lifetime. Its
  spec contract already landed (SPECIFICATION v024 §"Self-contained
  plugin dispatch"). Independent hardening; no sequencing coupling to
  the consumer slices; it is already `ready`, so the factory drains it
  on its own — this thread owes it nothing.
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
   contract for the injection consumer (clauses + scenarios), the
   authoritative acceptance both slices implement TO. The accept record
   (decision + rationale + resulting files) is
   `SPECIFICATION/history/v030/proposed_changes/lessons-brief-injection-revision.md`;
   the impl-followup commitment `lessons-brief-injection-consumer`
   (now paired on S2 `bd-ib-zwl7w3`) is the front-matter
   `spec_commitments.impl_followups[].id_hint` of the paired original
   proposal
   `SPECIFICATION/history/v030/proposed_changes/lessons-brief-injection.md`.
2. `loop-reflection-gate/best-practices-and-design.md` — the gate's
   design-of-record and the epic's ratified brainstorm decisions.
3. `loop-reflection-gate/lessons.md` — the human-ratification
   contract (proposal → PR → merge) the injection consumer must
   honor: only merged content ever injects.

## Next action

Grooming is complete. `.10` was decomposed (2026-07-05) into two
factory slices, both children of the epic:

- **S1 `bd-ib-nznswb`** (ratified-lessons reader) — `ready`.
- **S2 `bd-ib-zwl7w3`** (inject into brief) — `pending-approval`,
  blocked by a `blocks` edge to S1; carries the v030
  `spec_commitment_hint`.

Note on the ready gate: the earlier claim that groomed slices always
land at `pending-approval` for a maintainer approval was too broad. This
repo runs `admission:auto`, and intake-DoR (`intake_dor.py`) auto-promotes
a DEPENDENCY-FREE auto-admission slice straight to `ready`. So S1 (no
blocking dep) is `ready` and factory-dispatchable WITHOUT further
approval — the maintainer confirmed 2026-07-05 to leave it ready and keep
the work moving. S2 stayed `pending-approval` because it carries a
blocking dep on S1.

**The next action is to DISPATCH the ready factory work** — never inline
in a planning session. Either the Dispatcher drains `ready` items on its
own, or an operator runs the `orchestrate` operation
(`/livespec-orchestrator-beads-fabro:orchestrate`) to dispatch S1
(`bd-ib-nznswb`) now. Then, in order:

1. **After S1 lands + closes**, its `blocks` edge to S2 resolves. Move
   S2 (`bd-ib-zwl7w3`) `pending-approval → ready` (the maintainer
   approval / re-admission), then dispatch it the same way.
2. **When S1 and S2 both close** (the consumer is built), the epic's
   remaining consumer work is done — proceed to Close-out.

## Hygiene and coordination notes

- `bd-ib-umno37` is at status `ready` and its `ready` label agrees —
  the earlier pre-lifecycle STATUS-vs-label discrepancy resolved. It is
  independent hardening the factory drains on its own; no action owed by
  this thread.
- Origin-labeling: the groomed slices S1/S2 both carry `origin:freeform`.
  Sibling `.4` still carries none; fix opportunistically when it is next
  written, not as standalone churn.

## Close-out condition

When both groomed slices (`bd-ib-nznswb`, `bd-ib-zwl7w3`) land and
close, and epic `livespec-impl-beads-29f` closes, archive this thread
via a docs-only PR
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
