# 011 — What the coordinator does today, and who would do it next

[Back to index](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/README.md)

Detailed responsibility mapping · 27 October 2026 · authority correction 28 October 2026

Current coordinator: **gitops-fleet-capacity-monitoring**, `livespec-dev-tooling-dfixhe`.
Proposed replacement infrastructure: **dispatch-control-plane**, `bd-ib-k6dqwc`.

**30 October follow-up:** [Spec-side obligations and the autonomy repair](012-spec-side-obligations-and-autonomy-followup.md) adds the missing proposal/revision responsibilities, corrects the prior-art survey, and records the independent stopgap started before this plan update.

**Correction, 28 October:** this report originally treated R121 as an agreed
restriction. That was wrong: it was a coordinator-authored restriction following
a peer objection, not a verified maintainer decision. The maintainer has now
explicitly rejected it and the later blanket picker ban, R158. The coordinator's
09:52 handoff voids both. Preserve delegated authority and record the actual
answerer; do not solve misattribution by stopping authorized answers. See the
[stall-prevention requirements](#preventing-the-same-stall) and [C9](#c9).

The proposed system must preserve the coordinator's useful work while separating
judgment, routine checks, execution and human decisions. It is not simply the
same coordinator divided into four chat sessions. Much of today's work belongs
in ordinary services; some belongs with individual plan owners; some remains
fleet-wide judgment.

This report maps **58 recurring activities** and **all 15 current completion
requirements**. Each activity has one row, showing the present mechanism beside
its proposed destination. An activity can require several participants; the new
column names who is accountable and who performs the supporting work. The rows
are a responsibility inventory, not a claim that each historical incident is
still open or that the proposed services already exist.

The current-state evidence is a complete context-envelope snapshot containing
3,357 coordinator comments, including 21 scope events, 56 handoffs and 10 directly
linked children. Its latest comment is dated **2026-10-27 22:19:32 UTC**. I traced
the scope changes, standing rules and their corrections, recent operating reports,
and the current epic description. I did not re-run the fleet's live measurements.
Run counts, rollout examples and incident results below are attributed ledger
reports, not a new health check. Cross-tenant work is also linked in prose, so the
ten direct children are not the coordinator's complete workload. [Evidence](#evidence-and-how-to-check-it).

## The proposed owners, in plain language

The four judgment roles come from the approved second-pass design, with later
portability and delegation rulings applied. These are descriptive names for this
comparison, not implemented command names or four mandatory permanent processes.
Different roles can use different agents or models. A role's obligations persist
even when no model is running. [Proposed direction](009-portable-coordination-research-summary.md),
[original approved split](archive/004-discussion-transcript-and-maintainer-directions.md#the-coordinator-with-grants).

| Proposed owner | Responsibility | What it must leave to someone else |
| --- | --- | --- |
| **Plan-progress role** | Keep each authorized plan moving: find an absent owner, identify a stall, arrange continuation, and verify the required result. | Writing the plan's implementation, changing its acceptance criteria, or declaring its proof sufficient. Those belong to the owning plan and its established review process. |
| **Cross-plan coordination role** | Resolve conflicting priorities, dependencies, ownership and competing changes across plans. | Counting capacity, reserving slots, or implementing the changes it coordinates. |
| **Fleet-incident role** | Coordinate outages, releases, risky transitions and unfamiliar failures that affect several plans or factories. | Routine health polling, independent changes to credentials or account policy, or bypassing the deployment owner's controls. |
| **Attention and decision role** | Prepare questions with enough evidence to decide; answer within a recorded grant or obtain the authorized person's answer; track its application. | Treating every question as delegated, pretending an agent answer came directly from the human, or keeping other roles blocked while it waits. |
| **Fleet scheduler and admission services** | Combine eligible work with typed capacity, priorities, holds and reservations; enforce limits and reconcile launches. | Redefining a plan's goals or silently changing a repository's committed model routing. Fabro continues to own its host run slots. |
| **Attention, delivery and reconciliation services** | Assemble current facts; store and route questions, answers, assignments and action requests; reject stale requests; distinguish delivery from completion. | Deciding unfamiliar policy questions merely because a record exists. |
| **Session/worker supervision** | Detect an expired worker or missing heartbeat, preserve the obligation, and start an authorized continuation. Reuse overseer capabilities where applicable. | Restarting protected maintainer sessions or assuming an old worker has stopped merely because its lease expired. |
| **Individual plan owners and their execution workers** | Groom, implement, dispatch through public operations, repair proof, capture host evidence, accept and close their work. | Overriding another plan's policy or independently launching around shared admission. |
| **Existing infrastructure owners** | Fabro executes runs; deployment tooling applies GitOps; telemetry owners operate measurement; Dolt-server manages database lifecycle; caam owns account selection policy. | Becoming interchangeable just because all components use containers. |
| **Human, through a console, terminal or conversational frontend** | Make genuinely reserved decisions and change grants or product direction. | Serving as the manual relay between every agent and every other agent. |

The orchestrator owns coordination operations, derived facts and action rules;
`livespec-runtime` owns shared attention types; the overseer owns supervision
integration; the console presents public operations. Deployment and database
lifecycle stay with their respective owners. Exact service packaging and some
role boundaries remain design work.

**Status key in the tables:** **Agreed direction** means the responsibility follows
recorded decisions, although the implementation may not exist. **Assignment
needed** means this report identifies a necessary destination or contract that
the proposal has not yet specified. **Existing owner retained** means the new
control plane coordinates an existing capability instead of absorbing it.

## 1. Goals, priorities and ownership

Sources: [C1](#c1), [C2](#c2), [C3](#c3), [C7](#c7), [C8](#c8), [N1](#n1).

| Current capability or function | Specifically how the current coordinator provides it | How the new plan would provide it |
| --- | --- | --- |
| **A01. Answer ad-hoc fleet questions** | The maintainer talks to the long-lived coordinator session. It reads ledgers, factory state and owner reports, then answers or routes an investigation. This was part of the original charter. | **Attention role**, supported by the relevant domain owner, handles the conversation through any supported frontend. A question that requires work creates a durable request with an owner. **Agreed direction.** The existing conversation can remain the first frontend. |
| **A02. Keep the actual mission current** | Maintainer corrections changed the epic from an hp cap experiment to factory migration, then added Kubernetes observability and fleet-wide stability. The coordinator updates the DoD and which work items satisfy it. It previously failed to update the obsolete hp goal. | The **owning plan** retains its goals and rulings; **plan progress** checks that current work serves them; **cross-plan coordination** handles conflicts between goals. A maintained link from each obligation to its owner is needed. **Existing owner retained; exact tracking contract needs specification.** |
| **A03. Notice that the main goal is stalled** | Mandatory tick measurements counted repos not yet on Petri, hp runs and the next cutover action. An unchanged count across two ticks or a slipped ETA required dropping unrelated work and investigating the real blocker. Later priorities changed. | **Plan progress** evaluates current plan-specific progress signals. Deterministic checks raise a stall fact; an agent investigates when judgment is needed. **Assignment needed:** retain this goal-based check, not just worker liveness. Do not hard-code obsolete hp counters. |
| **A04. Set cross-plan priority** | It issues numbered rulings and a prioritized list, puts prerequisites or spend-reduction fixes at the head, and tells the Petri owner which tickets move. Rule F now ranks work removed above vendor switching. | **Cross-plan coordination** makes granted priority decisions; the **scheduler** consumes durable priority records. Changes carry their reason, authority and review condition. **Agreed direction.** Priority is policy; selecting the next eligible item is code. |
| **A05. Identify who owns a piece of work** | It maintains a seat roster, finds the owning plan, routes messages there, and has opened a named seat when no owner existed. It also transfers abandoned work to another owner. | **Plan progress** owns assignment and escalation; **supervision** starts an authorized worker. Store plan, role and worker identities separately from terminal locations. **Assignment needed:** owner handover, acknowledgement and abandoned-assignment rules. |
| **A06. Resolve cross-plan dependencies** | It distinguishes a real blocking prerequisite from an ordering preference, sometimes directing an owner to replace `blocks` with `relates-to`. R122 avoided blocking runnable work behind an hp retirement obligation that had no immediate executable action. | **Cross-plan coordination** resolves the semantic conflict; owning plans apply authorized changes through public operations. The scheduler then uses computed eligibility. **Agreed direction.** It must not remove a blocker merely to fill capacity. |
| **A07. Keep independent tracks moving** | It routes spec work, host captures, deployment work and factory work to their owners instead of treating a factory wait as a reason for the whole plan to stop. It asks what would make “host-bound” work faster. | **Plan progress** maintains the independent outstanding obligations; workers continue tracks whose prerequisites are met. **Assignment needed:** represent host work and reviews as well as factory dispatches. |
| **A08. Track work across repository boundaries** | The epic links work in other tenants through carrier lists and prose, because a native parent-child edge does not join different tenants. Assertion 14 alone names adoption work in eleven repositories. | **Cross-plan coordination** tracks references using repository/tenant plus item identity; each plan's own status remains in its ledger. Shared assignments and dependencies between owners live in coordination Dolt. **Agreed direction; cross-tenant reference schema still needed.** |
| **A09. Preserve findings without filing pointless work** | It reuses an existing item for repeated failures, routes new evidence to the right owner, and sometimes records a parking-lot finding until an owner exists. A work item must accomplish a real change, not merely manufacture activity. | **Plan progress** routes intake to the owning plan; **cross-plan coordination** resolves ambiguous ownership. **Assignment needed:** a bounded, reviewable home for unassigned findings, with a reconsider date, so they do not disappear into chat or an endless epic. |

## 2. Sessions, questions and delegated authority

Sources: [C2](#c2), [C3](#c3), [C4](#c4), [C5](#c5), [C6](#c6), [C9](#c9), [N2](#n2).

| Current capability or function | Specifically how the current coordinator provides it | How the new plan would provide it |
| --- | --- | --- |
| **B01. Detect blocked or unattended seats** | It uses agent lists and pane reads to find blocked pickers, idle/done seats and owners that have stopped progressing; its recent loop watches inactivity around forty minutes. | **Supervision** emits structured worker and obligation facts; **plan progress** interprets a genuine stall. **Agreed direction.** A quiet process, a waiting question and an unfulfilled assignment are distinct states. |
| **B02. Wake an owner with a concrete next step** | It sends a message naming the work, ruling and next action, then watches for a response or movement. Historically this used `herdr agent prompt` and cross-session messages. | **Plan progress** submits a durable assignment through the shared API. Delivery/reconciliation tracks received, started and completed separately. **Agreed direction; acknowledgement deadlines and retry contracts need specification.** |
| **B03. Create or recover an authorized seat** | It opens an owner tab or arranges restart after an outage. Rule A now makes the maintainer's active sessions, including dispatch-control-plane, monitor-only: no messaging, rename, restart or close by the coordinator. | **Supervision** starts a replacement only under the affected plan's grant. **Plan progress** escalates protected sessions to the human. **Agreed direction.** Protection must be checked by the service, not remembered only in an agent prompt. |
| **B04. Keep the coordinator itself supervised** | A Claude `/loop` and an overseer state file maintain its activity. Rule D forbids self-declared context wind-down: the overseer measures context and signals handoff, because premature “awaiting successor” previously left no replacement. | **Supervision** owns lifecycle; role obligations survive a worker's exit in shared state. A role may finish a bounded invocation without abandoning its work. **Assignment needed:** prove successor recovery, fencing and protected-session handling rather than copying a local state file into a pod. |
| **B05. Avoid stopping the whole fleet on a question** | The coordinator is forbidden to present a blocking picker. It decides ordinary operational questions and reports them; genuine maintainer questions appear as non-blocking text. | **Attention role** holds the decision request while unrelated roles continue. Its worker may stop after saving a safe continuation. **Agreed direction.** One waiting answer must not suspend the scheduler or all plan-progress work. |
| **B06. Answer delegated decisions** | The maintainer delegated authority to answer blocking seat pickers. R121 narrowed that authority following a peer refusal; R158 later stopped picker answers altogether. On October 28 the maintainer rejected both restrictions. The coordinator resumed answering and recording that it, acting under delegation, chose the answer. | **Attention role** answers a durable question under the active grant. The adapter preserves actual actor, represented authority, question identity and evidence version. A peer complaint is evidence to investigate, not a grant revocation. **Agreed direction; enforcement needs implementation.** |
| **B07. Enforce actual authority limits without inventing new ones** | The October 28 purge retains maintainer-sourced limits, including paid credits, caam policy, Codex hook-trust prompts and protected sessions. It explicitly voids R121's peer-derived blanket human-only restriction. Independently existing repository and tool controls must be identified by their own source, not attributed to R121. | **Attention and applying services** use authenticated grants and explicit governing restrictions. An objection must identify the action and actual conflicting rule; it cannot suspend unrelated authorized answers. A real tool refusal remains a specific unresolved operation with an owner and authorized resolution path. **Agreed direction; exact policy resolution and enforcement need implementation.** |
| **B08. Clear a stale usage-limit menu** | Amended rule B permits choosing “stop and wait” when the active account actually has allowance, then resuming the owner. It does not permit switching to paid usage credits. | **Supervision and the harness adapter** detect a recoverable stale session condition; **attention** decides exceptional cases. **Assignment needed:** separate stale UI state from genuine exhausted allowance and from a purchase decision. Keep the existing authorized recovery during transition. |
| **B09. Respect account-policy ownership** | The coordinator reads caam usage and selection. Rule E explicitly forbids instructing caam to change rotation, protected accounts or reserve floors—even under a general “unblock everything” direction. | **Scheduler** consumes published account availability; **incident/attention roles** route problems to caam's owner. **Existing owner retained.** Neither a scheduler nor a new coordinator agent gets account-policy authority by default. |
| **B10. Give the human understandable identities** | Reports must name workspace and tab, not opaque pane coordinates. Internally, however, the coordinator still needs pane addresses for terminal actions. | Frontends show plan, role, owner and human-readable worker names; stable IDs route actions across hosts. **Assignment needed:** preserve useful names without making a Herdr pane the identity of an obligation. |
| **B11. Verify that an answer actually unblocked work** | It reads back messages, checks the pane or item, and later observes whether the owner resumed. R120 exposed a separate problem: a delegated keypress had been recorded as direct maintainer authorization. | **Delivery/reconciliation** records answerer, grant and evidence, then observes the owning operation's result. **Attention** follows unresolved outcomes. **Agreed direction.** “Answer delivered” and “work completed” remain separate, and delegated provenance must remain visible. |

## 3. Work supply, capacity and holds

Sources: [C2](#c2), [C7](#c7), [C10](#c10), [C11](#c11), [N1](#n1), [N2](#n2).

| Current capability or function | Specifically how the current coordinator provides it | How the new plan would provide it |
| --- | --- | --- |
| **C01. Determine what can really run** | It asks for the Dispatcher's ranked ready set, checks prerequisites and routes eligible items. A raw `status == ready` list is forbidden as an admission decision because it ignores blockers. | **Scheduler** consumes the public readiness/ranking operation; **Dispatcher admission** remains authoritative. **Agreed direction.** Other consumers display the same derived eligibility instead of reconstructing it from statuses. |
| **C02. Audit unused factory capacity** | The idle-slot audit joins full tenant listings, all ways children are linked, and live factory boards. It classifies stale edges, acceptance work, approvals, unadmitted work and host-only work, then names owners and idle slot-hours. | **Deterministic capacity/attention service** produces the finding; **plan progress** gets the responsible owner moving. **Agreed direction.** Audit heuristics may flag suspicious edges but must not authorize dispatch or claim “merged” from `active` status alone. |
| **C03. Choose a supportable operating cap** | It requests throughput and waste measurements, issues cap experiments, and revises them. R128/R135 showed why a short completion window and a faulty image can produce misleading conclusions; the affected comparison was marked provisional. | **Fleet policy and scheduler services** enforce an approved cap/pacing policy; the **incident role** routes uncertain measurements to the capacity owner. **Assignment needed:** the estimator, experiment rules and authority to change policy. Automation does not make an invalid metric sound. |
| **C04. Keep the different limits consistent** | The Petri owner coordinates temporary fleet/gmktec caps and pre-run gates; repo WIP caps, Fabro settings and Kubernetes quotas can independently bind. The coordinator has found one stale limit silently keeping effective capacity below the intended value. | **Scheduler/admission** models each constraint separately and explains the binding one. Fabro and Kubernetes continue enforcing their own limits. **Agreed direction; exact integration needed.** Do not create a second hidden host-slot scheduler. |
| **C05. Prevent launch races and starvation** | Earlier launchers used a mutex, in-flight marker files, staggered slots and FIFO tickets. The Petri owner later centralized the FIFO; marker/launcher races still caused overshoot and conflicting turns. | **Scheduler** reserves before launch using conditional writes and stale-owner fencing in coordination Dolt; it provides a documented fairness policy. **Agreed direction.** The database transaction and external launch recovery still need proof. |
| **C06. Hold and release work deliberately** | It orders fleet or factory freezes, temporary allowlists and cap-zero intervals, using owner messages and local markers. Holds have reasons and reconsider/release conditions; some historical freeze criteria were later superseded. | **Scheduler** enforces durable scoped holds. **Incident or coordination roles** set/release only the holds their grants cover; attention shows affected work and the release condition. **Agreed direction.** Preserve current scope, not every old freeze rule. |
| **C07. Account for provider capacity and spend** | It consumes hourly spend/account reports, distinguishes interactive consumption from factory load, and paces work around quota and reset times. It cannot assume another provider is free or change caam policy. | **Scheduler** uses distinct subscription, metered and local-model pools, alongside factory slots; account telemetry comes from its owner. **Agreed direction.** Interactive demand, uncertain cost and protected reserves require explicit treatment, not one summed capacity number. |
| **C08. Limit work against acceptance capacity too** | It observes acceptance backlogs, assembles capture/replay help, and adjusts priorities while repo WIP limits constrain dispatch. Much of the acceptance bottleneck is handled manually after it appears. | **Scheduler** considers acceptance capacity as well as inference; **plan progress** exposes unmet capture/review obligations. **Agreed direction, metric undecided.** Do not treat an unfilled factory slot as permission to create unlimited downstream review work. |
| **C09. Respect committed routing and exceptions** | It arranges model-routing changes through owning plans and verifies the rollout. Separate factories and repository exceptions, such as mi-homelab, are not automatically included in a fleet-wide change. | **Scheduler** selects only pools allowed by the repository's committed routing. **Cross-plan coordination** handles a proposed policy change; owners implement it. **Existing owner retained.** No agent preference or stale message overrides current configuration. |
| **C10. Make every launch use the same control path** | R61 found old launchers and a seat dispatching outside the centralized Petri path; model environment settings were therefore inconsistent. The coordinator stopped the divergent path and had the owner relaunch with verified settings. | One **fleet-supply service** and shared admission replace per-seat launch policy. The design must also cover separately authorized plan/console dispatches so they cannot bypass holds or reservations. **Agreed direction.** Retire temporary launchers only after all active callers migrate. |

## 4. Failures, proof and acceptance

Sources: [C2](#c2), [C7](#c7), [C8](#c8), [C12](#c12), [C13](#c13), [N1](#n1).

| Current capability or function | Specifically how the current coordinator provides it | How the new plan would provide it |
| --- | --- | --- |
| **D01. Know which runs are actually alive** | It joins factory boards, item records and owner reports. R99 corrected a count of dispatcher-loop processes that had been mistaken for live runs; detached factory runs outlived their launchers. | **Fact collection/reconciliation** reads the owning Fabro service and records observation time/source availability. **Agreed direction.** A dead client or empty local process list must not imply a finished run. |
| **D02. Classify endings meaningfully** | It distinguishes converging fix rounds, defective workflow/proof behavior and infrastructure failures, excluding designed endings and probes from some tallies. These classes drive hold, retry and rollback decisions. | Deterministic classification covers known signatures; the **incident role** handles ambiguous cases using captured evidence. **Assignment needed:** a maintained classification contract and corrections that update affected decisions. |
| **D03. Find and group common root causes** | It asks owners or investigators to inspect tool calls, dumps and telemetry, challenges misleading summaries, and links several failed items to one cause. The zero-width-terminal incident joined apparent OOMs, long hooks and lost turns. | **Incident role** owns fleet-level diagnosis; owning plans investigate their components. **Attention service** groups affected work by cause without discarding individual obligations. **Agreed direction.** Fix the shared cause instead of answering the same question once per failed run. |
| **D04. Stop blind retries** | Repeated identical failures are held for diagnosis. Owners may resume a captured run with a specific rider or release it once under a bounded rule; failure budgets and known classes matter. | **Reconciliation/recovery service** enforces explicit retry policy and preserves action identity. **Incident role** decides unfamiliar exceptions. **Agreed direction; per-action contracts needed.** A retry must recheck evidence and ownership. |
| **D05. Salvage healthy work when orchestration fails** | It directs owners to finish from an existing PR or preserved work when publish/proof machinery fails, rather than pay for another full implementation. R149 used a hand-authored replayable proof instead of a third run. | The **owning plan** performs the supported repair/resume/local-completion route; **plan progress** tracks it, and **incident** owns the recurring factory defect. **Existing owner retained.** The new central roles should not become substitute implementers. |
| **D06. Repair acceptance criteria and proof placement** | The coordinator has become deeply involved in factory-captured versus host-captured splits, proof-loop riders, DoD corrections and deciding where an assertion can be demonstrated. Some rulings were later corrected after inspecting the actual item. | The **owning plan** owns those judgments, with its established reviews. **Plan progress** detects the blockage and obtains an owner/disposition. **Agreed boundary, explicit handover needed.** This is a responsibility to move, not a capability to delete. |
| **D07. Arrange independent capture and replay** | It assigns one seat to capture host evidence and another to replay it, checks observer identity and released builds, and follows the result through reconciliation and acceptance. | **Owning plans** commission and validate their proof; **plan progress** tracks separate capture, independent verification and closure obligations. **Assignment needed:** qualified reviewer availability and provenance must survive worker replacement. Independence is not just a second process name. |
| **D08. Recover publication and close the loop** | It routes divergent branches, missing proof records, merged-but-open items and failed janitors to the owner. It checks merge/release evidence and requires real acceptance; the priority list explicitly says never force-accept. | Existing **public reconciliation/acceptance operations** perform the work; **plan progress** follows the required result and escalates missing support. **Agreed direction.** An accepted answer or merged PR is not automatically completed work. |
| **D09. Stop a broken shared release from spreading** | It raises stop-the-line rulings, routes a fix or revert, checks the actual failure, and distinguishes release defects from host-specific gate failures. R143 did this when a change broke the Codex judge path and increased fallback spend. | **Incident role** coordinates containment; **scheduler** enforces the scoped hold; owning plans carry the fix/revert and verification. **Existing execution owners retained.** Exact automatic hold/release thresholds remain to be specified. |

## 5. Deployment, migration and housekeeping

Sources: [C1](#c1), [C10](#c10), [C12](#c12), [C14](#c14), [N2](#n2).

| Current capability or function | Specifically how the current coordinator provides it | How the new plan would provide it |
| --- | --- | --- |
| **E01. Coordinate a factory restart and recover its work** | Under the applicable upgrade authorization, it coordinates capture of live runs, cancellation to idle, guarded deployment, pod reaping, quota read-back and redispatch by the owners. Later rulings may defer a nonessential restart to avoid unnecessary cancellations. | **Incident role** coordinates the maintenance operation; deployment and factory owners execute it. Shared action records preserve every affected item until its recovery is observed. **Assignment needed:** a resumable maintenance contract, including authority and partial failure. No general host-mutation grant is implied. |
| **E02. Require a useful canary and a control** | It accepts a proportionate candidate test and checks that it exercises the failing mechanism. R145's control caught a probe aimed at the wrong stdout; the corrected image probe ran through both Docker and Kubernetes. | **Owning delivery plan** defines and executes the canary; **incident role** checks the fleet transition's evidence and risk. **Existing owner retained.** An image probe, a real implementation run and a host capture are different proof claims. |
| **E03. Watch a rollout and decide whether to roll back** | A release ruling names the first runs to watch, the new failure shapes that justify a revert, and temporary riders that can be retired after proof. It later audits observed failures against those criteria. | **Telemetry/reconciliation** evaluates known checks; **incident role** handles unfamiliar symptoms. **Assignment needed:** durable rollout/watch identity, comparison baseline, completion and rollback conditions. |
| **E04. Make an installed release actually active** | It checks merged versions, registry publication, per-repo plugin registrations and running-session freshness. It has sent `/reload-plugins` to idle seats while avoiding busy, protected and independently owned sessions. | Deployment/installation owners supply version facts; **supervision** replaces or refreshes authorized workers at safe boundaries. **Plan progress** tracks adoption. **Assignment needed:** installed-versus-running version contracts for all three harnesses. Container image publication alone is insufficient. |
| **E05. Evaluate model-chain changes by node and outcome** | It follows real canaries, distinguishes quality failures from infrastructure/provider failures, and may request a node-specific rollback rather than revert the whole chain. The model actually used matters, not just configured intent. | **Owning routing plan** evaluates quality; **incident** coordinates fleet risk; deterministic records preserve model selection and fallback per dispatch/node. **Agreed direction.** The scheduler consumes the approved chain rather than inventing one. |
| **E06. Release dependent work only when its prerequisite is usable** | It checks that a fix has merged, shipped and reached the relevant dispatcher or factory before lifting a hold. A merge on master is often insufficient because a running process still uses an old build. | **Reconciliation** exposes release/adoption predicates; **scheduler/admission** checks them before launch. **Plan progress** resolves missing rollout work. **Agreed direction; exact predicates need specification.** |
| **E07. Clean disk, pods and worktrees without losing live work** | The coordinator routes retention and reaper work to owners, requests dry-run counts, and protects live runs, recent failures and preserved references. A directly linked child fixed reaping a live run's source worktree. | Existing **cleanup services** own deletion rules and evidence retention; **incident/plan progress** handle exceptional debt. **Existing owner retained.** Shared ownership and run state must inform cleanup; a missing local marker is not sufficient permission to delete. |
| **E08. Coordinate different factories and infrastructure owners** | It routes work between hp, gmktec, candidate factories and mi-homelab, with separate endpoints and exceptions. It coordinates deployment owners instead of assuming one host or repository represents the fleet. | **Coordination and incident roles** work from an explicit factory/tenant inventory; services address the correct owner over the network. **Agreed direction.** Kubernetes deployment does not erase separate factory policies, database scopes or host responsibilities. |

## 6. Measurement and reducing wasted work

Sources: [C7](#c7), [C10](#c10), [C11](#c11), [C12](#c12), [C15](#c15), [N1](#n1).

| Current capability or function | Specifically how the current coordinator provides it | How the new plan would provide it |
| --- | --- | --- |
| **F01. Establish trustworthy operational evidence** | It requests Honeycomb, factory, Kubernetes and host measurements and challenges the instrument when results conflict. Examples include run-count corrections, a false “etcd” interpretation, missing event counts and mis-aimed canaries. | **Telemetry owners** provide attributed observations; deterministic services expose freshness and unavailable sources; **incident** investigates disagreements. **Existing owner retained.** The control plane must not quietly convert missing data into a healthy state. |
| **F02. Attribute resource use and cost correctly** | Token-spend-analysis supplies reports distinguishing main sessions, subprocess judges, subagents and factory runs. Corrections deduplicate messages/request IDs. CI pool job-hours were measured separately to inform Kueue weights. | Existing **spend and infrastructure telemetry owners** supply separate measures to the scheduler and role views. **Assignment needed:** resource attribution and cost-input contracts. Do not combine vendor billing, token work, CI demand and factory slots into one interchangeable number. |
| **F03. Prefer work reduction over moving the bill** | Permanent rule F requires ranking fixes by tokens, calls and run-hours removed. Prompt reduction, verdict reuse and avoided retries outrank provider switching unless the destination is confirmed effectively free. | **Cross-plan coordination** applies that policy; **plan progress** drives the owning efficiency plans and checks outcomes. Deterministic unchanged-state ticks make no model call. **Agreed direction.** Splitting into more agents must demonstrate lower total work, not merely distribute it. |
| **F04. Turn repeated observations into lasting fixes** | It groups recurrent proof failures into existing items, retires temporary riders when a released fix is proven, and asks owners to make repeated hand recovery unnecessary. | **Incident role** owns the shared problem; component plans implement it; **reconciliation** verifies the fix is active before removing the workaround. **Agreed direction.** Keep a durable link from temporary mitigation to permanent fix and its removal condition. |
| **F05. Operate the observability program itself** | Beyond consuming dashboards, the coordinator owns completion of node/pod telemetry, workload/control-plane signals, boards, alerts and GitOps convergence through the observability plan. | The **observability plan remains accountable for delivery**; telemetry/GitOps owners operate the result. **Plan progress** tracks completion, and **incident** consumes the signals. **Existing owners retained.** A new attention UI is not a replacement for the measurement system. |

## 7. State, reporting and continuity

Sources: [C2](#c2), [C3](#c3), [C4](#c4), [C8](#c8), [C9](#c9), [N1](#n1), [N2](#n2).

| Current capability or function | Specifically how the current coordinator provides it | How the new plan would provide it |
| --- | --- | --- |
| **G01. Remember current operational commitments** | Current obligations are spread across coordinator comments, owner handoffs, native sessions, local hold/cap files, FIFO tickets and in-flight markers; dispatch recovery also depends on the host-local journal. Owners reconstruct the active combination when they resume. | **Dedicated non-Beads coordination Dolt** owns cross-tenant assignments, questions, answers, holds, reservations and unfinished actions. Existing Beads items and Fabro run records remain authoritative for their own facts. **Agreed direction.** No fleet operational queue in a plan's comments. |
| **G02. Preserve policy without promoting peer preferences into rules** | Successors follow RULES, amendments and handoffs. R121 and R158 demonstrate that a newer numbered entry can still be an unauthorized restriction. This report initially repeated that error. The October 28 maintainer correction voids both. | Plan rulings remain in their owning ledgers. Shared grants/policy in coordination Dolt need authenticated issuer, source, scope, version and explicit supersession. Only a principal entitled to change a grant may do so; a coordinator cannot narrow the maintainer's delegation because a peer objects. **Assignment needed:** verify authority to change policy, not merely chronology. |
| **G03. Hand work over without losing waits or actions** | The coordinator records a sanctioned handoff; owners carry gate IDs, pending watchers, run IDs, FIFO order and recovery pointers. An apparently live session is not sufficient evidence that the obligation is progressing. | **Supervision and reconciliation** restore obligations from shared state and distinguish intent, attempted effect, observed effect and completion. **Agreed direction.** A crash between recording an intent and applying it requires reconciliation; an action marker alone is not an exactly-once guarantee. |
| **G04. Preserve who answered and whose authority they used** | R120 corrected a seat that called a coordinator keypress direct maintainer authorization. The ensuing restrictions R121/R158 were the wrong remedy and are now void. Current practice follows the picker answer with a message recording delegated authorship. | **Authenticated answer/action records** retain the actual actor and the maintainer grant separately. Services validate both; worker replacement preserves the grant. **Assignment needed:** make attribution part of the accepted answer, rather than a later message that can be lost. Accurate provenance must not remove authorized delegation. |
| **G05. Report progress without creating another endless transcript** | It posts ticks, hourly capacity results, owner reports and major-change summaries, and records them in the epic. The charter also called for six-hour reports. The accumulated history now exceeds 3,300 entries. | Deterministic views show current obligations and changes; telemetry holds observations; plan ledgers retain their own rulings and outcomes. **Attention role** gives concise human summaries. **Agreed direction; retention and digest-refresh policy need specification.** |
| **G06. Retire the old coordination mechanism safely** | The current session continues to carry obligations even when underlying launchers or processes change. Its old charter's “retire when bespoke hosts retire” condition no longer captures its expanded remit. | Transfer one responsibility explicitly, disable the incumbent's independent execution of it, and prove continuity before expanding. Keep the incumbent for untransferred duties. **Agreed direction.** Closing its epic requires disposition of outstanding obligations, not merely deploying containers. |

## 8. The coordinator's 15 completion requirements must also survive

These are delivery obligations, not fifteen new agents. The current epic already
names them. The new coordination infrastructure should help their owners finish
them; it must not silently move all their implementation into dispatch-control-plane
or declare them satisfied by installing a scheduler.

Carrier names below identify recorded responsibility, not a fresh audit of each
item's completion. Later owner reports amend some of the older carrier lists;
those differences are called out. Sources: [C1](#c1), [C8](#c8), [C13](#c13).

| Current requirement | How the current coordinator carries it | How it survives in the new arrangement |
| --- | --- | --- |
| **DoD 1. Every fleet repo routes to gmktec, none to hp** | Tracks per-repo configuration, the control-node factory inventory and cutover PRs; `bd-ib-iud52v` carries the cutover/retirement work. | Owning migration plan retains the requirement. **Plan progress** checks every repository's outcome; **coordination** resolves cross-repo blockers. Scheduler routing uses the verified inventory. |
| **DoD 2. The next dispatch from each cut-over repo actually appears on gmktec** | Requires observed runs, not only changed configuration. Recorded carriers include `bd-ib-iud52v` and `livespec-runtime-gfhy2a`. | Owning plans produce per-repository dispatch evidence. **Reconciliation** joins dispatch identity to the correct factory; **plan progress** notices missing proof. |
| **DoD 3. Correct gmktec engine build; hp legacy service retired safely** | Coordinates Fabro currency (`bd-ib-6tcjfx`) and hp retirement. A later direction deferred further upgrades and accepts the serving build for the current proof. | Currency and retirement owners remain. **Incident** coordinates any authorized upgrade/restart; **plan progress** respects the recorded deferral. Do not reinterpret “current candidate” as permission for an unsolicited upgrade. |
| **DoD 4. A real Kubernetes implementation run merges a PR, and Kubernetes becomes the default sandbox** | Tracks `bd-ib-nmuyjc` and its children, including implementation, default-provider changes and live proof. | Sandbox/migration owners retain execution and proof. **Plan progress** tracks it; **incident** coordinates the transition. Running the coordination API on Kubernetes does not satisfy this separate factory requirement. |
| **DoD 5. A 24-hour gmktec measurement supports the operating cap** | Plan-level proof uses Honeycomb for successes/hour, infrastructure failure share and OOMs. Cap experiments have required corrections and must exclude confounded conclusions. | The owning capacity plan retains the explicit proof obligation. **Telemetry** supplies data; **scheduler** enforces the resulting policy. A short question-routing demonstration cannot replace this still-recorded measurement requirement. |
| **DoD 6. hp has no factory role in committed inventory** | `bd-ib-iud52v` carries inventory retirement, with timing and passive-soak dependencies recorded separately. | Deployment owner implements retirement; **plan progress** verifies committed and applied state. **Coordination** prevents the retirement wait from blocking unrelated runnable work. |
| **DoD 7. Every cluster node reports resource and condition signals** | Observability plan `livespec-dev-tooling-dfdiil` and its collector/hostmetrics children cover CPU, memory, filesystems, network, Ready/pressure conditions, correct node/host identity and datapoints in every 15-minute window. | Observability owner retains delivery and operation. **Attention** exposes missing/stale sources; **incident** responds to real node problems. |
| **DoD 8. Pod measurements identify node/namespace, with requests and limits beside allocatable capacity** | Collector attribution work, initially `livespec-dev-tooling-a2aiza`, supplies data the coordinator needs to interpret actual placement and pressure. | Telemetry owner supplies the attributed measurements; **scheduler/capacity services** consume them without taking over the collector. |
| **DoD 9. Workload health is visible, including restarts, OOMs and admission/pending problems** | `ec2rkp` covers events/workload evidence. Its October 27 report says it closed and proposes `jmwa7k` for the remaining last-termination-reason evidence under this epic. | Observability plan and the explicitly transferred follow-up retain their obligations. **Plan progress** reconciles that carrier-map update; **attention/incident** consume workload facts. **Do not lose the follow-up simply because ec2rkp closed.** |
| **DoD 10. Control-plane, datastore, ResourceQuota and Kueue health are visible** | `vdleg7` carries control-plane emission. Scope corrections distinguish kine/SQLite from actual etcd, factory ResourceQuotas from CI/gate Kueue ClusterQueues. | Telemetry/deployment owners retain those distinctions. **Incident** consumes their health facts; **scheduler** uses the relevant quota facts. The new control plane must not flatten these into one queue. |
| **DoD 11. A useful board and actionable triggers exist** | Recorded carriers include `uftb4o`, `b7wwgy` and `t6om4l`. The latest observability report requests a factory ticket for the board/trigger work after its prerequisites closed. | Observability owner finishes the board and triggers; **scheduler** admits eligible implementation work; **plan progress** tracks remaining live verification. The unified attention view complements these tools. |
| **DoD 12. Collector, board and trigger state converge from GitOps** | Collector/deployment and board work must be reproducible from committed configuration and detect drift after apply. | Deployment/telemetry owners continue GitOps reconciliation. **Plan progress** tracks proof; **incident** handles unresolved drift. **Existing infrastructure ownership remains.** |
| **DoD 13. An incomplete implement turn after a refused commit can retry with the actual hook findings** | Initially mapped to `bd-ib-y7372n`; later stability work includes retry and detached-commit fixes. The requirement applies across factories on the released orchestrator. | The orchestrator workflow's owning plan delivers and proves this behavior. **Plan progress** tracks release/adoption; **incident** groups recurring failures. It is not a judgment for the attention agent to emulate by hand. |
| **DoD 14. Every applicable repo rejects staged lint/type errors before the expensive aggregate** | Shared fix `nil6v7` plus eleven per-repo adoption items. Scope excludes repos without the dev-tooling pin; cross-tenant adoption is recorded in the carrier map. | Dev-tooling and adopting repository owners retain implementation. **Coordination** follows the fleet rollout; **plan progress** verifies each applicable repo. Keep the explicit exclusions rather than expanding scope automatically. |
| **DoD 15. Every needs-human ending exposes its recorded cause and hook verdict** | Recorded carriers `bd-ib-36d3x5` and `bd-ib-k3nmbi`; the coordinator currently checks raw stage/tool evidence when summaries are misleading. | Workflow owners make the evidence available; **attention** presents it and **incident** diagnoses unfamiliar cases. **Plan progress** verifies the released behavior. A nicer UI cannot compensate for missing source evidence. |

## 9. Where the proposal needs work or deserves pushback

The mapping shows that the direction is useful, but four role names do not yet
cover the operating contracts required to replace the current coordinator.

| Issue exposed by the mapping | Why it matters | Required design response |
| --- | --- | --- |
| **The current coordinator is also the owner of a substantial delivery program.** | Factory migration, observability and stability are not merely “monitoring.” Removing the long-lived session could orphan them even if scheduling improves. | Retain the current epic and accountable delivery owners until each obligation is explicitly completed, transferred or deferred. Keep the 15-row mapping beside the service rollout. |
| **The proposed boundary is narrower than current practice.** | The approved split keeps per-item acceptance out of central coordination, but today's coordinator spends substantial effort repairing proof and arranging acceptance. | Move that work to capable plan owners and provide review/capture capacity. Removing the central work before the owners can do it creates a gap, not simplification. |
| **Peer objections have been promoted into binding restrictions.** | R121 and R158 narrowed the maintainer's delegation without his authority; R158 left a plan stalled for about five and a half hours. This report initially reinforced R121 by labeling it agreed direction. | Keep grant changes separate from observations and peer preferences. Enforce who can change grants, retain their source, and treat an unanswered delegated question as an overdue obligation. Correct attribution without revoking authority. |
| **Routine capacity enforcement and capacity policy are different jobs.** | The approved design says the coordinator should not touch caps, but some current experiments depend on judgment about invalid measurements, priorities and incidents. | Specify who owns policy changes, how they are approved, and what the deterministic scheduler may tune by itself. Preserve domain judgment without putting an LLM back into every admission. |
| **Service recovery is broader than restarting a process.** | A maintenance transition may be interrupted after some runs are cancelled, after a deployment, or before redispatch is recorded. A live model process may also have stopped fulfilling its obligation. | Model the maintenance and work obligations explicitly. Reconcile effects against Fabro and deployment state. Prove stale-worker exclusion and lost-notification recovery. |
| **A shared database is necessary to this direction but is not a complete workflow engine.** | A transaction cannot atomically include an arbitrary later Fabro, Beads or GitHub action. Recording “started” does not prove an action happened. | Prove each supported action's identity, retry, uncertain-outcome and stale-evidence rules. Keep cross-tenant coordination in dedicated Dolt; do not fall back to an epic comment stream. |
| **The evidence source can be wrong even when a query succeeds.** | Recent corrections changed run counts, cost rates, capacity conclusions, event counts and the datastore interpretation. | Preserve source identity, observation time, confidence and correction history. Validate important assumptions with a positive control before automating decisions from them. |
| **Four resident agents could increase the problem they are meant to solve.** | More sessions can mean more polling, context replay, duplicate questions and coordination chatter. Rule F now explicitly prioritizes removing work. | Keep duties persistent and invoke models only for changed facts requiring judgment. Measure tokens/calls/run-hours, useful outcomes and human handling time across the whole system. |
| **A universal worker must not erase domain ownership.** | caam, Fabro, GitOps, observability, spec review and plan acceptance each have distinct contracts and authority. | Give the new services narrow APIs into those owners. Keep the question “who may decide?” separate from “which process can execute?” |

## Preventing the same stall

The failure was not simply a missed message. A peer raised a valid attribution
problem; the coordinator chose an unauthorized policy change as the remedy;
that change became a standing rule; and blocked work did not trigger recovery.
A later report, including this one, then treated the recorded restriction as
legitimate. More emphatic prompt instructions alone leave all four failures
possible. Kubernetes and headless execution do not fix them either.

The following are **proposed implementation requirements**, derived from the
maintainer's correction. They are not deployed protections or newly approved
numerical timeout settings.

1. **Separate grants from observations.** Store shared coordination grants in
   dedicated non-Beads Dolt, with an authenticated issuer, recipient, scope,
   source and revision. A worker may report an objection or propose a change;
   it cannot turn that into a revocation. This is an API/write-permission
   boundary, not another instruction to the model. Do not give ordinary workers
   unrestricted SQL access to grant records. Existing owners retain domain
   controls; a coordinator-authored note cannot impersonate their policy either.
2. **Accept answers with attribution attached.** The answer records the actual
   actor, the grant being exercised, the specific question occurrence and the
   evidence revision. “The coordinator answered for the maintainer” is accurate;
   “the maintainer typed this” is not. The receiving plan checks the current grant
   and consumes the answer without asking the human to repeat an already
   delegated decision. During migration, any legacy picker adapter must preserve
   the authoritative attribution even if the UI cannot render it.
3. **Make unblocking an outstanding obligation.** A delegated question has an
   accountable role, a due time and an expected result. Deterministic supervision
   detects unanswered or unapplied answers independently of the model's loop.
   On expiry it verifies current authority, retries delivery or assigns a
   replacement decision worker, then checks continuation. A heartbeat or an
   “I am monitoring” message does not satisfy the obligation. Retries and
   replacement are bounded, with an escalation path, rather than an unlimited
   model loop. Exact time budgets remain to be chosen.
4. **Require a concrete basis for a refusal.** A refusal identifies the exact
   action, applicable rule and source. A peer's discomfort or a tool's wording
   does not become a fleet-wide prohibition. A genuine enforcing control is not
   bypassed: route its specific conflict to the authorized owner while other
   work continues. The coordinator may also have introduced a needless
   constraint in its own launch prompt; check that source as well as the ledger.
5. **Keep authority and work recoverable.** A replacement process reads current
   grants and outstanding questions from the shared service. It does not rebuild
   policy from the newest-looking chat paragraph. Superseded restrictions remain
   audit history but are excluded from active policy. Expired workers cannot
   overwrite newer answers or change the grant.
6. **Measure outcomes.** Track age of delegated questions, time from answer to
   observed continuation, unsupported refusals, repeated human requests for
   already delegated choices, and recovery cost. Advancing an obligation means
   observing its expected result, not receiving any arbitrary tool call. A
   timeout is a failed service obligation to recover, not permission to declare
   success or manufacture approval.

The first delivery should prove these behaviors on a small delegated decision
before broad rollout. These are acceptance scenarios to implement, not claims
that the existing six native-input probes already cover them:

| Scenario | Required observable outcome |
| --- | --- |
| A peer says “do not answer my picker.” | The objection is recorded; the maintainer's grant remains unchanged; an authorized answer is applied and the plan continues. |
| A worker tries to publish that objection as a standing restriction. | The policy write is rejected because the worker lacks authority to narrow the grant; unrelated authorized work continues. |
| A delegated answer is received. | The record identifies the actual coordinator actor and grant, and never claims the human typed it. |
| The coordinator remains alive but ignores a delegated question. | Its due time expires; supervision detects the unmet obligation and effects bounded recovery without waiting for the human to notice. |
| The worker dies after answering but before confirming application. | A replacement reconciles the same answer identity and observes continuation without duplicating the effect. |
| An old worker replays a superseded restriction or stale answer. | Current policy and answer revision checks reject the stale change; history cannot silently become active policy. |
| The maintainer explicitly revokes a grant, or an independently sourced control refuses the operation. | The affected action stops or follows the authorized exception path; the system does not broaden the restriction to unrelated work or bypass the control. |
| The chosen plan has independent work while one operation is unresolved. | Its owner continues the independent work, while the coordinator retains and resolves the blocked obligation. |

These checks belong to the portable coordination contract, exercised through
Claude, Codex and pi adapters and across worker loss on both Compose and Kubernetes.
The existing coordinator remains responsible until a particular duty has passed
that proof and been explicitly transferred. The admission/scheduler and supervision
services must detect this failure without spending a model turn on every poll.

## 10. What to transfer first, and what to keep with the incumbent

This is a proposed implementation order, not a new permission grant. The accepted
coexistence sequence remains observe → route questions → transfer one responsibility
→ expand. Each transfer needs an accountable owner, defined permissions, a shared
record, proof of the required effect and a way to recover from interrupted work.

| Slice | What moves to the new system | What the existing coordinator still does | Proof before expanding |
| --- | --- | --- | --- |
| **1. Shared read-only facts** | Aggregate current questions, owners, holds and relevant run facts through the existing public surfaces. | All decisions, routing and existing execution coordination. | Compare results with current sources, report unknown/stale inputs, and account for cross-tenant obligations rather than only direct children. |
| **2. One ordinary delegated decision class** | Save a question in coordination Dolt; accept the authorized answer through a common API; route it to the owning plan. | Answers within its existing grant and continues to own all untransferred duties and actual maintainer-sourced exceptions. Limiting the pilot does not narrow the incumbent's wider delegation. | Cross-host/harness answer delivery, stale/conflicting-answer rejection, accurate delegated attribution, process-loss recovery and observed continuation. Inject a peer objection and prove it cannot revoke the grant or leave the question unattended. Native-input tests in report 010 do not prove this. |
| **3. One plan-continuation responsibility** | A plan-progress worker takes a named obligation with fenced ownership; deterministic supervision handles routine recovery. | Untransferred plans, fleet incidents, migration and observability delivery, and unresolved judgments. | Explicit handover stops duplicate incumbent action; worker replacement preserves the obligation and does not wake a protected session. |
| **4. Scheduling and routine reconciliation** | Typed pools, reserve-before-launch, shared holds, fair supply and recovery replace the corresponding temporary launch mechanisms. | Policy exceptions and fleet incidents within its grants; domain owners retain their actual operations. | Prove database/concurrency guarantees, admission compatibility, account restrictions, rollback and unknown outcomes on both Compose and Kubernetes. |
| **5. Further judgment roles and retirement** | Transfer cross-plan and incident duties when their interfaces and owners are ready; retire obsolete scripts and state only after their callers migrate. | Any delivery obligation that has not been explicitly disposed. | All 58 functions have an owner or an explicit retirement decision; all 15 completion requirements retain a valid disposition. A container rollout alone never closes the coordinator epic. |

## Evidence and how to check it

This report follows the latest relevant rulings rather than treating the first
charter, the highest-looking R-number, or the last general authorization as final.
Some coordinator R-numbers repeat across days. Timestamps below are the ledger's
`created_at` values; an October 27 correction explicitly warns that some timestamps
written inside comment prose were estimated incorrectly.

The two context snapshots were obtained through the public, read-only `context`
operation, from each target repository's root:

```text
livespec-orchestrator-beads-fabro:context livespec-dev-tooling-dfixhe --json
livespec-orchestrator-beads-fabro:context bd-ib-k6dqwc --json
```

The first command belongs in `livespec-dev-tooling`; the second in this repository.
For the original timestamped comments, use the configured environment wrapper and
`bd comments <epic> --json` in the corresponding repository. Comment text is under
`text`. These commands are read-only. The table row IDs are for this report; they
are not new ledger items or deployed operation names.

<a id="c1"></a>
**C1 — Current mission and carrier map.** Coordinator epic description, all 15
assertions; scope events at 2026-10-22 22:03:16, 2026-10-24 16:13:46, 16:17:28,
16:28:13, 17:02:35 and 22:10:15; 2026-10-25 00:02:49 and 00:59:21 UTC.
The [original charter](https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/plan/gitops-fleet-capacity-monitoring/research/001-charter-2026-10-13.md)
is useful history but its original hp-cap DoD is superseded.

<a id="c2"></a>
**C2 — Coordinator discipline, tick and original operational split.** Scope events
2026-10-14 00:28:12, 08:42:06 and 09:10:34; RULES at 2026-10-20 11:35:27;
replacement RULES at 2026-10-22 22:03:18 and stall amendment at 22:32:06 UTC.
Historical numerical caps and freeze policies in these entries are not asserted
as today's values.

<a id="c3"></a>
**C3 — Ownership roster and protected sessions.** Handoffs at 2026-10-25 18:51:55
and 2026-10-26 13:25:16 UTC. The latter's rule A makes maintainer sessions
monitor-only. Its rule B is subsequently amended; its suggestion to decide caam
exclusion is subsequently withdrawn by rule E.

<a id="c4"></a>
**C4 — Supervision and authorized wind-down.** Correction at 2026-10-26 20:00:24
and standing rule D at 20:01:30 UTC.

<a id="c5"></a>
**C5 — Delegation and stale usage menus.** Maintainer direction/R54 at 2026-10-26
20:05:46 and amended rule B at 20:12:34 UTC. Read with C6 and C9, not in isolation.

<a id="c6"></a>
**C6 — Account policy remains caam's.** Standing rule E at 2026-10-26 20:16:29
and R98 at 2026-10-27 04:08:41 UTC; the latter refuses a live canary account switch
that would rewrite shared Claude state.

<a id="c7"></a>
**C7 — Acceptance work and spend reduction.** Priority handoff at 2026-10-26
19:06:27, corrected spend priority at 2026-10-27 04:50:11, permanent rule F at
04:53:01, and R105 at 04:54:54 UTC.

<a id="c8"></a>
**C8 — Latest delivery and remaining work.** R122 at 2026-10-27 09:31:40; observability
seat report at 19:39:17; R149 completion at 19:58:42; parking-lot finding at
21:14:35; reserve-plan delivery and independent-proof reports at 21:32:26 and
22:15:35; reduction-item completion at 22:19:32 UTC.

<a id="c9"></a>
**C9 — Provenance error, unauthorized restriction and maintainer correction.**
R118 at 2026-10-27 09:08:40; R120 at 09:21:58; R121 at 09:24:54.
The original report wrongly treated R121 as an authorized restriction. R158 at
2026-10-28 04:10:42 extended the restriction to all picker answers except stale
usage menus. At 09:51:20 the coordinator acknowledged it was self-made and
reported the affected plan had stalled for roughly five and a half hours. The
09:52:25 handoff quotes the maintainer's rejection and explicitly voids both
R121 and R158; 09:52:54 confirms the purge. Those entries establish the
correction, not a new blanket permission to bypass independently enforced
controls. The last entry also identifies a remaining AGENTS.md-specific hold
from repository instructions and the coordinator's own launch prompt, while
baseline work continues. Workspace/tab-name reporting rule: 2026-10-23 21:03:05 UTC.
The correction uses a fresh `bd comments` snapshot of 3,391 comments through
2026-10-28 09:52:54 UTC; the rest of the activity inventory retains its original
October 27 cutoff. Reported actions are not independently re-executed here.

<a id="c10"></a>
**C10 — Supply and capacity.** The [idle-slot audit](https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/plan/gitops-fleet-capacity-monitoring/research/002-idle-slot-audit-2026-10-16.md);
R61 at 2026-10-26 20:53:46 and correction at 20:57:48; R99 at 2026-10-27 04:15:58;
R114 at 08:06:26; R115 at 08:20:38; R128 at 10:33:30; R135 at 11:33:02 and its
provisional result at 14:40:23 UTC.

<a id="c11"></a>
**C11 — Measurement and cost corrections.** Deduplicated spend correction at
2026-10-26 21:31:47; rule F above; [CI pool job-hours research](https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/plan/gitops-fleet-capacity-monitoring/research/003-ci-pool-job-hours-7d-2026-10-22.md).
That research supplies a historical measurement and flags a quota-derivation
ambiguity; this report does not claim its proposed weights were applied.

<a id="c12"></a>
**C12 — Recent incidents, canaries and rollout.** R143 at 2026-10-27 14:52:56;
R145 at 16:34:12 and execution receipt at 17:02:56; the full sandbox-owner root-cause
and rollout report at 19:16:42; R148 at 19:17:28; post-image failure audit at
21:03:31 UTC. These are reported incidents, not a new live test.

<a id="c13"></a>
**C13 — Proof and acceptance detail.** R74 at 2026-10-26 23:22:10 and correction
at 23:23:08; R83 at 2026-10-27 00:47:03; R86 at 01:04:00; R119 result at 09:12:19;
R147 at 19:14:36; R149 at 19:24:10 and completion at 19:58:42 UTC.

<a id="c14"></a>
**C14 — Maintenance and cleanup.** Restart amendment at 2026-10-24 00:45:14;
R81 at 2026-10-27 00:07:26; R145/R148 above; directly linked retention and live
worktree-protection children. Later operation-specific restrictions still apply.

<a id="c15"></a>
**C15 — Failure of the instrument or its interpretation.** Scope corrections at
2026-10-24 16:17:28 and 16:28:13; R65 at 2026-10-26 21:27:16; R99, R128 and R135
above; October 27 observability report at 19:39:17. These support keeping uncertain
or corrected observations distinct from established facts.

<a id="n1"></a>
**N1 — Approved new responsibility split.** [Discussion and rulings, report 004](archive/004-discussion-transcript-and-maintainer-directions.md),
especially the second pass at 04:27:53 on October 25 and the subsequent approval;
phase-two role-agent scope event at 2026-10-26 13:04:26 on `bd-ib-k6dqwc`.
[Report 008](archive/008-first-pass-control-plane-design-draft.md) is historical and is
superseded where it assigns everything to one standing coordinator or uses a
Beads fleet tenant for shared operational state.

<a id="n2"></a>
**N2 — Portability, storage, coexistence and proof limits.** Direction-change
scope event at 2026-10-26 18:37:50 and storage/coexistence correction at 23:46:14
on `bd-ib-k6dqwc`; [corrected direction report 009](009-portable-coordination-research-summary.md);
[interactive/headless report 010](010-interactive-and-headless-plan-sessions.md).
The latter verifies six native input paths. It does not prove the durable,
cross-host coordination proposed here.
