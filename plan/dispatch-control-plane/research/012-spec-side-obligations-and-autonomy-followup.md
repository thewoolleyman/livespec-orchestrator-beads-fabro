# 012 — Spec-side progress: immediate repair and the missing control-plane responsibility

[Back to index](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/README.md)

30 October 2026. This extends the [responsibility mapping](011-coordinator-responsibility-mapping.md) and the [portable coordination direction](009-portable-coordination-research-summary.md). It records verified source findings and the maintainer-authorized sequence. The service behavior below is proposed design, not deployed enforcement or permission to ratify the production backlog.

## Decision and startup order

The maintainer first requested discussion only. After reviewing the proposal, he authorized the following, verbatim:

> OK, so the stopgap low hanging fruit is the Spec-side autonomy follow-up, correct? You can go ahead and update your plan with all these findings and research (capture research doc as appropriate) , but only  after you kick off that follow-up plan and get it running, and hand off to the coordinator?  Is my understanding correct?

The immediate follow-up repairs the existing delegated-revise path and its descriptions. Automatic discovery and scheduled initiation are the larger integration change; they are not silently added to the stopgap.

The required order was followed before this note was written:

- An independent **spec-autonomy-followup** session was started in the livespec repository, in its own Herdr tab beside dispatch-control-plane.
- It created **Spec-side autonomy follow-up** (`livespec-7ap2fb`) through the plan primitive, with five explicitly session-derived completion assertions and opening research. The ledger record was independently read back by this session.
- It verified the prose contradictions, surveyed overlaps, filed **Core revise-prose conformance** (`livespec-hitmrz`), repaired its mechanical reference finding and submitted it through the factory path. Its reported dispatch gate is `20261030T183121Z-3308918`; submission is not a claim that the repair has merged or passed acceptance.
- It sent the coordinator **gitops-fleet-capacity-monitoring** a first-class `SendMessage` handoff. The launch receipt records successful inbox delivery at about 18:34 UTC, message `2e418103-6225-4d96-a81a-85bfcc2c3db5`. The coordinator acknowledged taking the plan into cross-plan monitoring and recorded it on `livespec-dev-tooling-dfixhe`; that ledger delta, timestamped 18:33:52 UTC, was independently read back before publication.
- The follow-up remained active, publishing its plan artifacts and routing the remaining repair work. Its initial publication was still in progress when this note began.

These are dated startup observations, not a second plan-status store. Current follow-up status belongs in its livespec ledger and its owner's session. The coordinator owns ongoing cross-plan routing. This plan does not absorb the follow-up's implementation or claim it complete.

## What the investigation established

The coordinator's October 30 incident brief described R219 as another instance of delegated work being converted into a human-only obligation. The ledger record at **2026-10-29 15:37:56 UTC** confirms the relevant R219: it declares all spec-change ratification to be the maintainer's and adds proposals to his queue. R-numbers are reused; an October 19 R219 concerns model routing and is unrelated.

The coordinator subsequently marked R219 and its blanket human-only variants **void** in the October 30 handoff recorded at 18:28:03 UTC. That entry was independently read back. This follow-up repairs the surfaces that helped produce the mistaken rule; it does not need to rescind an already-void rule.

Both livespec-dev-tooling and livespec-orchestrator-beads-fabro have committed settings for `revise_decision_mode: delegated`, `ratification_review: auto-spawn`, `ratification_reviewer_model: [sonnet]`, and `spec_pr_merge: auto-on-green`. The inspected files had no working-tree diff. These settings authorize the applicable operation's delegated path; they neither make every proposal eligible nor specify a background scheduling mechanism.

Core's specification resolves policy per proposal, applying its mandatory exception rules and per-proposal overrides. Delegated non-drift acceptance requires an independent reviewer and independent delegated decider agreeing on the exact final bytes. Drift, design-record conflicts or absence, reviewer blockers, disagreement and unavailable participants retain their governing treatment. Evidence must be current when applied. Do not paraphrase this as every old review requiring permanent human intervention: the ratified review rule permits a fresh conforming review of reassembled bytes to supersede stale review without escalation.

The source review also corrected the incident brief in three useful ways:

