# 003 — How work reaches the factory, and which host holds the controls

[Back to index](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/README.md)

**Archived — supporting research, 25 October 2026.** Retained as evidence for the current reports. Observations and source checks describe that date, not a fresh assessment of the running system.

Research for `dispatch-control-plane`, plan anchor `bd-ib-k6dqwc`. Read-only observations on **2026-10-25, starting 01:30 UTC**. This note is the only authored artifact. Paths below describe the system observed, not a proposed replacement.

## Answer

**Work currently reaches the factory primarily through interactive plan seats and their detached, uncommitted `tmp/petri-canary/dispatch-dual-r681b.sh` launchers, which invoke the installed `drive --action impl:<id>` and thereby a bounded Dispatcher `loop`.** At 01:32:49Z, `ps -eo pid,ppid,etimes,args` showed 16 distinct item-launcher jobs using that tmp script, three `drive` processes with three corresponding one-item loops, one explicit `dispatcher.py resume`, and the reconcile timer's process; it showed no console executable or unscoped queue-drain loop. In this repository's journal window **2026-10-24T01:30:00Z–2026-10-25T01:33:00Z**, 15/18 `dispatch-run-stamp` rows carried `claude:petri-factory-on-gmktec`, one carried `seat:spec-implementation-lockstep`, and two were unattributed. These are launch records for this tenant, not completed throughput or a fleet census. The unattended queue drain exists, but needs an invoker: its committed `work-supply@` timer is not installed here. The console can dispatch today, through real Dispatcher subprocess ports, but its fleet-control track is on hold and no console process appeared in the snapshot. The overseer daemon is alive and keeps interactive sessions resumable; the foreman skill was removed, while the supervisor pair-member role still survives. Committing `fleet-launch/` has preserved launcher code, **not its operational state or its live adoption**: cap, hold, tickets, markers, credential selection, install registry, and decision-bearing journal history remain local. Evidence: process sample §2; journal lines 500742–503725; `O/_drive_impl_dispatch.py:89`; `fleet-launch/README.md:1`; `V/plan/remove-supervisor-skill/research/001-what-supervisor-resolves-to-and-the-cut.md`; detailed citations follow.

## Reading this map

Source aliases keep citations readable:

