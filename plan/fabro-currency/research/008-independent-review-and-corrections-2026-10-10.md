# 008 — independent review and corrections (2026-10-10)

An independent Codex session (model gpt-6-astra, Codex CLI 0.162.1, read-only) reviewed the plan session's direction summary. Part A is the summary as reviewed, Part B the critique verbatim, Part C the corrections the plan session adopted after verifying each finding against source. The ledger rewrite of the same day (scope event, regrooms of bd-ib-j9x and bd-ib-otyq6l, children bd-ib-6vhgqg, bd-ib-njbg7j and bd-ib-433fcr, riders on bd-ib-sxcnj7 and bd-ib-iud52v) implements Part C.

## Part A — the summary as reviewed

## fabro-currency direction summary, 2026-10-10

Written by the fabro-currency plan session for independent review. Every
claim below was measured in the session unless marked "assumed". The
reviewer's job is to find omissions, holes, wrong framing and anything the
discussion missed, with the whole picture in view.

### 1. Where we are

- Repo: livespec-orchestrator-beads-fabro. Plan `fabro-currency`, epic
  `bd-ib-6tcjfx`, goal: move the self-hosted dark factory from the pinned
  Fabro 0.254 fork carrier onto the current Petri-era Fabro, keeping
  current factory functionality and deferring everything else.
- Pinned production engine on hp: fabro 0.254.0 build 8869e88 from our fork
  `thewoolleyman/fabro`, branch `factory-integration`, server unit
  `fabro-server`, port 32276, Docker sandbox provider.
- Candidate engine on hp in parallel: fabro 0.378.0-nightly.0 (64b9d88),
  unit `fabro-server-candidate`, port 32278. Exact upstream tag, no carries.
- Spec constraint (constraints.md "One non-renewable Petri transition"):
  the 0.254 carrier may serve only before 2026-11-14T00:00:00Z. After that
  the ordinary 30-day currency rule refuses dispatch. Not renewable.
- Maintainer direction: stay current on Fabro, build what the factory needs
  on top, preferably by contributing upstream, never freeze on the fork.
  Scope ruling 2026-10-08: defer anything current functionality does not
  depend on; spend and unimplemented features are out of scope.
- P4 (port to candidate) is nearly done: the renderer, graph port, facade,
  Petri output parsing items closed on independent host replays. The
  native-secrets item `bd-ib-4ipmub` is in its fifth dispatch, now under
  Codex-only routing, run 01M4HA8YVAAH, gate 20261009T214831Z-2194632.

### 2. Architecture, as measured in source at the candidate tag

- Fabro re-platformed onto Petri (lithoscomputer/petri) on 2026-09-17.
  Petri was written new by Bryan Helmkamp from 2026-08-25 as Fabro's
  engine (763 of 813 commits), not extracted from Fabro and not
  pre-existing. Same two authors as Fabro (Helmkamp, Scott Werner).
- Petri owns: IR, compile and validate, firing, routing, retries, loops,
  executor including ACP to coding agents, sandbox acquisition over
  host/Docker/Daytona via the `sandbox-driver` crates, the run event log.
  Petri also ships Fabro's workflow-format frontend.
- Fabro owns: server, HTTP API, web console, auth, GitHub App, vault and
  masking, storage, run listing and inspection, checkpoint and PR hooks,
  interviews, blobs, the projection of Petri records into Fabro's run view.
- Boundary: `fabro-petri` is the one crate touching Petri. Fabro builds
  `RunOptions` and `SandboxOptions`, Petri does everything inside the
  sandbox including container creation.
- Daytona: hosted cloud sandbox service. The open-source repo
  daytonaio/daytona is archived (last push 2026-07-24, last release
  v0.190.0 2026-06-23, AGPL). No evidence of any Helmkamp financial or
  board interest in Daytona; his only tie is a Rust SDK he maintains.
  This repo has never used Daytona; Docker on hp from day one.

### 3. The resource-ceiling finding

- Today: the pinned engine turns the workflow's declared CPU and memory
  into Docker host-config limits (measured: 4 CPU quota, 8 GB memory on
  production containers). hp is 16 cores, 30 GB, up to 15 sandboxes.
- Candidate: Petri forwards resources only to Daytona. Its
  `SandboxOptions` has no Docker resources field; the Docker path builds
  `Resources::default()` (unlimited). Petri's own frontend emits the
  diagnostic "resource limits apply to a Daytona runner; the host and
  Docker providers run unconstrained". Deliberate, documented, unchanged on
  Petri main (2548c10, 2026-10-08). The sandbox-driver Docker layer DOES
  apply memory and cpu_quota when the spec carries them.
- So the cutover on Docker drops per-run limits. Not a cause of any
  failure so far; a regression the cutover would introduce.
- Item `bd-ib-otyq6l` ("forward resources to the Petri Docker sandbox")
  needs a Petri change plus one fabro line. Petri fork was considered and
  rejected; upstream Petri PR considered.

### 4. The Kubernetes finding and the chosen direction

- Nobody upstream is building a Kubernetes backend. A complete one exists
  in a fork (mhermann/fabro PR 4, merged into that fork 2026-09-10, pod per
  run, exec API, NetworkPolicy, ~5000 lines) against the pre-Petri sandbox
  layer; never offered upstream.
- Maintainers' stated direction (Firecracker PR 567 closed 2026-10-07):
  backends are third-party plugins over the sandbox-driver JSON-RPC
  protocol v2, maintained by their authors. Fabro issue 937 (open,
  2026-10-07) is the missing wiring: Fabro constructs Petri with only
  Host/Docker/Daytona, so a configured plugin cannot yet execute workflows.
- Decision (maintainer, this session): Kubernetes becomes the sandbox
  backend, as a plugin we own, on a cluster we own (hp first, other
  workers later for capacity). Per-run limits come from pod
  requests/limits natively, so the Petri resource change is dropped.
- Maintainer confirmed: no new Fabro fork; the existing fork and its
  `factory-integration` carrier are rebuilt, and the Kubernetes wiring is a
  branch on that fork cut from the rebuilt carrier, no upstream PR needed
  to start. The scope event forbidding public changes to non-owned repos
  does not bind our own fork or our own PRs.

### 5. The telemetry finding (corrected twice in session)

