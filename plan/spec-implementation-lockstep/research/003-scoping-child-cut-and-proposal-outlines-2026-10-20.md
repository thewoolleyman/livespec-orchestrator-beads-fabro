# Scoping: the child cut, the carrier map, and the proposal outlines (2026-10-20 UTC)

Written by the `spec-implementation-lockstep` session on its first resume. It records the
facts measured this session, the decisions taken under the standing rules, the children the
plan files, the carrier map the scoping event records, and the explicit deferrals. The
independent review of this note is appended as note 004.

Goal served: the plan's Definition of Done, in the maintainer's words of 2026-10-19 — "the
implementation and the specification are kept in sync in a virtuous feedback loop", "actual new
behavior should get new spec", "the spec should be generalized to be correct rather than always
expanded", and "what to do about the existing drift/gap noise and debt". Every decision below
names the measurement it rests on.

## 1. Facts measured this session

| Fact | Measurement |
|---|---|
| Resume state | `resume_directive` returned `ask: True`, reason "next_action kind human raises the picker", and one finding: `plan-progress-tracking: missing` (the only pointer ever written was `kind: human` with null tracking; the next executable write heals it). No scope event exists on the epic. No children exist. No record-rate warning fired. |
| The audit's open population (304 items, key `class`) | UNGOVERNED 88, PARTIAL 54, GOVERNED 79, NOT_BEHAVIOUR 81, UNCLEAR 2. By type: bug 161, task 111, feature 24, chore 8. 29 UNGOVERNED items sit in `ready`, `pending-approval`, `active` or `acceptance`; 22 of those 29 are typed `bug`, 3 `task`, 4 `feature`. 57 items cite a reference that does not govern them. |
| The audit's merged sample (60 of 210) | GOVERNED 38, PARTIAL 9, UNGOVERNED 4, NOT_BEHAVIOUR 9; 16 cite a non-governing reference. |
| Where the shared judgement can live | `livespec-runtime` is a library with its own spec, tenant `livespec-runtime` (101 items), factory `hp`. Its `constraints.md` funnels every subprocess through one seam and forbids threads, asyncio and subprocess pools. So the judgement module defines the prompt, the inputs and the verdict schema, and takes the model runner by INJECTION; it never calls a model itself. |
| The model runner already in flight | `bd-ib-7f66ar` (active, plan `hp-factory-failure-follow-ups`) implements the ratified "Judged before admission" (v132) and "Judged again before dispatch" (v141) paragraphs of `contracts.md` §"Effective acceptance criteria". It is the host-side runner the shared judgement plugs into. |
| The ledger-intent scan | Ratified in v026 as `## Scenario 38 — capture-spec-drift surfaces ledger intent missing from spec`; never built (`tests/heading-coverage.json` owner `bd-ib-heat`, `test: "TODO"`). It needs no proposal. |
| The drift binding | `contracts.md` §"Detection coverage records and staleness facts" ratifies the records, the coverage point and the merge-count fact, and ends with the agent-written v078 sentence "nothing in this section runs a detector headlessly, and no policy setting MAY do so". `.livespec.jsonc` sets `drift_capture_merge_threshold: 1`. Zero `capture-spec-drift` records exist on anchor `bd-ib-j5fzyo`. |
| Gap detection | `contracts.md` §"`detect-impl-gaps`" enumerates every MUST/SHOULD clause and derives a gap id per clause. `tests/heading-coverage.json` holds 251 entries; the heading-without-test signal already exists there mechanically. livespec core's doctor consumes the gap-id set for `gap-tracking-one-to-one` and `no-stale-gap-tied`, and 22 live items carry clause-derived gap ids. |
| The inverted classifier | `_dispatcher_policy_overrides._is_spec_change_tier` and `_plan_disposition._refuse_spec_change_tier` test `spec_commitment_hint`, which marks an impl follow-up to an ALREADY ratified change. `bd-ib-yykjko` (backlog, parentless) records both directions of the inversion. |
| Spec governance here | `revise_decision_mode: delegated`, `ratification_review: auto-spawn` with reviewer `gpt-6-astra`, `spec_pr_merge: auto-on-green`, `drift_acceptance_mode` at its human default. Core forbids every non-human mode from accepting a DRIFT-origin proposal; the proposals below are plan-origin, not drift-origin. |
| Standing rules that bind this session | `.ai/plan-session-lessons.md`: no pickers; take the recorded action under a recorded continuation authorization; read every scope event; start every independent track in the same turn; smallest canary first; route by the goal, not by prior ledger text. |

