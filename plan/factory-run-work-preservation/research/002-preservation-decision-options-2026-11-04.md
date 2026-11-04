# 002 — The preservation decision: what each run ending keeps today, and the options (2026-11-04)

Session: factory-run-work-preservation plan seat, 2026-11-04.

These facts were measured on master `0abc4d379` with the Fabro engine serving `c39bdbded` (the Petri-era fork). They come from two read-only code sweeps, one over the Dispatcher and one over the workflow graph and the engine, plus a spot re-check of the load-bearing lines.

All Dispatcher paths are under `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`. The list of ending paths reuses and extends the one in invariant item bd-ib-xdhe5z, as legacy-coordinator-agent asked.

**This note is the decision brief. The maintainer decides.** The last section is a recommendation, marked as one.

## Notation

- **Committed tree.** The run's newest commit in its sandbox clone, and the files that commit holds.
- **Preserved.** The committed tree is fetchable from a named ref on origin (GitHub).
- **Pointer.** The "preserve-by-reference" ledger comment.
- **Destroy.** Any act that makes the sandbox or the run's server-side record unreadable: `fabro rm -f`, a container or pod delete, a server-side prune.

## 1. What survives each ending today

| # | Ending | Trigger (file:line) | What reaches origin | When the tree is lost |
|---|---|---|---|---|
| 1 | needs_human node | `workflow.fabro:2150-2155` (command node, in the sandbox) | Hookless commit pushed to `refs/heads/needs-human/<id>` through `push_origin` with a freshly minted GitHub App token | Only if the push fails or the 600 s node timeout passes. That leaves the pointer alone. |
| 2 | Failed engine checkpoint (Scenario 183) | `_dispatcher_terminal_preservation.py:78` → `_dispatcher_preserved_tree_publish.py:108` | Host-side Git Data API commit (no push, no hook) on `refs/livespec/preserved-publish/<item>/<sha>`, parented on the base commit. Files come from `GET /runs/<id>/files` (`_fabro_port_http.py:229`). | When a terminal patch was observed instead (pointer only, `_dispatcher_preserved_tree_trigger.py:157-167`), or when the host journal lacks the base row (another host dispatched). |
| 3 | **Run-wall-budget cancel (Scenario 175)** | `_dispatcher_run_wall_budget_watch.py:202-203` | Nothing. The pointer is written, then `port.rm` runs `fabro rm -f`. | **Immediately.** The pointer's own retrieval command is dead the moment the rm runs. This is the bd-ib-yuwftp incident. |
| 4 | Stall-watchdog cancel | `_dispatcher_stall_cancel.py:97` (server cancel, no rm) | Nothing. Status `stalled-no-progress` is not in the pointer statuses. | When the sandbox is reclaimed (row 9) or the run is collected. |
| 5 | Stale-item reap | `_dispatcher_stale_item_reap.py:67` (`rm -f`) | Nothing before the rm. | Immediately. |
| 6 | Orphan reconcile (export-then-reap) | `_dispatcher_reconcile_runs_terminate.py:124` (abandon) → `:138` (cancel) → `:148` (`rm -f`) | The pointer only, read back first. | The `rm -f` fallback loses it at once. The other routes lose it at prune. |
| 7 | A cancel the Dispatcher did not issue (operator, restart) | `_dispatcher_fabro_terminal.py:202` → `_dispatcher_terminal_routing.py:115` | A comment only. | At sandbox reclaim. This is the measured bd-ib-vraou4 loss of bd-ib-uq2ocd run 01M6JSNVH32S. |
| 8 | Engine terminal failure (`non_converged`, `dead_implementer`) | `workflow.fabro:2194-2198`, `:1904-1908` (no push) | The pointer only. | At prune. `non_converged` can hold hours of fix work. |
| 9 | Docker sandbox container reclaim | `_dispatcher_sandbox_container_port.py:142` (`docker rm -f`) | Nothing. There is no item-status gate. | Immediately, and it also removes what `/files` would read. |
| 10 | Ended-run collection | `_dispatcher_ended_run_collection.py:51` (unforced rm) | n/a. This runs only for an item that is closed or done. | By design. |
| 11 | ACP availability probe reap | `_acp_availability_probe_run.py:346` | n/a (no work item). | — |
| 12 | publish_draft rebase conflict | `workflow.fabro:2337` → `refresh_repair` → `needs_human` | Same as row 1. | Same as row 1. |
| 13 | Stale publish-branch reclaim (Scenario 144) | `_dispatcher_publish_branch_preserve.py:127` | The branch tip copied to `preserved-publish` and confirmed before the branch is deleted. | Not lost. |
| 14 | cancel-for-restart (Scenario 306, v294) | Not built. No code hits for `cancel_for_restart` in `.claude-plugin/` or `tests/`. bd-ib-adcaa6 is in flight. | Specified: preserved-publish before cancel, for janitor-green runs only. | Today the restart cancels everything (row 7). |
| 15 | Fabro server restart or crash, an operator `fabro rm`, a pod eviction | Outside the Dispatcher entirely | Nothing. | Whenever it happens. |

