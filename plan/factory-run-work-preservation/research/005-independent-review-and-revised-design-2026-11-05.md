# 005 — Independent review of the chosen direction, and the revised design (2026-11-05)

Session: factory-run-work-preservation plan seat, 2026-11-05. The maintainer asked for "two new reviewers again" after the
direction in note 004 was written up. This note records what they found, which findings were verified and adopted, and the design
that results. **Where this note and note 004 §3 to §6 differ, this note governs.** The maintainer's ruling (note 004 §1) is
unchanged.

## The reviews

Both reviewers were independent and read-only. Each got the same brief (`data/review-brief-2026-11-05.md`) and worked without
seeing the other's output.

- **Astra:** Codex CLI 0.166.0, `gpt-6-astra`, run in a herdr split pane. Report: `data/review-astra-gpt-6-astra-2026-11-05.md`,
  9 findings.
- **Fable:** Claude Fable 5.1, run as a Claude Code subagent. Report: `data/review-fable-5-1-2026-11-05.md`, 11 findings.

**Shared verdict.** Preserve-on-progress is the right direction and needs no Fabro change. As drafted, though, it could preserve
and seed from a tree that carries no work. Its destroy-time wrapper was also most of its surface while buying little.

## Findings verified by this session and adopted

Each was checked against source before adoption.

1. **The engine resets the run branch onto a detached HEAD.** Both reviewers found this.
   - **Source.** `fabro-petri/src/checkpoint.rs:766-790` (`ensure_repository`) runs `git checkout -q -B <run-branch>` whenever
     `HEAD` is not on the run branch. `:521-537` then commits `--allow-empty`.
   - **Effect.** After a node leaves `HEAD` detached on master, the next checkpoint makes the run branch "master plus an empty
     commit". "Preserve the branch tip, never HEAD" therefore did not close the bd-ib-rhivsm hole. Choosing the "newest ref by
     committer time" would then seed a re-dispatch from a work-free tree.
   - **Adopted.** A tree guard: never preserve a tip whose tree equals the run's base tree or the default branch's tree.
2. **Committer time cannot order captures, and the reference script does force.** Found by Astra.
   - **Source.** The checkpoint is a plain `git commit --allow-empty` with no ordinal (`checkpoint.rs:522-535`).
     `preserve_runs.sh:62` pushes `"+$sha:$ref"`.
   - **Adopted.** Immutable, numbered capture refs `refs/livespec/wip/<item>/<run>/<n>`. Each is created once and never moved.
     There is no ancestry search and no sibling naming. The latest capture is the highest number.
3. **`checkpoint_saved` hooks do not run.** Fable proposed this hook event; Astra disproved it.
   - **Source.** Petri `crates/attractor/steps/src/hooks/mod.rs:451-465` reports `checkpoint_saved` hooks as `unsupported`
     ("Petri writes no checkpoints").
4. **Where to push. Adopted: at the end of the three commit-settle command steps.**
   - **Fable's option.** The single-implement graph the maintainer directed a revert to already has `implement_commit_settle`,
     `fix_commit_settle` and `review_fix_commit_settle` (`e7f5ec757^:workflow.fabro:411, 572, 1807`).
     - Every agent commit goes through the detached commit runner, and those steps settle it. Pushing at their end preserves every
       committed change.
     - It costs three to six pushes a run, adds no node and moves no edge condition.
     - The credential stays in a command step, which the confinement clause can name.
   - **Astra's option.** Two run hooks, `stage_complete` plus `stage_failed`.
   - **Why the settle steps.** A run hook runs in the agent's sandbox environment with no stage identity, so the credential scoping
     being built by bd-ib-w64kr3 and bd-ib-sgnfom has nothing to key on (Astra finding 4, Fable F4). The other nodes' checkpoints
     hold no product state that the broker does not already post. The `needs_human` step is added as a fifth preserving step.
5. **`needs_human` has the same detached-HEAD defect.** Found by Fable (F8).
   - **Source.** `workflow.fabro:2071` pushes `HEAD:$ref` after committing on `HEAD`.
   - **Adopted.** The needs-human commit is built on the run branch tip, under the same tree guard.
6. **The preserve-then-destroy wrapper is unnecessary, and its check was unbuildable.** Found by both.
   - **Recovery already finds refs.** Routing discovers preserved refs by `git ls-remote` on the run id
     (`_dispatcher_recovery_preserved.py:221-248`).
   - **Endings already pass one point.** Every non-green ending passes `_dispatcher_terminal_routing.py:100-160`.
   - **The check could not be built as written.** `fabro_port_seam` confines transport, not callers
     (`dev-tooling/checks/fabro_port_seam.py:19-45`). A caller check keyed on `.cancel(` would also flag thread handles and
     probe-run removals (`_acp_availability_probe_run.py:346`).
   - **Adopted.** One receipt comment where the ending is recorded, plus "could not be determined" as a third outcome. The plan's
     check moves to where it can be built: a repository check that fails a workflow declaring a commit-settling step without the
     preservation.