1. **The two quoted Python passages are comments, not the emitted refusal.** `_spec_change_tier_wall.py` and `_dispatcher_loop_candidates.py` describe waiting for a human to ratify. `_spec_change_tier_hold.py` actually emits a refusal naming the topic and hold reason without asserting human-only authority. Fix the misleading explanation while retaining the valid hold until ratification and re-evaluation.
2. **The contradiction is inside core prose too.** Revise's per-proposal steps unconditionally say to prompt for confirmation before resolving decision ownership, and describe modifying content with the user. The later manual-spawn paragraph also needs to agree with the specification's delegated automatic-review rule. Fixing only the Claude/Codex/pi discovery descriptions would leave contradictory instructions.
3. **The prior-art sweep missed an explicit design.** The console retirement/redesign record's D3 and capability table propose revise as a complete workflow variant, with pending-proposal work triggered by staleness facts. It names **Pluggable factory workflow configs** (`bd-ib-yqpdrt`) as the mechanism. That is prior design to reconcile, not evidence that the integration exists. Do not repeat the claim that nothing ever designed automatic initiation.

The archived spec-side-autonomy brainstorm assumed a foreman would run revise. Its historical ledger epic is closed, but closure alone establishes neither a currently working trigger nor a live end-to-end proof. The old work delivered useful policy mechanics; the missing unattended outcome must be assessed separately. This investigation did not independently audit every historical closure comment or reproduce the brief's complete five-ledger absence claim.

Two existing backlog items are relevant: **Stale-proposal doctor invariant** (`livespec-yaig`) detects proposals that age without disposition; **Spec-side autonomy rollout shortfall** (`livespec-vb12`) records an earlier failure to arm policy. Detection does not initiate work, and the latter's historical consensus wording must not override current core doctrine. Avoid duplicate items.

## The stopgap and its owner

The independent follow-up in livespec owns a focused repair with these recorded outcomes:

| Follow-up responsibility | Completion evidence |
| --- | --- |
| Correct core revise prose. | Released prose prompts only when effective policy or a core exception requires it, and preserves delegated automatic independent review. |
| Correct Claude, Codex and pi driver discovery/binding wording. | Released bindings describe both manual and delegated ownership without fixing the reviewer model in prose. |
| Correct orchestrator explanations. | The hold is described as awaiting ratification rather than necessarily a human; held work still cannot bypass ratification. |
| Demonstrate the existing delegated path. | An explicitly initiated, bounded operation through released installed surfaces ratifies an isolated non-drift proposal with the two independent signals bound to the same final bytes. |
| Demonstrate the limits. | Manual ownership and a core exception produce the required human-confirmation outcome rather than unauthorized ratification. |

This initial bounded demonstration is not proof of an unattended queue consumer, all three adapters' full integration, or worker-loss behavior on Compose and Kubernetes. Those remain control-plane acceptance work. The follow-up's session-derived assertions remain labeled as such rather than being represented as verbatim maintainer wording.

No general scheduler, new permanent foreman, production backlog sweep, authority change is part of this stopgap authorization. R219 has already been voided in the coordinator's own record. Ordinary conformance fixes and the governed fixture demonstration should proceed under their existing authorized paths.

## Responsibilities missing from the control-plane inventory

The earlier 58-row mapping covered many generic duties but did not assign the spec-side lifecycle explicitly. These additions make that obligation concrete; they do not replace the incumbent's other responsibilities.

| Capability | Current mechanism or gap | Proposed accountable owner and behavior |
| --- | --- | --- |
| S01. Discover proposals without a live plan session. | A session or attention query notices pending files; the retired foreman was assumed to start work. | Deterministic work supply maintains an inventory across registered repositories and spec trees; plan progress owns unassigned obligations. Recover missed events through periodic reconciliation. |
| S02. Resolve a spec-change-tier hold. | Implementation admission correctly refuses held work, but no complete continuation follows the proposal automatically. | Plan progress follows the linked proposal and required next operation. The owning plan supplies a missing proposal; revise cannot repair a missing-topic hold by itself. |
| S03. Determine who may decide. | Agents can read contradictory prose, peer claims or a compacted rule instead of the effective policy. | Core owns policy resolution. The orchestrator consumes a structured result and its reason, including proposal overrides and mandatory exceptions. |
| S04. Start an eligible assessment. | No demonstrated service owns the full initiation obligation; a ranked spec-next result is not proof of readiness. | The work-supply service claims and launches a bounded attempt; plan progress is accountable for stalls. Eligibility to start review is separate from permission to ratify after review. |
| S05. Review and decide. | Core already defines independent exact-byte signals, but invocation and surrounding wording are incomplete or inconsistent. | Core revise and its independent participants retain semantic ownership. Prefer a complete workflow using the existing factory mechanism, reconciling the console redesign and workflow-variants plan rather than inventing a second executor. |
| S06. Recover interrupted or competing attempts. | The absence of an owner is handled through ad hoc session messages. | Shared coordination records retain ownership, attempt identity, current policy and observed effects. Start with serialized conflicting spec publication per repository; reconcile publication before retrying. |
| S07. Continue after disposition. | A person or session tells the factory owner that a topic ratified. | Reconciliation observes ratification/publication or rejection and re-evaluates the linked implementation item through its existing eligibility rules. Rejection is not permission to dispatch. |
| S08. Detect starvation and observation failure. | Queue age and initiation delay are not complete service obligations. The current spec-next adapter can omit its row when core is unavailable. | Supervision distinguishes an empty queue from unavailable observation, tracks due work and raises a specific recoverable failure. It must not depend on an LLM polling every tick. |

