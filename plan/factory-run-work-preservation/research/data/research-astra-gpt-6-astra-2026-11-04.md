# Preserving factory-run work: independent research

2026-11-04. **Opinion:** preserve recoverable bytes on progress, then require a verified preservation receipt before destructive cleanup. Cancellation should stop compute without granting permission to destroy its storage.

This serves the factory’s goal of recovering expensive implementation work: the measured wall-budget path verifies a ledger pointer, then removes the run; the pointer contains hashes and retrieval instructions, not the work itself.

**Scope and provenance.** Read-only source/document research; no runs exercised, ledger writes, or coordination with the other researcher. Local source roots below distinguish versions:
- **O** = this repository, commit `2348100b1b29`.
- **F** = `/data/projects/fabro`, checked out at older feature commit `3b37818887c8`.
- **C** = `/home/ubuntu/.worktrees/fabro/carrier-candidate-registered-20261023`, commit `9f6c38fab5a5`, containing Fabro’s Petri adapter.
- **P** = `/data/projects/petri`, commit `b99987bcf0d0`.

These are source observations, not attestation of the running binary. Kubernetes copy-out failure and incident measurements are supplied facts from `context-facts.md`, not independently reproduced. Current upstream documentation differs materially from F.

**Fabro/Petri: what actually survives**