- The fork carries OTLP span export (upstream PR 576's transport) plus
  fork-local: worker OTLP env re-injection, W3C traceparent join, OTLP
  decoupled from FABRO_LOG, and a `run_turn` ACP turn span carrying the
  redacted adapter command and digest.
- Candidate tag, upstream main (0c279ea, 2026-10-09) and Petri (locked rev
  and main) have ZERO OTLP/OpenTelemetry code (positive control: the
  pinned carrier hits in 5 files).
- Production hp unit has OTEL_EXPORTER_OTLP_ENDPOINT/PROTOCOL/SERVICE_NAME
  set; Honeycomb `fabro` dataset received 869 `run_turn` spans in the
  last 7 days plus stage/checkpoint/edge events.
- The Dispatcher has an OTLP receiver (`_otel_receive.py`), a run-turn
  sink and a NON-BLOCKING post-dispatch run-turn guard that appends an
  export assertion per green dispatch. The ratified contract requires a
  reader can check the rendered adapter command and digest "against the
  redacted run_turn.command record the factory emits".
- Therefore the 2026-10-08 deferral of telemetry as "observability, not
  factory function" was wrong in premise. Telemetry is a factory
  verification dependency. It stays in fabro-currency.
- Upstream PR 576 thread: Bryan's last word 2026-07-25 wants Fabro all-in
  on OTLP starting with canonical run events as OTel LOGS, traces deferred.
  The maintainer agreed on 2026-08-02 and promised a rewrite, holding until
  Bryan confirmed. Bryan never replied (9 weeks). Bryan's sketch link
  expired 2026-08-24; our only copy is the snapshot in
  plan/archive/fabro-otlp-telemetry/research/. PR is CONFLICTING against
  main, 1 commit. In the Petri-era code `RunEvent` is now Petri's type
  (`petri_execution::events::RunEvent`) folded by fabro's projector, so
  the logs design targets a type that moved.
- Maintainer decision: keep the same PR number (it holds Bryan's design
  agreement); rewrite the branch on upstream main to the logs design and
  force-push `otlp-span-export`. The run_turn trace span stays fork-local
  until upstream takes traces.
- Upstream PR 688 (spend-limit classification): close with a comment; the
  Dispatcher classifies provider ceilings itself and spend is out of scope.

### 6. Plan `factory-run-correlation-observability` (epic bd-ib-qfv9)

- Opened 2026-08-20; wires work-item/dispatch/run/factory identity onto
  fabro run spans so Honeycomb can answer which factory ran a run. 4 of 5
  children closed; one in backlog since 2026-08-22 (prove the factory
  attribute varies with input, one live hp dispatch). Dormant, no session.
- It is a CONSUMER of the engine telemetry, not an owner of any carry.
  fabro-currency's telemetry port must preserve its attributes and the
  traceparent join. The Kubernetes plan must redefine the factory
  attribute as node/pod. The plan owns nothing new and archives after its
  proof runs on the current engine.

### 7. Cross-tenant dependency scan (all 18 tenants, every item incl. closed)

- Zero references to fabro-currency or its children outside this repo's
  tenant (15 family tenants plus homelab, openbrain, resume via their own
  wrappers; plus every project's plan/ and SPECIFICATION/).
- Inside this repo: the model-fallback plan's one open item
  (`bd-ib-vuwrv5`, epic bd-ib-jxvgq5) needs the current engine serving on
  hp and one live fallback dispatch there, i.e. the cutover (P6), not the
  deferred pieces. run-lifecycle-false-verdicts items cite plan items as
  evidence only. Three items had blocks edges on the closed renderer item
  (already released).
- The bundle item `bd-ib-sxcnj7` carries blocks edges on `bd-ib-otyq6l`
  (resource forwarding) and `bd-ib-j9x` (version-ceiling gate). Both edges
  must be removed when those items are closed/deferred or the bundle stays
  blocked on work we decided not to do.

### 8. Fork state (thewoolleyman/fabro) and cleanup

- 15 branches, zero open PRs inside the fork. Two open upstream PRs by the
  maintainer: 576 (OTLP) and 688 (spend-limit). Two earlier upstream PRs
  merged (552, 568), whose carries the bundle drops.
- Hygiene pass 2026-09-30 (bd-ib-kqbuju) deleted 1,422 run artifacts and
  11 branches, retired fork `main`, default = factory-integration, kept 12
  ordinary branches whose value "was not disproved". Recovery bundle at
  ~/.local/state/fabro-ref-backups/. Nine local worktrees under
  ~/.worktrees/fabro/, several from August, two preserved modified files.
- Proposed: triage and delete the 12 branches and the worktrees in
  fabro-currency before the carrier rebuild; carrier rebuilt (rebased onto
  the candidate tag with only surviving carries), outgoing tip retained as
  a tagged rollback ref.

### 9. The two-plan split as currently proposed

#### fabro-currency (immediate; must cut over before 2026-11-14)

1. Finish bd-ib-4ipmub (native secrets), merge, reconcile.
2. Scope event reversing the telemetry deferral (reason: run-turn guard and
   run_turn.command contract consume engine spans).
3. New child: port the telemetry carry set (576 transport, worker env
   re-injection, traceparent join, log decoupling, run_turn span) onto the
   rebuilt carrier; criteria include correlation attributes and traceparent
   join surviving; proof = one candidate-instance dispatch on hp landing
   run_turn spans in Honeycomb `fabro`. Blocks the bundle.
4. Correct the bundle's carry inventory: telemetry patches are "port" not
   "drop".
5. Reply to Bryan on PR 576 now (rewrite will follow his logs design on
   Petri-era main; trace span stays fork-local).
6. After cutover: rewrite `otlp-span-export` on upstream main as the logs
   exporter, carry run_turn on top in the fork, force-push same branch.
   Done = pushed and replied, NOT merged. Maintainer amends the
   "do not push PR head branches" scope line when this starts.
7. Close upstream PR 688 with a comment.
8. Close bd-ib-otyq6l as superseded (Kubernetes); defer bd-ib-j9x out of
   the bundle's blockers with a floor-gate regroom note; remove both
   blocks edges from the bundle.
9. Fork cleanup: triage/delete 12 branches and 9 worktrees.
10. Interim host protection with no fork: Docker daemon default cgroup
    parent under a systemd slice with a total memory ceiling, plus a
    concurrency limit sized to hp. Aggregate protection only; one run can
    still starve others within the slice. Accepted as a bridge.
11. Bundle: exact candidate tag + surviving carries; host unit,
    orchestrator image, runbook in lockstep.
12. Canary dispatches on the candidate; default_factory cutover on hp;
    verify production; retire the 0.254 carrier; rollback binary retained.
13. Archive. bd-ib-vuwrv5 (model fallback) unblocks at step 12.

#### kubernetes-sandbox-backend (follow-on; proposed slug)

1. k3s on hp; registry access for the sandbox image; pod-to-tailnet reach
   to the beads Dolt tenant verified first.
2. Kubernetes sandbox-driver plugin (protocol v2) in its own repository
   under the maintainer's account, ported from the fork's pod/exec
   mechanics, proven against the sandbox-driver conformance suite.
3. Fabro wiring for plugin execution through Petri (issue 937): a branch
   on the existing fork cut from the rebuilt carrier, after
   fabro-currency's bundle lands; offer upstream later.
4. Per-run CPU/memory via pod requests and limits, replacing the slice.
5. Canary; default_factory cutover to the Kubernetes backend; retire the
   Docker slice; port rescue tooling (dump, preserved refs, disk
   reclamation, load diagnosis) to pod equivalents.
6. Version floor gate, regroomed from bd-ib-j9x.
7. Redefine and re-prove the factory correlation attribute as node/pod.
8. Additional worker nodes elsewhere for capacity (Kubernetes adds no
   capacity by itself; hp at load ~21 on 16 cores is the real constraint).
9. Decide whether to refresh PR 576 upstream is NOT here (it is in
   fabro-currency step 6).

### 10. Things the session got wrong, for the reviewer's calibration

- Proposed forking Petri / an upstream Petri PR before asking whether the
  per-run limit was needed at all.
- Proposed closing PR 576 before measuring that the candidate has no OTLP
  and that the Dispatcher consumes the spans.
- Claimed closing our own PR needed a scope lift.
- Routed the PR 576 rewrite to a third plan by repeating a disposition line
  without reading that plan.
- Pattern: routing by prior ledger text instead of by the goal.

### 11. Open questions the session has NOT resolved

- Whether k3s on hp coexists with the Docker sandbox slice during the
  bridge (both compete for the same 16 cores / 30 GB).
- Whether Petri's host provider or the plugin protocol imposes anything a
  pod cannot satisfy (snapshots, volumes, sidecars, PTY caps).
- Whether the beads `bd` guard, the GitHub App token flow and the
  1Password wrapper work from inside a pod (today they work because the
  sandbox is on hp's network and image).
- Whether the logs-based PR 576 rewrite can carry the run_turn command
  digest the Dispatcher contract needs, or whether the trace carry is
  permanent.
- Who runs the correlation plan's remaining proof and when.
- Whether the interim cgroup slice needs its own spec change (constraints
  or NFRs mention per-run limits?). Not checked.
- Whether the 2026-11-14 deadline is achievable given 4ipmub's five
  dispatches and the bundle not yet started. Not estimated.

## Part B — the critique, verbatim

## Independent review: Fabro currency and Kubernetes direction

Reviewed 2026-10-10. Findings are ranked by their consequence for the stated goals, with immediate migration blockers first.

The two-plan split is sensible, but its proposed contents do not yet support a safe cutover or continued currency. In particular, it defers a ratified currency obligation, understates work at the Petri boundary, and treats a future Kubernetes implementation as already replacing present resource isolation. Keep Kubernetes out of the November critical path. Make the first plan deliver a reproducible, supportable current factory, including its admission rule, bounded interim operation, and proven telemetry contract.

### Evidence and limits

I read the supplied summary in full and checked the current repository's specification, configuration, command implementations, rollout research, correlation research, archived OTLP sketch, and image runbook. I inspected Fabro's serving source at `8869e88b2`, candidate tag `v0.378.0-nightly.0` (commit `64b9d8815`; the annotated tag object is `81042594`), and local `upstream/main` at `0c279ea284`. Petri's supplied checkout is `e46845bd`; sandbox-driver's supplied checkout is `7d1932b5`. GitHub reads confirmed Petri main at `2548c104`, sandbox-driver main at `90b0d825`, the current releases, and the relevant PR/issue threads.

Below, **repo** means `/data/projects/livespec-orchestrator-beads-fabro`; **commands** means its `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`; **Petri** and **driver** mean the supplied checkouts above. Fabro source references specify the revision when needed. Links identify upstream evidence; local paths identify independently inspected evidence.

This was a read-only source review. I did not run dispatches, tests that create runtime state, host configuration probes, or ledger commands. Consequently the reported live Honeycomb counts, hp utilization, current fifth-dispatch status, and cross-tenant scan remain the summary's observations, not independently repeated measurements. Only this requested critique file was written.

### 1. Critical: the currency admission rule has been dropped under the wrong name

**Wrong or missing.** `bd-ib-j9x` cannot simply become a deferred Kubernetes “version floor” task. Engine currency and a minimum supported plugin release are different predicates. The summary also presents refusal after November 14 as existing behavior, although the checked implementation does not establish it.

**Evidence checked.** `SPECIFICATION/contracts.md:2425` requires every dispatch path to validate the selected factory's serving commit, published release-tag ancestry, newest release publication date, and a release observation no older than seven days, before claim or mutation. `constraints.md:124–168` defines the 30-day publication-date window and the nonrenewable exception. Research `001-currency-assessment-2026-09-30.md:133` already explicitly reinterprets `j9x` as enforcing that currency window. Searches through command implementations found no implementation of the deadline or release/ancestry predicate; the positive controls find registered-plugin currency and the separate `dispatcher.minimum_release` checks. `tests/heading-coverage.json` explicitly says the integration binding for the ratified currency contract is owed, rather than claiming existing coverage.

**Change.** Keep target-aware engine currency admission in **fabro-currency**, or identify and verify the already-landed implementation if it exists outside the checked tree. Keep plugin release floors and feature capability checks separate. Exercise expired metadata, failed refresh, unknown commit, no release ancestor, parallel old/new factories, and the deadline boundary. Until this is implemented, describe November 14 as a binding policy deadline, not an automatic technical safeguard that is known to work.

### 2. Critical: the timeline does not reserve time for soak, currency refresh, or a usable rollback

**Wrong or missing.** “Before November 14” is not the cutover date. The existing plan requires a week of soak and retirement of the old service before that date. A rollback to 0.254 stops being policy-compliant at the deadline. The selected October 6 candidate also has no exemption if later releases put it outside the currency window.

**Evidence checked.** Research `005-rescope-and-parallel-rollout-2026-10-08.md` prescribes a week of soak, separate stores, and retirement before `2026-11-14T00:00:00Z`. GitHub already lists [v0.381.0-nightly.0](https://github.com/fabro-sh/fabro/releases/tag/v0.381.0-nightly.0), published October 9, ahead of the October 6 candidate. The rule compares **two release publication timestamps**, not the base's age relative to today's clock: an October 6 base becomes ineligible when the newest observed release is more than 30 days later. The first assessment estimated 3–6 focused weeks for the re-platforming; the summary supplies no updated estimate for the unfinished secrets, telemetry, bridge, bundle, or acceptance work.

**Change.** Work backward from a legacy-service retirement date with buffer: a full seven-day soak alone puts cutover no later than roughly November 7, and an earlier target is prudent. Put named owners, latest finish dates, and explicit escalation decisions on the remaining work. Re-survey releases before rebuilding and before cutover; qualify a newer tag if needed. Retain a **qualified Petri-era rollback build and its compatible state** for operation beyond November 14. State explicitly that the old carrier then becomes an archival/rescue artifact, not the service fallback. Keep PR housekeeping and Kubernetes implementation off this critical path.

### 3. High: the telemetry “port” hides a new instrumentation design and overstates the existing digest evidence

**Wrong or missing.** The old ACP instrumentation lives in code that Petri replaced. This is not just moving the exporter and adding an identical span in Fabro. Moreover, the checked carrier does not support the summary's claim that its `run_turn.command` already carries a digest of complete rendered bytes.

**Evidence checked.** At `8869e88`, `lib/crates/fabro-workflow/src/handler/llm/acp.rs:849,1055` builds `command_display = process_spec.to_string()` and emits command, node, visit, candidate index, and stop reason. `lib/crates/fabro-acp/src/command.rs:121` renders only shell-quoted program and args; it emits no environment digest. Petri launches the resolved command in `crates/attractor/steps/src/agent/backend.rs:95–149`, resolving secret references before `Client::spawn`; prompt turns are handled separately. Its ACP hooks are permission/tool-use hooks, not an existing replacement for the old turn span. The ratified contract at `SPECIFICATION/contracts.md:5999` requires comparison with the complete rendered-byte digest while excluding raw environment values.

**Change.** Make the telemetry child's first deliverable an exact emitter design: where actual launch and turn boundaries are observed; what defines a turn, retry, firing, and visit; how command/args and the agreed digest are derived; how success, errors, and cancellation terminate spans; and how context crosses server, worker, and executor boundaries. Decide whether a Fabro executor/observer extension is sufficient or a small Petri extension is required. Do not silently reconstruct an “executed command” solely from planned graph input. Add a discriminating digest test where an environment/config change changes the digest without exposing its value. A name-preserving span alone does not fulfill the contract.

### 4. High: one candidate span in Honeycomb cannot prove the Dispatcher verification path

**Wrong or missing.** The summary correctly restores telemetry to migration scope, but its proposed proof is much weaker than the consumer contract. The local guard currently cannot attribute a successful export reliably to the dispatch being checked, and it explicitly exempts `hp` from observation.

**Evidence checked.** `commands/_dispatcher_run_turn_guard.py::_observable_from_dispatch_record` returns false for factory name `hp`. `_dispatcher_run_turn_sink.py` accepts a global `fabro.run_turn` last-export timestamp as well as any matching IDs; its receiver fallback is also global. Concurrent legacy spans can therefore satisfy a candidate-era presence check without proving the candidate exported. `orchestrator-image/README.md:594–662` documents the global marker, remote observation limitations, and an unresolved marker anomaly. `_otel_enrich.py` also extracts run identity from legacy event names `Workflow run started` and `Sandbox initialized`; simply preserving raw IDs under new Petri event shapes does not preserve that join.

**Change.** Keep this verification work in **fabro-currency**, coordinated with the existing correlation plan. Prove a uniquely identified candidate dispatch across engine output, receiver ingestion, successful export, command/digest, trace parentage, and final guard evidence. Include two concurrent runs and a negative control where the candidate's exporter is disabled while legacy telemetry continues. Replace the hard-coded factory-name exception with the actual observation capability. Specify the receiver process and endpoint explicitly: the runbook pins the engine to Docker-bridge port 4318, whereas `_dispatcher_otel_wiring.py` can fall back to an ephemeral port and advertises that address to the sandbox. That fallback does not itself reconfigure a long-lived engine exporter. Prove both routes under a port collision and across the candidate/production overlap. If the guard remains advisory, say so; do not equate an advisory global liveness check with per-dispatch provenance.

### 5. High: the Docker cgroup bridge changes shared host policy and does not preserve the old resource envelope

**Wrong or missing.** “No fork” does not mean a low-risk bridge. A daemon-wide default cgroup parent applies to unrelated containers as well as Fabro. A memory-only aggregate cap leaves CPU, swap, process counts, disk growth, and I/O pressure unresolved. Multiple independently scheduled Fabro instances can each be within their own concurrency ceiling while exceeding the intended host budget.

**Evidence checked.** [Docker's daemon documentation](https://github.com/docker/cli/blob/master/docs/reference/dockerd.md#default-cgroup-parent) describes a default for all containers, different systemd/cgroupfs naming rules, and per-container overrides taking precedence. Driver `crates/sandbox-driver-docker/src/create.rs:155–172` sets memory and CPU only from `SandboxSpec.resources`, otherwise leaving host configuration defaults. The production workflow declares 4 CPU/8 GB in `.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml:405`. Research 006 separately configures the candidate scheduler at three runs. `contracts.md:4781` puts concurrency in the Fabro scheduler and forbids inventing a Dispatcher host-wide admission limiter. Docker's documented reloadable option list does not include `cgroup-parent`, so this needs a real restart/change-window assessment, not an assumed harmless reload.

**Change.** Give the bridge an owner, exact cgroup hierarchy and driver, total budgets, excluded infrastructure, restart/drain procedure, rollback, and expiration condition. Inventory every container using the daemon and every active scheduler, including candidate and any auxiliary instance. Reserve host control-plane capacity and size the **sum** of scheduler ceilings. Verify new and existing containers' actual cgroup membership; do not assume changing a default moves existing containers. Test a noisy/OOM canary, exit classification, reconcile, and absence of retry storms. Decide CPU and swap treatment explicitly and bound disk/PID pressure where relevant. If the shared daemon makes this too broad, compare a dedicated candidate daemon or a small resource-forwarding change before committing to the bridge.

I found no explicit per-run CPU/memory MUST in the searched current top-level spec prose. There is nevertheless a declared workflow allocation, an existing regression test, and a rollout promise to preserve Docker limits. Record their temporary changed meaning and acceptance criteria rather than letting a known red test disappear implicitly.

### 6. High: “Kubernetes replaces resource forwarding” is premature, and the wiring may require Petri changes

**Wrong or missing.** A future plugin does not close today's resource regression. Kubernetes enforces only the resource specification it receives; it cannot recover workflow resource settings discarded before plugin invocation. Treating issue 937 as solely Fabro registration work understates the boundary.

**Evidence checked.** Candidate `fabro-petri/src/engine.rs:195–217,460` accepts only Local/Docker/Daytona and forwards resource settings only for Daytona. Petri `backend.rs:15–85` has a closed `SandboxBackend` enum and no generic resource field; the same shape remains on Petri main `2548c104`. `routing.rs::plugin_kind` selects only Docker/Daytona for container execution. Its in-process path explicitly refuses missing providers instead of launching a plugin. The fixed-provider escape hatch defaults to Docker-style host addressing/workspace mounting, so it is not automatically a safe generic remote-provider solution. Container-spec construction in `executor-sandbox/src/lib.rs:479` also constructs Docker-specific provider configuration. [Issue 937](https://github.com/fabro-sh/fabro/issues/937) explicitly requires lifecycle, configuration, capability, network, recovery, and pruning consistency.

**Change.** Keep the resource gap open as an accepted, time-bounded bridge obligation until an actual replacement is demonstrated; supersede the implementation proposal without claiming the capability exists. In the Kubernetes plan, first prove the full path `workflow resources → Fabro → Petri → plugin SandboxSpec → pod requests/limits`, plus generic provider identity, network requirements, and retention. Identify which upstream component must change and how that change is consumed reproducibly. A no-new-Petri-fork preference is reasonable; assuming it makes Petri work unnecessary is not. Seek alignment on the minimal generic extension early, independently of building the backend.

### 7. High: protocol v2 is a local process/data-channel contract, not a remote JSON-RPC service

**Wrong or missing.** A pod API implementation and a protocol conformance test are not yet the required ACP execution design. The plugin normally belongs beside the Fabro worker, using Kubernetes remotely. Putting the plugin itself in an arbitrary pod or behind a network service does not satisfy the described transport.

**Evidence checked.** Driver [protocol v2](https://github.com/lithoscomputer/sandbox-driver/blob/7d1932b5fd758dbc67ae5a34aaed08d8733ddaba/docs/protocol.md), §§2, 5, 9, 11–12: control uses stdin/stdout; data uses authenticated Unix-domain sockets in a private directory; operations must interleave; cancellation has reserved capacity; output loss and termination uncertainty must be reported honestly. `channel.rs` validates peer credentials, and spawned clients bind trust to the plugin PID. Plugins start from a scrubbed environment and require a checksum or explicit development mode. Petri ACP requires a long-lived spawned process with writable stdin and readable stdout, not a buffered `exec` response.

**Change.** Specify the deployment topology and implement the plugin-side v2 transport using the existing Rust protocol library if practical. Keep kubeconfig and provider credentials in the host/plugin trust boundary. Bound the plugin host's own transport/capture memory: the documented maximum of two streams × 1,024 active I/O operations × 16 MiB retained output is 32 GiB if fully exercised, before other overhead; these are defaults to tune, not measured consumption, and pod limits would not contain that host process. Pin the executable and exact driver revision on every execution host, and test worker launch configuration, restart, and later attach, not just an interactive shell invocation. Scope capabilities to current factory needs: streamed stdio, exec, files, labels, lifecycle, and required network policy first. Explicitly refuse unsupported snapshots, PTY, live-process fork, or one-shot containers; do not build them merely because the protocol lists them. If one-shots are required, note that they promise the sandbox's workspace **and network namespace**, which a separate arbitrary Kubernetes Job would not provide.

### 8. High: retained workspace and stop/start semantics must be designed before reusing the old Kubernetes backend

**Wrong or missing.** Pod-per-run creation is the easy part. Petri expects durable sandbox identity, stop/start fencing, attach, retention, and later pruning. A terminated Kubernetes pod is not a restartable Docker container. Deleting a pod can erase the only implementation work before rescue runs. The proposed plan places rescue tooling after cutover; that is too late.

**Evidence checked.** Candidate `fabro-petri/src/engine.rs` selects `Retention::Always` and `LostSandbox::Refuse`. Petri `lease.rs:652–656` fences recovery with stop then start. `run.rs` uses labels `petri.run`, `petri.lease`, and `petri.workspace`; the last value is `<run>/<workspace>`, which also needs encoding before use as a [Kubernetes label value](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#syntax-and-character-set). The old [Kubernetes PR](https://github.com/mhermann/fabro/pull/4), merge `7c14f9ae`, constructs a `restart_policy: Never` pod running `sleep infinity`; its inspected `pod_manifest` has no durable workspace volume. Its shell execution control uses a stop-file watcher with automatic TERM→KILL escalation, whereas v2 gives escalation policy to the host.

**Change.** Define a logical sandbox identity independent of an individual pod UID, a workspace persistence choice, and precise stop/start/delete behavior. Translate labels losslessly through the driver's API, preserving provider-side list/filter and ownership checks; keep original values in annotations or another reversible representation where necessary. Test process cancellation without deleting unrelated work, worker crash/restart, API outage after create, ambiguous retries, node loss, original-workspace resume, retained attach, dump/rescue, and eventual cleanup. Put rescue and garbage-collection acceptance **before** Kubernetes default cutover. Reuse selected mechanics from the old backend, not its lifecycle assumptions. A PVC is one option, not proof that recovery works; local storage also requires an explicit node-affinity and node-loss policy.

### 9. High: k3s/Docker coexistence requires a shared capacity and network design

**Wrong or missing.** The plan recognizes coexistence as a question but schedules installation before answering it. Kubernetes scheduling does not automatically account for arbitrary Docker allocations outside its pods. Pod limits also do not protect a colocated control plane from disk exhaustion or uncontrolled non-pod workloads.

**Evidence checked.** The summary reports 16 cores/30 GB and load around 21; research 006 adds the second Fabro scheduler. [K3s requirements](https://docs.k3s.io/installation/requirements) call for control-plane resources and specific networking. [Kubernetes node reservation guidance](https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/) distinguishes allocatable pod resources, system reservation, kube reservation, and eviction thresholds. [K3s runtime guidance](https://docs.k3s.io/advanced#using-docker-as-the-container-runtime) says containerd is the default, so the proposed Docker slice does not automatically govern k3s pods. [K3s networking services](https://docs.k3s.io/networking/networking-services) documents default Traefik/ServiceLB use of ports 80/443 and network-policy iptables rules that can persist after disabling the controller.

**Change.** Before installing on hp, budget simultaneous legacy Docker, candidate Docker, Kubernetes pods, Fabro workers, k3s, OS, telemetry, and image-build/pull activity. Set reservations and eviction/storage thresholds consistent with the Docker slice; test under overlap load. At 8 GB **requests**, 30 GB hosts cannot schedule fifteen such pods; allow for a major concurrency change and pending-pod behavior. Choose containerd versus Docker deliberately, inventory ports/CIDRs, disable unneeded ingress/LB components, and validate Docker/Tailscale/CNI forwarding and firewall coexistence. Keep an out-of-band recovery path and an infrastructure rollback procedure that does not wipe Docker or tailnet rules. Do not remove the Docker protection until remaining legacy/rollback workloads have been addressed.

### 10. High: pod connectivity and credentials need a complete end-to-end contract, not only a Dolt TCP probe

**Wrong or missing.** “Same image” and “can reach Dolt” do not establish that a pod can execute the factory. The host wrapper and the sandbox credential projection are different mechanisms. Mounting the host's privileged wrapper setup or broad Kubernetes credentials into every sandbox would be an unnecessary new dependency.

**Evidence checked.** `.livespec.jsonc` names the host credential wrapper and current ACP catalog configuration. Petri `acp/command.rs::spec` resolves only named secret references into the launched agent environment. Driver protocol §11 scrubs plugin env and §14 explicitly defers `host/credentials`; its `access.vpn` field is a tombstone, not Tailscale integration. The repository's documented beads path is a guarded `/usr/local/bin/bd` consuming a bare password with repo-local connection pointers. Candidate research 006 records a legacy vault import removal date of October 11, so a later candidate cannot rely on recreating the current setup by copying the old vault file.

**Change.** Define which process receives each credential and by which existing channel. Prove fresh provisioning through supported secret APIs, inspect/dump/log redaction, expiry and refresh during a long run, GitHub App clone/push/PR behavior, OAuth-only ACP authentication, the guarded beads binary and correct tenant configuration, and cleanup of per-run credentials. Test DNS, API egress, registry pulls, SSH/tailnet routes where actually used, the telemetry receiver, and any callback from sandbox to worker; test from a second worker node, not just hp. Ensure `127.0.0.1` references are interpreted in the intended namespace. Registry credentials consumed by containerd are not automatically the pod's GitHub App token. Keep cluster-admin credentials and host privilege machinery outside the agent container unless a specific tested requirement justifies them.

### 11. High: PR 576 needs a new event-export design, and the current receiver cannot accept its logs

**Wrong or missing.** Preserving the PR number is fine; preserving the July implementation design literally is not. Nor can “carry the run_turn span on top” mean deleting its trace-export transport once a logs exporter exists.

**Evidence checked.** [Bryan's July 25 comment](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5079036739) asks to start with canonical events as OTel logs. The [August 2 reply](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5154982522) promises a non-blocking, redacted, bounded exporter. The archived sketch assumes `fabro-types::RunEvent`, old composition roots, and an old sink topology. Today's candidate projector lives in the server, folds both Petri and platform records after durable commit, and can replay records. Petri's event identity is `(log, seq, index)`; `recorded_at` and `observed_at` differ; replay is at-least-once and the live projector can overflow without failing a run. `commands/_otel_receive.py:78–79,267–279` accepts JSON traces and metrics only; `/v1/logs` returns 404. The runbook explicitly requires `http/json` for this receiver and strips credential-bearing exporter headers from workers.

**Change.** Rewrite 576 around an explicit current event contract: which Petri and Fabro platform events are exported; export location; stable IDs; replay/deduplication; timestamp mapping; redaction boundary; bounded buffering; outage/drop reporting; and shutdown/flush order. Do not put collector latency in the projection transaction or export the same event from both server and worker accidentally. Choose whether logs go to a standard collector or a separately implemented receiver route, and test the actual wire encoding. Preserve the trace exporter, propagation, and consumer path independently until trace consumers migrate through an explicit contract change. Logs can carry command/digest fields, but adding those fields does not make a log record satisfy today's span sink. Keep the fork's strict header handling unless deliberately revisited; the old sketch's broader worker-header forwarding is not automatically appropriate here.

A pushed rewrite can legitimately complete a contribution milestone. It does not retire a production carry until the required behavior is available in an eligible upstream release and passes factory qualification. Assign ongoing ownership and dated review of that carry after the milestone.

### 12. High: “cut over default_factory” is not a fleet cutover or a historical-state migration

**Wrong or missing.** A single repository's default change does not reroute all tenants sharing hp, and stopping the legacy service leaves historical runs, retained workspaces, console links, and rescue references with an access problem. A retained binary and directory are necessary but not a complete historical-read procedure.

**Evidence checked.** `.livespec.jsonc:516–531` currently inventories only `hp` at port 32276 and documents per-factory client compatibility; it says unnamed reconciliation surveys the active inventory. Research 005 acknowledges different client generations and in-flight runs pinned to their original factory. Research 006 identifies a hand-installed candidate unit and an Ansible role in **livespec-dev-tooling** that currently shares one binary path across instances. The stores differ: old SlateDB versus candidate SQLite. Existing plan notes say fleet workspaces with a factories block default to `hp`. The cross-tenant citation scan does not inventory those runtime consumers.

**Change.** Make the bundle explicitly own a fleet target/client/configuration map, infrastructure-role changes, candidate registration, promotion strategy, and drain verification across all tenants. Decide whether the stable `hp` name/endpoint is promoted or every consumer changes, preserving original-run routing either way. Verify timers, console, automated reconcile, backups, and rescue commands against both generations. Define how historical runs remain inspectable after the legacy service stops, including authentication, exports, and storage-compatible tooling, without silently running the expired engine for new work. Specify rollback as restoring a coherent binary/config/store/client tuple; reverting one PR is sufficient only if that full tuple remains available and all consumers honor the routing change.

### 13. Medium-high: the fallback plan is not automatically unblocked by removing its engine capability

**Wrong or missing.** The summary simultaneously defers cross-candidate fallback and claims the remaining model-fallback proof needs only a current engine. That dependency is behavioral, not just temporal.

**Evidence checked.** Research 005 says the candidate fallback carry is deferred because no production dispatch uses it. The fallback plan's `post-ratification-slice-research-2026-09-09.md` calls for a capability-bearing build and a controlled journey that advances candidates. Its S7a receipt identifies `acp.fallback_chain.v1` and `acp.candidate_config_options.v1` on the old carrier. `commands/_acp_capability_gate.py` correctly refuses new chain grammar when the resolved server does not advertise those capabilities. Petri's inspected ACP backend selects one command and warns that model/provider/effort node fields are observer metadata; upgrading the engine alone is not evidence of ordered candidate failover. I did not read `bd-ib-vuwrv5`'s latest ledger criteria, so a later narrowed scope remains possible.

**Change.** Before promising this unblock, compare that item's actual current acceptance criteria with the exact surviving carry inventory. Either explicitly defer/regroom its unsupported proof or identify the replacement capability and add the proper prerequisite. Do not reintroduce unused fallback into the November migration merely to preserve an old plan's closure story. Also reconcile the older S7a claim that vps would return during P6 with the newer explicit retirement scope.

### 14. Medium-high: factory identity must remain distinct from node and pod identity

**Wrong or missing.** Redefining the existing factory attribute as “node/pod” destroys the question it currently answers. A factory endpoint can schedule many pods on many nodes; two runs on different nodes may still belong to the same factory.

**Evidence checked.** The correlation plan's `00-opening-brief.md` explicitly separates “same factory” from “same sandbox” and demands two deliberately different factory inputs as a control. `commands/_otel_enrich.py:102–107` models `livespec.dispatch.factory` alongside work-item, dispatch, and Fabro run IDs. Its join cache is keyed first by work item and preserves previously known values, which deserves a repeat-dispatch test when the same item changes factory.

**Change.** Preserve `livespec.dispatch.factory` as the resolved stable factory identity. Add separate cluster, node, namespace, pod UID, and sandbox/lease identity fields where useful. Prove two candidate dispatches with different factory inputs on the **current engine** as part of telemetry qualification; assign the owner now. Later prove same-factory/different-node and restart/new-pod cases in the Kubernetes plan. Test repeated dispatch of the same work item so stale cached correlation cannot mislabel the second run. Do not archive the correlation plan merely because one span contains a nonempty constant.

### 15. Medium: fork cleanup is not a prerequisite for the new carrier and can destroy evidence the migration needs

**Wrong or missing.** Deleting a fixed count of branches/worktrees is the wrong acceptance criterion. Some worktrees contain uncommitted and untracked files or an unresolved rebase; the September recovery bundle cannot be assumed to preserve today's dirty state. The OTLP PR head is explicitly needed again. Cleanup before porting removes useful comparisons without advancing currency.

**Evidence checked.** The September hygiene note records an unresolved `trial-rebase`, unpublished work, and shared target-cache use by `factory-wave-c`. Current read-only status still shows unresolved merge paths in `trial-rebase`; `instrument-v0254` contains numerous modifications plus an untracked `otel.rs` and target directory. Current `git worktree list` reports eight entries total, including the primary, rather than the summary's nine. The `factory-integration` worktree is detached at the old serving commit. The existing archived bundle specifically preserves prior refs and a particular two-file patch, not an assertion that every current untracked artifact is recoverable.

**Change.** Separate inventory/preservation from deletion. Freeze exact outgoing carrier and PR-head SHAs, preserve current dirty/untracked evidence with a tested recovery manifest, check active processes and shared cache users, then retire only disposable worktrees after successor behavior is proven. Build the new carrier in a fresh isolated worktree; reconcile how it is published onto the standing `factory-integration` authority without racing another session. Use an explicit expected remote head when eventually rewriting 576. Put broad branch housekeeping after the qualified bundle or in nonblocking follow-up work. Preserve only artifacts with a stated recovery purpose, rather than keeping every old branch indefinitely.

### 16. Medium: contribution ownership and post-cutover maintenance are missing from the split

**Wrong or missing.** “Offer upstream later” and “archive after cutover” can recreate the permanent fork the maintainer is trying to escape. The plan currently risks two separate telemetry implementations, generic plugin wiring, a Kubernetes plugin, host infrastructure, and a resource workaround without a lifecycle owner for each.

**Evidence checked.** [Issue 937](https://github.com/fabro-sh/fabro/issues/937) already supplies upstream's generic integration requirements; [the closure of 567](https://github.com/fabro-sh/fabro/pull/567#issuecomment-6043751434) assigns backend maintenance/distribution to plugin authors. `SPECIFICATION/constraints.md:108–122` requires a disposition, owner, and review-by date within 30 days for every carry. Existing carry inventory rows have October 14 review dates. The newer `v0.381` keeps the candidate's Petri revision but updates sandbox-driver to `5663536c`, demonstrating that the transitive integration surface can change independently even across a small Fabro upgrade.

**Change.** Keep two delivery plans, but add an explicit continuing maintenance obligation: weekly currency observation, a tagged-candidate qualification matrix, carry review, and a reproducible lockfile/build manifest. Upstream alignment on 937 should happen early; it need not block local implementation or require upstream merge before deployment. Assign backend releases, checksums, protocol compatibility, and incident maintenance to the Kubernetes repository; generic integration belongs with Fabro/Petri, and hp provisioning belongs with the infrastructure owner. Keep 576's contribution milestone in fabro-currency if desired, but do not let upstream response time block service cutover, and do not archive unresolved maintenance obligations without a named successor.

### 17. Medium: the evidence narrative needs small corrections and stronger absence controls

**Wrong or missing.** Several statements are broader or staler than the checked evidence. Individually they are minor; together they can send the next implementer to the wrong boundary or convince them a dependency does not exist.

**Evidence checked.** Candidate `lib/components/fabro-dot/src/lib.rs:16` explicitly says it and `fabro-petri` are the **two** places importing Petri, contradicting the “one crate” assertion. GitHub records the Kubernetes PR's merge at `2026-09-11T06:26:37Z`, not September 10. The newest published release is now October 9's v0.381. The correlation opening brief asks for two distinct inputs, not just one hp run. The scope notes themselves identify a required livespec-dev-tooling Ansible change even though the summary's cross-tenant reference scan reports no external dependencies. A GitHub issue search across the three upstream repositories found no Kubernetes issues, but that cannot establish that nobody is privately developing a backend.

**Change.** Replace “nobody upstream is building” with “no published implementation or commitment found in the checked sources.” Separate observed live facts, source facts, historical notes, and proposed acceptance. Preserve evidence timestamps and exact revisions. Scan dependencies by consumed API, runtime target, credentials, image, and infrastructure ownership as well as text references to the plan. Avoid using Daytona's ownership/history as a proxy for either backend fitness or upstream acceptance; the meaningful strategic choice is to own compute and minimize the integration code the factory must maintain.

### Suggested corrected plan boundary

| Owner | Required outcome |
| --- | --- |
| **fabro-currency, before default cutover** | Native secrets; exact current eligible carrier and reproducible image; target-aware currency admission; documented/tested Docker bridge; real command/digest and correlated telemetry; infrastructure/client/fleet routing; acceptance journeys and rescue; an explicit rollback procedure. |
| **fabro-currency, retirement milestone** | Completed soak before November 14; old admission stopped and active inventory reconciled; historical evidence readable; a current-generation rollback available; fresh release/carry evidence. |
| **fabro-currency, nonblocking contribution work** | 576 rewritten against current event architecture, 688 dispositioned, dated carry ownership and contribution follow-up. Broad fork deletion follows preservation and qualification. |
| **kubernetes-sandbox-backend, before hp installation** | Minimal capability contract; generic Fabro/Petri extension design; resource propagation; logical sandbox/workspace lifecycle; coexistence budget, network/security design, and infrastructure ownership. |
| **kubernetes-sandbox-backend, before default cutover** | Pinned local plugin, protocol and full Fabro lifecycle proofs, pod resource enforcement, retained-workspace recovery, credentials/telemetry from another node, operational rescue and cleanup, and a proven Docker fallback. |
| **correlation plan** | Current-engine discriminating proof owned and scheduled now; stable factory semantics retained. Kubernetes adds placement dimensions rather than redefining factory identity. |

The most useful immediate change is to replace “finish secrets, then bundle” with a short, owned closure matrix for the actual acceptance obligations above. The highest-risk unknowns are now identifiable source seams and operator proofs, not a general need to investigate Kubernetes further.

## Part C — corrections adopted

## Corrections after the independent review, 2026-10-10

Each entry: the reviewer's finding, what I verified, the correction adopted.

### Confirmed and adopted

1. Engine-currency admission is NOT implemented. The only currency code
   (`_dispatcher_staleness_gate.py`) gates the PLUGIN build against its
   release branch; nothing implements contracts.md "Fabro currency
   admission" (release-tag ancestry, publication window, the 2026-11-14
   exception). bd-ib-j9x is therefore NOT deferred: it is regroomed in
   fabro-currency into "implement the ratified Fabro currency admission
   predicate" and stays a blocker of the bundle. Nov 14 is a policy
   deadline today, not a technical safeguard.
2. Window math. 14 upstream releases in the last 30 days. The candidate
   v0.378.0-nightly.0 was published 2026-10-06; it leaves the 30-day window
   when a release published after 2026-11-05 is observed. The cutover must
   land on a tag qualified inside the window, and staying current is a
   standing re-pin cadence, not one event. Research 005 requires a week of
   soak and legacy retirement before Nov 14, so cutover no later than
   ~Nov 7, and a Petri-era rollback build must exist for after Nov 14.
3. run_turn carries `command` (shell-quoted program and args) and no
   digest. The contract's digest clause is unmet on the carrier too. The
   telemetry child starts with an emitter design, not a port.
4. The run-turn guard exempts factory `hp` (`_observable_from_dispatch_record`)
   and the sink matches on a global last-export key. So for production
   dispatches the guard observes nothing; the live consumers of engine
   spans are Honeycomb and the ratified contract, not the guard. The
   telemetry proof must be a uniquely identified candidate dispatch traced
   end to end, with a negative control.
5. bd-ib-vuwrv5 (model fallback) requires a refused primary and a fallback
   finishing the same node visit on hp; that needs the ordered-fallback
   capability r5cnjd deferred. The cutover does NOT unblock it. Correction
   recorded on the item; the regroom is that plan's call.
6. Vault import removal 2026-10-11 (research 006): tags after that do not
   read the legacy vault, so native secrets (bd-ib-4ipmub) is a prerequisite
   for re-qualifying ANY newer tag, which item 2 makes mandatory.
7. Ansible role `fabro_server` in livespec-dev-tooling hardcodes one binary
   path; the bundle has an external-repo dependency my text scan could not
   see. Already named in sxcnj7; now explicit.
8. The receiver accepts /v1/traces and /v1/metrics only; a logs-based 576
   rewrite cannot feed it. The trace exporter stays until an explicit
   consumer change.
9. Docker cgroup bridge is a shared-daemon policy change needing an owner,
   budgets, restart window, canary and expiry; and k3s pods are containerd,
   not covered by the Docker slice. Both moved to explicit items.
10. Kubernetes does not close today's resource gap until the full path
    workflow resources -> Fabro -> Petri -> plugin spec -> pod limits is
    proven; Petri's SandboxOptions has no generic resource field and
    routing selects only Docker/Daytona for container execution. The
    Kubernetes plan starts with the generic extension design.
11. Protocol v2 is a local stdin/stdout + Unix-socket contract; the plugin
    runs beside the worker and talks to the cluster remotely.
12. Retained-workspace / stop-start / rescue semantics must be designed
    before cutover, not after.
13. Fork cleanup: preservation and inventory first, deletion after the
    bundle is qualified; `otlp-span-export` head is needed again.
14. Factory identity stays `livespec.dispatch.factory`; node/pod are added
    dimensions, not a redefinition.
15. Minor: fabro-dot also imports Petri (two crates, not one); the Kubernetes
    fork PR merged 2026-09-11; "nobody upstream is building" becomes "no
    published implementation or commitment found".

### Rejected or narrowed

- None rejected outright. Finding 12 (fleet cutover) is narrowed: only hp
  is in `.livespec.jsonc` factories now, so the routing change is the hp
  endpoint promotion plus the Ansible role; historical-run readability is
  adopted as a bundle criterion.
