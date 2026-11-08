# 003 — Best-practices research: Fabro and Petri, other AI factories, and the direction they point to (2026-11-04)

Session: factory-run-work-preservation plan seat, 2026-11-04. This note serves plan Definition of Done assertion 6, the research the maintainer added: "Include deep research into fabro/petri best practices and other ai dark factories, with astra and fable subagents, to determine best practices and ideas for direction."

Two researchers worked independently from the same brief. Neither read the other's output.

- **Astra:** Codex CLI 0.166.0, model `gpt-6-astra`, with live web search. It ran in a herdr split pane.
- **Fable:** Claude Fable 5.1, run as a Claude Code subagent with web search and fetch.

The raw outputs are kept beside this note:

- `data/research-brief-2026-11-04.md` — the brief both researchers were given.
- `data/research-context-facts-2026-11-04.md` — the measured facts they started from, a condensed form of note 002.
- `data/research-astra-gpt-6-astra-2026-11-04.md` — Astra's report.
- `data/research-fable-5-1-2026-11-04.md` — Fable's report.

Notation: an "ending" is any way a factory run stops. The ending labels E1 to E9 are Fable's:

| Label | Ending |
|---|---|
| E1 | Whole-run wall budget |
| E2 | Stall watchdog |
| E3 | Stale-item reap |
| E4 | Orphan reconcile |
| E5 | Engine terminal failure |
| E6 | A cancel made outside the Dispatcher |
| E7 | A Fabro server restart or crash |
| E8 | An operator `fabro rm` |
| E9 | A Docker or Kubernetes sandbox reclaim |

Both map onto the rows of note 002 §1.

## Caveats on provenance (checked by this session)

- **Engine versions differ, so line numbers may have moved.** The serving engine is 0.393.0-nightly.1 at `c39bdbded` (`.livespec.jsonc:1078-1099`). The two researchers read different fork checkouts:
  - Astra read `carrier-candidate-registered-20261023` at `9f6c38fab5a5`, which is the lineage the serving build comes from.
  - Fable read `carrier-petri-v0.382` at `adeefec4c`, which is the previous release.

  Fable's Fabro file:line citations are therefore against 0.382. Where the two agree on a behaviour (cancelled attempts are not checkpointed, failed runs are not published, `rm -f` deletes the run store), the behaviour holds across both builds.
- **Some platform claims are unverified.** Both researchers marked as UNVERIFIED any platform claim they could not confirm from a primary source. Neither treated a vendor's pause/resume feature as a crash-recovery guarantee. Fable did not reach Factory.ai, Sweep, Amp or Sourcegraph. Astra covered Factory and Amp, and found Sweep's repository no longer describes an agent bot.
- **Fable's first attempt stalled.** It handed the web research to helper agents that never reported back. It was restarted at 22:15Z, told to do the research itself, and completed directly.

## 1. What Fabro and Petri themselves provide

The two researchers agree on all of this.

- **Upstream Fabro's durability answer is the run-branch push.** Upstream docs (`docs/public/execution/checkpoints.mdx`) say: "When pushing is configured, Fabro pushes `fabro/run/{run_id}` after each checkpoint and again before successful completion". Fork and rewind both require it.
  - Upstream defaults to pushing for GitHub targets. This factory turned it off (`workflow.toml:432-438`).
  - Upstream no longer creates `fabro/meta/*` branches, so `meta_branch.push` is dead config.
  - Upstream keeps "no second checkout, bare snapshot repository, or Git checkpoint bundle on the server for a remote sandbox".
- **The push credential would enter the sandbox.** The engine hands the server's GitHub App token to `git` inside the sandbox as an HTTP-header environment value for one command (Fabro `publish.rs:287-345`). The ratified clause forbids that: contracts.md "Publication is mechanically confined to the scripted publication stages", which says "never through an environment variable".
- **Cancelled attempts are not checkpointed**, but failed attempts are (`fabro-petri/src/hooks.rs`). Even with the push on, the uncommitted tail of a cancelled attempt is lost, along with any agent commits made since the last checkpoint.
- **`finalize_run` runs for failed and cancelled runs while a driver is alive.** It writes the cumulative base-to-head `run.diff`, but only into the run store, which `rm -f` deletes. It publishes only on success.
  - Petri's "restart exits do not finalize" refers to a workflow `loop_restart` successor, not a server restart (Petri `HOOKS.md`).
  - A server restart or crash leaves no driver to finalize anything. The resumed driver "holds no environment".