- **O/** = `/data/projects/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`.
- **C/** = `/data/projects/livespec-console-beads-fabro/`.
- **V/** = `/data/projects/livespec-overseer/`.
- Unqualified repository paths are in `/data/projects/livespec-orchestrator-beads-fabro`.
- **D-state** in the table means the Dispatcher state detailed in §3 and §18: `tmp/fabro-dispatch-journal.jsonl`, `tmp/fabro-dispatch-<id>.lock`, the per-user tenant-checkout registry, factory registry and client/auth installation, credential wrapper and credentials, retained plugin payload, and generated run files. It does **not** mean all these files are consulted in every branch.

“Portable” asks two questions. A bare fresh checkout has no host services, credentials, plugin registration or executable installation; those prerequisites already prevent equivalent execution. **Even after those prerequisites are provisioned and the same ledger/forge/factories are reachable**, an empty `tmp/` and a different host-local state set can change dispatch, hold, ordering and recovery decisions. The table identifies the latter differences instead of attributing every failure to missing credentials. Remote ledger records, GitHub PR/proof records and factory-native run/availability evidence are separate from host-local state.

The source baseline observed was orchestrator `dbdbfebf9347c73e59f901b1daa93d0d5ecec818` (2026-10-25T02:04:21+01:00), console `1780428146191f4206f7dd6b0152a20ae1ad6901` (2026-10-24T09:43:47Z), and overseer `877784a8619c6bbe7dd07e926b23bd9c58426b25` (2026-10-25T00:11:20+02:00). Long-lived processes can execute earlier builds. The observations below distinguish checkout source, installed build, and running process.

## 1. Surface matrix

Every row has the same fields. A helper that releases a hold, transports a command or supplies proof is included because it changes whether the next dispatch can happen, even if it creates no run itself.

| Surface | Entry point | Invoker | Decides whether to dispatch | Host-local reads | Host-local writes | Portable to fresh host / empty tmp? | Committed / specified status |
|---|---|---|---|---|---|---|---|
| Explicit Dispatcher dispatch | `dispatcher.py dispatch --repo R --item ID` | Human, agent, canary script | Named item; preflights/wall/admission; explicit operator path does not enforce drain WIP cap | D-state, repo config/workflow/spec | Journal, locks, payload/goal/overlay, source/janitor worktrees; also ledger/forge/run effects | **No**: missing history changes holds/recovery; host registry/client/auth must exist | Committed; `SPECIFICATION/contracts.md`, Dispatcher invocation/admission clauses |
| Dispatcher queue drain | `dispatcher.py loop --repo R --budget N [--parallel K] [--item ID]` | Caller, console, seat, optional timer | Ranked readiness, blockers, budget, WIP accounting, rework selection, wall and candidate availability/headroom | D-state; ledger and config | D-state outputs and admitted-item lifecycle effects | **No**: local accounting/history changes; no persistent engine starts merely from checkout | Committed and specified; `O/_dispatcher_loop_command.py:87` |
| `drive impl` | `drive.py --repo R --action impl:ID` | Operator or agent session, including seat launcher | Routes into **cap-enforcing** `loop --budget 1 --parallel 1 --item ID` | Installed plugin/payload, then D-state | Captured subprocess output plus delegated D-state writes | **No**, same downstream dependencies | Committed, specified published action; `O/_drive_impl_dispatch.py:89` |
| Run reconciliation / timer | `dispatcher.py reconcile-runs`; system `reconcile-runs.timer` | Root-manager timer runs service as `ubuntu`; also dispatch preamble | Does not select new work; classifies orphan runs, stranded claims and drift frontier | Journal ownership/history, ledger metadata, locks/PIDs/host identity, config/registry, remote boards | Journal/pass telemetry; recovery effects, ledger comments/status/claims and remote termination where authorized | **No**: different ownership/replay evidence and host identity; unit installation is separate | Code/templates/spec committed; rendered units host-local; observed enabled/running |
| Merged-item reconciliation | `dispatcher.py reconcile-merged --item ID [--regrade]` | Human or supervising seat | Already-merged PR and lifecycle/acceptance evidence; **no new implementation run** | Repo integration config, local checkout; merge/proof records from forge/ledger | Invocation/outcome journal, retained janitor evidence, janitor worktree, primary refresh; ledger acceptance | **No** equivalent local venue/evidence; durable PR proof can survive | Committed and specified; `O/_dispatcher_reconcile_merged.py:98` |
| Explicit run continuation | `dispatcher.py resume --item ID` | Seat/human, sometimes recovery routing | Published PR/head/proof/cancel anchor, run liveness, same-criteria and bounded-resume checks | Journal's cancel/release/resume/workflow history, lock; config/client/auth; forge/factory | Resume/dispatch journal, lock, new run and lifecycle effects | **No**: some anchors survive on PR, but local cancellation/history/lock evidence does not | Committed and specified; added to brief's starting list; observed live |
| Clock-fired work supply | `work-supply@TENANT.timer` → `work-supply-pass.sh` → transient unit → `loop` | System timer, if installed | Timer only starts an ordinary unattended drain; Dispatcher decides admission | `/etc/livespec/work-supply/*.env`, unit/drop-in, operator's plugin registry/cache, wrapper; D-state downstream | Transient system unit and journal; downstream D-state | **No**: no installed timer/instance/registration on fresh host; history still differs | Committed and specified; **not installed/loaded here**; added surface |
| Console | `livespec-console-beads-fabro serve` / `tui`, operator dispatch/drain action | Human; pending recorded command is executed by console | Operator command; console checks ready-evidence emptiness for drain; Dispatcher owns eligibility/autonomy | SQLite store/checkpoints; selected repo journal/config; plugin registry/cache, executables/wrapper; remote source adapters | SQLite commands/events/checkpoints; delegated loop/drive writes | **No**: loses commands/history/checkpoints and journal facts; can rebuild some current facts from remote sources | Committed, specified TUI; future GUI/API language is not proof of a running web scheduler |
| Interactive overseer and `overseerd` | `livespec-overseer:overseer`, top daemon/bottom operator pane | Human starts/adopts; deterministic daemon restarts declared-ready seats | No independent next-work selection; keeps tracked sessions alive; resumed seat can dispatch | `~/.livespec-overseer*.{json,jsonl}`, repo `tmp/overseer/`, `/proc`, terminal backend, session transcripts, ledger epic | Mapping/stamps, declarations/round state, rotated daemon log; terminal input/replacement | **No**: mappings, pane identities, ready declarations and restart interlocks are host-specific | Committed and specified; alive; not retired with foreman |
| Backlog drain operation | `livespec-overseer:drain-backlog` → `scripts/drain-backlog/engine-on-green.sh` | Interactive LLM session with ruled batches and its tick/monitor | Frozen scope + rulings; launcher adds credential/exhaustion/master-green gate; then Dispatcher | `tmp/drain-backlog/{snapshot,dispositions,handoff,last-tick,...}`, engine logs/journal, cache, credentials, remote PR/CI | Same tmp tree, detached engine logs; ledger handoffs/dispositions if epic bound | **No**: snapshot/remaining queue/tick cursor may be lost; no-epic mode also loses handoff/rulings | Committed prose/scripts; current launcher contains a caller-CI gate conflicting with current orchestrator rule |
| Account rotation | `livespec-overseer:caam-anthropic-loop` and session recurring job | Human or runtime Cron job | Chooses usable account/headroom, not work-item; affects downstream eligibility and hold-release watcher | caam vault, live credentials, rotation state/baselines, session state and provider usage | Rotation state/lock, live credential on switch, selected-account record, session/model actions as applicable | **No**: vault/history/active profile and session-only schedule do not accompany clone | Committed, specified; live Herdr runner tab; no pass executed for this research |
| Coordinator and specialist seats | Herdr tabs; plan resume; cross-session instructions | Human steering + LLM tick loops | Recorded mandates, ranked work, fleet budget/holds, launch order, runtime findings | Ledger handoffs/rulings plus local boards/cap/queues/markers/logs and session context | Ledger comments/handoffs; edits cap/hold; starts detached launchers and logs | **No**: ledger survives, operational files/terminal session and transient instructions do not | General operations specified; evolved coordination protocol partly ledger-only; analysis/charter committed |
| Current tmp launcher | `tmp/petri-canary/dispatch-dual-r681b.sh ID` | Seat, usually via `just gate-start` | Ready set, fleet cap, DoD preflight, factory count/CPU, FIFO/mutex/binding marker, credentials; hold for petri branch | `fleet-cap`, `hold-gmktec`, queues/holder/markers, installed build, boards, remote CPU/credential file | Tickets/holder/marker; preflight, JSON/stderr/verdict/capture files; refreshes checkout; delegates drive | **No**: file absent → no launcher; cap absent → zero/no launch; hold loss can unpause; order/markers lost | **Uncommitted**; pattern now specified provisionally, but not every historical variant is sanctioned |
| Other tmp launchers/chains/probes | Inventory in §19 | Seats, detached chains; most not running in sampled population | Item/queue files, previous logs/exit states, fixed rulings, release/PR/headroom/cap waits; then a named launcher | Script-specific local files listed in inventory, plus delegated dependencies | Queue-handled logs/active lists, preflight/capture outputs; some mutate cap/hold | **No**: missing scripts/queue/cursors/old-build/worktree paths change or stop work | Uncommitted; inventory is observation, not endorsement or proof each is executable now |
| Provisional committed launcher | `fleet-launch/dispatch-dual.sh ID` | Intended seat launch from master via gate runner | Same provisional caller concerns; host config centralized; **hold applies to both targets** | `fleet-launch/config.sh`; default state still `tmp/petri-canary`; shared `/run/user/1000` dirs; registry/cache/client/wrapper | Tickets/holder/marker, preflight, JSON/stderr/verdict/capture; refreshes checkout; drive | **No** equivalent state, despite portable code and env overrides | Committed `04b13b2ed` 2026-10-24; spec v207; live cutover unfinished |
| Hold-release helper | `fleet-launch/release-hold-on-caam-rotation.sh` or tmp copy | Seat-started watcher | Profile changed away from held profile; bounded wait | Hold-file existence, `caam status claude` | Deletes hold when condition met; stdout log | **No**: missing hold means “already removed”, different active profile changes release | Committed helper + uncommitted predecessor; caller mechanism named in provisional spec |
| Launch proof helpers | `host-capture-payload.py`, `ready-set-check.py`, wrapper shims, default-factory resolver | Seat/launcher | Helpers supply readiness/proof/credential venue; no scheduler | Launcher evidence/journal, plugin/factory registries, repo config and remote proof; wrapper argv | Payload JSON; resolver fetch updates Git refs; readiness only reads; wrapper may update its cache | **No**: capture evidence and host registrations absent | Committed under `fleet-launch/`, tmp predecessors still present |
| Plan session continuation | `plan` → `resume_directive`; `LIVESPEC_PLAN_UNATTENDED=1` on daemon restart | Attended or restarted interactive seat | Typed ledger `next_action`, required result, authority/budget/liveness; `impl` → drive, `await` → bounded observation | Host session/env and underlying D-state; **plan state itself is ledger-held** | Sanctioned pointer/timeline updates when required; delegated dispatch/wait artifacts | **Partly**: pointer/handoff portable through ledger; local dispatcher and restart context not equivalent | Committed and specified; `.claude-plugin/prose/plan.md:243` |
| `implement` and host-only driver door | `implement`; `drive driver-dispatch:ID` | Human/agent | Product work normally routes to drive; explicit exceptions route in-session; driver door restricted to ready host-only set | Work-item/config/session, journal, host checkout | Factory path delegates D-state; host-only door journals and changes lifecycle, creates **no Fabro run** | **No** host state; do not count host-only work as factory throughput | Committed/spec'd; added boundary surface |
| Automated groom door | `groom.groom_dispatch(repo,item,variant,journal)` then dispatch under groom pin | Groom front-end operator | Backlog item + groom-kind variant + size decision; unattended drain cannot independently pick arbitrary backlog | Config/variant, item, local claim/lock | Ledger workflow pin/status, local lock and `groom-dispatch` journal; later ordinary dispatch | **No**: partial door recognition depends on local claim; pin alone is not a running factory | Committed/spec'd package entry; added door, not observed running |
| Detachment transports | `just gate-start -- COMMAND`; `V/scripts/detached-dispatch.sh RUN_DIR -- COMMAND` | Seat | Transport command survival/verdict; overseer script also runs acceptance guard | Repo common Git dir, passed command; overseer guard reads item record/labels | `tmp/gate-runs/ID/{pid,started_at,output.log,exit_code,...}` or `RUN_DIR/{pid,output.log,verdict.env}` | **No**: lose verdict/monitor handle even if remote run continues | Committed; necessary operational path, not a new scheduling authority |
| Container/canary adapters | `orchestrator-image/real-work-dispatch.sh ... --run`; `just canary-dispatch FACTORY` | Operator/rehearsal | Explicit target/item or filed canary, then ordinary Dispatcher | Container image/volume, host auth/client/env; config, registries/tenant pointer inside clone | Container clones/metadata/run state/journal/log; canary ledger record and ordinary dispatch | **No** identical history from a fresh container; fresh cloning is not state portability | Committed/spec/test substrates; added; no such adapter process observed in sample |
| Retired foreman / supervise-plan skills | Historical skills, **not current entry points** | Previously per-repo foreman / attended supervisor | Foreman proposed bounded actions through actuator; supervise-plan authored binder | Historical runtime/heartbeat/panel/binder files | Historical actuator journal, runtime/panel state, ledger binder | **No**; obsolete entry points cannot be restored by checkout of current source | Removed 2026-09-06; surviving pair-member role treated separately in §8 |

## 2. What is actually running, and what “most” means

At **01:32:49Z**, the full host `ps -eo pid,ppid,etimes,args` snapshot, filtered by executable and script argument rather than counting shell command text, yielded these examples:

| Process | Parent and role | Observed command / identity |
|---|---|---|
| PID 2032940 | Seat launcher | `bash .../tmp/petri-canary/dispatch-dual-r681b.sh bd-ib-aehdnb` |
| PID 3610485 | Under that launcher, via wrapper | Installed `367598dfff84/scripts/bin/drive.py --repo ... --action impl:bd-ib-aehdnb --invoker claude:petri-factory-on-gmktec --json` |
| PID 3627890 | Child of 3610485 | `/tmp/...payload-0.241.1-.../payload/scripts/bin/dispatcher.py loop --budget 1 --parallel 1 --item bd-ib-aehdnb` |
| PID 1711953 | Child of that loop, earlier 01:30:40Z snapshot | Petri client `fabro run ... --label work.item.id=bd-ib-aehdnb --label livespec.dispatch.id=2ae37ffc78aa43c3a08d2a10d35c020a --server https://gmktec-xubuntu.perch-rudd.ts.net:32276` |
| PIDs 1086721 → 645462 → 657549 | Another launcher → drive → loop | `livespec-dev-tooling-ebtm6t`, installed/payload release 0.241.4; same petri-seat invoker |
| PIDs 1087087 → 860899 → 868869 | Another launcher → drive → loop | `livespec-dev-tooling-tlfc3w`, same registered build and invoker |
| PID 738768 | Detached gate/wrapper ancestry | `dispatcher.py resume ... --factory petri --item bd-ib-h5jr5x --invoker claude:petri-factory-on-gmktec` |
| PID 1036096 | System service/wrapper ancestry | Source-checkout `dispatcher.py reconcile-runs ... --invoker timer:reconcile-runs` |
| PID 1095450 | Long-running daemon | `~/.local/share/livespec-overseer/runtime/6f5cbeafcda570f86a549716d373f5d391719497/venv/bin/overseerd` |

The 17 matching bash processes represented **16 distinct launcher items**, because one was a transient subshell of the same launcher. The distinct item set was `bd-ib-nvhqyq`, `bd-ib-nz4av6`, `bd-ib-idpr32`, `bd-ib-3kqdln`, `livespec-dev-tooling-ebtm6t`, `livespec-dev-tooling-tlfc3w`, `bd-ib-eqiw4f`, `bd-ib-aehdnb`, `bd-ib-7nx7p3`, `bd-ib-nf4wwb`, `livespec-dev-tooling-vdleg7`, `bd-ib-yzk2h2`, `bd-ib-wnrird`, `livespec-runtime-gfhy2a`, `bd-ib-hfi52b`, and `livespec-dev-tooling-hrdj6s`. All named `tmp/petri-canary/dispatch-dual-r681b.sh`; none named `fleet-launch/dispatch-dual.sh`.

**Absence scope/control:** the same full process population successfully found the eight Python drive/dispatcher processes and the actual overseerd executable. Among Python Dispatcher `loop` argv, every hit had `--item`, `--budget 1`, and a drive parent. Among executable names, no token contained `livespec-console`; among bash script arguments under `petri-canary/` or `fleet-launch/`, the only script was r681b. This does not establish that no remote console, differently wrapped process, or future tick exists. It does establish which launch path was occupying this host at that instant. No script was executed to obtain the inventory.

Journal attribution was measured by parsing valid JSON and selecting **stage**, not by counting all lines. The file was approximately 326 MB with 503,988 parsed rows at the first scan; its tail was dominated by watchdog polls. Last-500-row invoker counts (474 petri-seat rows) would therefore be a misleading throughput denominator. In the fixed window above:

| Stage | Petri-seat invoker | Other named seat | Unattributed | Total |
|---|---:|---:|---:|---:|
| `dispatch-id` | 15 | 2 | 7 | 24 |
| `dispatch-run-stamp` | 15 | 1 | 2 | 18 |
| `loop-pick` | 15 | 0 | 7 | 22 |

Examples of launch stamps are line **503588**, 2026-10-24T23:13:03Z, `bd-ib-aty2ay`, run `01M5R30EFBDRJ1TK0RTWJSW8QX`; **503668**, 23:27:42Z, `bd-ib-36d3x5`, run `01M5R3TPGV3NSNSK30K9KR31Z2`; **503725**, 23:34:17Z, `bd-ib-aehdnb`, run `01M5R46VD306FWW04R6H2MX92J`. All three have the petri-seat invoker. `dispatch-id` precedes run creation and cannot itself prove a submitted run. An opaque invoker is asserted attribution, not cryptographic proof of a human or a seat; `O/_dispatcher_journal_file.py:58` stamps the identity supplied by the invocation, and `SPECIFICATION/contracts.md:4215` describes identity strings as opaque.

## 3. Dispatcher dispatch, drain, and drive

### Explicit `dispatch --item`

The direct path is a materially different operator choice from `drive impl`. `O/_dispatcher_admission.py:145` explicitly documents that targeted `dispatch --item` uses `enforce_cap=False`; `drive` routes through the cap-enforcing drain. This difference belongs in a control-plane map because replacing one command with the other changes admission, even on the same host. It does not remove the shared source/CI/wall/credential/eligibility protections. The direct canary wrapper uses this operator path (`dev-tooling/just-canary-dispatch.sh:124`).

### The “auto loop” is a bounded engine with an external starter

`O/_dispatcher_loop_command.py:87` starts a pass, selects candidates up to `args.budget`, dispatches the wave, processes outcomes and returns. `--parallel` bounds concurrency within that pass. Selection is the common ranked ready predicate, narrowed by `--item` when supplied; the anonymous queue drain additionally filters standing acceptance/DoD refusals (`O/_dispatcher_loop_candidates.py:35`). Rework candidates are handled before new ready admissions (`O/_dispatcher_admission.py:159`). A drain is not a daemon that appears when a checkout or plugin is installed. The spec calls no-item selection the steady-state path and separately requires clock-fired work supply (`SPECIFICATION/contracts.md:4281`, `:4289`).

`O/_dispatcher_loop_selection.py:122` and `:166` distinguish genuinely ready rows from blockers, parked rework and the deliberately opened groom door. The raw beads-native `bd ready` and a status-only filter are not interchangeable with that predicate (`AGENTS.md`, Beads runtime prerequisites). This research used neither to select work.

### `drive --action impl:ID`

`O/_drive_impl_dispatch.py:89` constructs exactly `python3 <same payload>/scripts/bin/dispatcher.py loop --repo R --budget 1 --parallel 1 --item ID --json`, forwarding asserted invoker and optional workflow/ACP overrides. It does not implement another scheduling algorithm. The child code/assets remain available in a retained `/tmp/livespec-orchestrator-beads-fabro-payload-<release>-*/payload/` tree even if the harness replaces the install; installed-root currency and executing-payload identity remain separate (`.claude-plugin/scripts/bin/_payload.py`; `O/_dispatcher_paths.py:253`, `:276`). The live 0.241.1 process beside current registered 0.241.4 illustrates that distinction.

### Which admission conditions belong here

`AGENTS.md:1228` states, verbatim: **“These are the three admission conditions the Dispatcher owns, and a caller MUST NOT duplicate any of them:”**

1. The bounded default-branch CI wait: 1,800 seconds, polling every 60 seconds, with still-pending exhaustion a distinct deferred outcome, not red CI (`O/_dispatcher_ci_preflight_wait.py`; `AGENTS.md:1252`).
2. Candidate-local session-headroom assessment, including available fallback candidates, no claim when all required chains lack an eligible candidate (`O/_dispatcher_admission.py:299`; `O/_dispatcher_session_headroom_gate.py:165`; current Claude and Codex clauses at `SPECIFICATION/contracts.md:6024`).
3. Plugin currency: registered-install lag warns; only the committed `dispatcher.minimum_release` floor blocks (`AGENTS.md:1264`; `SPECIFICATION/contracts.md:3028`).

The same AGENTS section permits caller conditions for **“capacity on the factory host … the availability of a launch slot the loop schedules itself, and the spacing between launches.”** Those decide when to invoke the Dispatcher. They do not grant a caller authority to reinterpret the three admission conditions. These are the three conditions the caller must not duplicate, **not an exhaustive list of every validation the Dispatcher performs**: schema, source integrity, factory-safety, effective criteria, size, availability, invoker, and lifecycle checks also exist (`O/_dispatcher_run_checks.py:187`; `O/_dispatcher_pre_dispatch_wall.py`).

### The journal changes decisions, not just the operator's view

The default is `R/tmp/fabro-dispatch-journal.jsonl`, overridable with `--journal` (`O/_dispatcher_paths.py:139`). `JournalFile.append` adds UTC time and resolved invoker/source and appends JSONL (`O/_dispatcher_journal_file.py:50`). Important readers encountered on these paths are:

| Decision / reader | What it takes from local history | Consequence of missing/empty/different history |
|---|---|---|
| Counted-claim/WIP accounting, `O/_dispatcher_claim_reclaim.py:101`, `:188` | Latest `ledger-admit` and outcome; live locks across registered local tenant checkouts | Unreadable journal counts lockless active rows conservatively; a readable empty history follows a different branch. Per-host checkout/lock visibility is not cross-host exclusivity. |
| Legacy provider exhaustion, `O/_dispatcher_provider_exhaustion.py:156` | Unexpired exhaustion/clear records, provider and credential identity | No journal gives no journal-held exhaustion. Current factory-native candidate availability can independently hold a candidate; losing this file does not imply every current admission passes. |
| Session drain projection, `O/_dispatcher_session_headroom_baseline.py:62` | Prior assessment of same opaque credential within the projection window | No baseline yields no measured drain-rate projection; live quota/floor rules still apply. This is a changed input, not an equivalent historical assessment. |
| Degraded-step persistence, `O/_dispatcher_step_gate.py:150` | Outstanding degraded post-merge step and its clear/waiver history | Missing record cannot carry its continuing refusal into the next dispatch. |
| Recovery routing, `O/_dispatcher_recovery_routing.py`, `O/_dispatcher_recovery_release.py:79` | Whether latest dispatch released the item for recovery | Unmentioned/unreadable release shape is “not released”; routing can take fresh instead of examining prior preserved work. |
| Resume gather, `O/_dispatcher_resume_observation.py:170` | Cancel anchors, prior resumes, earlier workflow/dispatch/run identities | PR proof records retain some anchors, but local cancellation and resume history are different; no blanket claim that every resume needs only this file or only the PR is valid. |
| Reconcile ownership and replay, `O/_dispatcher_reconcile_runs_attribution.py:1`, `:188`; `O/_dispatcher_stranded_claim_observe.py:155` | Typed launch stamps and newest run; claim effect/replay evidence | Ledger metadata is an independent ownership leg. Runs absent from both ledger stamp and journal are out of this tenant's destructive scope; replay evidence can be lost. |
| Console and drain monitors | Dispatch/outcome/auto-disposition stream and last-read position | History and event-driven progress signals vanish even if the remote run remains alive (`C/crates/console-cli/src/lib.rs:1982`; `V/.claude-plugin/prose/drain-backlog.md:377`). |

This is a map of readers encountered, not the genesis history commissioned to research note 002. Newer factory-native availability evidence and durable ledger/PR proofs coexist with these readers. A host-global fleet-cap file is a separate caller authority and is **not** the Dispatcher journal or the per-tenant WIP cap (`SPECIFICATION/contracts.md:9654`).

## 4. Reconciliation and its actual root-system timer

`systemctl cat reconcile-runs.service reconcile-runs.timer` read **`/etc/systemd/system/reconcile-runs.{service,timer}`**. The rendered service has `User=ubuntu`, `WorkingDirectory=/data/projects/livespec-orchestrator-beads-fabro`, and this source-checkout entry point:

```text
/usr/local/bin/with-livespec-env.sh -- /usr/bin/python3 /data/projects/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/dispatcher.py reconcile-runs --repo /data/projects/livespec-orchestrator-beads-fabro --invoker timer:reconcile-runs --json
```

The timer has `OnBootSec=5min`, `OnUnitActiveSec=10min`, `AccuracySec=1min`, `Persistent=true`; service timeout is 600 seconds. `systemctl show` reported **enabled, active, running** while the pass was executing. The first `list-timers --all` showed no next instant during that running pass, which must not be misread as “timer disabled.” The user-manager timer population had three entries and no reconcile timer; the **system** manager had the actual timer and the PID sample found its command. These units are root-system managed, but the configured command runs as ubuntu, not as root. Committed templates/explanation: `orchestrator-image/services/reconcile-runs/`.

The dispatch preamble also runs one reconciliation pass before selection/admission (`O/_dispatcher_run_checks.py:221`, `:294`). It surveys declared factories using each appropriate client; joins ledger stamps and typed journal launch stamps; preserves run references before authorized termination; handles claim recovery with dispatching-host/liveness and idempotence evidence; and has a drift lane (`O/_dispatcher_reconcile_runs_pass.py:225`; `O/_dispatcher_reconcile_runs_command.py:1`). It **does not** feed ready work to the factory.

The standalone command's `--dry-run` protects the factory from export/termination, but its current header explicitly says every invocation, including a dry run, appends one `reconcile-runs-pass` record (`O/_dispatcher_reconcile_runs_command.py:39`). That conflicts with the earlier header shorthand “no journal write” at line 11 and with a broad “pure read” reading. I did not run it; the console currently requests that projection (`C/crates/console-cli/src/lib.rs:2032`). This is a state-writing observation path to account for in a future portability audit.

## 5. `reconcile-merged` and `resume` are different continuation paths

### Merged-item reconciliation

`O/_dispatcher_reconcile_merged.py:98` validates the selected item and integration configuration, records a distinct invocation, resolves an already-merged PR, then runs the required post-merge janitor/acceptance tail. An item already in acceptance takes re-acceptance without rerunning the janitor or remerging; `--regrade` is another explicit arm. Its local janitor venue is `~/.worktrees/<repo>/janitor-reconcile-<id>` (`O/_dispatcher_fabro_argv.py:319`). Journal tail lines 503974–503982 showed `seat:github-app-checks-read` carrying an already-merged `bd-ib-36d3x5` through janitor and acceptance parking. That is progress after merge, not a new implementation launch.

### Explicit and automatically selected resume

The live `bd-ib-h5jr5x` command made `resume --item` an added observed surface. `O/_dispatcher_resume_command.py:172` gathers and grades before new claim/run effects. `O/_dispatcher_resume_observation.py:1` names three remote evidence systems—ledger, forge, factory—and explicitly notes why a proof's DoD snapshot is read from the **published record**, which survives another checkout's journal being invisible. It also reads local locks and journal-derived cancellation/resume/workflow information. Automatic recovery routing runs after the wall and before admission, while the item is still ready; it can choose fresh, seeded, resume or held (`O/_dispatcher_recovery_routing.py:1`). A control-plane migration must preserve that choice, not merely provide a new command spelling.

## 6. Added surface: clock-fired work supply exists but is not installed here

`orchestrator-image/services/work-supply/README.md:1` says **“Installing it on a host is a separate operator action; nothing in this repository installs it.”** Each firing runs an ordinary no-item drain under the operator's current registered plugin. `work-supply-pass.sh:113` reads that registration; `:171` requires repo, budget, wrapper, user/home; `:225` starts a `systemd-run --collect` transient unit with `--uid`, explicit operator HOME, wrapper and `dispatcher.py loop --budget ... --invoker timer:work-supply --json`. Root owns the firing because system-scope transient-unit creation requires that authority; the pass runs as the operator. Overlapping passes are not blocked by a launcher mutex.

Templates and installer persist host-specific units, instance interval drop-ins and `/etc/livespec/work-supply/<instance>.env` (`install.sh:212`). Defaults are 30-minute firing interval, minimum 10 minutes, budget 3. The last source change observed was `ad45339eb`, 2026-10-19T10:16:15Z, “run each pass as the operator, not as the root firing.” Governing spec: `SPECIFICATION/contracts.md:4289`, Scenario 201.

**Absence scope/control:** `systemctl list-unit-files '*work-supply*'` returned zero unit files in both system and user managers; `systemctl list-units --all 'work-supply*'` returned zero loaded units. The same manager's `list-unit-files reconcile-runs.timer` returned the enabled reconcile timer, and its process was observable. The work-supply template source itself is a positive match for the searched name. Thus clock-fired supply is shipped capability, not measured host automation here. No installation was performed.

## 7. Console: capable command surface, not the currently running fleet scheduler

### Design decisions and their amendment

The console plan's `research/redesign-brainstorm-and-decisions.md:119` labels its decisions **proposals until a scope event or ratified clause says otherwise**. Relevant exact text is:

> **D1 — Retire tmux as the transport.** Sessions become data: questions, permissions, rate limits, context and turn events are protocol messages composed into needs-attention.

> **D4 — The thin non-dispatchable set, exactly:** (1) maintainer-in-person infra acts (AWS console, registrar, billing, break-glass), recorded as scope events; (2) the interactive context session — questions, rulings, research authoring, routing judgment; (3) the broken-factory fallback — a human + LLM session driving worktree → PR by hand …

Do not quote the original D5 freeze as the maintainer's current ruling. At `:180`, **D5 AMENDED 2026-09-09** quotes the maintainer:

> “I will probably keep the overseer skill, and the caam skill(s), and the new drain-backlog skill. And I will keep the repo name, it's good enough for now. Everything else will get deprecated and deleted (supervisor and foreman skills and anything only used by them).”

The same amendment says the repository is **not frozen**, and caam/drain-backlog remain in overseer. The actual console specification now forbids a resident deciding agent and terminal-scraping agent transport (`C/SPECIFICATION/spec.md:52`–`:72`); it observes and executes explicit recorded commands through orchestrator ports. That boundary is compatible with the console being the human cockpit; it is not a fleet budget scheduler implemented by the UI.

### Current code really dispatches

`C/crates/console-cli/src/main.rs:204` wires `DispatcherFactoryDrainPort` and `DispatcherFactoryDispatchItemPort` to the selected Dispatcher executable with `loop --repo R`. The application implementations at `crates/console-application/src/lib.rs:3893` and `:3953` add budget/parallel, and for a selected item add `--budget 1 --parallel 1 --item ID`. `drive.py` is wired separately for valves/settings (`main.rs:215`). **The console's factory buttons call Dispatcher loop directly; they do not run seat tmp scripts.**

The console persists command envelopes before handling them, claims pending commands, invokes ports and records outcomes (`C/crates/console-cli/src/lib.rs:3155`). `FactoryDrainPolicy` checks empty ready evidence in ingested lane/attention events (`C/crates/console-application/src/lib.rs:3835`); it does not replace the Dispatcher's blocker, cap or admission checks. `BackingCliResolution` uses selected-repo plugin resolution and executable/wrapper resolution (`C/crates/console-cli/src/backing_cli.rs:210`). The default store is **process-relative** `tmp/livespec-console.sqlite`, overridable by `LIVESPEC_CONSOLE_STORE_PATH` (`main.rs:1659`); the Dispatcher journal path is selected-repo-relative and explicitly resolved to an absolute path (`backing_cli.rs:280`). This distinction matters when moving the console to a container or launching it outside the governed checkout.

Source adapters read orchestrator work-items, the local Dispatcher journal, configured Fabro servers, LiveSpec, GitHub, needs-attention and the reconcile projection (`C/crates/console-cli/src/lib.rs:1849`, `:1982`; `source_adapters.rs`). SQLite holds events, commands, checkpoints and projections (`C/SPECIFICATION/contracts.md:125`). Losing the store loses pending-command/history/checkpoint state; re-ingestion of current ledger facts is not a recovery of that command history. Losing only the dispatch journal removes a distinct event source.

### Plans and hold status must be dated

`C/plan/retire-overseer-and-redesign-control-plane-around-console/research/012-plans-as-a-first-class-console-concept.md:112` reports the **2026-09-29** state: no Plans view and a stranded static HTML `plans <epic-id>` page. That is historical evidence, not current code. Current `TuiView` includes `Plans` at `C/crates/console-application/src/lib.rs:349`, and current source carries `crates/console-cli/tests/scenario_33_plans_roster.rs`. The research note's dated vocabulary ruling at `:99` is: **“‘plan’ is the domain word everywhere a human reads … ‘epic’ survives only at the beads realization boundary.”** The note explains the portable plan identity as ledger record plus optional write-once research directory, not a machine-local mutable plan file (`:77`).

The old b1–b3 hold is recorded at `research/program-board.md:98`, `:119` and on `livespec-console-beads-fabro-pzbdbo`; do not infer those dependencies' current status from the old description alone. Its latest timeline entries (read via wrapped `bd comments`, key `text`) on 2026-10-10 retire that tmux session and describe a DoD-refused attempted child dispatch. The **newer maintainer framing on 2026-10-24** is explicit in this repo's provisional-launch charter: **“Ideally the long term would be that this is driven through the console application but we have had that track of work on hold for a while and probably still will.”** (`plan/provisional-fleet-launch/research/001-charter-provisional-fleet-launch.md:3`; also `fleet-launch/README.md:8`). Therefore “track on hold” is supported, but “console cannot dispatch” is false, and the old exact blocker set is not re-certified here. The specification is TUI-first with future GUI/API (`C/SPECIFICATION/spec.md:109`); the historical static HTML page is not proof of a live web control plane.

## 8. Overseer, foreman and supervisor: three distinct facts

### Overseer operation and daemon survive

The binding at `V/.claude-plugin/skills/overseer/SKILL.md` resolves `V/.claude-plugin/prose/overseer.md`. That prose at `:44` calls the overseer **“A permanent alternate to autonomous mode.”** Its two panes are deterministic `overseerd` and thin human-facing operator session; the daemon watches context/declared state and replaces only a session that declares ready (`:95`). It reads `/proc` and tmux/Herdr native state and is deliberately Linux-specific (`:64`). It discovers plans and joins them to `~/.livespec-overseer.jsonl`, stamps at `~/.livespec-overseer-stamps.json`, and watch-set at `~/.livespec-overseer-repos.json` (`:482`; `V/overseer/_registry_core.py:113`).

Its decisions are **when/how to wind down, restart, adopt and notify**, not which ready item the factory should take. The indirect dispatch path is daemon restart → resumed plan session → typed next action → drive. The daemon itself runs the `supervisor.py` loop; that Python name does not mean the retired supervisor skill still ships. Runtime path observed: `~/.local/share/livespec-overseer/runtime/6f5cbeaf.../venv/bin/overseerd`, not this checkout's current interpreter/module path. The bottom operator must not perform track work itself (`V/.claude-plugin/prose/overseer.md:34`).

### No current foreman skill in the requested population

Removal commits: **`b773755a`**, 2026-09-06T19:59:03Z, “remove the foreman seat”; **`32e771af`**, 2026-09-06T21:04:51Z, “remove the supervise-plan seat.” Before removal, `foreman.md` specified a per-repo named seat, bounded tick, singleton/heartbeat and durable runtime state, with mutations only through whitelisted `foreman-act` proposals (`git show b773755a^:.claude-plugin/prose/foreman.md:6`). `supervise-plan` authored a shared role charter and attributed per-plan ledger binder (`git show 32e771af^:.claude-plugin/prose/supervise-plan.md:10`).

**Absence scope/control:** all **8** current `/data/projects/*/.claude-plugin` roots were enumerated recursively, including hidden harness subtrees, yielding **70 `SKILL.md` files**. Their frontmatter `name:` declarations were tested for `(^|[-:])foreman$`, which catches `foreman` and pi's fully prefixed form. Zero matched; the same parser found the current overseer skill in Claude and Codex trees. A path-name search also found no foreman skill directory; the positive historical `name: foreman` above proves the token is appropriate. A case-insensitive `foreman` search over all six current top-level `V/SPECIFICATION/*.md` files also returned zero. This is absence in the requested current-source population, not a claim that historical Git blobs or every old home-directory plugin cache contain no copy.

Current shipped skill directories include overseer, drain-backlog, caam-anthropic-loop and llm-provider-manager. Foreman-flavoured modules deliberately remain for shared consumers: `_foreman_vendor_path.py`, `foreman_gather_sources.py`, `caam_foreman_override.py` (`V/tests/test_foreman_seat_removed.py:26`). Those names are not an available foreman operation. Test source pins the retired seats separately (`V/tests/test_shipped_skill_surface.py:71`); tests were read, not run.

### Supervisor pair-member removal is still pending

`V/plan/remove-supervisor-skill/research/001-what-supervisor-resolves-to-and-the-cut.md` distinguishes the nonexistent exact skill name `supervisor`, the removed `supervise-plan` authoring skill, and the **surviving attended supervisor pair-member role**. Current `V/SPECIFICATION/spec.md:1098` still specifies the supervisor's own ready declaration and shared-epic binder; `contracts.md:143` still has the supervisor restart-artifact interlock; `V/overseer/registry.py:65` still exports `SupervisorSeat`. The plan was opened by `9cd1537b` on 2026-09-12. Read-back of **`overseer-hnjolu`** shows `backlog` and `next_action.kind=human` asking to confirm the pair-member interpretation before filing the spec child. Thus it is incorrect to report the whole supervisor role removed. Likewise a `supervisor.py` process/module remains the daemon by design, an unrelated homonym catalogued by that research note.

## 9. Drain-backlog: a session is still the outer loop

`V/.claude-plugin/prose/drain-backlog.md:37` puts frozen snapshot, snapshot history, engine/launch logs and `last-tick` under `R/tmp/drain-backlog/`. With a bound plan epic, dispositions and handoffs go through the ledger; without one, `dispositions.jsonl` and `handoff.md` are authoritative skill state. The invocation can update the frozen snapshot; it does not create a foreman seat (`:13`). Its rule is explicit at `:375`: **“The session IS the loop.”** The LLM handles journal outcomes, needs-attention and PRs on a monitor/heartbeat, relaunches ripe batches, grooms repeated failures and continues plan closure. The detached Dispatcher engine is finite; the session supplies the next wave.

The shipped `V/.claude-plugin/scripts/drain-backlog/engine-on-green.sh` reads current credential status, invokes the exhaustion-clear valve when appropriate (`:43`), then polls latest master CI (`:55`), and launches detached `dispatcher.py loop --budget <number of IDs> --parallel K --item ...` (`:63`). Its default invoker is `skill:drain-backlog`; its default orchestrator build is selected by newest cache mtime (`:31`), unlike registry-exact seat/work-supply resolution. It writes `engine-<label>.log`; the invoking session writes `launch-<label>.log` and watches engine/journal state.

**Measured code/contract discrepancy:** the script's caller master-CI gate at lines 55–74 duplicates a condition `AGENTS.md:1228` and `SPECIFICATION/contracts.md:5313` now reserve to the Dispatcher. It is shipped source, not inferred from the prose alone; this research did not execute or fix it. Historical headroom wait scripts in tmp similarly add caller quota decisions (§19). The existence of an old wrapper is not authority to copy its policy into a new control plane.

## 10. Caam: account supply and hold-release input, not work selection

`V/.claude-plugin/prose/caam-anthropic-loop.md:18` requires a recurring runtime job at `7,37 * * * *`, plus expiry-directed warm wakes; its exact limitations are **“the job lives only while this Claude session is open, and recurring jobs auto-expire after 7 days.”** This is not a root system timer. Without Cron tools the operation reports inability to self-install and runs the current pass; it must not invent a replacement scheduler (`:55`). Herdr tab enumeration found `caam-anthropic-loop-runner`, `w5:t3`; that proves a runner tab, not that a rotation pass was executing at this instant.

The program reads `~/.local/share/caam/vault/claude/<profile>/.credentials.json` and active `~/.claude/.credentials.json`; it stores usage cache, refusals/protection floors, fleet-load/drain baselines, model exceptions and switch/warm history in **`~/.local/state/caam-usage-rotate/state.json`** (`V/overseer/caam_profile_state.py:1`, `:58`). Switch serialization uses `switch.lock` (`caam_switch.py:46`); the identity-only consumer output is `selected-account.json` (`caam_selection_record.py:43`). The published selection is explicitly **an output, not an input to caam's own selection** (`prose/caam-anthropic-loop.md:355`). The Dispatcher has a consumer reader at `O/_dispatcher_factory_account_selector.py:101`.

Factory admission headroom, interactive seat availability, factory credential following and the launch hold watcher can therefore react to account state without caam choosing an item. A new host with the same repository but no vault, baselines, active account or live Cron owner does not reproduce this behavior. No credential contents were read or printed in this investigation.

## 11. Interactive coordinator, specialist seats, and Herdr

The committed comparison note describes the evolved pattern: one coordinator's TICK loop, specialist plan seats, cross-session messages, ledger-held handoffs/rulings, and per-seat shell launchers (`plan/provisional-fleet-launch/research/002-analysis-coordinator-seats-vs-console.md:24`). Its ledger sources are **`livespec-dev-tooling-dfixhe`** for the coordinator and **`bd-ib-fyozyd`** for the petri seat. It reports attention/cost measurements as a dated sample, with explicit Claude-only and in-flight undercount caveats (`:11`); this note does not turn those estimates into new measurements.

`herdr tab list` returned live labels/targets including **`gitops-fleet-capacity-monitoring` (`w2J:tA`)**, **`petri-factory-on-gmktec` (`w6:t9`)**, **`fabro-currency` (`w6:t1`)**, **`kubernetes-sandbox-backend` (`w6:t2`)**, **`delegated-gate-fleet-rollout` (`w2J:tD`)**, **`github-app-checks-read` (`w2J:tE`)**, **`herdr-overseer` (`w5:t5`)**, and **`overseerd` (`w5:t1`)**. Herdr's `agent_status` is a display observation, not proof a plan is disposed or a remote dispatch ended. These pane names make the owner attribution actionable; a filesystem path alone would not identify the steering session.

The coordinator ledger read returned 2,999 comments. Recent records are stronger evidence than an old handoff's hold claim: comment **`01a170aa-f920-7b1a-b492-0d2341a925da`**, 2026-10-25T01:26:56Z, records `hold-gmktec` lifted at 01:18Z and cap 10 read at 01:24:24Z; **`01a170ad-8e43-7c62-9837-5ab4ac24ffc2`**, 01:29:45Z, records ebtm6t listed on petri; **`01a170b3-2fdc-7d5f-8146-ef27ff90e5fa`**, 01:35:54Z, records tlfc3w listed. Adjacent corrections demonstrate why the latest ruling matters: **`01a170ab-47ff-7164-acbf-1f929009bd55`**, 01:27:16Z, supersedes two speech-transcription readings with the maintainer's **“I said throughput, throughput, throughput.”** The ruling's operative quote is **“…focus, as the highest priority, on fixing the instability and PROVE THROUGHPUT.”** These are ledger records, not a committed machine-readable scheduler policy.

Handoffs/rulings can survive host loss in Dolt, but their execution depends on a living seat, terminal/session context, local cap/hold/queue and installed runtime. A fresh clone alone neither replays every ruling into a scheduler nor restores a FIFO position. The coordinator pattern is not a currently shipped foreman skill under another name; the requested foreman search and removal evidence are in §8.

## 12. The running tmp launchers

`tmp/petri-canary/dispatch-dual-r681b.sh:57` sets item/seat/repo, hard-coded output and factory/client paths. `:86` reads `fleet-cap`, defaulting an absent/non-numeric value to zero; `:117` reads gmktec and mi-homelab boards and deliberately treats retired hp/vps as empty; `:98` counts live unlisted markers; `:138` creates its own marker before a binding re-count; `:172` handles mutex-holder age/PID; `:214` resolves installed plugin version; `:236` writes DoD preflight output; `:251` takes an early FIFO ticket; `:275` tests the petri hold; `:332` invokes drive and records JSON/stderr. Header rulings are historical strata; the executable body, not an old header promise about hp, defines today's branch.

At the state inspection shortly after the process sample:

- `tmp/petri-canary/fleet-cap` existed and contained **`10\n`**.
- `tmp/petri-canary/hold-gmktec` was absent. That agrees with the newer coordinator comment, not the 23:00Z handoff that still described a hold.
- `/run/user/1000/gmktec-launch-queue.d/` held **13** readable item tickets, oldest sampled ticket for `bd-ib-eqiw4f`; ticket names are nanosecond-sort keys plus seat and contents name owner/PID/item.
- `/run/user/1000/fleet-inflight.d/` held the tlfc3w marker, naming PID 1087087 and factory petri. The count excludes dead-PID markers only after checking whether a drive for that item is still alive (`:107`).
- `/run/user/1000/gmktec-launch-lock.d/` was absent at inspection. Absence between launches does not mean the mutex mechanism is unused.

Portable behavior is not preserved by merely recreating empty directories. Missing cap makes `fleet_green` false; deleting a hold can make a previously held branch launch; losing an unlisted marker undercounts submissions; re-creating tickets changes order; PIDs in another host/namespace do not establish the same liveness; different CPU/board visibility changes the host gate. A shared remote factory with **separate per-container** queue/marker dirs would not have the current single-host coordination property. These are inferences from the source branches above, not experiments performed against a running factory.

The current r681b executable body no longer reads hp/vps boards, although their URLs and old helper functions remain in the file. Its hp launch branch is `if false ...`; it uses petri at gmktec `:32276` and mi-homelab `:32277`. Current `.livespec.jsonc:288` sets `default_factory` to **petri**, and `/etc/livespec/fabro-factories.json` contains just petri and mi-homelab with those URLs. Do not substitute the older AGENTS host-factory paragraph's hp/vps routing example for that current registry/config measurement.

Other historical scripts remain callable files, not proven active engines. The full script inventory is §19; unlike a filename-only census it marks direct launchers, resume wrappers, fill/sequence runners, headroom gates, cap/hold writers, observers and credential/proof helpers separately. No process in the sampled launcher population executed those other script names. That is **not** evidence that it is safe to delete them; cutover/cleanup belongs to the other plan.

## 13. Committed `fleet-launch/`: code captured, state still local, cutover incomplete

The maintainer's full directive is committed at `plan/provisional-fleet-launch/research/001-charter-provisional-fleet-launch.md:3`. Key exact sentences are:

> “Okay it's unacceptable that this logic is living in uncommitted scripts. Anything that is not committed should be committed but this is also a one-off and sort of hack workaround just for this plan. It is useful as a pattern that emerged.”

> “I want you to spin up a new plan which will follow all proper livespec precedents and discipline, and commit these scripts, but as provisional and experimental.”

> “There should be no scripts living under the tmp directory.”

The preferred console sentence is quoted in §7. These are requirements for the cutover plan, not proof the cutover happened. Commit **`04b13b2ed`**, 2026-10-24T21:59:19+02:00, captured the scripts; plan comment `01a16fc5-9104-75a4-9f43-f5c54844e569` records merge PR **#3595** and the first-class replacement **`bd-ib-jr6w7v`**. Spec v207 added the provisional contract/scenario (PR #3597, latest handoff on **`bd-ib-klkbxp`**). Its newest sampled handoff, **`01a17025-c820-7f11-ac2e-6c2d832d0fd6`**, 2026-10-24T23:01:27Z, still awaits C2 `bd-ib-nz4av6`, then C3 `bd-ib-pdmadj`: cut over every launcher, verify no tmp-script process, **only then** delete tmp scripts. The live process and file inventory independently confirm that tail has not completed.

`fleet-launch/config.sh:13` centralizes host-specific values with `FLEET_LAUNCH_*` overrides: repo/seat, state/cap/hold, two servers, SSH/remote credential file, host caps/CPU floor, pinned Fabro client, queue/mutex/marker dirs, plugin registry/cache, wrapper locations and timing. Defaults still include `/data/projects/...`, `/home/ubuntu/...`, `/run/user/1000/...`, and **`tmp/petri-canary`**. Committed code is thus reviewable/configurable, not self-provisioning state.

`fleet-launch/dispatch-dual.sh` uses the installed ready set (`:171`), cap/boards/markers (`:62`), FIFO/mutex (`:136`), hold (`:220`), DoD preflight (`:191`), credential probe (`:268`) and drive (`:279`). It refreshes the checkout via fetch/ff-only merge (`:264`). Important deliberate differences from the seat copy are recorded in `fleet-launch/README.md:78`: retired factory boards are not read; **the hold applies to mi-homelab as well**; capture identification uses drive-process ancestry; final drive rc gets a timestamp. The code is not a byte-identical drop-in for every tmp variant.

`SPECIFICATION/contracts.md:9654` names this a **caller-side** provisional loop and forbids the Dispatcher from reading/enforcing/depending on its fleet cap/FIFO/hold/markers. It also requires retirement when the console or first-class loop owns every launch and no seat runs this directory. A ratified allowance for caller-side files is different from a ratified guarantee of cross-host durable dispatch state—the current plan `bd-ib-k6dqwc` explicitly seeks the latter.

## 14. Helpers that can stop or release launches

### Hold release

`fleet-launch/release-hold-on-caam-rotation.sh:14` reads the configured hold and profile (default held profile `anthropic-1`), checks `caam status claude` every minute, removes the hold only after a different nonempty profile, and after three hours leaves the hold standing. If the file is already absent it reports it already removed. The tmp predecessor uses the same fixed hold path. This watcher is a local control path in its own right; losing it can leave a hold forever, losing the hold can release work without its intended condition.

### Readiness, wrappers, default factory and proof capture

`fleet-launch/ready-set-check.py` imports the registered build's ready predicate and reads the actual tenant; it does not reproduce ready as status equality. `fleet-launch/wrappers/` has PATH-preserving dolt-server/openbrain/resume shims, homelab argv-based credential wrapper and nested mi-homelab-key/family-wrapper helper. `homelab-wrapper.argv` is parameter **paths**, not secret values. These shims add credential venue/host-path dependencies, not a new queue.

`fleet-launch/resolve-default-factory.sh:11` fetches origin then reads `origin/HEAD:.livespec.jsonc`; its local writes are Git remote-tracking/FETCH_HEAD state, despite its printed result being only a factory name. `fleet-launch/host-capture-payload.py:93` builds an output JSON from launch argv, gate logs/verdicts, registry resolution, journal rows, installed build and remote PR/run evidence; it refuses before the final `write_text` when evidence is missing (`:176`; `_capture_evidence.py:13`, `:141`). Empty tmp can therefore block host proof/acceptance after a successful remote merge even when dispatch itself is reconstructed. It does not post proof or approve an item on its own.

## 15. Plan sessions and unattended continuation

`.claude-plugin/prose/plan.md:225` maps `kind: impl` to `impl:<ref>` and `kind: await` to bounded observation of a `run:`, `gate:`, `item:` or `epic:` handle. The current unattended contract at `:243` reads typed **ledger metadata**, not a next-action sentence parsed from a comment. It requires observable result, authority and unexpired budget. Satisfied pointers are reconciled/advanced; a still-unsatisfied impl target with a live run becomes await, preserving the obligation/budget; unobservable or expired progress routes to authorized diagnosis/recovery rather than a duplicate dispatch. `O/_plan_resume.py:45`, `_plan_resume_reconcile.py` and `_plan_resume_tracking.py` implement those branches.

The daemon adds `LIVESPEC_PLAN_UNATTENDED=1` only for its restart launch (`V/overseer/_supervisor_launch_profile.py:74`); an ordinary attended launch keeps the picker unless a current continuation ruling authorizes taking the default. The variable is carried through credential/bootstrap seams (`.claude-plugin/scripts/bin/_bootstrap.py:183`). An `await gate:<id>` still points to a local detached-run handle; moving to a host lacking `tmp/gate-runs/<id>` loses that observation even though the pointer is durable. A remote run/item/epic handle has a different portability profile. A typed pointer is not a new scheduler or permission to invent store-write consent (`plan.md:257`).

## 16. Additional doors and launch transports

### `implement`, driver-dispatch and groom

`.claude-plugin/prose/implement.md:24` defines factory routing as **“dispatch through the Dispatcher — the drive operation's impl:<id> action or the Dispatcher's own drain of ready items.”** In-session exceptions and non-product work are explicitly separate. `O/_drive_driver_dispatch.py:1` journals the ready host-only door and records its driver-session reference; it does not launch a Fabro run. This prevents interpreting every `active` row or “implementation session” as factory load.

The automated groom door is a package API, `groom.groom_dispatch`, re-exported by `commands/groom.py:58`. It requires operator initiation, a backlog row and a groom-kind variant, pins workflow before moving status, creates a local claim/lock and journals `groom-dispatch` (`O/_dispatcher_groom_door.py:122`). Subsequent dispatch recognizes that deliberately opened claim; an unattended drain may not independently scoop arbitrary backlog. The ordinary interactive groom prose still says **“Does NOT dispatch slices — the Dispatcher drains the factory slices”** (`.claude-plugin/prose/groom.md:283`). These concern different phases/subjects and should not be flattened into a general auto-groom scheduler.

### Detached gate runner and overseer disk-verdict transport

`dev-tooling/gate-run.sh:32` names the evidence files `started_at`, `pid`, `output.log`, `exit_code`; `:64` explains that storage resolves through the shared Git dir to the **primary checkout's** `tmp/gate-runs/<run-id>`, surviving worktree removal but not primary tmp loss. It also records config-watch evidence (`core_before`, `core_after`, `config-writes.log`). The sampled long-lived launcher parents were `gate-run.sh __child ...`. A live PID is not a pass and no exit code is not a refusal.

`V/scripts/detached-dispatch.sh:76` recognizes impl arguments, runs `dispatch_acceptance_guard.py`, then starts `setsid nohup` and writes `RUN_DIR/pid`, `output.log`, atomically replaced `verdict.env` (`:25`, `:100`). The guard reads item/acceptance/tier facts (`V/scripts/dispatch_acceptance_guard.py:1`). That source file lives in **`V/scripts/`**, while the overseer prose references `scripts/detached-dispatch.sh`; a guessed `.claude-plugin/scripts/` path would miss it. It is a transport for a passed drive command, not a fleet scheduler. No separate live detached-dispatch script process was established by the sampled targeted process filter; the live transport observed here was the gate runner.

### Fresh-clone container and canary adapters

`orchestrator-image/real-work-dispatch.sh:1` describes fresh in-container orchestrator/target clones, scratch-generated tenant pointer metadata, projected host credentials, Docker volume/run state and custom journal/log path. At `:514` it runs one named-item Dispatcher loop. The container entrypoint provisions services then executes its supplied command or shell (`orchestrator-image/orchestrator-entrypoint.sh:204`); it does **not** unconditionally start a ready-queue scheduler. The real-work script's historical “production substrate” description is source documentation, not evidence of current traffic. `dev-tooling/just-canary-dispatch.sh:117` files a canary then calls direct dispatch to an explicitly declared factory. These were added from source search, not run.

## 17. What cannot be inferred from a fresh checkout

The state with remote durability is substantial: item/dependency/plan/policy records in Dolt; PR/merge/proof records on GitHub; running and preserved factory-native evidence. The checkout also carries configuration, workflow and spec. But the actual launch decision composes those with **local** journal memory, local counted-claim visibility, selected installation, account history and a caller's fleet scheduling files. Evidence in §3 gives concrete counterexamples to “same ledger means same decision.” Evidence in §12 gives concrete counterexamples to “committed launcher means portable scheduler.” Neither was tested by removing live state; all conclusions follow from reader branches and observed file/process state.

## 18. Host-local state inventory and specification naming audit

This inventory distinguishes **named behavior** from a **named concrete path**. A specification may require a journal/replay/hold without saying the location is this host file. The naming audit below searches **current top-level `SPECIFICATION/*.md`** in O's repository, C and V; it excludes snapshots and proposed changes. Exact literal searches had positive controls: `fleet-launch/` matched this repo's current contract/scenario, `Clock-fired work supply` matched contracts/scenarios, and `~/.fabro` matched constraints. Thus “literal not found” below means the stated population/pattern, not “unspecified semantics” and not an all-history absence claim.

| State path / object encountered | Owner and read/write role | Does a current specification name it? / evidence |
|---|---|---|
| `R/.livespec.jsonc`, committed workflows/spec, Git config/refs and `origin/HEAD` | All dispatchers/launchers; read policy/integration/defaults, source/primary refresh updates local refs | Config/workflow semantics and `.livespec.jsonc` named throughout `SPECIFICATION/contracts.md`; source integrity/default-branch clauses. Local Git clone state still differs. |
| `R/.beads/config.yaml` and **gitignored** `R/.beads/metadata.json` | `bd` tenant connection; read by all ledger consumers; pointer must be provisioned on new host/clone | Tenant-resolution contract exists; literal `metadata.json` absent in audited spec roots. Explicit operational source: `AGENTS.md:202`; container adapter comments `real-work-dispatch.sh:18`. No bd init was run. |
| Dolt server at `127.0.0.1:3307` and bare `BEADS_DOLT_PASSWORD` injection | Host backend/wrapper, reached from correct repo root | Connection/provisioning boundary specified; concrete prerequisite in `AGENTS.md:202`. Loopback points to a different service/namespace in a container. |
| `R/tmp/fabro-dispatch-journal.jsonl` | Dispatcher append, admission/recovery/reconcile readers; console/drain/capture consumers | Journal/history **semantics** specified, e.g. `contracts.md:1073`, `:5975`, `:6024`; literal `fabro-dispatch-journal` absent from all audited current spec roots. Code path `O/_dispatcher_paths.py:139`. |
| `R/tmp/fabro-dispatch-<id>.lock` and reclaim sidecar | Dispatcher/groom claim, PID/start-time identity and liveness; read/update/delete | Live-lock counted-claim class named in `contracts.md:1073`; exact per-item filename is implementation (`O/_dispatcher_dispatch_lock.py:57`, `:180`). |
| `$XDG_STATE_HOME/livespec-orchestrator-beads-fabro/tenant-checkouts/<tenant>/<digest>.json` or `~/.local/state/...` | Claim writer registers local checkouts; WIP accounting reads them | Tenant-scoped counted claims specified; exact literal `tenant-checkouts` absent in current audited specs. `O/_dispatcher_tenant_checkouts.py:73`, `:87`. Per-user host registry, not a multi-host ledger lock. |
| `R/tmp/fabro-dispatch-journal-{reflection,reflector-oob,cost-report,calibration,dispatch}-spans.jsonl` | Dispatcher telemetry writes and egress reads | Telemetry/reflection semantics specified; concrete siblings in `O/_dispatcher_paths.py:145`, `:224`. Loss affects observation, not a license to alter verdict. |
| `R/tmp/fabro-dispatch-journal-otel-heartbeat.json`, `-otel-cost.json`, `-tdd-order.json` | Receiver writes heartbeat/cost/order aggregates; watchdog/cost/calibration read | Heartbeat/cost/order behavior specified, e.g. scenarios 5918/8276; concrete paths in `O/_dispatcher_paths.py:168`, `:179`, `:242`. |
| `~/.local/state/livespec-orchestrator-beads-fabro/run-turn-exports/fabro.json` (XDG variant) | Host-global telemetry export marker; post-run guard reads | Run-turn telemetry behavior; exact path from `O/_dispatcher_paths.py:192`. This repo's spec literal `XDG_STATE_HOME` absent. |
| `/etc/livespec/fabro-factories.json`, optional `LIVESPEC_FABRO_FACTORY_REGISTRY` | Factory resolver/capture/console read provisioned addresses and optional client settings | Registry-backed factory **behavior** named at `contracts.md:7379`; concrete default/override in `O/_factory_registry.py:95`. Observed keys petri/mi-homelab. |
| `/etc/systemd/system/reconcile-runs.{service,timer}` and system journal | Root-system runtime; runs ubuntu reconciliation, writes system logs | Reconciliation contract + committed service templates; rendered host installation proved by `systemctl cat`; no checkout auto-installs units. |
| `/etc/systemd/system/work-supply@.{service,timer}`, `work-supply@<instance>.timer.d/interval.conf`, `/etc/livespec/work-supply/<instance>.env`, transient `work-supply-pass-*` units | Optional work-supply starter; installer writes, timer reads | Clock-fired supply specified at `contracts.md:4289`; concrete destinations in `orchestrator-image/services/work-supply/install.sh:212`; absent here in both manager populations. |
| `~/.claude/plugins/installed_plugins.json` | Work supply, console, DoD preflight, seat launchers resolve registered build | Registered-runtime build resolution specified (`contracts.md:4289`, Self-contained plugin dispatch); concrete Claude registry path in code/launcher. |
| `~/.claude/plugins/cache/.../<build>/`; Codex host plugin registration `~/.codex/config.toml` | Harness installation/code/assets/config; runtime resolves reads; harness updates externally | Plugin-distribution/self-contained behavior specified; operational host scope in `AGENTS.md:73`. Research read Claude marketplace/registry, not Codex config contents. |
| `/tmp/livespec-orchestrator-beads-fabro-payload-<release>-*/payload/` | Entry-point retained code/assets, child reuse, lifetime cleanup | Self-contained execution requirement; concrete retention implementation `.claude-plugin/scripts/bin/_payload.py`. Current specs did not match literal `retained payload`; synonymous prose may still govern behavior. |
| `/tmp/fabro-goal-<id>.md`, `/tmp/fabro-run-config-<id>.toml`, `/tmp/fabro-workflow-<id>/` | Dispatcher renders goal/config/workflow; client reads; overlays hold projected credentials and are cleaned by lifetime | Workflow/credential projection behavior specified; concrete paths `O/_dispatcher_loop_plan.py:89`. Their contents were not dumped. |
| `~/.worktrees/<repo>/fabro-source-<suffix>`; source Git refs | Dispatcher source staging creates/pushes/cleans | Source isolation/integrity behavior; exact venue `O/_dispatcher_source_staging.py:126`. |
| `~/.worktrees/<repo>/janitor-<id>`, `janitor-reconcile-<id>`; retained reconcile/janitor evidence under repo tmp | Janitor/reconcile create, run hook/bootstrap/check, remove; primary refresh | Janitor/integration behavior specified; venue `O/_dispatcher_fabro_argv.py:298`; retention `O/_dispatcher_reconcile_merged.py:150`. |
| `~/.fabro/bin/fabro` and pinned `~/.local/state/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro` | Installed clients/servers, launcher board reader | `~/.fabro/bin/fabro` explicitly named by `SPECIFICATION/constraints.md:98`, `:156`; carrier path in `fleet-launch/config.sh:34`. Different engine clients are not interchangeable. |
| `~/.fabro/auth.json`, `~/.fabro/storage/` | Fabro client login/server configuration and local durable run/storage artifacts | Fabro runtime/auth behavior; exact selection supported by `.livespec.jsonc:948` and AGENTS host notes. Directory existence checked only; no secret contents read. `~/.fabro/runs` was **absent** in this home, so it is not asserted as the current storage root. |
| Remote gmktec `/home/cwoolley/.fabro/storage/server.env` | Launcher reads token over SSH into env; credential freshness/input | Credential provisioning behavior; concrete file `fleet-launch/config.sh:26`, `dispatch-dual.sh:252`. This is factory-host-local state, not carried by clone; research did not fetch token. |
| `~/.claude/.credentials.json`, `$CODEX_HOME/auth.json` / `~/.codex/auth.json`, relevant projected token env | Dispatcher/preflight/caam read credential; caam can switch; projection writes per-run files | Credential freshness/use-window/projection specified; path readers `O/_dispatcher_codex_auth.py:84`, `V/overseer/caam_profile_state.py:58`; no secret-value inspection. |
| `/usr/local/bin/with-livespec-env.sh` and independent wrappers; invoking UID persistent **kernel keyring**; encrypted wrapper credential `/etc/credstore.encrypted/1password-env-wrapper-livespec` | Wrapper reads/provisions env and caches injected variables; every wrapped ledger/forge path depends on it | Wrapper integration required; this repo's current specs do not name literal `keyring`. Canonical wrapper comments at `/data/projects/1password-env-wrapper/with-livespec-env.sh:327` describe 300-second UID cache; `AGENTS.md` documents failure signatures. It is not a repo tmp file and not root's cache by assumption. |
| `tmp/petri-canary/fleet-cap` | Coordinator/old restore scripts write; all live seat launchers read, currently 10 | Generic shared fleet cap provisionally named at `contracts.md:9654`; literal `fleet-cap` appears in Scenario 242; concrete state path not specified (`fleet-launch/config.sh:18`). |
| `tmp/petri-canary/hold-gmktec`, retained lifted/backup forms | Coordinator/hold watchers create/remove; launcher reads; absent at inspection | Generic hold named in provisional contract; literal `hold-gmktec` absent in audited current specs. Loss changes gating. |
| `/run/user/1000/fleet-inflight.d/*` | Launcher creates/removes; all seats count live unlisted launches | In-flight-reader mechanism provisionally named; exact literal `fleet-inflight` absent in specs; `fleet-launch/config.sh:37`. |
| `/run/user/1000/gmktec-launch-queue.d/*`, `gmktec-launch-lock.d/holder`; historical `hp-launch-queue.d`, `hp-launch-lock.d` | Launchers create/read/clean tickets and mutex ownership; coordinator reads | FIFO/mutex mechanism specified provisionally; exact `gmktec-launch` literal absent; paths in `fleet-launch/config.sh:38`; legacy paths in tmp predecessors. |
| `tmp/petri-canary/fill-queue*.txt`, `fill-gates*.{log,active}`, registry-switch/capture/sequence logs, hard-coded prior gate handles | Historical fill/sequence runners read queue/handled/terminal state and write next launch handles | No literal `petri-canary` in any audited current spec. Per-script references inventoried in §19; evolved state is not a specified fleet queue. |
| `tmp/petri-canary/<id>-preflight*.txt`, `<id>-r267.{json,stderr,verdict,capture-argv}`, `seq-<id>.log`; canary/resume attempts | Seat/committed launcher writes; chain/proof/operator reads | Proof/dispatch observation semantics specified; exact legacy filenames are implementation/seat conventions (`fleet-launch/dispatch-dual.sh:192`, `:279`, `:305`). |
| `tmp/petri-canary/headroom-wait-f6cc.log`, capacity `samples.jsonl`, payload output JSON | Old headroom gates read/write rolling local baseline; observer/capture outputs | Caller headroom decisions are not licensed by the Dispatcher-owned condition; code evidence in §19. Capacity/proof observations are separate from quota authority. |
| Primary `tmp/gate-runs/<id>/{started_at,pid,output.log,exit_code,core_before,core_after,config-writes.log,...}` | Gate runner writes, seats/chains/plan-await read | Detached/protected launch behavior; concrete operational store in `dev-tooling/gate-run.sh:32`, `:64`; not a durable remote handle. |
| `RUN_DIR/{pid,output.log,verdict.env,verdict.env.tmp.*}` | Overseer detached-dispatch transport | Disk-verdict transport in `V/.claude-plugin/prose/overseer.md:724`; exact source `V/scripts/detached-dispatch.sh:25`. |
| Process-relative `tmp/livespec-console.sqlite` plus SQLite WAL/SHM, or `LIVESPEC_CONSOLE_STORE_PATH` | Console writes event/command/checkpoint store; projections/worker read | **SQLite/WAL/schema explicitly specified** at `C/SPECIFICATION/contracts.md:125`; concrete default `C/.../main.rs:1659`. |
| `~/.livespec-overseer.jsonl`, `.livespec-overseer-stamps.json`, `.livespec-overseer-repos.json` and locking sidecars | Daemon/operator mapping, restart rounds/injection and watch scope | Watch-set/mapping semantics explicitly specified at `V/SPECIFICATION/spec.md:887`, `:901`; concrete paths `V/overseer/_registry_core.py:113`. |
| `R/tmp/overseer/<topic>/.overseer-state`, supervisor equivalent, daemon singleton/round state; `daemon.log` and `.1`–`.7` | Seats declare ready/blocked/winding-down; daemon reads/updates/restarts/logs | Declaration/supervisor state **explicitly named** in `V/SPECIFICATION/contracts.md:23`; log behavior in `V/.claude-plugin/prose/overseer.md:130`. Deleting tmp removes restart interlock evidence. |
| `~/.local/share/livespec-overseer/runtime/<revision>/venv/` | Installed daemon runtime code/venv | Distribution/runtime installation, not plan state; observed executable path in §2. A checkout update is not proof this process changed code. |
| `~/.claude/sessions/<pid>.json`, `~/.claude/projects/.../*.jsonl`, Codex session/rollout files; `/proc/<pid>/*`; tmux/Herdr sockets, tabs and pane identities | Overseer/session adoption/context/model/liveness readers; harness/backend owns writes | Session/runtime/terminal observation explicitly specified by `V/SPECIFICATION/spec.md`, Supervised runtimes and session identity clauses; no portable terminal history is implied. Only process argv and Herdr listing were inspected here, not transcript/credential environments. |
| `R/tmp/drain-backlog/{snapshot.json,snapshot-UTC.json,dispositions.jsonl,handoff.md,engine-*.log,launch-*.log,last-tick}` | Drain session owns scope, progress cursor, fallback handoff and engine transport | **Committed operation prose** gives exact files (`V/.claude-plugin/prose/drain-backlog.md:37`); do not substitute that for a claim that every file is named by governing SPECIFICATION. |
| `~/.local/share/caam/vault/claude/<profile>/`, `~/.local/state/caam-usage-rotate/{state.json,switch.lock,selected-account.json}` | Rotation program reads profiles/live credential/history, serializes switch and publishes selected identity | Account-rotation behavior specified in `V/SPECIFICATION/spec.md`; exact paths in `V/overseer/caam_profile_state.py:58`, `caam_switch.py:46`, `caam_selection_record.py:43`. |
| Runtime Cron/one-off warm-wake jobs | Caam owning interactive session creates; runtime schedules and expires | Exact self-install/schedule/lifetime in `V/.claude-plugin/prose/caam-anthropic-loop.md:18`; separate from system unit installation. |
| Container named volume `livespec-orch-realwork-varlib`, clones `/workspace/...`, in-container `.beads/metadata.json`, `/tmp/livespec-realwork-{journal.jsonl,dispatch.log}` | Explicit real-work adapter creates/reads/copies/cleans; Dispatcher writes inside container | Containerized dispatch substrate documented in `orchestrator-image/real-work-dispatch.sh:1`; fresh clone does not inherit journal/control files. Sandbox-local `/workspace/.tmux` is another generated **sandbox**, not operator-host, namespace (`O/_dispatcher_tmux_socket_root.py:37`). |
| Historical `tmp/overseer/foreman/` runtime/heartbeat/lock/panel files and supervisor binder files | **Retired** foreman and supervise-plan authorship | Historical source at removal parents (§8); no current foreman clauses in audited V spec. Surviving pair-member binder/state is listed separately above. |

Plan metadata, timeline comments and authority epochs are deliberately **not** in this host-local table: they live in the tenant ledger (`plan.md:243`; `C/.../research/012-...md:77`). `plan/<slug>/research/` and `associated_work_item_id` are committed/write-once context, not a replacement for that ledger. The table lists code/config dependencies as well as mutable state because moving hosts can fail on either; it does not recommend copying credential-bearing files or stale PID locks.

## 19. Complete tmp script inventory, by effect

At inspection `tmp/petri-canary/` had **868 immediate entries** and **918 recursive files**, including **115 `.sh` and 10 `.py` files**. Other recursive file counts were 229 `.txt`, 154 `.json`, 148 `.stderr`, 125 `.verdict`, 69 `.log`, 30 `.capture-argv`, 23 `.bak`, and smaller singleton/paired state formats. Those extensions describe artifacts, not additional schedulers. The three explicitly `RETIRED-*.txt` shell-source copies and backup suffixes are data/history, not counted as `.sh` entry points. Live script census and gate parents are in §2.

The inventory below lists **every `.sh`/`.py` file** observed. Its categories describe entry/invoker/decision/state effects and apply to each named file; executable call/path reference lines are included so a particular variant can be audited without trusting a family resemblance. All entries are uncommitted tmp artifacts; a fresh empty tmp contains none of them. Unless specifically identified as a cap/hold writer, a launcher reads those controls and writes launch artifacts, not the cap itself. Historical variants have not been executed to establish present usability, and lack of a process is scoped to §2's sample.

| Category | Entry point / invoker / decision | Reads | Writes / portability impact |
|---|---|---|---|
| D — direct launch | Seat calls one-item impl through a specific script/build | Item/config, indicated boards/CPU/credential probe; variants with cap/hold/queues/markers read those literal controls | Per-attempt JSON/stderr/log/verdict; ticket/holder/marker when present; delegates D-state. Empty tmp removes entry, history and sometimes control file. |
| R — resume launch | Seat continues one item using Dispatcher resume, sometimes resolves-blocked first | Same launch infrastructure as version; PR/run/journal resume evidence | Resume result/attempt files, launch coordination and delegated D-state. |
| S — sequence/fill | Seat starts fixed-list/file-list runner; waits on previous gate/log/status before launching next | `fill-queue*`, handled/active logs, named gate `output.log`/`exit_code`, plugin build, readiness/preflight and child launcher | `fill-gates*`, registry/capture/sequence log/active records; preflight output and detached gate handles. Lost cursor can duplicate/skip/reorder scheduling. |
| H — headroom wait | Seat gate/probe decides whether quota is clear, sometimes launches a successor | Installed plugin/projection and local `headroom-wait-f6cc.log` baseline, provider credential/usage | Probe log and in-process prior reading; some exec successor. This historical caller condition duplicates admission concerns, not an independent authority endorsed here. |
| W — cap/hold control | Seat-started timed/conditional control | Current fleet cap, clock or target run/profile | Explicit cap rewrite or hold create/remove. State loss changes fleet-wide admission timing. |
| O — observer/waiter | Seat watches board/PR/release/host metric or an already-running dispatch | Remote board/SSH metrics or Git refs, markers, argv/process evidence as applicable | Stdout/log, metrics sample file; release watchers fetch tags and thus update local Git refs. Does not itself dispatch unless separately chained. |
| C — credential/config helper | Seat/launcher invokes shim or resolver | Host wrapper/argv/PATH/credential source or committed default-factory config | Wrapper's own credential-cache effects; fetch refs for default resolver; child command's effects. |
| P — proof payload | Seat generates host proof JSON from recorded dispatch | Capture argv/verdict/gate log, dispatch journal, installed/factory registries and PR/run | Caller-named output JSON, no dispatch; missing evidence blocks proof. |
| Q — readiness/precheck | Runner checks ledger/blockers/criteria through selected build | Item/store/config/comments/dependencies; no status-only stand-in asserted | Stdout/exit verdict; callers persist it. No independent scheduler. |

<!-- The per-file census is appended below from the read-only source inventory. -->

| File under `tmp/petri-canary/` | Class | Executable source evidence (line numbers; category above supplies effects) |
|---|---|---|
| `3lbt4o-after-ry43xm.sh` | S | handled/active log L11; prior gate log L7; result files L11; `dispatch-dual-r267.sh` L10 |
| `after-cap2-blm57z.sh` | S | cap L9; `dispatch-dual-r681.sh` L15 |
| `bdgj-relaunch-r373.sh` | S | `with-livespec-env.sh` L7; `dispatch-dual-r361.sh` L11 |
| `bdgj-tail-r361.sh` | S | plugin registry L9; prior gate log L8; `with-livespec-env.sh` L11; `dispatch-dual-r361.sh` L14 |
| `blocker-check.py` | Q | L6: `plugin, repo, item_id = sys.argv[1], sys.argv[2], sys.argv[3]` |
| `canaries-r338.sh` | S | plugin registry L10; prior gate log L15; `dispatch-dual-r314.sh` L13 |
| `canaries-r339.sh` | S | plugin registry L11; prior gate log L16; `dispatch-dual-r314.sh` L14; `dispatch-dual-r267.sh` L22 |
| `canary-0220-dual.sh` | D | cap L33; in-flight L32; FIFO/mutex L151; plugin registry L180; impl call L183; result files L183; refs L179; `with-livespec-env.sh` L183 |
| `canary-7rnipp-r177.sh` | D | impl call L57; result files L57; `with-livespec-env.sh` L57 |
| `canary-7rnipp-r178.sh` | D | impl call L27; result files L27; `with-livespec-env.sh` L27 |
| `canary-7rnipp.sh` | D | impl call L26; result files L26; `with-livespec-env.sh` L26 |
| `canary-knnhbn.sh` | D | plugin registry L33; impl call L37; result files L37; refs L30; `with-livespec-env.sh` L37 |
| `capacity/sample-gmktec.sh` | O | result files L60 |
| `capture-runner-r373.sh` | S | prior gate log L8; `hp-item-capture-r373.sh` L15 |
| `capture-tail-r373.sh` | S | prior gate log L16; `hp-item-capture-r373.sh` L12 |
| `capture-tail2-r374.sh` | S | prior gate log L16; `hp-item-capture-r373.sh` L12 |
| `capture-tail3-r374.sh` | S | prior gate log L16; `hp-item-capture-r373.sh` L12 |
| `chain-934d.sh` | S | prior gate log L11; result files L21; `hp-item-r369.sh` L21 |
| `dispatch-36d3x5-hp-r220.sh` | D | FIFO/mutex L14; plugin registry L88; impl call L92; result files L92; refs L87; `with-livespec-env.sh` L92 |
| `dispatch-36d3x5-hp-r221.sh` | D | FIFO/mutex L14; plugin registry L100; impl call L104; result files L104; refs L99; `with-livespec-env.sh` L104 |
| `dispatch-36d3x5-hp-r222.sh` | D | FIFO/mutex L14; plugin registry L100; impl call L104; result files L104; refs L99; `with-livespec-env.sh` L104 |
| `dispatch-36d3x5-hp.sh` | D | FIFO/mutex L14; plugin registry L76; impl call L80; result files L80; refs L75; `with-livespec-env.sh` L80 |
| `dispatch-7qfnh6-hp.sh` | D | FIFO/mutex L12; plugin registry L37; impl call L41; result files L41; refs L36; `with-livespec-env.sh` L41 |
| `dispatch-dual-f6cc.sh` | D | cap L62; hold L221; in-flight L61; FIFO/mutex L223; plugin registry L192; impl call L274; result files L204; refs L260; `with-livespec-env.sh` L194 |
| `dispatch-dual-r249.sh` | D | cap L38; hold L154; in-flight L37; FIFO/mutex L156; plugin registry L185; impl call L191; result files L191; refs L184; `with-livespec-env.sh` L187 |
| `dispatch-dual-r250.sh` | D | cap L41; hold L167; in-flight L40; FIFO/mutex L169; plugin registry L200; impl call L206; result files L206; refs L199; `with-livespec-env.sh` L202 |
| `dispatch-dual-r262.sh` | D | cap L42; hold L168; in-flight L41; FIFO/mutex L170; plugin registry L201; impl call L207; result files L207; refs L200; `with-livespec-env.sh` L203 |
| `dispatch-dual-r263.sh` | D | cap L43; hold L169; in-flight L42; FIFO/mutex L171; plugin registry L202; impl call L208; result files L208; refs L201; `with-livespec-env.sh` L204 |
| `dispatch-dual-r264.sh` | D | cap L44; hold L170; in-flight L43; FIFO/mutex L172; plugin registry L203; impl call L209; result files L209; refs L202; `with-livespec-env.sh` L205 |
| `dispatch-dual-r265.sh` | D | cap L53; hold L182; in-flight L52; FIFO/mutex L184; plugin registry L220; impl call L231; result files L231; refs L219; `with-livespec-env.sh` L222 |
| `dispatch-dual-r266.sh` | D | cap L55; hold L184; in-flight L54; FIFO/mutex L186; plugin registry L222; impl call L233; result files L233; refs L221; `with-livespec-env.sh` L224 |
| `dispatch-dual-r266x.sh` | D | cap L57; hold L186; in-flight L56; FIFO/mutex L188; plugin registry L224; impl call L235; result files L235; refs L223; `with-livespec-env.sh` L226 |
| `dispatch-dual-r267.sh` | D | cap L58; hold L210; in-flight L57; FIFO/mutex L212; plugin registry L184; impl call L263; result files L197; refs L249; `with-livespec-env.sh` L186 |
| `dispatch-dual-r267x.sh` | D | cap L59; hold L210; in-flight L58; FIFO/mutex L212; plugin registry L185; impl call L263; result files L197; refs L249; `with-livespec-env.sh` L187 |
| `dispatch-dual-r268.sh` | D | cap L58; hold L196; in-flight L57; FIFO/mutex L198; plugin registry L184; impl call L249; result files L249; refs L235; `with-livespec-env.sh` L186 |
| `dispatch-dual-r268x.sh` | D | cap L59; hold L196; in-flight L58; FIFO/mutex L198; plugin registry L185; impl call L249; result files L249; refs L235; `with-livespec-env.sh` L187 |
| `dispatch-dual-r314.sh` | D | cap L61; hold L217; in-flight L60; FIFO/mutex L219; plugin registry L187; impl call L277; result files L204; refs L256; `with-livespec-env.sh` L189 |
| `dispatch-dual-r361.sh` | D | cap L61; hold L220; in-flight L60; FIFO/mutex L222; plugin registry L191; impl call L273; result files L203; refs L259; `with-livespec-env.sh` L193 |
| `dispatch-dual-r369.sh` | D | cap L60; hold L215; in-flight L59; FIFO/mutex L217; plugin registry L190; impl call L270; result files L202; refs L256; `with-livespec-env.sh` L192 |
| `dispatch-dual-r681.sh` | D | cap L64; hold L253; in-flight L63; FIFO/mutex L236; plugin registry L204; impl call L100; result files L226; refs L295; `with-livespec-env.sh` L210 |
| `dispatch-dual-r681b.sh` | D | cap L70; hold L275; in-flight L69; FIFO/mutex L246; plugin registry L214; impl call L109; result files L236; refs L319; `with-livespec-env.sh` L220 |
| `dispatch-fubkcv.sh` | D | plugin registry L33; impl call L37; result files L37; refs L30; `with-livespec-env.sh` L37 |
| `dispatch-petri-current.sh` | D | cap L34; in-flight L88; FIFO/mutex L31; plugin registry L118; impl call L176; result files L176; refs L172; `with-livespec-env.sh` L176 |
| `dispatch-petri-r232.sh` | D | FIFO/mutex L19; plugin registry L71; impl call L73; result files L73; refs L70; `with-livespec-env.sh` L73 |
| `dispatch-petri-r234.sh` | D | FIFO/mutex L23; plugin registry L102; impl call L104; result files L104; refs L101; `with-livespec-env.sh` L104 |
| `dispatch-petri-r236.sh` | D | FIFO/mutex L25; plugin registry L111; impl call L113; result files L113; refs L110; `with-livespec-env.sh` L113 |
| `dispatch-petri-r237.sh` | D | FIFO/mutex L27; plugin registry L123; impl call L125; result files L125; refs L122; `with-livespec-env.sh` L125 |
| `dispatch-petri-r238.sh` | D | cap L31; FIFO/mutex L28; plugin registry L128; impl call L130; result files L130; refs L127; `with-livespec-env.sh` L130 |
| `dispatch-petri-r239.sh` | D | cap L33; in-flight L87; FIFO/mutex L30; plugin registry L158; impl call L160; result files L160; refs L157; `with-livespec-env.sh` L160 |
| `dispatch-petri-r240.sh` | D | cap L34; in-flight L88; FIFO/mutex L31; plugin registry L118; impl call L176; result files L176; refs L172; `with-livespec-env.sh` L176 |
| `dispatch-petri-resume-r238.sh` | R | cap L34; FIFO/mutex L31; plugin registry L138; resume call L140; result files L140; refs L97; `with-livespec-env.sh` L140 |
| `dispatch-petri-resume-r239.sh` | R | cap L36; in-flight L91; FIFO/mutex L33; plugin registry L162; resume call L164; result files L164; refs L161; `with-livespec-env.sh` L164 |
| `dispatch-petri-resume-r240.sh` | R | cap L37; in-flight L92; FIFO/mutex L34; plugin registry L122; resume call L180; result files L180; refs L176; `with-livespec-env.sh` L180 |
| `dispatch-petri-resume.sh` | R | FIFO/mutex L30; plugin registry L133; resume call L135; result files L135; refs L92; `with-livespec-env.sh` L135 |
| `dispatch-petri.sh` | D | plugin registry L18; impl call L20; result files L20; refs L17; `with-livespec-env.sh` L20 |
| `dispatch-resume-r382.sh` | R | cap L62; hold L221; in-flight L61; FIFO/mutex L223; plugin registry L192; resume call L284; result files L208; refs L260; `with-livespec-env.sh` L194 |
| `dispatch-resume2-r267.sh` | R | cap L56; hold L185; in-flight L55; FIFO/mutex L187; plugin registry L225; resume call L262; result files L262; refs L224; `with-livespec-env.sh` L227 |
| `dispatch-resume3-r308.sh` | R | cap L59; hold L210; in-flight L58; FIFO/mutex L212; plugin registry L185; resume call L265; result files L197; refs L249; `with-livespec-env.sh` L187 |
| `dispatch-resume4-r315.sh` | R | cap L62; hold L217; in-flight L61; FIFO/mutex L219; plugin registry L188; resume call L280; result files L204; refs L256; `with-livespec-env.sh` L190 |
| `dispatch-txadim-hp.sh` | D | FIFO/mutex L12; plugin registry L37; impl call L41; result files L41; refs L36; `with-livespec-env.sh` L41 |
| `fill-precheck-pa.py` | Q | L4: `plugin, item_id = sys.argv[1], sys.argv[2]` |
| `fill-precheck-stale.py` | Q | L5: `plugin, item_id = sys.argv[1], sys.argv[2]` |
| `fill-precheck.py` | Q | L4: `plugin, item_id = sys.argv[1], sys.argv[2]` |
| `fill-runner-r265.sh` | S | plugin registry L14; queue input L11; handled/active log L12; prior gate log L25; result files L17; `with-livespec-env.sh` L16; `fill-precheck.py` L16; `dod-preflight.sh` L18; `dispatch-dual-r265.sh` L22 |
| `fill-runner-r266.sh` | S | plugin registry L16; queue input L13; handled/active log L14; prior gate log L28; result files L19; `with-livespec-env.sh` L18; `fill-precheck.py` L18; `dod-preflight.sh` L20; `dispatch-dual-r266.sh` L35 |
| `fill-runner-r267.sh` | S | plugin registry L16; queue input L13; handled/active log L14; prior gate log L28; result files L19; `with-livespec-env.sh` L18; `fill-precheck.py` L18; `dod-preflight.sh` L20; `dispatch-dual-r267.sh` L35 |
| `fill-runner-r289.sh` | S | plugin registry L17; queue input L14; handled/active log L15; prior gate log L29; result files L20; `with-livespec-env.sh` L19; `fill-precheck.py` L19; `dod-preflight.sh` L21; `dispatch-dual-r267.sh` L36 |
| `fill-runner-r291.sh` | S | plugin registry L21; queue input L18; handled/active log L19; prior gate log L33; result files L24; `with-livespec-env.sh` L23; `fill-precheck-stale.py` L23; `dod-preflight.sh` L25; `dispatch-dual-r267.sh` L40 |
| `fill-runner.sh` | S | plugin registry L14; queue input L12; handled/active log L13; prior gate log L21; result files L17; `with-livespec-env.sh` L16; `fill-precheck.py` L16; `dispatch-dual-r263.sh` L18 |
| `headroom-probe-r396.py` | H | L18: `sys.path.insert(0, f"{sys.argv[1]}/scripts/bin")` |
| `headroom-then-bzrzr3-r469.sh` | H | `headroom-wait-r450.sh` L7; `hp-item-r369.sh` L10 |
| `headroom-then-bzrzr3-r471.sh` | H | plugin registry L8; headroom log L9; `with-livespec-env.sh` L12; `headroom-probe-r396.py` L12; `headroom-verdict-r471.py` L14; `hp-item-r369.sh` L19 |
| `headroom-verdict-r471.py` | H | L8: `rc, prev_rem, prev_ok = sys.argv[1], sys.argv[2], sys.argv[3] == "1"` |
| `headroom-wait-f6cc.sh` | H | plugin registry L7; headroom log L11; `with-livespec-env.sh` L10; `headroom-probe-r396.py` L10 |
| `headroom-wait-r450.sh` | H | plugin registry L9; headroom log L10; `with-livespec-env.sh` L13; `headroom-probe-r396.py` L13 |
| `hold-gmktec-until-davaxq-r279.sh` | W | hold L9; `dispatch-dual-r267.sh` L7 |
| `host-capture-payload-f6cc.py` | P | plugin registry L90; prior gate log L80; impl call L106; result files L4; `host-capture-payload-r373.py` L4; `observe-capture-r391.sh` L104 |
| `host-capture-payload-r373.py` | P | plugin registry L90; prior gate log L80; impl call L106; result files L4; `observe-capture-r391.sh` L104 |
| `host-capture-payload-r681.py` | P | plugin registry L102; prior gate log L92; impl call L118; result files L6; `host-capture-payload-r373.py` L6; `observe-capture-r391.sh` L116 |
| `hp-item-capture-r373.sh` | S | plugin registry L9; handled/active log L14; result files L14; refs L8; `with-livespec-env.sh` L12; `fill-precheck-pa.py` L12; `dod-preflight.sh` L15; `dispatch-dual-r369.sh` L17 |
| `hp-item-r1.sh` | S | plugin registry L8; handled/active log L13; result files L13; refs L7; `with-livespec-env.sh` L11; `fill-precheck-pa.py` L11; `dod-preflight.sh` L14; `dispatch-dual-r266x.sh` L16 |
| `hp-item-r2.sh` | S | plugin registry L8; handled/active log L13; result files L13; refs L7; `with-livespec-env.sh` L11; `fill-precheck-pa.py` L11; `dod-preflight.sh` L14; `dispatch-dual-r267x.sh` L16 |
| `hp-item-r369.sh` | S | plugin registry L9; handled/active log L14; result files L14; refs L8; `with-livespec-env.sh` L12; `fill-precheck-pa.py` L12; `dod-preflight.sh` L15; `dispatch-dual-r369.sh` L17 |
| `launch-sequence-09ea.sh` | S | `dispatch-dual-r681.sh` L26 |
| `ma3fvj-resume-after-t3znvw-r291.sh` | S | `with-livespec-env.sh` L9; `dispatch-resume2-r267.sh` L11 |
| `mluwnm-headroom-gate-r396.sh` | H | plugin registry L7; `with-livespec-env.sh` L10; `headroom-probe-r396.py` L10; `mluwnm-launch-r391.sh` L12 |
| `mluwnm-launch-r391.sh` | S | `with-livespec-env.sh` L7; `dispatch-dual-r361.sh` L11 |
| `observe-capture-r391.sh` | O | Entry/source L1; category as above |
| `observe-repos-f6cc.sh` | O | result files L37 |
| `r369-seq.sh` | S | prior gate log L6; `hp-item-r369.sh` L8; `with-livespec-env.sh` L12; `dispatch-dual-r361.sh` L15 |
| `r404-runner.sh` | S | plugin registry L8; prior gate log L29; result files L20; `with-livespec-env.sh` L12; `headroom-probe-r396.py` L12; `mluwnm-launch-r391.sh` L20; `hp-item-capture-r373.sh` L25 |
| `r405-runner2.sh` | S | plugin registry L9; prior gate log L22; result files L15; refs L15; `with-livespec-env.sh` L11; `headroom-probe-r396.py` L11; `hp-item-capture-r373.sh` L19 |
| `r414-runner3.sh` | S | plugin registry L9; prior gate log L22; result files L15; refs L15; `with-livespec-env.sh` L11; `headroom-probe-r396.py` L11; `hp-item-capture-r373.sh` L19 |
| `ready-set-check.py` | Q | L5: `plugin, repo, item_id = sys.argv[1], sys.argv[2], sys.argv[3]` |
| `registry-switch-runner-r320.sh` | S | prior gate log L25; `hp-item-r2.sh` L20 |
| `registry-switch-runner-r338.sh` | S | plugin registry L22; prior gate log L18; `hp-item-r2.sh` L25 |
| `registry-switch-runner-r339.sh` | S | plugin registry L23; prior gate log L19; `hp-item-r2.sh` L26 |
| `registry-switch-runner-r352.sh` | S | plugin registry L17; prior gate log L25; `hp-item-r2.sh` L20 |
| `registry-switch-tail-r339.sh` | S | plugin registry L9; prior gate log L8; `hp-item-r2.sh` L12 |
| `relaunch-after-wkfwtx.sh` | S | handled/active log L11; prior gate log L6; result files L11; `dispatch-dual-r267.sh` L10 |
| `release-hold-on-caam-rotation.sh` | W | hold L6 |
| `requeue-runner-r310.sh` | S | plugin registry L19; handled/active log L13; prior gate log L25; result files L39; `with-livespec-env.sh` L35; `ready-set-check.py` L35; `fill-precheck-stale.py` L37; `dod-preflight.sh` L39; `dispatch-dual-r267.sh` L42 |
| `resolve-default-factory.sh` | C | refs L6 |
| `restore-cap-1320.sh` | W | cap L6 |
| `restore-cap-r255.sh` | W | cap L6 |
| `resume-fill-after-7f66ar-r2.sh` | S | plugin registry L9; handled/active log L21; prior gate log L5; result files L18; `with-livespec-env.sh` L12; `fill-precheck.py` L12; `dod-preflight.sh` L17; `dispatch-dual-r266.sh` L20; `fill-runner-r266.sh` L25 |
| `resume-fill-after-7f66ar-r3.sh` | S | plugin registry L9; handled/active log L21; prior gate log L5; result files L18; `with-livespec-env.sh` L12; `fill-precheck-pa.py` L12; `dod-preflight.sh` L17; `dispatch-dual-r266.sh` L20; `fill-runner-r266.sh` L25 |
| `resume-fill-after-7f66ar.sh` | S | handled/active log L8; prior gate log L4; `fill-runner-r266.sh` L7 |
| `resume-fubkcv-2.sh` | R | plugin registry L23; resume call L28; result files L26; refs L21; `with-livespec-env.sh` L26 |
| `resume-fubkcv.sh` | R | plugin registry L23; resume call L28; result files L26; refs L21; `with-livespec-env.sh` L26 |
| `runtime-lfu53l-r1.sh` | S | plugin registry L10; handled/active log L15; prior gate log L6; result files L15; `with-livespec-env.sh` L13; `fill-precheck-pa.py` L13; `dod-preflight.sh` L16; `dispatch-dual-r266x.sh` L18 |
| `ry43xm-after-b5-pw.sh` | S | handled/active log L12; prior gate log L7; result files L12; `dispatch-dual-r267.sh` L11 |
| `sequence-r4.sh` | S | plugin registry L6; handled/active log L11; prior gate log L16; result files L10; `dod-preflight.sh` L5; `with-livespec-env.sh` L10; `dispatch-dual-r266.sh` L12; `fill-precheck-pa.py` L20; `fill-runner-r266.sh` L24 |
| `sequence-r5.sh` | S | plugin registry L6; handled/active log L13; prior gate log L15; result files L10; `dod-preflight.sh` L4; `with-livespec-env.sh` L8; `fill-precheck-pa.py` L8; `dispatch-dual-r266.sh` L12; `fill-runner-r266.sh` L20 |
| `wait-gmktec-quiet.sh` | O | in-flight L10 |
| `watch-gmktec-oom.sh` | O | L5: `read0() { ssh -o BatchMode=yes cwoolley@gmktec-xubuntu "awk '/^oom_kill /{print \$2}' $S/memory.events; a` |
| `watch-pr-merge.sh` | O | L6: `s=$(gh pr view "$pr" -R "$repo" --json state,mergeCommit --jq '.state+" "+(.mergeCommit.oid // "")' 2>/de` |
| `watch-release-8623f79b.sh` | O | refs L6 |
| `watch-release-9f2e3ff2.sh` | O | refs L6 |
| `with-dolt-server-env-keep-path.sh` | C | wrapper L6; `with-dolt-server-env.sh` L6 |
| `with-homelab-wrapper-keep-path.sh` | C | wrapper L5 |
| `with-mi-homelab-key-and-livespec.sh` | C | `with-homelab-aws.sh` L5; `with-livespec-env.sh` L7 |
| `with-openbrain-env-keep-path.sh` | C | wrapper L5; `with-openbrain-env.sh` L5 |
| `with-resume-env-keep-path.sh` | C | wrapper L5; `with-resume-env.sh` L5 |
| `woacnk-chain-r318.sh` | S | result files L7; `with-livespec-env.sh` L7; `dod-preflight.sh` L7; `dispatch-dual-r267.sh` L10 |

Census check: 125 source files (115 shell, 10 Python), each assigned exactly one category. All referenced files were read as text; none was launched.


## 20. Open questions for the dispatch-control-plane plan

These are research gaps/design choices, **not permission questions or actions taken by this note**.

1. **Who owns durable fleet scheduling?** The maintainer's provisional-launch charter prefers the console or first-class loop tool (`bd-ib-jr6w7v`), while the console's ratified boundary forbids a resident deciding scheduler (`C/SPECIFICATION/spec.md:65`). The control-plane plan must record the actual ownership ruling and distinguish human command UI from fleet budget/queue execution. An unavailable foreman skill cannot be selected as an existing surface (§8).
2. **What state must survive a host/checkout disappearing?** `bd-ib-k6dqwc` explicitly asks for identical admission, hold and recovery decisions without the dispatch journal. The concrete counterexamples in §3 and the fleet controls in §12 give a starting acceptance population. Which authoritative replacement will cover journal releases/holds, headroom baselines, degraded steps, resume/replay history, cross-host claim accounting, FIFO/cap/hold and pending console commands? Copying JSONL into a new local path does not answer the plan's requirement that none of the decision state be a host-local file.
3. **When will scheduled supply actually be installed, and under what fleet budget?** The committed `work-supply@` path is absent here (§6); independent per-tenant firings would still have to compose with fleet token constraints. This note does not infer an authorization to install it, set a cap, or wake every ready queue. Its contract deliberately adds no host-scoped admission lock; overlapping-writer defects are documented in its README, with `bd-ib-2vda` / `bd-ib-m1av` as references.
4. **When does provisional-launch cutover complete?** `bd-ib-klkbxp`'s latest sampled handoff awaits C2 then C3; the running r681b jobs independently show adoption unfinished. Until the new reader/runner is verified, deleting tmp scripts would break the path carrying today's load. The other plan owns that transition; no cleanup was attempted here.
5. **Which obsolete caller gates need disposition?** The shipped drain-backlog master-CI gate and historical tmp headroom gates do not conform to the current Dispatcher-owned caller boundary (§3, §9, §19). They should be resolved by their owning contracts/implementation tracks, not silently treated as future requirements. The r681b versus committed launcher hold-scope difference also needs to be understood at cutover (§13).
6. **What should observation write?** The current standalone reconcile command documents one journal pass record even for `--dry-run`, while both its older header and console adapter language describe a read-only projection (§4). Decide the intended persistence boundary explicitly so future UI polling does not acquire hidden host-state effects.
7. **How much traffic comes from each surface fleet-wide?** This note establishes one host process population and one tenant's bounded journal sample, and names the two unattributed launch stamps. It cannot attribute those unknown callers or establish remote-host/whole-fleet proportions. A durable invocation/run identity source would permit that measurement without counting watchdog traffic or trusting an opaque identity as a human attestation (§2).
8. **What remains of the supervisor pair-member removal?** `overseer-hnjolu` still has a human interpretation gate and the current spec/code retain the role (§8). The 2026-09-09 amendment preserves overseer/caam/drain-backlog, but that is not evidence the later supervisor-residue plan has landed. Keep retired skill authorship, surviving pair protocol and daemon `supervisor.py` distinct.

No ledger mutation, launch, timer installation, credential rotation, commit, branch or worktree was performed for this research. Existing untracked spec proposals in the primary checkout were left alone. The only authored output is this note.

RESEARCH-NOTE-COMPLETE