## 2. Six measured facts that constrain any design

1. **The pointer holds no bytes, and the per-stage diffs leave out committed work.**
   - Each `stages/<n>-<stage>/diff.patch` is the engine checkpoint diffed against its parent (Fabro `hooks.rs:1150-1180`).
   - When an agent commits during a node, the parent is the agent's own commit, so the patch holds only what was still uncommitted. That is why the incident's `fix@2` patch was 78 bytes.
   - Only `conclusion.diff.patch` (base to last checkpoint, `hooks.rs:1412-1486`) is cumulative, and only when `finalize_run` ran.
   - `fabro rm -f` deletes all of it (Fabro `server.rs:2800-2900`).
2. **Nothing the engine checkpoints is pushed.**
   - The engine makes a hookless checkpoint commit on the local `fabro/run/<id>` branch after every node attempt.
   - The workflow sets `run_branch.push = false` and `meta_branch.push = false` (`workflow.toml:428-438`), so none of it is pushed.
   - Upstream's own durability mechanism is that push. Origin still holds 208 `fabro/run/*` and 62 `fabro/meta/*` refs from earlier configurations.
   - Cancelled node attempts are never checkpointed (Fabro `hooks.rs:1631`).
3. **Cancel-time preservation needs a readable sandbox.**
   - The Scenario 183 writer reads the changed files from the server (`/runs/<id>/files`), and the server serves them from the run's sandbox.
   - On the Kubernetes backend, `fabro sandbox cp/ssh` fails with "plugin response transport closed" (legacy-coordinator-agent, measured 2026-11-04). bd-ib-yuwftp's tree survived only because the kubernetes-sandbox-backend session copied the git objects out through the node.
   - **Unmeasured:** whether `/runs/<id>/files` works on Kubernetes.
4. **There is a transport chokepoint, but no policy chokepoint.**
   - Every engine call goes through the facade, enforced by `dev-tooling/checks/fabro_port_seam.py`. Every removal is `FabroPort.rm` (`_fabro_port.py:243`), and every cancel is `FabroHttpPort.cancel` (`_fabro_port_http.py:262`).
   - There are 9 destructive call sites in all: 5 rm, 2 cancel, 1 abandon, and 1 `docker rm -f` outside the facade.
   - Only 2 of them, the reconcile and the wall budget, export anything first, and neither export carries the tree.
5. **Credential confinement limits who may push** (contracts.md "Publication is mechanically confined to the scripted publication stages", Scenario 202).
   - "A push of any ref to origin" is a publication action.
   - Agent stages may hold no publication-capable credential.
   - Only publish_draft, pr_refresh and pr may publish, and only in their publication steps.
   - A command node that preserves a run's work, such as needs_human, "keeps the credentials its own contract requires".
   - The broker writes only pull-request comments and proof assets.
   - Today every stage still holds the credential. bd-ib-sgnfom and bd-ib-w64kr3 withdraw it.
   - A per-stage push from an agent turn is therefore forbidden. A push from a command node is allowed only under the needs_human sentence, which sits awkwardly beside the three-stage list. A ref write through the broker needs a spec amendment.
