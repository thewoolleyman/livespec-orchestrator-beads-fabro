# Factory run work preservation: measured facts (2026-11-04)

These facts were measured from the code on master, with file:line citations kept in the plan's research note.

## The system

- **The factory.** A "dark software factory" built on the Fabro workflow engine. The fork is at /data/projects/fabro. It serves through the Petri executor, whose fork is at /data/projects/petri.
- **The Dispatcher.** Host-side Python in /data/projects/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/. It admits work items from a beads/Dolt ledger and launches Fabro runs of the `implement-work-item` workflow graph (.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro). It watches those runs and ends them.
- **Where runs execute.** Each run works in a sandbox, which is a Docker container or, on the newer backend, a Kubernetes pod. The sandbox holds a git clone of the target repository.
- **How work gets committed.** Agent nodes (implement, fix, review_fix) commit with the repository hooks running. The engine also makes a hookless checkpoint commit on a local branch `fabro/run/<id>` after every node attempt.
- **Pushing is off.** `run_branch.push` and `meta_branch.push` are both false (workflow.toml:432-438), so nothing the engine checkpoints is pushed.
- **Runs are long.** A run takes up to 6 hours against the whole-run wall budget, going through dod_gate, implement, janitor, publish_draft, review, review_fix, fix laps, pr_refresh, pr, and proof.

## What survives today

- **needs_human is the only ending that pushes the tree.** That command node in the workflow graph makes a hookless commit of the current tree and pushes it to `refs/heads/needs-human/<id>` using a freshly minted GitHub App token. Origin now holds 420 such refs, and no rule ever removes them.
- **One host-side writer covers a failed engine checkpoint (Scenario 183).** It reads the run's changed files from the Fabro server (`GET /api/v1/runs/<id>/files`, served from the live sandbox) and publishes them to `refs/livespec/preserved-publish/<item>/<sha>` through the GitHub Git Data API, with no git push and no hook. The base commit comes from the host-local journal. These refs are write-once; there are 197 on origin and no retention rule.
- **The "preserve-by-reference pointer" holds no bytes.** It is a ledger comment holding paths, sizes and sha256 digests of the per-stage `diff.patch` artifacts on the factory, plus a `fabro dump` command to fetch them later. Each per-stage diff is the checkpoint against its PARENT, so already-committed work never appears in it. In the incident below it held 78 bytes.
- **`fabro rm -f` deletes everything.** It cancels the run with a 5 s grace, prunes the sandbox, and deletes the run directory, the run records, the checkpoint records, the patch blobs and the artifact store.

## How runs end, and what each ending keeps

- **Whole-run wall budget (6 h):** writes the pointer, then runs `fabro rm -f`. The tree is lost immediately. This is the incident.
- **Stall watchdog:** cancels through the server API and preserves nothing. The tree is lost when the sandbox is reclaimed.
- **Stale-item reap:** runs `fabro rm -f` with nothing preserved first.
- **Orphan reconcile:** writes the export pointer and reads it back, then abandons, cancels, or as a last resort runs `rm -f`.
- **A cancel the Dispatcher did not issue** (operator, server restart): writes only a comment, so the tree is lost.
- **Engine terminal failures** (non_converged caps, dead_implementer): write a pointer only.
- **publish_draft rebase conflict:** routes to needs_human, which pushes the tree.
- **Docker sandbox container reclaim:** runs `docker rm -f` on any container whose run is terminal, with no gate on the item's status.
- **Fabro server restart, crash, operator `fabro rm`:** happen entirely outside the Dispatcher.
- **cancel-for-restart (ratified, not built):** publishes a janitor-green run's tree to preserved-publish before it cancels.

## Chokepoints

At the transport level every Dispatcher engine call goes through a facade. Every removal goes through `FabroPort.rm` and every cancel through `FabroHttpPort.cancel`. Nothing at that layer makes preservation come first.

There are 9 destructive call sites in total: 5 rm, 2 cancel, 1 abandon, and 1 docker rm. Only 2 of them export first.

## Constraints

- **Credential confinement is ratified** (spec contracts.md "Publication is mechanically confined to the scripted publication stages").
  - Agent stages must hold NO publication-capable credential.
  - Only the command stages publish_draft, pr_refresh and pr may publish, and only in their publication steps.
  - A command node that preserves a run's work, such as needs_human, "keeps the credentials its own contract requires".
  - The broker may write only pull-request comments and proof assets.
  - Today every stage still has the credential. Items bd-ib-sgnfom and bd-ib-w64kr3 will withdraw it.
- **Kubernetes copy-out does not work.** `fabro sandbox cp/ssh` fail with "plugin response transport closed", so a cancel-time copy-out of the sandbox cannot run there. One tree survived only because an operator copied git objects out through the node.
- **Petri behaviour on endings.** Petri calls `finalize_run` (the cumulative base-to-last-checkpoint diff) for failed and cancelled runs, but not on a restart exit. Cancelled node attempts are not checkpointed.
- **History gets rewritten.** pr_refresh and publish_draft rebase, so progress refs need a unique name per push or a forced update.
- **The server offers hooks.** Fabro `[[run.hooks]]` provides `stage_complete`, `stage_failed` and `run_failed` events (`run_failed` does not fire on cancel), plus `sandbox_cleanup`. None is used today.

## The incident

On 2026-11-04, run 01M6KBH30NJA of work item bd-ib-yuwftp hit the 21600 s budget. It had done two review rounds, review_fix, and three fix laps. Its pointer held a 78-byte diff, then `fabro rm -f` removed the run, and about 6 hours of work were lost.

The pattern so far has been one preservation patch per cancel path, so any path nobody remembered stays a loss.

## Options already on the table (add others)

- **(a)** Preserve at cancel or terminal time through ONE chokepoint that every cancel and removal must pass, plus a check that no path bypasses it.
- **(b)** Preserve on progress: every commit-producing stage pushes a preservation ref as it happens, so no cancel path needs to know about preservation.
- **(c)** Both, or a hybrid. Where should the writer live: the dispatcher, the Fabro server, the sandbox, or the workflow graph?
