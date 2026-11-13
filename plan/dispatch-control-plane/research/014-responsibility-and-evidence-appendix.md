# 014 — Responsibility and evidence appendix

[Back to index](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/README.md)

Supporting detail for proposal 013 · ownership/evidence reconciled 2 November;
phase-two design and additional source review added 13 November 2026.

## How to read the inventory

A–G retain the **58 activity identifiers** from report 011; S retains the **eight
spec-side additions** from report 012. These are document row IDs, not work-item
IDs or implemented commands. Each row preserves the capability and its proposed
accountable owner. Historical mechanisms describe the October 27 inventory,
qualified by later rulings; they are not a current fleet-health census. Complete
incident examples and dated source keys remain in the retired reports.

“Progress”, “coordination”, “incident” and “attention” name the four judgment roles.
“Services” means deterministic collection, scheduling, supervision or reconciliation.
An owner named here is a proposed responsibility allocation, not a claim that its
service exists. The concrete design is in proposal 013; its **Decisions remaining** section
remains the single register of unresolved choices. Per-item delivery and proof remain with owning plans.

### A — Goals, priorities and ownership

| ID and capability | Historical mechanism | Proposed owner and preserved boundary |
| --- | --- | --- |
| A01. Answer ad-hoc fleet questions | Long-lived coordinator conversation and owner investigations. | Attention routes a durable request to the domain owner; the conversation can remain a frontend. |
| A02. Keep the actual mission current | Maintainer corrections and epic/carrier updates. | Owning plan retains goals; progress checks alignment; coordination resolves cross-plan conflicts. |
| A03. Notice a stalled main goal | Tick counters, deadlines and investigations. | Progress uses current goal-specific signals, not merely process liveness or obsolete hp counters. |
| A04. Set cross-plan priority | Rulings and ordered work lists. | Coordination sets granted priorities with reasons and review conditions; scheduler selects eligible work. |
| A05. Identify work owners | Seat roster, assignment and abandoned-work transfers. | Progress assigns plan/role/worker identities; supervision performs authorized startup and explicit handover. |
| A06. Resolve dependencies | Distinguishing real blockers from ordering preferences. | Coordination resolves semantics; owners update through public operations. Never remove blockers merely to fill slots. |
| A07. Keep independent tracks moving | Separate spec, capture, deployment and factory tracks. | Progress tracks every independent obligation, including host work and reviews, while workers execute eligible tracks. |
| A08. Track cross-repository work | Prose/carrier links where tenant edges cannot join. | Coordination uses repository/tenant plus item identity; own-plan status stays in each ledger. |
| A09. Preserve useful findings | Reuse items or park unassigned findings. | Progress routes intake; coordination assigns ambiguous work with bounded reconsideration, avoiding endless chat queues. |

### B — Sessions, questions and authority

| ID and capability | Historical mechanism | Proposed owner and preserved boundary |
| --- | --- | --- |
| B01. Detect blocked/unattended seats | Agent/pane inspection and inactivity checks. | Supervision exposes worker/obligation facts; progress distinguishes quiet, waiting and stalled work. |
| B02. Wake an owner concretely | Messages containing ruling and next action. | Progress creates durable assignment; services distinguish receipt, start and observed completion. |
| B03. Recover an authorized seat | Tabs, restarts and protected-session rules. | Supervision checks the affected plan's grant; protected sessions cannot be restarted by inference. |
| B04. Supervise the coordinator | Loop and overseer context monitoring. | Supervision owns lifecycle; obligations survive bounded worker exits, with successor fencing and recovery. |
| B05. Avoid fleet-wide question stalls | Nonblocking decisions and human referrals. | Attention preserves the decision and safe continuation while unrelated roles proceed. |
| B06. Answer delegated decisions | Maintainer delegation; later unauthorized R121/R158 restrictions voided. | Attention uses current grants and actual actor attribution. Peer objection cannot revoke delegation. |
| B07. Enforce real authority limits | Domain rules, tool refusals and corrected interpretations. | Accepting/applying services resolve sourced restrictions for the specific action; do not invent blanket bans or bypass controls. |
| B08. Clear a stale usage-limit menu | Authorized stop/wait and resume when allowance exists. | Adapter/supervision distinguish stale UI from genuine exhaustion and paid-credit purchase. Preserve scoped recovery. |
| B09. Respect account-policy ownership | caam usage/selection reads and rule E. | Scheduler consumes published availability; caam's owner retains rotation, protected accounts and reserve floors. |
| B10. Show understandable identities | Workspace/tab names alongside pane routing. | Frontends show named plans, roles and workers; durable identities route across hosts. |
| B11. Observe whether an answer unblocked work | Readback and later owner/item observation. | Services retain actor/grant/evidence and observe the required result; delivery alone is insufficient. |