7. **A failed push leaves more than one visit at risk.** Found by Astra (finding 2).
   - **Adopted.** The bound is stated honestly: preserved through the last *successful* capture.
     - Each failure is recorded in the step's own output and retried at the next capture.
     - The seven-day proof (plan assertion 5) counts a loss caused by a recorded preservation failure separately from a loss the
       design should have prevented.
   - **Not adopted.** Blocking the run on a failed push is heavier and contradicts the ruling's preference for simplicity. The
     maintainer may override this.
8. **Recovery must prove continuation, not just name a ref.** Found by Astra (finding 8).
   - **Adopted.** Scenario 316 gains an end-to-end case: a seed holding a settled implement commit and a later fix commit reaches
     publication in a fresh sandbox through the real gates. The existing published-PR resume precedence is stated explicitly.
9. **The retention cutoff was ungradeable.** Found by both.
   - **Problem.** Nothing records when a paragraph "took effect".
   - **Adopted.** Deletion fires only when the Dispatcher itself closes or accepts an item, and when its ended-run collection
     removes an ended run of a closed item. That collection already acts only on closed items
     (`_dispatcher_ended_run_collection.py:36-72`).
   - **Result.** Items closed before the rule shipped are untouched with no cutoff date, and deletion happens after the run can no
     longer push.
10. **The carrier items still demanded the superseded invariant.** Found by both.
    - **The items.** bd-ib-xdhe5z required "the newest committed tree on origin before every destroy". bd-ib-ofvsr3's Why still
      said "forced".
    - **The plan's own assertions 1 and 5 said the same.** Assertions 1 and 5 promised no loss of committed work at all, which the
      maintainer's ruling gave up for the visit in progress.
    - **Adopted.** All four children re-cut. Plan assertions 1 and 5 are re-worded to the ruling's bound and recorded as a
      carrier-map event; this is reported to the maintainer for objection.
11. **Smaller items.**
    - **Before the run ends (F5).** "Before the next agent turn" gave no deadline for a run that ends at `non_converged` or
      `dead_implementer`. The push now happens inside the preserving step, before the run's next transition or end.
    - **No longer applies (F9.2).** `refresh_repair` does not rebase; the publish stages do. The revised scenarios name no rebasing
      node.
    - **Dropped (F9.3, F9.4).** Receipt obligations that needed run events after `fabro rm` are removed.
    - **Corrected (F10).** With a single `implement` node, the amend happens before the visit's checkpoint, so it rewrites nothing
      that was pushed.

## Not adopted, and why

- **Retire Scenario 306 and supersede bd-ib-adcaa6, bd-ib-vraou4 and bd-ib-ds4yrm (Fable F7).**
  - They belong to plan bd-ib-acrr56, and vraou4 is active. The coordinator ruled that they not be cancelled.
  - Once bd-ib-ofvsr3 ships, a janitor-green head is already on a capture ref, so they may become redundant. That is recorded as a
    deferral, to be reconsidered when ofvsr3 is accepted.
- **Immutable refs mean more refs (Astra).** At three to six per run, deleted at close, that count is acceptable.

## The revised design

1. **Capture.** At the end of each commit-settle step and in `needs_human`, the run branch tip is pushed to
   `refs/livespec/wip/<item>/<run>/<n+1>`.
   - It is skipped when its tree equals the base or default-branch tree, or when it equals capture `<n>`.
   - It is never forced, changes nothing locally, ignores repository hooks and repository git configuration, and uses
     Dispatcher-materialized tooling.
   - It never fails the run; each failure is recorded and retried.
   - A repository check fails a commit-settling step that lacks it.
2. **Receipt.** At every non-merge ending and every absent-run release, the Dispatcher lists the run's capture refs and writes one
   `livespec-preserved-tree` comment: latest capture, none, or could not be determined.
3. **Recovery.** The latest capture counts as preserved work.
   - Preferred over it: a terminal needs-human or preserved-publish ref of the same run.
   - It is preferred over the published head and over every earlier run's refs.
   - Resume keeps its precedence.
4. **Retention.** Refs are deleted when the Dispatcher closes or accepts an item, and when it collects a closed item's ended runs.
   Deleting the existing 617 refs still needs a separate go.

**Dependency.** The commit-settle steps exist only in the single-implement graph the maintainer directed a revert to. bd-ib-ofvsr3
lands after that revert. The credential-withdrawal items must name the preserving steps; riders are recorded on bd-ib-w64kr3 and
bd-ib-sgnfom.

| Plan assertion | Carrier |
|---|---|
| 1 — every ending leaves the last settled tree on a named ref, its id on the ledger | bd-ib-ofvsr3, bd-ib-xdhe5z |
| 2 — a re-dispatch starts from the preserved tree | bd-ib-v6br5b |
| 3 — a check catches a committing step that skips preservation | bd-ib-ofvsr3 |
| 4 — preserved refs are removed by a stated retention rule | bd-ib-efiasj |
| 5 — seven days after release, no ending loses more than the visit in progress, other than through a recorded preservation failure | plan-level proof |
| 6 — research notes, with the chosen direction recorded against them | plan-level proof |