Upstream currently checkpoints code to `fabro/run/<id>`, stores execution records separately, and uses content-addressed storage for artifacts. It **no longer creates metadata branches**. Remote sandboxes have no second server checkout or Git bundle; ordinary resume requires their workspace. Intermediate pushes can fail with warnings; later checkpoints/final publication retry. Checkpoint commit failure stops execution. These distinctions invalidate treating durable execution records as a code backup. [Fabro checkpoints](https://github.com/fabro-sh/fabro/blob/main/docs/public/execution/checkpoints.mdx)

F’s older two-branch implementation defaults both run/meta pushes to true (`lib/foundation/fabro-config/src/resolve/run.rs:247`); this factory explicitly disables both (`O/.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml:432`). Current upstream still documents run-branch pushing; re-enabling obsolete metadata machinery is not a forward-compatible direction. [Run configuration](https://github.com/fabro-sh/fabro/blob/main/docs/public/execution/run-configuration.mdx)

C verifies the important failure boundaries:

- `lib/components/fabro-petri/src/hooks.rs:1543`: cancelled attempts skip snapshots; failed ordinary attempts do checkpoint.
- Same file, `:1324`: conclusion diff is base-to-last-recorded-checkpoint, not current dirty tree. Stage diffs are checkpoint-to-parent (`:26`); an agent’s preceding commits need not appear in them.
- Same file, `:1643`: finalization attempts the cumulative diff, but publication is success-only. Failed/cancelled runs do not gain guaranteed terminal pushes.
- `P/crates/core/execution/HOOKS.md:257`: required finalization runs before release on failure/cancellation, but not child invocations or workflow restart exits. **Workflow restart is distinct from a server process restart.** Crash recovery can repeat finalization; it does not recreate missing environments or supply independent effect retry/deduplication.
- `P/crates/core/driver/src/run.rs:1183`: even finalization rejection proceeds to environment release. A finalizer is not automatically a deletion veto.
- `P/crates/attractor/steps/src/hooks/mod.rs:741,821,843`: cancellation maps to `stage_failed`, not `stage_complete`; cancelled runs omit `run_failed`, while `sandbox_cleanup` runs at release. Local workflow hooks are observational/fail-open. Useful capture triggers, insufficient durability enforcement.
- `C/lib/components/fabro-petri/src/engine.rs:442`: Fabro maps release to `Retention::Always`; `preserve` affects deletion. `C/lib/apps/fabro-server/src/server.rs:2905` honors preserve for recorded sandboxes, but `:2757` deletes run directories, records and artifacts. Retaining a container alone therefore does not retain all resume state or protect against external runtime deletion.

Standalone Petri ignores run/meta Git sections: Git preservation belongs to its embedding host (`P/crates/fabro/frontend/src/workflow_toml.rs:1241`). Its replayable log is a useful coordination substrate, not an automatic filesystem backup. [Petri upstream](https://github.com/lithoscomputer/petri)

The existing host Git Data writer is reusable: it builds a tree over the recorded base and creates a commit/ref, avoiding sandbox publication credentials (`O/.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_preserved_tree_publish.py:125`). It preserves a reconstructed tree, not original commit history. Its live-sandbox input remains a dependency; do not assume HTTP file reads evade the broken Kubernetes provider transport.

**Other platforms: verified patterns and limits**

| Platform | Verified preservation behavior; remaining uncertainty |
|---|---|
| GitHub Copilot | Current cloud sandboxes snapshot stopped sessions and resume files/in-progress work. Older Actions-based coding-agent sessions push changes to PRs. Neither cited document promises export of every dirty write during arbitrary host loss. [Sandbox lifecycle](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/about-cloud-sandboxes), [Actions-era workflow](https://docs.github.com/en/enterprise-cloud%40latest/copilot/how-tos/use-copilot-agents/cloud-agent/use-cloud-agent-on-github) |
| Codex Cloud | Existing tasks retain saved files, including uncommitted changes and installed tools; documentation explicitly recommends committing/saving important work. Snapshot frequency and crash recovery bounds are unspecified there. [Saved state](https://learn.chatgpt.com/docs/environments/cloud-environments) |
| Devin | Self-hosted Outposts explicitly require snapshot-before-termination for resumability, preserving both checkout and worker-state directories. Missing directory stamps generate warnings. This is a strong operator contract, not evidence of automatic snapshots for every hosted crash. [Orchestration](https://docs.devin.ai/cloud/outposts/orchestration) |
| Jules | Paused tasks resume; deleted tasks are permanent. Work-in-progress can be exported to a branch/PR before completion. Automatic export on crash is unverified. [Lifecycle](https://jules.google/docs/tasks-repos), [Export](https://jules.google/docs/changelog/2025-08-15/) |
| Cursor | VM disk snapshots live outside the active VM, encrypted, with rolling 30-day inactivity retention. Conversation retention is separate. Exact crash checkpoint cadence remains unspecified. [Security](https://cursor.com/docs/cloud-agent/security) |
| Factory | Droid Computers retain files, packages, services and configuration between sessions; managed machines auto-pause/resume. That does not establish recovery after deleting a computer or losing its storage. [Computers](https://factory.com/product/droid-computers) |
| OpenHands | SDK persistence writes conversation state/events to disk. The cited guide alone does not establish an independently retained workspace backup after sandbox destruction. [Persistence](https://docs.openhands.dev/sdk/guides/convo-persistence) |
| Amp | Sleeping Orbs retain files/services; sync can transfer unpushed commits and dirty changes. This demonstrates recovery independent of forge publication, not a documented arbitrary-crash guarantee. [Orbs](https://ampcode.com/docs/orbs) |
| StrongDM/Attractor | Specification §5.3 checkpoints traversal/context/log state after nodes. That contract alone does not export Git objects or dirty files. [Specification](https://github.com/strongdm/attractor/blob/main/attractor-spec.md) |
| E2B | Explicit pause preserves filesystem and memory indefinitely until killed. Useful lifecycle separation; not proof that an unexpected machine loss performs a pause. [Persistence](https://docs.e2b.dev/sandbox/persistence) |

Sweep’s current repository describes a JetBrains assistant; this README did not substantiate historical bot cancellation guarantees. No independently verified Sourcegraph-specific crash-preservation guarantee emerged from this survey; Amp’s behavior must not be attributed to Sourcegraph generally. [Sweep](https://github.com/sweepai/sweep)

**Applicable durability/CI practice**

Persist payload **before acknowledging preserved progress**. Record immutable identity, digest, base/HEAD/tree, capture sequence and storage locator; acknowledge only after read-back verification. An outbox transaction can couple checkpoint metadata with an export request, but a request pointing to disposable bytes is insufficient. Duplicate delivery needs idempotent object identities. This applies [transactional-outbox practice](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html), not a claim that Git and object storage share a transaction.

[Temporal replay](https://docs.temporal.io/workflow-execution) restores recorded execution progress; external Git effects still require durable payloads and repeat-safe activities. Petri already supplies relevant hooks: a wholesale engine migration is unnecessary.

[Kubernetes finalizers](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/) delay API-object removal; they do not keep a deleting Pod’s processes running. Protect a retained persistent volume and export from a separate controller. A Pod finalizer cannot save an ephemeral container filesystem after termination. [PreStop](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/) shares the termination deadline and cannot rescue an already terminated container.

[CI artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data) supply explicit retention and immutable artifact versions. Upload during progress: a final cleanup step cannot execute after its runner disappears. Privileged removal of finalizers or underlying storage remains a bypass; already exported bytes must survive it. Archive storage must have a lifecycle independent of `fabro rm`.

**Five candidate designs**

Cost notation: **N** = changed-stage captures; **T** = periodic captures; **F** = changed files/capture. Counts exclude retries and verification reads. Proposed retention: merged/accepted work seven days after verified recovery no longer needs it; failed work 30 days, extended while an item references it. These are proposed policies, not current behavior.

The three existing fixes are **Restart** = preserve before cancel-for-restart (`bd-ib-adcaa6`), **External** = preserve externally cancelled runs (`bd-ib-vraou4`), **Budget** = preserve wall-budget cancellation (`bd-ib-ds4yrm`).

| Design | Coverage, writer/credentials, cost/cleanup, existing fixes |
|---|---|
| **Guarded terminal export** | Fabro server/retention controller captures a quiesced tree before rm/prune; Dispatcher facade invokes the same operation. Separate trusted host writer holds App credentials; existing proof/comment broker stays unchanged. Covers controlled cancel, timeout, terminal failure and operator rm routed through the gate. Misses abrupt loss; currently blocked where extraction fails. One push/ref, or roughly F+4 Git Data requests/capture. Apply proposed retention. Restart/Budget become callers; External requires server integration and remains incomplete for abrupt loss. |
| **Progress refs through trusted publisher** | Export after each checkpoint through a host-owned writer, with credentials inaccessible to agent processes, hooks and files. Immutable run/sequence/SHA refs survive rebases. Covers every later ending through the last successful push, including external rm/crash; misses active dirty attempts and failed pushes. N pushes/N immutable refs; alternatively, one append-only archive branch whose snapshot commits retain previous archive and source heads as parents gives N pushes/one ref without force-pushing after rebases. No per-file REST cost. Retain refs by policy. All three fixes consume receipts and retain terminal capture for the tail; none is fully replaced by progress alone. |
| **Progress bundles plus durable outbox** | Credential-free capture creates Git objects/refs and dirty-tree payload; a separate trusted exporter reads retained storage or receives an authenticated upload, then writes object storage using its own identity. Never uses the failing copy-out path or broadens the broker. Covers completed captures across all endings; stage-plus-periodic capture bounds active-work loss. Zero forge pushes/refs/API writes during capture; N+T object uploads plus manifests, with bundle CPU/bandwidth. Keep required incremental bases. All three fixes use one receipt/delete gate; External adds reconciliation of unfinished uploads. |
| **Persistent workspace with snapshot controller** | Put checkout, Git database and needed executor state on retained volumes. Infrastructure controller uses storage credentials, no forge token; CSI snapshots/export avoid sandbox cp. Covers process/server death, cancellation, Pod replacement and ordinary deletion; node/storage loss depends on replication, while concurrent snapshots may be inconsistent. Zero forge load; N+T snapshots and retained-volume storage. Requires snapshot-capable CSI and restore verification. Finalize volume deletion only after verified export; apply retention. Restart/External/Budget become stop-and-retain callers; common controller owns preservation. |
| **Quarantine retained sandboxes** | Use preserve/retention immediately and make all cleanup paths consult a durable quarantine registry. Host controller holds runtime credentials only. Covers cooperative endings/restarts when original storage survives; misses node loss, runtime bypass and unpersisted Kubernetes storage. Zero pushes/refs/forge load; highest accumulating disk cost, possible idle compute. Reap only after verified export; export failure holds storage and alerts/admission limits. All three fixes stop destructive cleanup and register quarantine, but still need a later export mechanism. |

**Selection — opinion**

Choose **progress bundles/outbox plus a common deletion gate**, backed by retained workspace volumes on Kubernetes. This decouples rescue from forge availability, rebases and publication authority. It adds one fleet export/retention service and restore tooling; that maintenance cost is justified by endings outside the Dispatcher. Start with quarantine as containment, not as the completed solution. The new upload/shared-volume route is a required implementation, not a verified workaround for today’s broken Kubernetes transport.

Use Petri’s checkpoint boundary for capture, required finalization for a last attempt, and a server/storage-controller gate for reclamation. Freeze writers before terminal capture; cancellation may stop compute immediately while storage remains. A failed finalizer must leave an independently enforced hold. The current publication contract requires explicit design ratification for any new forge writer (`O/SPECIFICATION/contracts.md:3457`); object archival avoids granting agents publication authority.

Preserve **both original Git history and the working state**, including untracked source, deletions, executable bits and interrupted rebase metadata. Exclude credentials/caches deliberately; record exclusions. Bundles alone omit uncommitted files and external LFS/submodule payloads. Use self-contained bundles or verified prerequisite chains; a rewritten branch must not invalidate recovery. [Git bundle](https://git-scm.com/docs/git-bundle)

Receipt acceptance should prove restoration into an empty workspace, matching the captured tree/manifest—not merely a ref, hash or nonempty patch. Exercise cancellation mid-edit, committed-before-checkpoint work, interrupted rebase, export outage, server kill, Pod removal and rm. Until that shared path is proven, retain Restart/External/Budget as protective adapters and regression scenarios; do not close them merely because a progress hook exists.

**Sources list**

- Local evidence: O workflow `:432`, contracts `:3457`; commands `_dispatcher_run_wall_budget_watch.py:160,203`, `_dispatcher_preserve_reference_body.py:49,55`, `_dispatcher_preserved_tree_publish.py:125`.
- Fabro carrier evidence: C `lib/components/fabro-petri/src/hooks.rs:1324,1543,1643`, `engine.rs:442`; `lib/apps/fabro-server/src/server.rs:2757,2905`.
- Petri evidence: P `crates/core/execution/HOOKS.md:257`, `crates/core/driver/src/run.rs:1183,2493`, `crates/attractor/steps/src/hooks/mod.rs:741,821,843`.
- Engine sources: [Fabro checkpoints](https://github.com/fabro-sh/fabro/blob/main/docs/public/execution/checkpoints.mdx), [configuration](https://github.com/fabro-sh/fabro/blob/main/docs/public/execution/run-configuration.mdx), [Petri](https://github.com/lithoscomputer/petri), [Attractor §5.3](https://github.com/strongdm/attractor/blob/main/attractor-spec.md).
- Platform sources: [Copilot](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/about-cloud-sandboxes), [Codex](https://learn.chatgpt.com/docs/environments/cloud-environments), [Devin](https://docs.devin.ai/cloud/outposts/orchestration), [Jules lifecycle](https://jules.google/docs/tasks-repos) and [export](https://jules.google/docs/changelog/2025-08-15/), [Cursor](https://cursor.com/docs/cloud-agent/security), [Factory](https://factory.com/product/droid-computers), [OpenHands](https://docs.openhands.dev/sdk/guides/convo-persistence), [Amp](https://ampcode.com/docs/orbs), [E2B](https://docs.e2b.dev/sandbox/persistence), [Sweep](https://github.com/sweepai/sweep).
- Durability sources: [Temporal](https://docs.temporal.io/workflow-execution), [AWS outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html), [Kubernetes finalizers](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/), [PreStop](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/), [CSI snapshots](https://kubernetes.io/docs/concepts/storage/volume-snapshots/), [CI artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data), [Git bundles](https://git-scm.com/docs/git-bundle).
- Web sources accessed 2026-11-04. Vendor pause/resume claims were not treated as arbitrary-crash guarantees.