### C — Supply, capacity and holds

| ID and capability | Historical mechanism | Proposed owner and preserved boundary |
| --- | --- | --- |
| C01. Determine runnable work | Public ranked readiness plus admission. | Scheduler consumes public eligibility; Dispatcher remains authoritative, not raw ready status. |
| C02. Audit idle capacity | Tenant listings, child links and factory boards. | Services classify causes and stale observations; progress finds owners. Audit heuristics do not admit work. |
| C03. Choose a supportable cap | Experiments, corrected metrics and rulings. | Capacity-policy owner judges evidence; scheduler enforces approved policy. Invalid metrics do not become valid through automation. |
| C04. Explain binding limits | Fleet/repo/Fabro/Kubernetes limits. | Scheduler models constraints separately; Fabro and Kubernetes retain enforcement. No second hidden host-slot scheduler. |
| C05. Prevent races and starvation | Mutexes, markers, staggered slots and FIFO. | Scheduler reserves through shared conditional writes and stale-owner fencing, with fairness and launch reconciliation. |
| C06. Hold/release deliberately | Scoped freezes, allowlists and local markers. | Durable holds carry reason and release condition; only granted incident/coordination actors change them. |
| C07. Account for provider capacity/spend | Account reports and quota/reset pacing. | Distinguish subscription, metered, local-model and factory-slot pools, interactive demand, uncertainty and protected reserves. |
| C08. Limit by acceptance capacity | Manual backlog/capture/replay coordination and WIP caps. | Scheduler considers downstream acceptance; progress exposes unmet review obligations rather than maximizing launches alone. |
| C09. Respect committed routing | Owner-controlled routing and rollout checks. | Scheduler uses permitted pools and current repository configuration; owners retain exceptions and policy changes. |
| C10. Use one launch control path | Divergent launchers replaced by centralized supply. | One fleet-supply service covers plan/console launches too; retire old callers only after migration. |

### D — Failures, proof and acceptance

| ID and capability | Historical mechanism | Proposed owner and preserved boundary |
| --- | --- | --- |
| D01. Know which runs live | Join boards, item facts and owner reports. | Services read authoritative Fabro state with freshness; dead clients do not imply finished runs. |
| D02. Classify endings | Separate convergence, workflow defects and infrastructure failures. | Deterministic signatures plus incident judgment; preserve corrections and their effect on decisions. |
| D03. Group root causes | Investigation across dumps, calls and telemetry. | Incident coordinates shared diagnosis; component owners investigate; grouped attention retains each obligation. |
| D04. Stop blind retries | Holds, bounded recovery and riders. | Services enforce per-action retry budgets, identity, current evidence and ownership; incident handles unfamiliar exceptions. |
| D05. Salvage healthy work | Resume preserved work/PR rather than reimplement. | Owning plan performs supported recovery; progress tracks outcome; incident owns the recurring infrastructure defect. |
| D06. Repair criteria/proof placement | Central intervention in assertion and proof failures. | Move judgment to capable plan owners and their reviews; progress ensures ownership before central help is withdrawn. |
| D07. Arrange independent proof | Separate capture/replay seats and released-build checks. | Owning plans commission independent participants; progress tracks availability and provenance through worker replacement. |
| D08. Close publication/acceptance loops | Route missing records, janitors and merged-open items. | Public reconcile/accept operations execute; progress observes acceptance, not merely merge or an answered question. |
| D09. Contain a broken shared release | Stop-the-line, revert/fix and rollout checks. | Incident coordinates containment, scheduler enforces scoped holds, owners repair and verify. |

### E — Deployment and housekeeping

| ID and capability | Historical mechanism | Proposed owner and preserved boundary |
| --- | --- | --- |
| E01. Restart factories and recover work | Capture/cancel/deploy/reap/redispatch sequence. | Incident coordinates; deployment/factory owners execute under specific authorization; partial maintenance retains every recovery obligation. |
| E02. Require meaningful canary/control | Mechanism-specific tests and positive controls. | Owning plan proves the change; incident checks transition risk. Image probes, implementation runs and host capture establish different claims. |
| E03. Watch rollout/rollback | Named watch runs and revert conditions. | Services evaluate known checks; incident handles unfamiliar symptoms; retain baseline, watch identity and terminal criteria. |
| E04. Make a release actually active | Compare merged, registered and running builds. | Installation owners expose versions; supervision refreshes authorized workers at safe boundaries; progress tracks adoption across tools. |
| E05. Evaluate model chains by outcomes | Node-specific quality and failure canaries. | Routing owner evaluates quality; incident coordinates risk; preserve actual selection/fallback evidence per dispatch/node. |
| E06. Release usable prerequisites | Check merge, release and relevant active build. | Services expose adoption predicates and admission enforces them; progress routes missing rollout work. |
| E07. Clean without losing live work | Dry runs, retention and protected references. | Existing cleanup owners use shared ownership/run facts; missing local markers never suffice as deletion permission. |
| E08. Coordinate distinct infrastructure owners | Separate factories/endpoints and repository exceptions. | Coordination/incident use explicit inventory and network interfaces; containers do not erase policies or tenant boundaries. |

