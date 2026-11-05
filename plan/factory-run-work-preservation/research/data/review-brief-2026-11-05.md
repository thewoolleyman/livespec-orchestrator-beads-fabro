# Independent review brief: factory run-work preservation, chosen direction (2026-11-05)

You are an independent, adversarial, READ-ONLY reviewer. You had no part in this design. Do not edit any file except your own
output file named below. Do not run `git push`, `bd` writes, `gh` writes, `fabro` or `kubectl` mutations, or anything that
changes shared state.

## The problem

Factory runs in this repository (`/data/projects/livespec-orchestrator-beads-fabro`) keep losing committed work when a run
ends without merging: a wall-budget cancel, a stall-watchdog cancel, a restart cancel, a cancel outside the Dispatcher, a
Fabro server crash, or an operator `fabro rm -f`. Background and measured inventory:

- `plan/factory-run-work-preservation/research/001-charter-and-problem-2026-11-04.md`
- `plan/factory-run-work-preservation/research/002-preservation-decision-options-2026-11-04.md`
- `plan/factory-run-work-preservation/research/003-best-practices-research-synthesis-2026-11-04.md` (an earlier Astra + Fable
  research pass; its section 5 is SUPERSEDED)

## What the maintainer chose (verbatim)

> I like this direction. It prioritizes simplicity. And I am fine accepting the loss of a single node if the entire server
> crashes or the run is cancelled.

Simplicity is the governing value. No Fabro or Fabro-fork change is wanted.

## What to review

The design, as written by the plan session, lives in a worktree that is not yet merged:

- Design note: `/home/ubuntu/.worktrees/livespec-orchestrator-beads-fabro/plan-frwp-direction/plan/factory-run-work-preservation/research/004-chosen-direction-preserve-on-progress-2026-11-05.md`
- Spec proposal (four findings, Scenarios 314-317, plus a credential-clause amendment):
  `/home/ubuntu/.worktrees/livespec-orchestrator-beads-fabro/plan-frwp-direction/SPECIFICATION/proposed_changes/factory-run-work-preserved-on-progress.md`
- The four ledger work items that carry it (descriptions with their Definitions of Done):
  `/data/projects/livespec-orchestrator-beads-fabro/tmp/frwp-review/children-2026-11-05.md`

Source you will want to check claims against:

- Workflow graph: `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro` and `workflow.toml` (note the existing
  `needs_human` preservation script, `[run.run_branch] push = false`, `[run.checkpoint]`).
- Spec: `SPECIFICATION/contracts.md` paragraphs "Publication is mechanically confined to the scripted publication stages",
  "A tree that nothing else carries is published to a preservation ref", "A janitor-green run that a factory restart or an
  outside cancel ends is published to a preservation ref", "Recovery from the failed run's preserved work".
- Dispatcher: `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/` (destroy call sites, `_dispatcher_preserved_tree_publish.py`,
  `_dispatcher_run_wall_budget_watch.py`) and `dev-tooling/checks/fabro_port_seam.py`.
- Fabro fork (serving lineage): `/home/ubuntu/.worktrees/fabro/carrier-candidate-registered-20261023/`, especially
  `lib/components/fabro-petri/src/checkpoint.rs`, `lib/components/fabro-petri/src/hooks.rs`,
  `lib/apps/fabro-cli/src/commands/run/publish.rs`, `lib/components/fabro-petri/src/source.rs`, and Fabro's run-hook docs.
- An interim reference script that already applies two of the guards:
  `/tmp/claude-1000/-data-projects-livespec-orchestrator-beads-fabro/c23be22c-a604-40c4-bd9c-3107b5db4a76/scratchpad/preserve_runs.sh`

Context you should know: the maintainer has directed a REVERT of the split red/green implement graph (red, commit_red, green,
commit_green) back to a single `implement` node with its detached commit runner. Review against the single-node graph.

## Questions to answer

1. **Holes.** Which run endings or states still lose more than the one node visit in progress? Be concrete: name the node, the
   ending, and the sequence.
2. **Correctness of the preserve step.** Is "push the run branch tip after every node visit that moved it; fast-forward the ref
   it descends from, otherwise open a `<run-id>-<sha12>` sibling; never force" correct and implementable inside a Fabro
   command node or run hook as they exist today, without a Fabro change? Does the engine checkpoint happen before or after the
   point where the step would run? Can a command node or run hook reach a push credential that the confinement clause and the
   in-flight credential-withdrawal items (bd-ib-w64kr3, bd-ib-sgnfom) allow? Is a command node after each agent node or one
   `stage_complete` run hook the better mechanism, and why?
3. **Over-engineering.** Measured against the maintainer's "prioritizes simplicity", what in the four findings and four work
   items is unnecessary, and what is the smallest design that still meets the plan's Definition of Done (in the epic,
   summarized in note 004 section 5)?
4. **Spec quality.** Is any proposed clause ambiguous, contradictory with existing text, or untestable? Is any work item's
   Definition of Done not gradeable, or mis-scoped?
5. **The big picture.** Anything the design gets wrong that the questions above do not cover.

Verify every claim you make against source and cite file and line. Mark anything you could not verify as UNVERIFIED.

## Output

Write a ranked list of findings (most severe first), each with: the claim, the evidence with citations, and a concrete
recommendation. Then a short overall verdict. Write it to the output file your launch prompt names, and end the file with
the single line `REVIEW-COMPLETE`.
