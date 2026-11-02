# 014 — Responsibility and evidence appendix

[Back to index](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/README.md)

Supporting detail for proposal 013 · reconciled 2 November 2026.

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
service exists. Engineering choices are centralized in proposal 013's **Decisions
remaining** section. Per-item delivery and proof remain with owning plans.

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

## Delivery obligations retained with the incumbent and domain owners

These **15 requirements** preserve report 011's October 27 carrier snapshot.
They are neither a fresh closure audit nor fifteen children of this plan. Later
rulings may change a carrier or disposition; the owning ledger governs that
change. A new control-plane deployment cannot count as completing these programs.

| Requirement | Recorded carrier/owner and continuity obligation |
| --- | --- |
| 1. Fleet repositories route to gmktec, not hp. | Factory migration/retirement (`bd-ib-iud52v`); progress follows each repo's outcome. |
| 2. A dispatch from each cut-over repo appears on gmktec. | Migration and runtime adoption (`livespec-runtime-gfhy2a`); require observed runs, not configuration alone. |
| 3. Correct engine build and safe legacy-service retirement. | Fabro currency (`bd-ib-6tcjfx`) and retirement owners; respect later upgrade deferrals. |
| 4. Real Kubernetes implementation merges and Kubernetes becomes default. | Kubernetes sandbox delivery (`bd-ib-nmuyjc`); hosting coordination on Kubernetes is different proof. |
| 5. A 24-hour measurement supports gmktec cap. | Owning capacity proof retains that specific obligation; short routing tests cannot replace it. |
| 6. hp leaves committed factory inventory. | Retirement/deployment owner; verify committed and applied state without blocking unrelated work. |
| 7. Every node emits resource/condition signals. | Node observability (`livespec-dev-tooling-dfdiil`); retain identity and 15-minute coverage criteria. |
| 8. Pods expose placement, requests/limits and allocatable context. | Collector attribution (`livespec-dev-tooling-a2aiza`); telemetry owns delivery. |
| 9. Workload health includes restarts, OOM and pending/admission failures. | Workload telemetry (`ec2rkp`) and last-termination follow-up (`jmwa7k`), both in dev-tooling; a closed predecessor does not erase residual work. |
| 10. Control-plane/datastore/quota/Kueue health is visible. | Control-plane emission (`vdleg7`, dev-tooling); retain kine/SQLite versus etcd and factory-quota versus CI-queue distinctions. |
| 11. Useful board and actionable triggers. | Observability owners (`uftb4o`, `b7wwgy`, `t6om4l`, dev-tooling); unified attention complements source evidence. |
| 12. Collector/board/trigger state converges through GitOps. | Telemetry/deployment owners; retain reproducibility and drift proof. |
| 13. Refused-commit incomplete turns can retry with actual hook findings. | Workflow stability (originally `bd-ib-y7372n`); prove released behavior across applicable factories. |
| 14. Applicable repos reject staged lint/type errors before expensive checks. | Dev-tooling shared fix (`nil6v7`) and adopting repo owners; preserve exclusions and cross-tenant carrier map. |
| 15. Needs-human endings expose recorded cause and hook verdict. | Workflow evidence (`bd-ib-36d3x5`, `bd-ib-k3nmbi`); attention cannot compensate for missing source evidence. |

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
| Coordinator comments through November 1 22:21:44 UTC, filtered for delegation/control-plane/follow-up changes, plus current epic | R121/R158 void at October 28 09:52; relevant R219 void at October 30 18:28. October 31 13:06 clarifies legacy picker unblocking. Later routing/cap observations are historical context, not authority to override current config. |
| Livespec current `SPECIFICATION/spec.md` | Complementary diagrams and zero direct Driver-to-orchestrator dependencies; effective spec policy and drift doctrine; proposal age is productivity tooling, not a doctor invariant. |
| Current orchestrator `_spec_change_tier_wall.py` and `_dispatcher_loop_candidates.py` | Wording now says linked-proposal ratification; the hold remains. This replaces report 012's diagnosis of obsolete comments. |
| Current `_needs_attention_spec_next_run.py` | Unresolvable core, failed subprocess or unusable output can return no row. A missing inbox row is not an authoritative empty-work observation. |
| Follow-up epic timeline, final capture/replay/completeness and forge PRs above | Released conformance and bounded fixture proof are recorded and archived. This session checked records and publication, not a new live execution. |
| Console `plan/retire-overseer-and-redesign-control-plane-around-console/research/redesign-brainstorm-and-decisions.md`, D3 and section 5 | Complete Fabro workflow variants, interview consent and staleness initiation were designed. Avoid a second execution substrate; measure existing capability before extending it. |
| Retired reports 002–007, 009–012 and native receipt | Dated genesis, factory entry paths, alternatives, external source assessments, incident examples and transport probes. Research is not deployment evidence. |

The latest parent scope event specifically corrects “GitLab” to **GitHub only**.
The original sequence in report 010 failed in GitHub's Mermaid 12.2.0 renderer:
its message `current state; act` produced a line-13 parse error. The retired
copy replaces that semicolon with “and”; the proposal uses complementary diagrams
with explicit target/existing labels. Render inspection is documented separately
in the committed evidence receipt after exercising the actual GitHub web pages.

External primary sources consulted in the original October 26–27 research remain
linked in the retired reports: Dolt transaction implementation, Kubernetes
Jobs/CronJobs and leader election, Compose, transactional outbox guidance,
Fabro interviews, agent input protocols and durable-workflow alternatives. They
informed design tradeoffs, not a deployed-version concurrency guarantee. No
commercial product benchmark or broker selection is inferred from them.