### F — Measurement and waste

| ID and capability | Historical mechanism | Proposed owner and preserved boundary |
| --- | --- | --- |
| F01. Establish trustworthy evidence | Telemetry requests, controls and disputed measurements. | Telemetry owners supply source/freshness; services expose unknowns; incident investigates discrepancies. |
| F02. Attribute resource cost | Separate/deduplicated model, subprocess, factory and CI reports. | Existing telemetry owners supply distinct inputs; scheduler must not collapse tokens, billing and slots into one number. |
| F03. Reduce work before moving cost | Rule F prioritizes removed calls/tokens/run-hours. | Coordination applies policy; progress verifies outcomes; unchanged deterministic ticks invoke no model. |
| F04. Replace repeated recovery with fixes | Group failures, release fixes and retire riders. | Incident owns recurring cause; component plans implement; services verify adoption before mitigation removal. |
| F05. Operate observability itself | Collector, board, trigger and GitOps delivery program. | Observability/deployment owners retain delivery; progress tracks it; attention consumes it rather than replacing measurement. |

### G — State and continuity

| ID and capability | Historical mechanism | Proposed owner and preserved boundary |
| --- | --- | --- |
| G01. Remember operational commitments | Comments, sessions, local holds/FIFO/markers and journal. | Dedicated coordination Dolt owns shared runtime obligations; Beads/Fabro retain their facts. |
| G02. Preserve legitimate policy | Rules and corrections sometimes promoted peer restrictions. | Authenticated issuer, scope, source, revision and supersession; only entitled principals change grants. |
| G03. Hand over unfinished work | Handoffs, watchers, run/gate IDs and recovery pointers. | Supervision/reconciliation restore intent, attempt, effect and completion distinctly; no exactly-once claim from an action marker. |
| G04. Preserve answerer and authority | Post-answer messages correcting attribution. | Attach authenticated actor and represented grant to acceptance itself, surviving worker replacement. |
| G05. Report without endless transcript growth | Ticks and reports in a long-lived epic. | Views expose current obligations/changes; telemetry holds observations; ledgers retain plan rulings/outcomes. Retention must preserve evidence. |
| G06. Retire old coordination safely | Incumbent retains obligations after infrastructure changes. | Transfer responsibility explicitly, stop duplicate execution, prove continuity; dispose outstanding work before closing its epic. |

### S — Spec lifecycle obligations

| ID and capability | Current distinction | Proposed owner and behavior |
| --- | --- | --- |
| S01. Discover proposals without a plan session | Configured policy does not inventory work. | Deterministic supply inventories registered repos/spec trees; progress owns unassigned obligations; reconciliation repairs missed events. |
| S02. Follow a spec-change-tier hold | A valid hold alone supplies no continuation. | Progress follows linked topic; owning plan repairs missing proposals. Revise cannot repair a missing-topic hold by itself. |
| S03. Resolve decision ownership | Prose/summaries may conflict with effective policy. | Core resolves overrides/floors and exposes reasons; orchestrator consumes that result rather than inventing another policy interpreter. |
| S04. Start an eligible assessment | Ranked next result is not an initiation service. | Supply claims a bounded attempt; progress owns stalls. Permission to assess differs from permission to ratify. |
| S05. Review and decide | Released delegated operation now has bounded proof. | Core/independent participants retain exact-byte semantics; reconcile complete workflow variants before adding an executor. |
| S06. Recover interrupted/competing attempts | Publication can race or have uncertain outcome. | Coordination stores attempt/ownership; serialize conflicting spec publication per repo initially and reconcile target before retry. |
| S07. Continue after disposition | Publication and implementation eligibility are distinct. | Reconciliation observes disposition and re-evaluates held work; rejection never releases admission by itself. |
| S08. Detect starvation/unavailable observation | Current spec-next can drop its row on failure. | Deterministic supervision exposes failed observation and overdue attempts, not an apparently empty queue or model-driven poll. |

## Delivery obligations and their current owning plans