Core remains authoritative for policy and proposal dispositions. Git remains authoritative for proposal/revision bytes; Beads for each plan and work item; Fabro for runs. **Dedicated non-Beads coordination Dolt** owns shared assignments, attempts, delivery and progress obligations, referring to those authorities rather than copying them into an epic comment stream.

## Authority, summaries and truthful wording

Grant validation is necessary but insufficient when the worker's ordinary instructions contradict the grant. Correct core prose, all driver discovery/binding surfaces, explanatory comments and any displayed guidance that misstates decision ownership. Do not add a second policy interpreter to each harness; use core's effective resolver and fix or expose its public result as needed through the governing contract.

A summary or launch prompt may refer to an active rule, but must retain its authoritative source, scope and revision. Compaction must not promote a coordinator's inference or a peer preference into a maintainer instruction. Before executing or refusing, reload the current authority. An unsupported blanket restriction is a conflict to resolve, not a new operating rule. Actual independently enforced controls still apply to their particular operations; unrelated work continues.

The new spec-work path must preserve explicit observation failure. Today `_needs_attention_spec_next_run.py` returns no spec item when core cannot resolve, exits unsuccessfully, or produces unusable output. That may keep the current inbox available, but a supervisor cannot interpret it as a successful empty-queue observation. Preserve inbox availability while exposing the missing observation and its age.

## Component and plan ownership

| Owner | Work it should carry |
| --- | --- |
| Livespec core and the focused follow-up | Existing-policy conformance, revise prose, effective policy semantics, independent evidence validation and the bounded operation demonstration. |
| Claude/Codex/pi drivers | Accurate discovery and binding behavior for the core-resolved path. The follow-up routes work through the applicable owners. |
| Orchestrator, through dispatch-control-plane | Obligation inventory, scheduling/admission, shared ownership, supervision, observable exceptions, hold continuation and metrics. |
| Existing workflow-variants track | Reuse or extend the execution mechanism for a complete revise workflow; verify what actually shipped before adding another runner. Cross-plan sequencing belongs to the coordinator. |
| Console | Render progress and genuine decisions through public operations; neither an open console nor a terminal picker is a prerequisite for progress. |
| Existing stale-proposal doctor item | Reuse its detection responsibility; do not mistake it for the work-starting service. |
| Fleet coordinator | Monitor the independent follow-up and resolve cross-plan priorities and owner handovers. It does not replace the required independent ratification participants. |

## Proof required before automatic execution transfers

These are proposed phase-two acceptance scenarios and the basis for the later concrete Definition of Done and child cut. They are not test results. The original six gradeable plan assertions remain unchanged pending that design review; this research/scope update does not silently claim a new approved implementation cut.

| Scenario | Observable result |
| --- | --- |
| A non-drift proposal appears in an enabled repository with no running plan session. | The service discovers it, owns an attempt, starts the complete revise operation, obtains conforming independent signals, observes publication, and re-evaluates the linked hold without a human prompt. |
| A proposal is eligible to begin review but has no review evidence yet. | The assessment starts; missing evidence does not create a circular prerequisite for starting its producer. Ratification still waits for valid evidence. |
| A proposal overrides ownership to manual or hits a core exception. | The correct scoped human decision is surfaced with its source, without changing policy or blocking independent proposals unnecessarily. |
| A peer or compacted summary asserts that every revise is human-only. | Effective core policy still governs; the unsupported restriction cannot suppress authorized work. |
| Review and decision disagree or resulting bytes change. | No stale or mismatched acceptance is applied. Reassembly/review or escalation follows current core semantics. |
| Two workers see the same proposal, or a worker dies during publication. | Ownership and reconciliation prevent duplicate or conflicting effects; a replacement observes the actual target before retrying. |
| Core or a repository is unreachable. | Observation is explicitly unavailable, not reported as no pending work. A bounded recovery obligation remains visible. |
| A proposal is rejected or its linked topic is missing. | Rejection does not release implementation admission; the owning plan receives the required repair or disposition obligation. |
| An attempt has stopped progressing while its process is alive. | The due obligation is detected and recovered within the chosen budget; heartbeat alone does not count as progress. |
| The same supported flow is exercised through Claude, Codex and pi on Compose and Kubernetes, including replacement on another host. | Authorities, outcomes and recovery agree across adapters and deployment modes. The native input tests in report 010 are not this proof. |

