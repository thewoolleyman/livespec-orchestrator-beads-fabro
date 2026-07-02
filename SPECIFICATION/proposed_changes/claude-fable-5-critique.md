---
topic: claude-fable-5-critique
author: claude-fable-5
created_at: 2026-07-02T09:29:05Z
---

## Proposal: skill-surface-count-reconciliation

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/spec.md
- SPECIFICATION/README.md

### Summary

The skill-surface counts disagree across the tree: contracts.md's H2 "The eight-skill surface" introduces an enumeration of TEN skills (six heavyweight + one operator + three thin-transport), its later section "Skills — augmented versus new" still says "this plugin's seven-skill surface" and describes groom as sharing the decomposition "as the other four heavyweight ops", spec.md's Purpose section says "the 8-skill surface", and SPECIFICATION/README.md's Required-content list still enumerates an eight-skill surface with "four heavyweight authored skills" — omitting groom and plan entirely.

### Motivation

Four mutually inconsistent counts (seven, eight, ten, plus stale ordinals) for the same REQUIRED surface make the authoritative skill inventory ambiguous for every consumer that reads it — the console about to be built against this contract, doctor's cross-boundary invariants, and adopters reading the README.

### Proposed Changes

The H2 SHOULD be renamed to a count-free "The skill surface" (co-editing tests/heading-coverage.json in the same revise per the heading co-edit discipline). Exactly ONE authoritative enumeration MUST remain (six heavyweight + one operator + three thin-transport); spec.md's Purpose sentence, the "seven-skill surface" phrase, the "other four heavyweight ops" ordinal, and README.md's Required-content list MUST be updated to reference that enumeration rather than restating their own counts.

## Proposal: retired-priority-vocabulary-sweep

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/spec.md
- SPECIFICATION/scenarios.md

### Summary

The Work-item beads-issue mapping ratifies that `priority` is REMOVED as a logical field (`rank` is the sole ordering authority) and the `next` section retires the old priority heuristic — yet `capture-work-item` still says "The user supplies title, description, type, and priority", `next`'s field semantics still name `priority` as an example of an extra emitted field, spec.md's Terminology work-item definition still lists `priority` in the materialized field set, Scenario 1 still narrates "gap-tied beats freeform at equal priority", and Scenario 4 still files an item with `priority: 2`.

### Motivation

The retired field surviving in five normative places contradicts the ratified rank-only ordering — two order sources would be two conflicting truths, the exact failure mode the mapping section names — and leaves capture-front-end and console builders unclear whether a priority input still exists on the capture surface.

### Proposed Changes