The **15 requirements** below originated in report 011's October 27 inventory.
On November 1 the maintainer replaced the old coordinator's assertions with one
transfer assertion, moved delivery to the owners below, then archived that plan.
This table incorporates that change; earlier carrier details remain historical in
report 011. The five owning epics' current descriptions were read directly from
their tenants on November 2. Ownership is established here, not completion of
their work. These are not children of dispatch-control-plane.

| Former requirement | Current accountable plan and assertion |
| --- | --- |
| 1. Fleet repositories route to gmktec, not hp. | gmktec-factory-placement (`livespec-dev-tooling-me5aqz`), assertion 1. |
| 2. A dispatch from each cut-over repo appears on gmktec. | gmktec-factory-placement, assertion 2; observed run required, not configuration alone. |
| 3. Correct engine build and safe legacy-service retirement. | gmktec-factory-placement, assertion 3; its November 2 wording names the serving candidate by build/commit. |
| 4. Real Kubernetes implementation merges and Kubernetes becomes default. | kubernetes-sandbox-backend (`bd-ib-nmuyjc`), assertions 1 and 5; its scope generalizes gmktec to the non-hp factory. |
| 5. A 24-hour measurement supports gmktec cap. | gmktec-factory-placement, assertion 4; short routing tests cannot replace it. |
| 6. hp leaves committed factory inventory. | gmktec-factory-placement, assertion 5. |
| 7. Every node emits resource/condition signals. | kubernetes-observability (`livespec-dev-tooling-s2aqob`), assertion 1; retains identity and 15-minute coverage. |
| 8. Pods expose placement, requests/limits and allocatable context. | kubernetes-observability, assertion 2. |
| 9. Workload health includes restarts, OOM and pending/admission failures. | kubernetes-observability, assertion 3; last-termination residual moved to this plan. |
| 10. Control-plane/datastore/quota/Kueue health is visible. | kubernetes-observability, assertion 4; retains kine/SQLite versus etcd and factory-quota versus CI-queue distinctions. |
| 11. Useful board and actionable triggers. | kubernetes-observability, assertion 5; unified attention complements source evidence. |
| 12. Collector/board/trigger state converges through GitOps. | kubernetes-observability, assertion 6; its reference to former assertion 11 is now assertion 5. |
| 13. Refused-commit incomplete turns retry with actual hook findings. | sandbox-commit-gate-ceiling (`bd-ib-qy5wol`), assertion 4. |
| 14. Applicable repos reject staged lint/type errors before expensive checks. | dev-host-test-gate-load (`livespec-dev-tooling-6vuiwe`), assertion 7. |
| 15. Needs-human endings expose recorded cause and hook verdict. | sandbox-commit-gate-ceiling, assertion 5. |