6. **Nothing cleans up preservation refs.**
   - Origin holds **420** `refs/heads/needs-human/*` and **197** `refs/livespec/preserved-publish/*` (counted with `git ls-remote origin` on 2026-11-04).
   - `preserved-publish` refs are write-once by contract (contracts.md, stale publish-branch reclaim).
   - Scope searched for a deletion rule: `.claude-plugin/scripts`, `dev-tooling/`, `.github/`, contracts.md and scenarios.md. None was found.
   - History is rewritten by `publish_draft` and `pr_refresh` rebases, and by `commit-red.sh` once the red/green split is wired. So a progress ref needs either a unique name per write or a forced update.

## 3. The options

### (a) Preserve at the terminal through one chokepoint

**What it is.**
- A single `preserve_then_destroy` gate. Every Dispatcher-issued cancel, abandon, rm, container delete and pod delete must pass through it, and it returns a receipt of one of three kinds:
  - the ref and commit id it published;
  - "no committed tree";
  - "not preserved, step X failed".
- The destroy goes ahead only once the receipt is written to the item's ledger.
- The writer is the Scenario 183 Git Data API writer, run host-side with the host `gh` auth.
- `fabro_port_seam` is extended so that a direct `rm`/`cancel` call outside the gate fails the check.
- Externally caused endings (row 7) get a best-effort publish when they are reported, which is bd-ib-vraou4's shape.

**Covers:** rows 3 to 9 and 14, which are every destroy the Dispatcher issues. It is the mechanical form of bd-ib-xdhe5z's enforcement assertion.

**Misses:** row 15, which is any ending the Dispatcher does not issue and whose sandbox is already gone. That includes a server crash, an operator `rm`, a pod eviction, and a Fabro server prune. It also misses any ending where the sandbox cannot be read, which today may be every Kubernetes run (fact 3).

**Costs:**
- One forge write set per ending, which is cheap.
- One ref per ending.
- No new sandbox credential.
- It adds latency to every cancel, bounded by a timeout. Per the bd-ib-xdhe5z assertion, the cancel still proceeds when publication fails.

**In-flight items:** bd-ib-ds4yrm, bd-ib-adcaa6 and bd-ib-vraou4 become the first three callers of the gate. They already reuse that writer, so their work is absorbed, not discarded.

### (b) Preserve on progress

**What it is.** Every commit-producing step makes its tree durable as it happens, so no ending has to know about preservation. There are three candidate writers.

- **(b1) A workflow command node after each commit-producing stage.**
  - Placement: after the settle nodes behind implement, fix and review_fix, plus commit_green once wired. The node pushes hooklessly to `refs/livespec/run-progress/<run-id>`.
  - Costs: about 5 to 30 pushes per run, and new graph nodes in every workflow. The command node needs a credential delivered where no agent can read it once bd-ib-w64kr3 lands. It also needs a spec amendment, because the three-stage publication list does not name it.
  - Misses: commits an agent made inside a node that is cancelled before its settle node runs.
- **(b2) The engine's own checkpoint push.**
  - Placement: turn on `run_branch.push`, pointed at a preservation namespace through a fork change. The engine then pushes `fabro/run/<id>` after every node attempt, from inside the sandbox, with a credential scoped to that one command (Fabro `checkpoint.rs:237-262`).
  - This is upstream's native mechanism. It needs no sandbox copy-out, so it works on Kubernetes, and it keeps working when the Dispatcher host is down.
  - Costs:
    - A fork change, so that a successful run does not also publish the run branch (`hooks.rs:1756`) and so that the ref is namespaced.
    - A spec amendment for an engine-made publication.
    - Proof that no agent-modifiable hook or environment can capture the per-command credential.
    - One push per node attempt, tens per run.
  - Misses: the in-flight attempt. Cancelled attempts are not checkpointed, so an agent's commits made during a long fix node that gets cancelled are lost.
- **(b3) A Dispatcher-side progress mirror.**
  - Placement: the Dispatcher already watches each run's event stream (the stall watchdog). On each `stage_complete`, and on a slow periodic tick while the run is active, it reads `/runs/<id>/files` and republishes the tree through the same Git Data API writer, by moving one mutable ref per run, `refs/livespec/run-progress/<item>/<run-id>`.
  - It needs no sandbox credential and no spec change to credential confinement. It reuses the writer the in-flight items are building.
  - Costs:
    - Forge API load of one blob per changed file per publish. The writer could skip a publish when the head has not moved. The GitHub App installation limit is 5,000 requests an hour, shared fleet-wide.
  - Misses:
    - Kubernetes runs, if `/files` does not work there (unmeasured).
    - Work done after the last mirrored tick.
    - Any span when the Dispatcher's watch loop is not running.
    - It flattens history into one commit on the base, as Scenario 183 already does.