`capture-work-item` MUST NOT name priority as a user-supplied field (initial rank placement is the store adapter's concern per the mapping). spec.md's Terminology field list MUST replace `priority` with `rank` plus the policy fields. Scenario 1's ranking line MUST be re-expressed in rank order, Scenario 4 MUST drop `priority: 2`, and `next`'s example extra field SHOULD name a live field (e.g. `origin` or `lane`).

## Proposal: lifecycle-vocabulary-consolidation-overdue

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

"Resolved realization choices" ratifies that there is NO separate needs-regroom label or status (a non-convergence bounce lands in `backlog`; defer returns to `pending-approval`), and the admission-valve section ratifies `admission_policy` as the first-class replacement for the human-gated/host-only text markers. The bridge sentence in "Dispatcher grooming behavior" kept Scenarios 9–11 valid only until the implement slice landed — that slice has merged — yet the "Gap-detectable behavior clauses" still normatively mandate tagging items `ready` / `needs-regroom` / `not-yet-actionable`, the four-maintainer-touchpoints prose and Scenarios 8, 9, 10, 11, and 14 still express intake, groom targeting, Dispatcher refusal, and the bounce in the retired vocabulary, and groom is still introduced as "provisional command name" although ratified elsewhere as shipped.

### Motivation

The lapsed bridge leaves the spec self-contradictory: one section declares the needs-regroom state nonexistent while other sections' authoritative clause lines still REQUIRE entering it, and the intake routing for a Definition-of-Ready failure is undefined in the 7-state vocabulary (backlog? pending-approval? blocked with needs-human?).

### Proposed Changes

The gap-detectable clauses and Scenarios 8–11/14 MUST be re-expressed in lifecycle vocabulary: intake routing MUST be defined explicitly (e.g. an epic-shaped capture MUST land in `backlog` for decomposition; a not-autonomously-verifiable item MUST land in a single named state — `blocked` with `blocked_reason: needs-human` OR `backlog` — pick one), the Dispatcher refusal MUST be restated as the admission valve holding effective-manual items, the non-convergence disposition MUST be restated as the `backlog` bounce, groom's target MUST be described by the lifecycle state that signals re-decomposition, and "provisional command name" MUST be dropped.

## Proposal: machine-path-exemption-scope-stale

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

The admission/acceptance section's "Consent boundary" declares the four lifecycle verbs admit/complete/accept/reject EXEMPT machine-path dispositions, citing "Machine-path exemption — the Dispatcher" — but that referenced section still defines the exemption as covering ONLY close-on-confirmed-merge, and constraints.md's Skill-orchestration bullet likewise still calls close-on-confirmed-merge "the SOLE exemption". The close-on-merge vocabulary itself predates the state machine: a green merge now transitions the item to `acceptance` (the `complete` verb), not straight to a closed/done terminal, so what `--no-close-on-merge` disables under the new lifecycle is undefined.

### Motivation

The exemption's defining clause and its two consumers are inconsistent about the exemption's scope, and the surviving close-on-merge terminology contradicts the ratified complete-into-acceptance transition — a consent-boundary ambiguity is exactly the kind that must not be left to implementation memory.

### Proposed Changes

"Machine-path exemption — the Dispatcher" MUST be widened to enumerate the machine-path dispositions it now covers (admit, complete, accept, reject, plus the pre-existing close-in-place disposition where applicable); constraints.md's "SOLE exemption" bullet MUST be updated to match; and `--no-close-on-merge` MUST be re-specified in lifecycle terms (e.g. it holds the item in `active` by skipping the `complete` transition) or renamed.

## Proposal: approval-evidence-ambiguity

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The admission valve states approval ≡ ready membership ("entering `ready` IS approving"; permission "was settled upstream" at pending-approval → ready), yet the same section requires the Dispatcher NOT to admit an effective-manual item "until it has been explicitly approved into `ready`", and Scenario 23's Given constructs "a ready item … not been explicitly approved into ready by a human" — a state the definition renders impossible. No approval-evidence field exists in the beads mapping, so a valve that re-checks cannot distinguish an approved manual ready item from an unapproved one.

### Motivation

The two claims are contradictory as written and leave the admission decision procedure ambiguous both for the enforcing Dispatcher and for the console, whose approve command's effect — transition pending-approval → ready, or annotate an already-ready item — is undefined.

### Proposed Changes

One model MUST be chosen and stated. EITHER (a) permission is checked only at the pending-approval → ready transition, in which case the valve MUST admit any ready item on capacity + assignee alone and Scenario 23's Given MUST be re-expressed as a `pending-approval` item the Dispatcher MUST NOT auto-approve; OR (b) the valve re-checks at admission, in which case the beads mapping MUST define the approval evidence the re-check reads (e.g. an `approved-by:` label or an audit entry). Scenario 23 MUST be updated to match the chosen model.

## Proposal: done-vs-closed-layering

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

The mapping confines the beads term to the adapter ("only `done` ↔ `closed` needs an adapter name-mapping — the one place a livespec term differs from its beads term") and the lane enum emits `done` — yet logical-layer clauses still use the beads term: list-work-items documents `--filter=closed`, the mapping's resolution rule reads "REQUIRED present when `status == closed`", the materialized-view section says "A `status: closed` issue is terminal", constraints.md's Forbidden-patterns rule says "Every `status: closed` issue", and the merge-evidence check walks `status == "closed"` without saying which layer it reads.

### Motivation

The mixed vocabulary is inconsistent with the adapter rule the same document ratifies, and leaves console and doctor consumers unclear whether materialized JSON carries status `done` or `closed` and which filter token selects terminal items.

### Proposed Changes

Each clause MUST name its layer. Logical-layer clauses (the list-work-items filter, the resolution requirement, terminality statements) SHOULD say `done` — with `--filter=done` as the documented token and `closed` at most a documented beads-layer alias — while substrate-layer checks (the merge-evidence walk over beads rows) MUST be labeled explicitly as reading the beads-native status.

## Proposal: rank-direction-terminology

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The `next` section defines rank order as ascending lexicographic with "the earliest `rank` is the most urgent", but the admission valve instructs admitting "the highest-`rank` admission-eligible `ready` item", and Scenario 22's Feature line repeats "highest-rank" while its example admits ranks a0 and a1 — the lexicographically earliest keys.

### Motivation

"Highest-rank" naturally reads as the greatest lexicographic key — the LEAST urgent item under the stated ascending order — so the admission instruction is ambiguous and, read literally, contradicts the ranking definition it composes.

### Proposed Changes

One term MUST be standardized — e.g. "top-ranked (the lexicographically earliest `rank`)" — defined once beside the `rank` field in the beads mapping, and "highest-rank" in the admission valve and in Scenario 22 MUST be replaced with it.

## Proposal: console-valve-command-surface-undefined

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The two human valves route through the console — Scenario 23 surfaces a manual item "for the maintainer to approve", Scenario 25 reaches done "only after a human confirms from the console", and the admission/acceptance section says "the console only commands (a human triggers `approve` for a manual item) and observes" — but the plugin's published operation surface offers no approve/accept/reject verb: list-work-items, next, and detect-impl-gaps are query-only by contract, orchestrate run only dispatches impl items or returns spec handoffs, and the Dispatcher is named the sole enforcer.

### Motivation

Before the console is built against this contract, the write path for the human valve decisions is undefined: per the two-seam discipline and core's console guidance the console must command through the owning plane's PUBLISHED surface, yet no such surface exists here, and a direct ledger write would silently bypass the store-write consent discipline this contract carefully scopes.

### Proposed Changes

The operator-facing valve surface MUST be specified before console buildout consumes the valve contract: either `orchestrate run` gains `approve:<id>` / `accept:<id>` / `reject:<id>` action ids, or a dedicated consented verb CLI is specified. The specification MUST state each verb's ledger transition, its consent classification (a human-triggered valve decision is not a machine-path disposition), and the audit evidence recorded.

## Proposal: dangling-schema-mapping-authority

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md

### Summary

spec.md's "What this spec is not" and contracts.md's "Beads connection model" and "Work-item beads-issue mapping" all delegate the field-map and connection-model derivation to `livespec/dev-tooling/implementation/research/beads-schema-mapping.md`, but that path no longer exists: livespec core consolidated its research into the single root `research/` tree (the beads topic now lives under `livespec/research/beads/`), and no `beads-schema-mapping.md` survives anywhere in core.

### Motivation

The named canonical authority is a dangling reference, so the delegation ("Not the canonical beads ⇄ livespec field-map authority") silently points at nothing and a reader cannot locate the derivation the contract claims resolved the mapping.

### Proposed Changes

Either the three citations MUST be repointed at the surviving core artifact under `livespec/research/beads/` (naming the actual file), or — preferably — this contracts.md's mapping section SHOULD be declared self-authoritative for the contract-level outcome, demoting the derivation citation to non-normative history so no external path is load-bearing.

## Proposal: implement-path-lifecycle-integration

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The implement section and Scenario 1 still describe the human-driven loop in pre-lifecycle terms: Scenario 1's freshly-filed issue carries "status: open" — the legacy enum the mapping declares superseded, and contradicting Scenario 28's 2-step landing in `backlog` — and the implement section walks Red → Green → close-in-place without locating the path on the 7-state machine: whether an implement-driven item transits ready/active, whether it may bypass `acceptance`, and from which states close-in-place is legal are all unstated.

### Motivation

The scenario asserts a status that is no longer a lifecycle state (contradicting the superseded-enum clause), and the implement path's relationship to the state machine is undefined — the acceptance-valve section governs only the Dispatcher path, leaving it unclear whether human-driven closures silently skip the no-release-with-zero-verification rule.

### Proposed Changes

Scenario 1 MUST be re-expressed (the filed item lands in `backlog` via the 2-step append; ranking is by `rank`), and the implement section MUST gain one clause locating the human-driven path on the state machine — e.g. implement MAY drive an item through the states directly under the operator's own consent with `acceptance` REQUIRED only on the Dispatcher path, OR both paths MUST route through `acceptance`; one model MUST be chosen and stated.