The old coordinator's current-state transfer record was independently replayed at
November 1 22:07:42 UTC and received completeness review at 22:14:54 UTC.
[Archive PR 3050](https://github.com/thewoolleyman/livespec-dev-tooling/pull/3050)
merged at 22:35:05 UTC as `1306ceb5159e5a987b59844454a6b2657135ef24`.
This discharged the transfer assertion, not the underlying delivery assertions.
The later verified ownership record supersedes the earlier unresolved-disposition
notes for the observability leftovers.

### The interim roles and replacement exits

**legacy-coordinator-agent** (`livespec-dev-tooling-6tgd2z`) directs and unblocks
owning plans and owns no delivery work. Its single completion assertion requires
the replacement to read maintainer priorities, report priorities/dependencies,
unblock seats and route decisions, then retire the legacy seat with no duty
unowned. Its November 1–2 scope rulings retain delegated picker authority,
source-verified reports and plan-specific sessions. Current report format is all
priorities, with dependency trees only for the top three. Priorities come only
from the maintainer and are read fresh; a failed read is reported, not guessed.
The latest record inspected is November 2 00:19:52 UTC. Temporary load/cap
observations are not copied into the architecture as permanent policy.

**legacy-dispatcher-agent** (`bd-ib-ynnykl`) runs the existing `tmp/petri-canary/`
and `tmp/petri-refill/` launchers break-fix only, retaining ticket ordering, holds,
refusal routing, outage re-ticketing and ending notifications to owning plans.
It owns no delivery items and adds no new features/scripts. Its single exit is
that this plan's scheduler admits gmktec work and no old temporary launcher process
runs on the dispatching host. Its November 2 00:08:18 handoff records current
continuity; transient queue order and caps remain there, not in this appendix.

The November 1 LEGACY CUTOVER decision explicitly keeps dispatch-control-plane
out of daily operations. This changes the identity and ownership assumptions in
the October 27 coexistence proposal, not the durable-storage, delegation,
no-duplicate-execution or proof boundaries. Replacing interim roles does not
move their domain plans' work into this plan.

## Reconciled evidence and its limits

### Spec-side autonomy follow-up

Read directly on 2 November from the livespec tenant: the follow-up epic is closed
as archived at **2026-10-31 19:56:05 UTC**. Its latest qualifying plan record is
**verified**, 19:47:15 UTC, by session `01686fd1-edc4-482c-8ac0-8df0e3738caf`,
after the 19:31 capture and 19:41 independent completeness review. It covers all
five assertions. An earlier 19:03 negative replay was followed by a fixture timing
repair and new capture/replay; it is not silently omitted or treated as final.

The record names core **v0.45.0**, Claude Driver **v0.12.1**, Codex Driver
**v0.8.4**, pi Driver **v0.6.2**, and orchestrator **v0.264.8**. It records released
wording checks across the Drivers and an installed Claude fixture operation with
independent review, a matching final-bytes digest, and manual/drift stops without
ratification. It is not an end-to-end control-plane test through every adapter.

Forge readback confirms [fixture repair PR 3019](https://github.com/thewoolleyman/livespec/pull/3019)
merged as `f68659fc8982a19fc5280fe16cda557c9c5ceac4`, and
[archive PR 3020](https://github.com/thewoolleyman/livespec/pull/3020) merged at
20:00:40 UTC as `6eab2338bf40ac71cbaf41ce9d0dbdc12eb8c0dc`.
Research/fixture files exist under livespec's `plan/archive/spec-autonomy-followup/`.
The coordinator's 20:03:06 UTC report independently records archival; this
reconciliation did not rerun that fixture or mint/copy credentials.

The closed **Pluggable factory workflow configs** mechanism (`bd-ib-yqpdrt`) does
not itself prove scheduled revise. Console D3 and section 5 explicitly designed
complete workflow variants and staleness initiation; retain that prior art.
General scheduling, the coordination store/services and complete workflow rollout
were deferred back to this plan in the follow-up's 19:17 scope event.
**Stale-proposal doctor invariant** (`livespec-yaig`) and **Spec-side autonomy rollout
shortfall** (`livespec-vb12`) remain separate reconsideration homes, not new
implementation carriers. Core currently classifies proposal aging as productivity
tooling, outside doctor invariants; any work on the former must reconcile that
contract rather than treating an old item title as authority.

### Six native input checks, 27 October

| Installed version then | Bare interactive | Headless |
| --- | --- | --- |
| Claude Code 2.1.311 / SDK 0.3.311 | Native question consumed Violet. | SDK callback held three seconds then returned Violet. |
| Codex CLI 0.164.0 | Native Plan-mode question consumed Violet. | App-server matching request/response completed after a three-second hold. |
| pi 0.84.4 / Node 24.20.0 | Loaded extension confirm consumed Yes. | RPC extension response with matching ID continued after three seconds. |

The unchanged [evidence receipt](evidence/input-verification-receipt.json) retains
IDs, results and terminal excerpts. Claude/Codex used model-issued questions;
pi exercised an extension with no model. Herdr was absent. Safe/isolated startup
excluded customizations; Codex continued without trusting a hook. These establish
native input transport, **not** installed Livespec integration, cross-host answer
routing, evidence/authority checks, concurrent answers, worker-loss recovery or
Compose/Kubernetes execution. Keep native request IDs distinct from durable IDs.

### Source and ruling register

| Source read | What it establishes and qualification |
| --- | --- |
| This epic's complete scope-event set, October 25–31 | Orchestrator ownership, dedicated non-Beads Dolt, typed capacity, performance-first/proportionate relief, portable services, coexistence and this consolidation request. Original six assertions remain unchanged. |
| Old coordinator scope/handoffs through November 1 22:21:44 UTC and its amended epic, plus new legacy-role records above | R121/R158 void at October 28 09:52; relevant R219 void at October 30 18:28. October 31 13:06 clarifies legacy picker unblocking. The November 1 cutover and transferred ownership supersede the old incumbent assumption; transient routing/cap observations do not override current config. |
| Livespec current `SPECIFICATION/spec.md` | Complementary diagrams and zero direct Driver-to-orchestrator dependencies; effective spec policy and drift doctrine; proposal age is productivity tooling, not a doctor invariant. |
| Current orchestrator `_spec_change_tier_wall.py` and `_dispatcher_loop_candidates.py` | Wording now says linked-proposal ratification; the hold remains. This replaces report 012's diagnosis of obsolete comments. |
| Current `_needs_attention_spec_next_run.py` | Unresolvable core, failed subprocess or unusable output can return no row. A missing inbox row is not an authoritative empty-work observation. |
| Follow-up epic timeline, final capture/replay/completeness and forge PRs above | Released conformance and bounded fixture proof are recorded and archived. This session checked records and publication, not a new live execution. |
| Console `plan/retire-overseer-and-redesign-control-plane-around-console/research/redesign-brainstorm-and-decisions.md`, D3 and section 5 | Complete Fabro workflow variants, interview consent and staleness initiation were designed. Avoid a second execution substrate; measure existing capability before extending it. |
| Retired reports 002–007, 009–012 and native receipt | Dated genesis, factory entry paths, alternatives, external source assessments, incident examples and transport probes. Research is not deployment evidence. |

The latest parent scope event specifically corrects “GitLab” to **GitHub only**.
The original sequence in report 010 failed in GitHub's Mermaid 12.2.0 renderer:
its message `current state; act` produced a line-13 parse error. Report 008 also used a semicolon in a sequence message and failed rendering.
The retired copies replace those semicolons with “and”; the proposal uses complementary diagrams
with explicit target/existing labels. The [rendering receipt](evidence/mermaid-rendering/receipt.json) records actual
GitHub frame inspection for all 11 blocks, exact source-byte matches and screenshots.
The current diagram bytes are identical to the immutable tested commit named there;
subsequent prose reconciliation does not change them. Browser captures used the
viewer reset control after scrolling into view; off-screen blank captures were
discarded rather than accepted as visual evidence.

External primary sources consulted in the original October 26–27 research remain
linked in the retired reports: Dolt transaction implementation, Kubernetes
Jobs/CronJobs and leader election, Compose, transactional outbox guidance,
Fabro interviews, agent input protocols and durable-workflow alternatives. They
informed design tradeoffs, not a deployed-version concurrency guarantee. No
commercial product benchmark or broker selection is inferred from them.

## Proposed phase-two completion assertions

These are **session-derived additions for confirmation**, not an amendment to the
epic. Keep the original six assertions verbatim. The numbers below would follow
them if confirmed. Each row is one observable outcome; the plan proof mode is
`host_captured`. An independent session must replay captured released-build steps.
The adapter/deployment matrix and fault cases qualify the relevant outcomes;
a native-input probe alone cannot discharge any portable coordination assertion.

| Proposed ordinal | Observable outcome |
| --- | --- |
| 7 | One fleet attention view exposes every pending coordination obligation with its source, required result, evidence age and current accountable owner. |
| 8 | An unreadable authoritative source appears as unavailable with its last observation time instead of a successful empty-work observation. |
| 9 | A question submitted through Claude, Codex or pi remains discoverable by its durable occurrence after its originating worker and host are lost. |
| 10 | An accepted answer records the authenticated actual actor and the versioned grant exercised for that question occurrence. |
| 11 | Answer acceptance refuses a cleared, superseded or evidence-changed question occurrence with the conflicting revision identified. |
| 12 | A supported target refuses application under an obsolete grant, occurrence or ownership generation before that answer can influence a future assignment. |
| 13 | Repeating the same supported target operation after a lost acknowledgement returns its original accepted result without a second answer or status effect. |
| 14 | A replacement worker reconciles an uncertain target effect before deciding whether to retry it. |
| 15 | Deterministic supervision exposes a still-unfulfilled required result at its due time even when its assigned process is alive. |
| 16 | Restoring coordination state preserves accepted decisions and unresolved effect identities so replacement workers can reconcile them. |
| 17 | A deterministic tick with unchanged relevant facts invokes no model. |
| 18 | An eligible isolated spec obligation progresses from discovery through the existing governed workflow to observed disposition and fresh linked-work eligibility evaluation. |
| 19 | The spec-work path preserves core manual/floor/refusal outcomes when a fixture is ineligible for delegated ratification. |
| 20 | Fleet supply derives placement budgets from one authoritative fleet concurrency policy revision while Dispatcher tenant WIP and Fabro execution limits retain their specified owners. |
| 21 | A fixed bounded preparation window continues preflighting queued eligible items while execution capacity is full. |
| 22 | A launch decision revalidates the prepared item's current admission and hold evidence immediately before invoking its public execution operation. |
| 23 | Placement feasibility accounts for co-resident gate admission/pending demand and per-node memory requests against allocatable memory with the explicit gate reserve. |
| 24 | Supply decisions retain distinct provider, local-model, factory-slot and acceptance-capacity constraints with the binding reason attributed to its policy owner. |
| 25 | Each transferred legacy duty has an accountable replacement and one active execution owner throughout handover and rollback. |
| 26 | Replacement coordination owners perform the retained A–G/S duties and retire the legacy coordinator with no duty unowned. |
| 27 | The replacement scheduler admits gmktec factory work through the public admission path. |
| 28 | The legacy dispatcher and obsolete `fleet-launch/` and temporary launch controls are retired, with no running process reading their former queue or cap files. |
| 29 | Per-dispatch and per-node selection/fallback evidence remains queryable by work item and dispatch identity after journal authority is removed. |
| 30 | Core component and family dependency diagrams describe the delivered roles, APIs, stores and actuators with code references that resolve. |
| 31 | While a human-only question remains pending, another independently assigned role completes its authorized required result without waiting for that question. |
| 32 | An authorized answer to a durable question produces its observed required continuation after the originating worker is lost, through the common client and deployment contracts. |
| 33 | One fleet-supply schedule supplies work after the superseded per-tenant and per-seat supply timers and policy loops are retired. |

Run the durable question/disposition/continuation case through all six client and
deployment combinations: Claude, Codex and pi, each on Compose and Kubernetes.
In each deployment, move from one client to a different client after losing the
worker, then use the remaining client for reconstruction. Include same-operation
retries, competing answers, a cleared-and-recurred question, evidence/grant
changes, an old worker writing after replacement, database restore and an
unavailable owning source. Start with the backlog disposition; the ready-path
fixture and later spec workflow prove continuation without production queues.
Record target effects separately from accepted answers and transport receipts.
For assertion 32, record the answered occurrence, the replacement worker's
continuation and the authoritative observation of the original required result;
question discovery or an accepted-answer receipt alone does not pass it.
For assertion 33, inventory the superseded timers and policy loops, verify their
retirement, and observe the single replacement schedule supplying work. An old
loop left active in shadow mode is not retirement evidence.
For replacement coordination, exercise every retained A–G/S duty against its
assigned owner; a partial pilot is not retirement evidence. The independent-work
case leaves the human-only question pending throughout the other role's completion.

The six existing assertions still cover journal genesis, factory entry paths,
the chosen owner, the exhaustive authority specification, fresh-host equivalence
and operator UX. The additional assertions do not weaken them. In particular,
local multi-checkout journal lookup and faster reads cannot discharge original
assertion 5. No fixed shadow duration or broad benchmark campaign is introduced.

## Proposed implementation cut and carrier-map preparation

Package names below describe proposed work, **not filed children or a second
queue**. File only after the relevant contracts and completion amendment are
confirmed. Reuse overlapping owned work before creating an item. Each eventual
implementation child needs a Definition of Done traced to the ratified governing
headings, its own permitted proof surface and the public filing display.

| Proposed package | Delivered behavior and prerequisite |
| --- | --- |
| Contracts and ownership | Specify fleet operations, question/answer identity, target receipts, state homes, authority boundaries and deployment-neutral recovery; reconcile host-concurrency, Process boundaries and current per-tenant supply contracts first. Update core diagrams when their corresponding contracts change. |
| Coordination state and service | Provide scoped network access, versioned operations, conditional writes, conflict/uncertain-commit recovery and restore on dedicated non-Beads Dolt; prove the deployed database assumptions before allowing mutations. |
| Answer target and assignment readers | Extend the existing public answer valve and all consumers so accepted answers are tied to current occurrences and target-side replay identity; demonstrate the isolated backlog disposition before the ready continuation. |
| Common clients and attention | Integrate Claude, Codex and pi with one durable decision API and one attention view; preserve unavailable observations and current actor/grant attribution through worker replacement. |
| Reconciliation and role activation | Recover requests against target receipts, wake bounded focused judgment only on relevant changes, and detect unfulfilled results independently of process liveness. Transfer one named question class only after target and deployment proof. |
| Fleet supply integration | Consume the separately published radar/admission contract; prepare work independently of free slots, reserve/reconcile shared resources and derived placement, and revalidate final admission. Do not duplicate the radar engine or Kubernetes placement implementation. |
| Spec-work integration | Reuse named workflow variants for one isolated discovery-to-disposition flow, exact-byte review, conflicting-publication recovery and linked-hold re-evaluation. Retain existing core authority. |
| Journal-authority migration | Move each decision reader to its owning shared source, preserving selection/audit evidence and proving identical decisions without a local journal from another host. |
| Staged handover and retirement | Prove the remaining duty inventory through explicit transfers, retain untransferred owners, and retire obsolete launch controls only after the replacement works. Capture/replay the released plan outcome separately from child closure. |

The authoritative carrier relation belongs only in the epic's `carriers:` scope
block. A complete map cannot honestly name unfiled child IDs or use `plan-level
proof` as a placeholder for work not yet routed. After confirmation, first record
the scope and explicit deferrals without claiming a complete map. File the
contract/spec work before its dependent implementation work. File dependent
implementation slices as backlog or otherwise held work, with their governing
proposed-change dependencies; filing does not establish readiness or admission.
Once the actual carrier IDs exist, assign every confirmed assertion to those
carriers or a genuine plan-level proof, amend the epic through the sanctioned
ledger path, and write and read back the complete carrier map. Ratify the
governing contracts and resolve each slice's admission findings before making it
ready or admitting it to implementation. Until those steps complete, the map and
contract changes remain named prerequisites, not accomplishments claimed by this
document.

## November 13 source reconciliation

The parent ledger received two additional design inputs after consolidation.
The November 11 launcher report requests preflight ahead at full capacity and
explicit gate/memory headroom. The November 12 relay cites the maintainer's
November 4 one-queue/one-number ruling and requests one fleet concurrency source
with derived placement. These are design inputs; this plan absorbs no current
operations and the dated launcher counts are not permanent settings.

The prior-art survey read all **2,429 orchestrator records across all statuses**
on November 13. The table records observed ownership/scope, not completion claims
inferred from titles. A source reviewer independently inspected the implementation;
that review is design evidence, not plan completeness review or Proof of Done.

| Source or existing work | Consequence for this design |
| --- | --- |
| `_drive_policy_valves.py`, `_drive_answer.py`, `_intake_valve_claim_writes.py`, `_drive_valve_delegation.py` and `_drive_cli.py` | Existing grant verification and optional guarded state writes are reusable. Answer append precedes the claim; the current CLI has no operation/occurrence/evidence-precondition arguments. Caller attribution is not authenticated network identity. Target support is a prerequisite, not delivered protection. |
| `contracts.md`, **Host concurrency belongs to the Fabro scheduler**, **Orchestrator-owned attention facts**, **Clock-fired work supply**, plus `constraints.md` **Process boundaries** | Current tenant-capacity projection, Fabro host ceiling and per-tenant timer contracts remain binding until revised. A fleet policy needs an explicit ownership amendment, not a new Dispatcher host gauge. |
| **Radar and deterministic admission** (`livespec-dev-tooling-w7ley3`), description and all scope events read directly from its tenant | Its assertion 23 explicitly requires a versioned input contract and this epic's adoption. The latest November 9 notes keep that track parked; this plan neither lifts its hold nor launches its children. Wait for the published contract and reconcile its fallback/placement semantics at the consumer seam. |
| **FIFO-head preflight during capacity wait** (`bd-ib-keuuwi`) | Preserve this existing launch-script work and owner; the new scheduler must retain its overlap rather than file a duplicate legacy repair. |
| **Launcher WIP single authority** (`bd-ib-5k2yq2`) | Existing work owns counted-claim parity and capacity-deferred handling. Distinguish that tenant limit from fleet policy and physical placement. |
| **Capacity-weighted sandbox placement** (`bd-ib-v5uti2`) | Kubernetes-sandbox-backend owns placement/provisioning; consume its allocatable/request observations instead of taking over its change. |
| **Journal-held attention facts** (`bd-ib-5xogp4`) | The item's scope is this repository's journal and explicitly excludes other hosts. Useful attention visibility is not replacement shared decision authority. |
| **Cross-checkout publish-branch lookup** (`bd-ib-ewdqub`) | Its described scope is local checkout journals; it does not establish original assertion 5's cross-host equivalence. |
| **Named workflow variants** (`bd-ib-yqpdrt`) and `_workflow_variants.py` | Reuse graph resolution and execution selection; separately prove automatic initiation and interrupted-publication recovery. |

Only the two current reports and index change in this documentation slice. The
Mermaid blocks and their original rendering receipts remain byte-identical;
no new diagram rendering or runtime proof is asserted here. Original assertions,
carrier authority, running services and legacy operating permissions are unchanged.

The separate design reviewer (`phase_two_draft_review`) found and corrected two
completion gaps: conditional transfer/cutover assertions could pass before the
legacy roles were actually replaced, and no assertion exercised independent role
progress while a human-only question waited. The revised proposed outcomes now
require observed replacement/retirement and that pending-question case. The review
also added definitive no-run reservation release and the Process boundaries
amendment prerequisite. These are design corrections, not executed proof cases.

A later independent requirements review (`phase_two_requirement_review`) made
the positive answer-to-continuation proof and retirement of per-tenant supply
loops explicit in proposed assertions 32 and 33. The duty inventory and delivery
prose already required those outcomes; named assertions avoid relying on the
omnibus duty-replacement assertion as their only proof obligation. The review
also clarified the scope, backlog filing, contract ratification and carrier-map
sequence above. These additions remain session-derived for confirmation and do
not amend the epic or authorize implementation.
