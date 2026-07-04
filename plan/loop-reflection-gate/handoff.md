# loop-reflection-gate — handoff

Thread state: **LIVE** — opened 2026-07-04 to drive the
reflection-gate's remaining work, now that the gate's design-of-record
docs live at top-level `loop-reflection-gate/` (moved out of
`research/` under the retire-research-dirs epic `livespec-gt7crt`,
livespec tenant).

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
dispatch of that remainder.

## Epic anchor

Epic `livespec-impl-beads-29f` (this repo's tenant) — "Reflection
gate realization — Honeycomb-backed eval/audit loop for the
dispatcher". Its eight original children are complete; the epic stays
OPEN because this thread added a ninth child (below). Status is
DERIVED, never stored here — verify live:

```bash
cd /data/projects/livespec-orchestrator-beads-fabro
/data/projects/1password-env-wrapper/with-livespec-env.sh \
  bd show livespec-impl-beads-29f livespec-impl-beads-29f.10 bd-ib-umno37 --json
```

## Work this thread drives

- `livespec-impl-beads-29f.10` (backlog) — Lessons brief-injection
  consumer: inject ratified `loop-reflection-gate/lessons.md` content
  into dispatch briefs (epic decision 7). The proposer half opens the
  ratification PR; NO code reads the merged file yet, so a ratified
  lesson has no effect on any brief until this lands.
- `bd-ib-umno37` (backlog) — post-verdict fail-open stages (cost
  gate, reflection, calibration, self-update canary) ride the ambient
  `GH_TOKEN` instead of the provider accessor; wrap their runners so
  first-class remint holds across the whole dispatch lifetime.
- Cross-tenant, READ-ONLY context: `livespec-dev-tooling-e60`
  (livespec-dev-tooling tenant) — the observability umbrella that
  consumes this pipeline's enriched telemetry. This thread reads its
  state for coordination only; writes belong to that tenant's own
  sessions.

## Read-first chain

1. `loop-reflection-gate/best-practices-and-design.md` — the gate's
   design-of-record and the epic's ratified brainstorm decisions.
2. `loop-reflection-gate/lessons.md` — the human-ratification
   contract (proposal → PR → merge) the injection consumer must
   honor: only merged content ever injects.

## Next action

Groom the injection-consumer item via
`/livespec-orchestrator-beads-fabro:groom livespec-impl-beads-29f.10`,
then dispatch the resulting ready slice(s) through the factory.
(`bd-ib-umno37` is independent hardening with no sequencing coupling
to the consumer item; it dispatches whenever admitted.)

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