**In-flight items under (b):** adcaa6, vraou4 and ds4yrm become redundant for any run that has a fresh progress ref, but they stay valuable as the final top-up. Under (b3) they share the writer.

### (c) A hybrid of progress preservation and the terminal gate

**What it is.** Progress preservation, from (b2) or (b3), makes the tree durable against endings nobody controls (row 15). The terminal gate from (a) does three things:
- a final top-up before any Dispatcher-issued destroy;
- writing the receipt to the ledger;
- carrying the enforcement check.

The re-dispatch seed (`_dispatcher_recovery_preserved.py:162`) reads the newest of {run-progress ref, preserved-publish ref, needs-human ref}. That also fixes two gaps:
- externally cancelled runs are never "released for recovery" (`_dispatcher_recovery_release.py:88-142`);
- the seed depends on the host-local journal.

**Covers:** every row, including row 15, up to the last progress write.

**Cost:** the sum of the chosen (b) variant and (a), less the shared writer.

### (d) Snapshot or retain the sandbox, without a ref

**What it is.** Set `environment.lifecycle.preserve` or `Retention::Always`, gate the container and pod deletes on item status (contracts.md "Sandbox retention and collection" already says a sandbox is kept while its item rests at blocked or needs-human), or put Kubernetes finalizers on the pod and its volume.

**Covers:** endings that leave the sandbox in place.

**Misses:** host loss, server prune, `rm -f` (which prunes unless `preserve` is set), and disk pressure.

**Verdict on its own:** it does not satisfy "on a ref on origin", which is the invariant in bd-ib-xdhe5z. It is useful only as a complement that widens the window in which (a) can still read the sandbox.

## 4. Retention and cleanup — needed under every option

The plan's Definition of Done assertion 4 requires a stated rule, and none exists today. A candidate rule, for the maintainer to adjust:

- **The `run-progress` ref.** One mutable ref per run. Delete it when the item closes with its work merged, or when a later run of the same item has published its own progress ref and that run reached publish.
- **The `preserved-publish` and `needs-human` refs.** Delete them when the item closes and 14 days have passed. Keep them indefinitely while the item is open.
- **The deleter.** Extend ended-run collection (`_dispatcher_ended_run_collection.py`), which already acts only for closed items.
- **The backlog of 617 existing refs.** Clearing it is a one-time, outward-facing deletion and needs its own explicit maintainer go.

## 5. Unknowns to measure before choosing between (b2) and (b3)

- **U1.** Does `GET /api/v1/runs/<id>/files` answer on the Kubernetes backend, given that `fabro sandbox cp/ssh` does not?
- **U2.** Does the engine's checkpoint push run with hooks disabled, and with the credential only in that command's environment, so that a planted hook or a still-running detached agent process cannot capture it?
- **U3.** What forge API load does (b3) add at current fleet throughput? That means publishes per run times changed files, against the shared 5,000-an-hour installation limit.

## 6. Recommendation for the maintainer — NOT a decision

**Option (c), the hybrid.** Its two parts:

- **Progress preservation through the Dispatcher-side mirror (b3)**, falling back to the engine checkpoint push (b2) if U1 shows `/files` cannot serve Kubernetes runs.
- **The one terminal gate from (a)**, with the seam check as the enforcement leg.

Why:

- Only progress preservation covers row 15, the endings nobody remembered, which is the failure pattern this plan exists to end.
- (b3) needs no credential-confinement amendment and no fork change.
- (b3) reuses the exact writer that adcaa6, vraou4 and ds4yrm are building, so those three are absorbed as the gate's first callers.
- The terminal gate turns bd-ib-xdhe5z's enforcement assertion into an executable check.

This recommendation is provisional until the best-practices research (assertion 6, note 003) is in. It is the session's judgement from the code alone.