- **Run hooks observe; they cannot preserve or block.** Hooks are observational and fail-open.
  - `stage_complete` is a usable capture trigger.
  - A cancel maps to `stage_failed`, and neither `run_complete` nor `run_failed` fires for a cancelled run.
  - `sandbox_cleanup` fires at scope release. A hook cannot refuse a teardown.
- **Retention is not durability.** The Kubernetes driver keeps the workspace in a node-local `hostPath` directory and refuses snapshots. That is why bd-ib-yuwftp's tree could be copied off the node by hand, and why it was not durable.
- **`GET /runs/{id}/files` needs the live sandbox.** It materializes from the live sandbox and falls back to the stored final patch once the sandbox is gone (Fabro `run_files.rs`). Neither researcher showed that it works on the Kubernetes backend. Astra: "do not assume HTTP file reads evade the broken Kubernetes provider transport". That leaves unknown U1 of note 002 open.

## 2. Other AI software factories and coding-agent platforms

| Platform | Pattern | Verified source |
|---|---|---|
| GitHub Copilot coding agent | Works on a branch and draft PR it owns. "Stopping a session ... preserves any commits already pushed". Newer cloud sandboxes snapshot stopped sessions. | docs.github.com (both researchers) |
| OpenAI Codex cloud | Platform-held diff and cached container state, up to 12 h. The docs tell users to commit or save important work. | learn.chatgpt.com (both) |
| Devin | Self-hosted Outposts require snapshot-before-termination, preserving the checkout and worker state. | docs.devin.ai (Astra); one page returned 404 to Fable |
| Cursor cloud agents | Isolated VMs that push to a separate branch. VM disk snapshots kept 30 days. | cursor.com (both) |
| Google Jules | Clones into a VM. Work in progress can be exported to a branch or PR before completion. Deleted tasks are permanent. | jules.google (both) |
| OpenHands | The only platform with an explicit preservation layer: a PVC-backed workspace that survives pause/resume, archived to S3 with a manifest BEFORE storage is released. | docs.openhands.dev (Fable) |
| Factory Droid Computers, Amp Orbs, E2B | Persistent machines or pause, which keep files across sessions. Not a crash guarantee. | (Astra) |
| StrongDM attractor (Fabro's lineage) | Checkpoints pipeline and traversal state, not git objects. | attractor spec §5.3 (Astra) |

**The shared lesson.** Every platform places durability at "already pushed to a branch" or "archived before release". None of them uses its durable-execution engine to keep the git tree itself, and none documents a guarantee that work survives an arbitrary host crash. Snapshots exist to reuse an environment, not to recover work.

## 3. Durable-execution and CI practice that applies

Both researchers cite the same set:

- **Progress before acknowledge** (Temporal). Petri already does this for control state; what is missing is a durable store for the tree.
- **The transactional outbox.** The sandbox's commit is the transaction, and a relay outside the sandbox does the forge write, at least once and idempotently.
- **Kubernetes finalizers.** Deletion cannot complete until an export record exists. A finalizer on a pod does not keep the pod's processes running, so the export must come from a separate controller or from retained storage.
- **preStop and last-moment hooks only bound the loss.** They share the termination deadline and fail on a container that has already terminated.
- **CI artifacts carry a TTL from the moment they are created**, so no later decision about deletion is needed.

Astra adds a requirement for receipt acceptance: a preservation receipt should prove the work can be restored into an empty workspace, not merely that a ref or a hash exists. It also names the cases a proof must exercise: a cancel in the middle of an edit, work committed before a checkpoint, an interrupted rebase, an export outage, a server kill, a pod removal, and an `rm`.

## 4. Where the two researchers converge, and where they split

### They converge on four points

1. **Preserve on progress, not at the ending.** Cancel-time mechanisms (`finalize_run`, `sandbox_cleanup`, preStop, and the Scenario 183 `/files` writer) need a live driver and a readable sandbox. They write into stores that `rm -f` deletes, and they never fire on E7. So option (a) of note 002 on its own leaves E6 to E8 permanently exposed. That is the "path nobody remembered" failure this plan exists to end.
2. **Add one deletion gate as well.** Before any destroy, a gate demands a verified preservation receipt; the destroy may still go ahead when publication fails, but the failure is recorded. The gate exports the uncommitted tail for Dispatcher-issued endings and carries the enforcement check. Astra: "cancellation should stop compute without granting permission to destroy its storage".
3. **Keep the sandbox credential-free, using an outbox.** The tree leaves the sandbox through a hop that holds no forge credential. A trusted writer outside the sandbox makes the durable write. Neither researcher proposes amending the confinement clause as the lasting answer.
4. **The three in-flight fixes are absorbed, not discarded.** bd-ib-ds4yrm, bd-ib-adcaa6 and bd-ib-vraou4 become callers of the gate, or flushes of the relay, and stay as regression scenarios. None should be closed merely because a progress hook exists.

### They split on where the preserved bytes land

- **Fable's pick: an outbox mirror to refs on origin.**
  - The engine's existing per-checkpoint push is enabled, but aimed at a credential-free bare git mirror on the factory host, which is write-only and reachable only from sandboxes.
  - A host-side relay pushes mirror refs to origin as one ref per run, `refs/livespec/wip/<item>/<run>`, using the Dispatcher's App token.
  - The fork change is small: per-environment push URL and credential selection.
  - It satisfies the plan's "on a named ref on origin" assertion and bd-ib-xdhe5z's invariant as written.
  - Interim: run_branch.push=true plus the Dispatcher deletion gate is a 48-hour stopgap of the same shape, but only if the maintainer amends the confinement clause.
- **Astra's pick: progress bundles to object storage, plus the gate, plus retained volumes on Kubernetes.**
  - Credential-free capture produces git bundles together with a payload of the working tree that includes uncommitted files.
  - A trusted exporter uploads them to object storage, independent of forge availability and rebases.
  - On Kubernetes, the workspaces sit on retained volumes with a snapshot controller.
  - It preserves BOTH the original history and the dirty working state.
  - It needs a new fleet export and retention service, and restore tooling.
  - It does NOT meet "a named ref on origin" as the plan Definition of Done and bd-ib-xdhe5z state it. Choosing it would mean re-wording assertion 1 and the invariant.

## 5. Revised recommendation for the maintainer — NOT a decision

> **Superseded 2026-11-05.** The maintainer chose a different, simpler direction, recorded in note
> `004-chosen-direction-preserve-on-progress-2026-11-05.md`. Both this section's outbox mirror and the engine run-branch push
> share a defect this section missed: the engine's push is never forced, so the Red-to-Green amend stalls it at the Red commit.
> This section is kept as the record of what was recommended.

This replaces note 002 §6, which picked a Dispatcher-side `/files` mirror (b3). Both researchers show that b3 depends on the live sandbox and the provider transport, which is exactly the dependency that fails on Kubernetes and on E7 and E8.

**Recommended direction: the outbox mirror to origin refs, plus one deletion gate.** This is Fable's design, with three additions from Astra.

1. **Progress leg.** Enable the engine's checkpoint push, aimed at a credential-free mirror on the factory host. A host relay publishes one force-updated `refs/livespec/wip/<item>/<run>` per run to origin.
   - Sandbox pods push over the network, so this avoids the broken `cp/ssh` transport. That still has to be measured on Kubernetes, as U1'.
2. **Gate leg.** Every Dispatcher cancel, abandon, rm and container or pod delete passes one `preserve_then_destroy` gate:
   - a final tail export, plus a relay flush;
   - a receipt on the item's ledger naming the run, the factory, the ref and the commit;
   - an extended `fabro_port_seam` check, so a direct destroy call fails the build.
3. **From Astra:**
   - the uncommitted working state rides along on the tail export;
   - receipt acceptance is a restore-into-an-empty-workspace proof;
   - failed relays are reconciled.
4. **Retention.** `wip/*` and `preserved-publish/*` refs are deleted when their item is accepted or closed. Every other preservation ref goes after 30 days. The 420 `needs-human/*` refs join the same rule. Clearing today's 617-ref backlog needs a separate explicit go.

Why this one:

- It is the only design both researchers' evidence supports that still meets the plan's Definition of Done and bd-ib-xdhe5z exactly as worded.
- It honours upstream Fabro's own durability mechanism instead of fighting it.
- It keeps the ratified confinement clause intact.
- It turns the three in-flight fixes into thin callers.

The object-storage design is the stronger long-run answer for preserving dirty state and for independence from the forge. It is the right choice if the maintainer prefers that and accepts re-wording assertion 1.