Measure oldest pending proposal, time to first attempt, time to disposition or justified escalation, unsupported human referrals, unanswered/unapplied decisions, duplicate attempts, and observation availability. Attribute blocked time by cause. Keep idle reconciliation deterministic and account for review capacity and spend rather than creating another unbounded inference queue. Numerical service budgets and final packaging still require concrete design.

## Sequence

1. **Start the focused repair first.** Done as a startup action above; its implementation and proof remain owned by spec-autonomy-followup. Do not hold that repair behind the larger architecture.
2. **Include spec obligations in the read-only inventory.** Correct source attribution and expose unknown observations. This can proceed while the repair runs.
3. **Prove the existing narrow durable-answer foundation.** Keep the accepted first delivery: shared questions/answers, actual delegated attribution, stale-evidence protection, one focused progress role and recoverable effects on Compose and Kubernetes. The existing coordinator remains the first client.
4. **Use one bounded delegated revise workflow as the first spec-side integration pilot.** Start with an isolated governed repository and one proposal. Adopt the existing execution substrate only after confirming its capabilities and the relevant contract. Do not make the entire scheduling program a prerequisite for the generic answer flow.
5. **Expand after proof.** Broader scheduling, typed capacity, fairness and additional roles remain in scope. Transfer each responsibility explicitly; retire neither the coordinator nor its untransferred delivery obligations merely because services are deployed.

This sequence does not authorize a production queue sweep or claim that configured delegation already provides a background trigger. The immediate repair, operation semantics, automatic initiation and operational proof are distinct deliverables.

## Source trail

The original coordinator brief was read in full from its October 30 scratchpad relay. Durable, independently checked sources for the findings are:

- `livespec-dev-tooling` ledger epic `livespec-dev-tooling-dfixhe`, comment `created_at=2026-10-29T15:37:56Z`, the relevant R219; October 30 entries at 18:28:03 UTC (R219 voided) and 18:33:52 UTC (follow-up monitoring accepted). The brief's queue totals are incident context, not a current readiness census performed here.
- Both repositories' committed `.livespec.jsonc`, `spec_governance` blocks; livespec `SPECIFICATION/spec.md`, “Intent preservation and design-record authority” and “Spec-governance policy settings.”
- Livespec `.claude-plugin/prose/revise.md`, per-proposal decision/confirmation/review steps; Claude, Codex and pi revise `SKILL.md` discovery descriptions and bindings. The follow-up identified Codex's source binding at `livespec-driver-codex/livespec/skills/revise/SKILL.md`.
- This repository's `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_spec_change_tier_wall.py`, `_dispatcher_loop_candidates.py`, `_spec_change_tier_hold.py`, `_needs_attention_spec_next_run.py` and `_needs_attention_spec_next_adapt.py`.
- [Archived spec-side-autonomy design](https://github.com/thewoolleyman/livespec/blob/master/plan/archive/spec-side-autonomy/research/brainstorm.md), especially the foreman execution assumption and two independent AI signals; its ledger epic `livespec-jvdvx4` and existing items `livespec-yaig` and `livespec-vb12` were read directly.
- [Console redesign decisions](https://github.com/thewoolleyman/livespec-console-beads-fabro/blob/master/plan/retire-overseer-and-redesign-control-plane-around-console/research/redesign-brainstorm-and-decisions.md), D3, amended D5 and section 5. These supply the previously missed workflow/staleness design; they do not establish an implemented trigger.
- [Unattended plan operation](../../archive/unattended-plan-operation/research/opening-research-2026-08-20.md), which concerns an already-running authorized session.
- Follow-up ledger epic `livespec-7ap2fb`, owner session `ce19c72a-238e-4973-bbde-0a4f85197eb8`, child `livespec-hitmrz`, and the SendMessage receipt above. The temporary startup receipt was inspected before this plan was changed; future state must be read from the ledger rather than that temporary file.