## 2. The lockstep rule applies to this plan first

Every child below that adds behaviour the ratified spec does not state is a FEATURE, so under
assertion 1 of this plan's own Definition of Done it cannot be dispatched until a linked proposed
change is ratified. The plan therefore files its implementation children now (filing stays a
parallel deposit, per the maintainer's 2026-05 design) and drives the proposals first; the
children rest at `pending-approval` until their proposal ratifies. The two children whose
behaviour IS already ratified (the ledger-intent scan, and the gap-signal consumer once P3 lands)
are the canaries.

## 3. The proposals (spec-ops)

Each proposal AMENDS existing clauses and adds at most one scenario heading, per the
"generalize, do not expand" ruling. Topics are canonical dash-case.

- **P1 (this repo) `spec-stated-judgement-and-spec-change-tier`.** Generalizes "Judged before
  admission" / "Judged again before dispatch": the one judgement the Dispatcher runs is the
  spec-stated judgement imported from `livespec-runtime`, whose verdict names the governing
  headings (`stated`), the heading whose generalization would state the behaviour (`partial`),
  or `unstated`, and classifies the item as feature, bug, chore or non-functional. Amends the
  Definition-of-Ready autonomy-tier bullet: the spec-change tier is DECIDED by that verdict at
  filing and at groom, only for features; a spec-change-tier item carries a linked proposed-change
  topic and rests at `pending-approval` until that topic is present under
  `history/vNNN/proposed_changes/`, which is a mechanical fact; bugs, chores and non-functional
  items are exempt; the judgement prefers naming a generalization target over a new clause.
  Amends the `dod_gate` and host-side citation checks to take their governing-heading verdict
  from the same judgement. Fails open exactly as v132/v141 do. One new scenario.
- **P2 (this repo) `per-merge-drift-run-and-coverage-baseline`.** Amends §"Detection coverage
  records and staleness facts": the drift-staleness fact becomes a RUN — after each default-branch
  merge the Dispatcher runs the drift pass scoped to that merge's diff through the shared
  judgement and files one proposed change per unstated behaviour (the machine path core and
  `spec.md` already permit), naming the generalization target; a completed coverage record names
  the merge SHA. Replaces the v078 sentence with the ratified boundary: filing may be unattended,
  acceptance of a drift-origin proposal stays human at `revise`. Amends `capture-spec-drift` so
  the ledger-intent scan uses the same judgement. One new scenario.
- **P3 (this repo) `gap-signal-from-heading-coverage`.** Amends §"`detect-impl-gaps`" and the
  `capture-impl-gaps` naming notes: the gap set is the set of H2 headings of the governed spec
  tree whose `tests/heading-coverage.json` entry is absent or `TODO`, with a gap id derived from
  the spec file and heading path; `--since-version` keeps its file-scoped meaning. Core's doctor
  consumers keep working because the id stays stable and gap-tied; the 22 clause-derived ids are
  migrated by the implementing child. One new scenario.
- **P4 (livespec-runtime) `spec-stated-judgement`.** Adds the module to §"Module-level public
  surface": `judge(...)`, `classify(...)`, `parse_verdict(...)`, the verdict dataclasses and the
  prompt constant, with the injected `run_model` callable as the only model seam. One scenario.
- **P5 (livespec-orchestrator-git-jsonl) `spec-stated-judgement-consumer`.** Filed with C7, not
  now: git-jsonl's `capture-spec-drift` and `capture-work-item` contracts name the runtime
  judgement. That repository is host-driven (no beads tenant, no factory).

## 4. The children

Nine children. "Factory" means factory-safe in the named tenant; "host" means host-routed with a
`### Host-captured` section and its `Reason:` line. Dependencies are `depends_on` edges; "after
Px" is the lockstep hold, recorded on the child as prose and enforced today by the
`pending-approval` rest (and by the C2 gate once it ships).

| Id | Title (short) | Repo / tenant | Route | After |
|---|---|---|---|---|
| C1 | The spec-stated judgement module | livespec-runtime | factory | P4 |
| C2 | Spec-change tier decided by the judgement at filing; a feature waits for its linked proposal's ratification before dispatch | this repo | factory | P1, C1, bd-ib-7f66ar |
| C3 | The ledger-intent scan (Scenario 38) over the judgement | this repo | factory | C1 |
| C4 | The per-merge drift run with a completed coverage point | this repo | factory | P2, C1 |
| C5 | Citation checks (filing advisory, pre-admission, pre-dispatch, `dod_gate`) delegate to the judgement | this repo | factory | P1, C1, bd-ib-7f66ar |
| C6 | `detect-impl-gaps` reports headings without an exercising test | this repo | factory | P3 |
| C7 | git-jsonl runs the same judgement | git-jsonl (filed here) | host | C1, P5 |
| R1 | Reconcile the audit's open UNGOVERNED and PARTIAL items in subsystem batches | this repo | host | C1 preferred, audit data suffices to begin |
| R2 | Reconcile merged unspecified behaviour and record the baseline coverage point | this repo | host | C4 |

C2 absorbs `bd-ib-yykjko`: its merge corrects both inverted predicates, and that item is closed
against C2's pull request. C5 is what releases the coordinator's R258(3) hold on `bd-ib-3now6p`.
`bd-ib-7rnipp` (Group 1 of note 001, no spec exists) is the first real customer of the C2 gate,
and stays its own item.

### Definition of Done drafts

Each child's section follows the four authoring rules of `plan.md` §"Routing a child's Definition
of Done". References lines name an existing H2 today; once a proposal ratifies, the child's line is
re-pointed to the new scenario BEFORE dispatch (the evaluator reads the dispatch-time snapshot).

**C1 — livespec-runtime**

- `livespec_runtime.spec_stated.judge(spec_tree=..., statement=..., run_model=...)` returns a verdict whose `stated_by` names each governing H2 heading verbatim, whose `kind` is `stated`, `partial` or `unstated`, and whose `generalization_target` names the existing heading to amend or `none`.
- `livespec_runtime.spec_stated.classify(title=..., description=..., item_type=..., run_model=...)` returns `feature`, `bug`, `chore` or `non_functional`.
- The module invokes a model only through the caller-supplied `run_model` callable and performs no subprocess and no network call of its own.
- `parse_verdict` round-trips the verdict JSON a model returns, and a malformed response yields a typed failure naming the field.
- The prompt text and the verdict schema are importable constants that both orchestrators read from this one module.

References: `## Module-level public surface` (runtime spec; re-pointed to P4's scenario).

**C2 — this repo**

- At filing and at groom, an implement-kind item typed `feature` is run through the spec-stated judgement, and an `unstated` or `partial` verdict is recorded on the item with the proposed-change topic it must link.
- An item typed `bug` or `chore`, or one the judgement classifies as non-functional, is routed through intake exactly as it is today.
- A spec-change-tier item whose linked topic is absent from `history/vNNN/proposed_changes/` rests at `pending-approval`, and the pre-dispatch wall refuses it with exit code 5 naming the unratified topic.
- Once the linked topic is present under a ratified version, the next intake or drain pass routes the item to `ready` without a human valve.
- `_is_spec_change_tier` and `_refuse_spec_change_tier` read the recorded tier and no longer read `spec_commitment_hint`.
- When the judgement cannot run, the item is routed as it is today and the did-not-run cause is recorded on the item.

References: `## Scenario 10 — Dispatcher never auto-approves a manual-admission spec-change item` (re-pointed to P1's scenario).

**C3 — this repo**

- `orchestrator.py ledger-intent-scan --json` lists every live work-item whose intent the spec-stated judgement classifies `unstated` or `partial`, each with the verdict and the generalization target.
- Items the judgement classifies `stated`, and items classified bug, chore or non-functional, produce no finding.
- `--since-version vN` restricts the scan to items captured at or after the cut of version vN.
- `capture-spec-drift` presents each finding through the per-finding consent flow and, on consent, hands it to propose-change naming the generalization target.
- Every run appends an attempt record to the detection-coverage anchor and mutates no work-item.

References: `## Scenario 38 — capture-spec-drift surfaces ledger intent missing from spec`.

**C4 — this repo**

- After a default-branch merge, the post-merge janitor runs the drift pass scoped to that merge's diff through the spec-stated judgement and files one proposed change per unstated behaviour, naming the generalization target, with a drift origin.
- A merge whose diff adds no unstated behaviour writes a completed drift coverage record naming the merge SHA and files no proposal.
- An interrupted or failed pass writes an attempt record and no completed record.
- After a successful pass the drift-staleness fact reports zero merges since the recorded point.
- The pass never accepts a proposal; acceptance stays at `revise`.

References: `## The skill surface` (re-pointed to P2's scenario).

**C5 — this repo**

- The filing-time reference advisory, the pre-admission judgement, the pre-dispatch judgement and the `dod_gate` node each take the governing-heading verdict for an item's assertions from the spec-stated judgement and name the heading it returns as the remedy.
- An item whose References line names a heading that does not govern its assertions is held before admission with the judgement's named heading as the remedy.
- The `dod_gate` node continues to steer the proof stage to the referenced scenario's steps.
- A verdict is reused while the item's effective criteria and referenced headings are byte-unchanged.

References: `## Scenario 141 — The referenced scenario governs the proof, and the record names it` (re-pointed to P1's scenario).

**C6 — this repo**

- `detect-impl-gaps --json` emits one gap per H2 heading of the governed spec tree whose `tests/heading-coverage.json` entry is absent or carries `test: "TODO"`, with a gap id derived from the spec file and heading path.
- A heading whose coverage entry names an existing test produces no gap.
- `capture-impl-gaps` files a gap-tied item naming the uncovered heading and the coverage entry to fill.
- The 22 live gap-tied items carry heading-derived gap ids after the migration the change ships, and livespec core's `gap-tracking-one-to-one` and `no-stale-gap-tied` invariants pass on this repository.

References: `## The skill surface` (re-pointed to P3's scenario).

**C7 — git-jsonl, filed here**

Host-captured. Reason: `livespec-orchestrator-git-jsonl` has no ledger tenant and no factory of
its own, so the change lands by hand in that repository and is proved on the host.

- git-jsonl's ledger-intent scan and its `capture-work-item` filing obtain the stated/unstated verdict and the feature/bug classification from `livespec_runtime.spec_stated`.
- A feature whose behaviour the judgement classifies `unstated` is filed in git-jsonl with the spec-change tier and its linked proposal topic.

References: `## Scope boundary`.

**R1 — this repo**

Host-captured. Reason: ledger triage of 142 live items on the shared tenant, with proposals filed
through the attended spec-side operation.

- Every item the 2026-10-19 audit classified UNGOVERNED or PARTIAL carries, on the ledger, one of: a reclassification comment naming it bug, chore or non-functional; a linked proposed-change topic; or a closure reason naming it obsolete.
- Every feature in that set whose behaviour the spec does not state is linked to a proposal that amends an existing clause where one can be generalized.
- Each batch ends with a comment on the plan epic recording the counts by disposition and the spec's H2 heading count and MUST/SHOULD clause count before and after the batch's ratifications.

References: `## Scenario 38 — capture-spec-drift surfaces ledger intent missing from spec`.

**R2 — this repo**

Host-captured. Reason: a backfill over 210 merges on the live default branch through the C4 pass,
with removals landed as pull requests.

- Every default-branch merge between 2026-10-04 and the baseline merge is run through the drift pass, and each finding ends as a ratified clause amending an existing one where possible, a merged removal pull request, or an anchor comment recording accepted implementation detail.
- A completed drift coverage record names the baseline merge SHA, and the next drift-staleness fact counts only merges after it.
- The reconciliation comment on the plan epic records the spec's H2 heading count and MUST/SHOULD clause count before and after.

References: `## The skill surface` (re-pointed to P2's scenario).

## 5. The carrier map

Plan assertions in Definition of Done order:

| Ordinal | Assertion (short) | Carriers |
|---|---|---|
| 1 | A feature without a ratified clause cannot be dispatched until its linked proposal ratifies | C2 |
| 2 | Bugs, chores and non-functional items dispatch without a new clause | C2 |
| 3 | A generalizable clause is amended rather than added to | C2, R1 |
| 4 | Per-merge drift pass files proposals and records a coverage point | C4 |
| 5 | The ledger-intent scan lists open unstated items | C3 |
| 6 | Both orchestrators run the same judgement from livespec-runtime | C1, C7 |
| 7 | Every audited open unspecified item ends resolved | R1 |
| 8 | Every merged unspecified change ends resolved | R2 |
| 9 | A completed coverage point is recorded and later runs report only merges after it | R2, C4 |
| 10 | Gap detection reports headings without an exercising test | C6 |
| 11 | Reconciliation batches do not grow the spec beyond genuinely new behaviour | R1, R2, plan-level proof |

## 6. Explicit deferrals

- **livespec core is not changed.** No checkpoint mandate and no judgement CLI in core (both
  withdrawn in note 002); core's "Orchestrators MAY file drift" already permits P2's machine path.
- **The repeat-failure breaker** is ratified in v117 and owned by `bd-ib-s5idxj` / `bd-ib-5vtqaq`.
- **The host-side rider-coherence check and the title-only matcher threshold** (check 4 and check 6
  of note 001) are owned by plan `hp-factory-failure-follow-ups` (`bd-ib-7f66ar`, `bd-ib-nj3xsy`);
  this plan consumes that runner and changes only what the verdict is taken from.
- **`bd-ib-3now6p`** stays held under the coordinator's R258(3) until C5 ships or its citation is
  corrected; it is not a child.
- **`bd-ib-7rnipp`** is the C2 gate's first real customer, not a child; its spec route is its own.
- **A cross-vendor drift acceptance panel** (`drift_acceptance_mode: consensus`) is not built;
  acceptance stays human at `revise`.
- **A proposal-queue cap** is carried as a design constraint inside C4 (one proposal per unstated
  behaviour, scoped to the merge diff) and reconsidered after R2 measures the volume.
- **Retiring clause enumeration entirely** is reconsidered after R1; C6 keeps core's doctor
  consumers working through stable heading-derived ids.

## 7. Sequencing and the canary

Wave 1, now and in parallel: P3 (smallest spec-op), P1, P2 here; P4 in livespec-runtime; file
all nine children. Wave 2: P3 ratifies, dispatch C6 as the smallest canary; P4 ratifies, dispatch
C1 in the runtime tenant. Wave 3: C2 and C5 after P1, C1 and `bd-ib-7f66ar`; C4 after P2 and C1;
C3 after C1; C7 by hand. Wave 4: R1 batches (begun from the audit data, finished with the
judgement), R2 after C4. Wave 5: plan proof, independent completeness review, archive.

The typed next action after scoping is `spec-op` `propose-change:gap-signal-from-heading-coverage`,
tracked as the proposal file present on master, with P1, P2 and P4 driven beside it.

## 8. Decisions taken without asking

- The judgement takes its model runner by injection; this follows the runtime's own constraints.
- Children reference an existing H2 today and are re-pointed to the ratified scenario before
  dispatch; filing stays a parallel deposit.
- R3 (baseline point and net-size measure) is folded into R2 and the batch comments of R1.
- `bd-ib-yykjko` is absorbed by C2 rather than adopted as a child, because its description is a
  code-level finding and C2 states the behaviour.
