# scenarios.md — livespec-impl-beads

End-to-end behavioral journeys illustrating the plugin's intended use
across the workflow loops defined in `livespec/SPECIFICATION/`. They are
now expressed in Gherkin `Given` / `When` / `Then` form (matching the
house style `livespec` core uses in its own `SPECIFICATION/scenarios.md`),
but they remain reader-facing journeys an agent or contributor follows —
not the pytest test cases (those live under `tests/`).

## Scenario 1 — Gap-tied fix cycle

```gherkin
Feature: Gap-tied fix cycle
  As an agent maintaining an impl against a freshly-revised spec
  I want the gap-tied work to be detected, ranked, implemented, and closed
  So that a new spec MUST clause becomes honored impl with a verified audit trail

Scenario: A new MUST clause is detected, filed, implemented, and closed in place
  Given a consumer project has a fresh `livespec` revision (vNNN+1)
  And that revision introduced a new MUST clause not yet honored in the impl
  When the user invokes `/livespec-impl-beads:capture-impl-gaps`
  Then the skill loads the rule set via the Spec Reader
  And walks each rule against the impl
  And surfaces uncaptured gaps one at a time
  When the user consents to file a gap
  Then the skill creates a beads issue via `bd create` carrying the `origin:gap-tied` label
  And the `gap-id:<stable-id>` label
  And `status: open`
  And the user-confirmed title and description
  When the user invokes `/livespec-impl-beads:next`
  Then the ranker reads the materialized work-items back from `bd`
  And surfaces the newly-filed gap-tied item as the recommendation (gap-tied beats freeform at equal priority)
  When the user invokes `/livespec-impl-beads:implement` for that work-item
  Then the skill walks Red → Green → closure
  And at closure re-runs `capture-impl-gaps` in dry-run mode
  And confirms the `gap_id` is no longer detected
  And closes the issue IN PLACE with `bd close --reason …`
  And `bd update` sets the `resolution:completed` label
  And the `AuditRecord` (`verification_timestamp`, `commits`, `files_changed`, `merge_sha`, optional `pr_number`) is written into the issue's `metadata` column
```

## Scenario 2 — Memo → spec-bound disposition

```gherkin
Feature: Memo → spec-bound disposition
  As a user who noticed something intent-bearing during impl work
  I want to deposit it as a memo and later route it to the spec side
  So that the observation becomes a governed propose-change

Scenario: A memo is deposited and later dispositioned spec-bound
  Given the user notices something that does not fit the current work-item but is intent-bearing
  When the user invokes `/livespec-impl-beads:capture-memo`
  And types a one-paragraph observation
  Then the skill creates a beads issue carrying the `kind:memo` label
  And the `state:untriaged` label
  And a fresh `id`
  When the user later invokes `/livespec-impl-beads:process-memos`
  And picks `spec-bound` for this memo
  Then the skill hands off to `/livespec:propose-change` with the memo content as the proposed-change source
  And a new file lands under the consumer's `<spec-root>/proposed_changes/`
  And the memo issue is updated IN PLACE from `state:untriaged` to `state:dispositioned` plus a `disposition:spec-bound` label
  And the resulting `propose_change_topic` is recorded in the issue's `metadata` column for cross-reference
  When the next `/livespec:doctor` pass runs
  Then it sees one fewer untriaged memo
  And any memo-hygiene `warn` driven by the memo backlog clears
```

## Scenario 3 — Memo → persistent-knowledge graduation

```gherkin
Feature: Memo → persistent-knowledge graduation
  As a user re-discovering the same workflow gotcha across sessions
  I want a memo about it graduated into the Persistent Agent Knowledge store
  So that future sessions load it on demand

Scenario: A recurring-gotcha memo is graduated to a knowledge file
  Given a memo describing a recurring workflow gotcha exists
  When the user invokes `/livespec-impl-beads:process-memos`
  And picks `persistent-knowledge` for this memo
  And supplies a topic name (e.g. `mise-exec-for-git-hooks`)
  Then the skill writes the memo content to `.ai/mise-exec-for-git-hooks.md` (creating the file if absent)
  And ensures `CLAUDE.md` and/or `AGENTS.md` references that file via a bullet (adding the reference if missing)
  And updates the memo issue IN PLACE to `state:dispositioned` plus a `disposition:persistent-knowledge` label
  And records `knowledge_file: ".ai/mise-exec-for-git-hooks.md"` in the issue's `metadata` column
  And future sessions load that knowledge file on demand via the harness's `CLAUDE.md` / `AGENTS.md` reference traversal
```

## Scenario 4 — Freeform bug fix

```gherkin
Feature: Freeform bug fix
  As a user who spots a bug unrelated to any open gap
  I want to file it as a freeform work-item and fix it
  So that it closes without any gap re-detection

Scenario: A freeform bug is filed, implemented, and closed
  Given the user spots a bug unrelated to any open gap
  When the user invokes `/livespec-impl-beads:capture-work-item`
  And supplies title, description, `type: bug`, and `priority: 2`
  Then the skill creates a beads issue carrying the `origin:freeform` label and no `gap-id:` label
  When the user invokes `/livespec-impl-beads:implement` for that item
  Then Red → Green proceeds normally
  And at closure the skill takes the freeform path
  And closes the issue IN PLACE with `resolution:completed` and the user-supplied `--reason` (`bd close --reason`, `bd update` for the resolution label)
  And no `gap_id` re-detection runs
```

## Scenario 5 — Doctor cross-boundary read

```gherkin
Feature: Doctor cross-boundary read
  As a user running doctor in a consumer project
  I want doctor's cross-boundary phase to read this plugin's query surfaces
  So that the memo-hygiene and work-item structural invariants are evaluated deterministically

Scenario: Doctor reads spec directly and invokes the thin-transport query skills
  Given the user invokes `/livespec:doctor` in a consumer project
  When doctor's static phase runs
  Then it reads `<spec-root>/` directly
  When doctor's cross-boundary phase runs
  Then it invokes `/livespec-impl-beads:list-memos --filter=untriaged --json` for the memo-hygiene invariant
  And invokes `/livespec-impl-beads:list-work-items --json` for the work-item structural invariants
  And each invocation reads the tenant DB through `bd`
  And completes deterministically with the contract-mandated JSON schema
  And a missing or malformed plugin surface fires a `fail` finding (no silent skips)
  And in hermetic / CI contexts the in-memory fake backend stands in for a live tenant DB and satisfies the same schema
```

## Scenario 6 — Cross-repo Layer 3 loop driver (livespec-resident)

```gherkin
Feature: Cross-repo Layer 3 loop driver (livespec-resident)
  # Cross-reference: cross-side composition of impl-side `next` with
  # spec-side `/livespec:next` is a Layer 3 (project-local orchestration)
  # concern per `livespec/SPECIFICATION/spec.md` §"Three-layer orchestration
  # architecture" → "Cross-side composition belongs at Layer 3". This
  # scenario describes the Layer 3 driver's behavior; this plugin's `next`
  # skill itself ranks impl-side state only and MUST NOT bake a cross-side
  # weighting in. This plugin is responsible only for the impl-side `next`
  # output schema and behavior; the composition rules and empty-queue
  # handoff policy are entirely in scope for `livespec` and the
  # project-local driver, not for this spec.
  As the livespec-resident Layer 3 loop driver
  I want to compose the spec-side and impl-side `next` outputs each iteration
  So that cross-repo work is sequenced without the impl-side `next` baking in a cross-side weighting

Scenario: The driver composes both sides' next at the top of each iteration
  Given the livespec-resident cross-repo orchestration driver
  When the driver invokes `/livespec:next --json`
  Then it obtains a spec-side recommendation
  When the driver invokes `/livespec-impl-beads:next --json`
  Then it obtains an impl-side recommendation
  When the driver composes the two outputs
  Then it produces a per-iteration action plan per the orchestration-layer rules defined in `livespec/SPECIFICATION/`
  And memo, gap-detection, and drift-detection invocations (`/livespec-impl-beads:process-memos`, `/livespec-impl-beads:capture-impl-gaps`, `/livespec-impl-beads:capture-spec-drift`) are likewise Layer 3 driver-side concerns invoked outside `next`'s ranking — `next` ranks materialized work-items only (the canonical actionable-memo probe is `list-memos --filter=untriaged`)

Scenario: Empty-queue handoff offers a hygiene fallback
  Given both `/livespec:next` and `/livespec-impl-beads:next` emit empty `candidates: []` arrays (the no-work signal on both sides)
  When the Layer 3 driver reaches the empty-queue handoff
  Then it SHOULD offer the user a hygiene fallback — at minimum a `/livespec:doctor` pass and a `/livespec:critique` pass
  And it MAY also offer `/livespec:prune-history` if `next.prune_history_threshold` would otherwise have suppressed it
  And the hygiene fallback is a Layer 3 productivity heuristic that is NEVER baked into the Layer 2 `next` emission itself
```

## Scenario 7 — Regroom an oversized work-item

```gherkin
Feature: Regroom an oversized work-item
  # Cross-reference: the grooming PATTERN this scenario realizes is
  # repo-agnostic non-functional guidance in `livespec`'s
  # `non-functional-requirements.md`; the realization shown here (the
  # groom front-end, the `needs-regroom` state, the per-slice fields, the
  # calibration journal fields) is this orchestrator's own, codified in
  # §"Grooming and slice-size calibration" of `contracts.md`.
  As a maintainer with an oversized or non-converging work-item
  I want to regroom it into ready slices via the groom front-end
  So that the Dispatcher can drain the slices by dependency layer

Scenario: An oversized item is regroomed into ready slices and drained
  Given an item arrives at `needs-regroom` — either an intake Definition-of-Ready failure (an epic with more than one coherent "done") or a Dispatcher non-convergence bounce (a dispatched slice that would not converge through the janitor gate, marked and surfaced rather than infinite-retried)
  When the maintainer runs the groom front-end (`groom <id>`)
  Then it reads the item, the relevant spec / scenarios, and the ledger
  And DRAFTS candidate slices read-only — each pre-filled with acceptance / autonomy tier / dependency links / repo target / scope, arranged into dependency layers
  When the maintainer edits the cut / acceptance / deps / tiers and approves (or sends it back to re-draft; the maintainer OWNS the cut and the acceptance, the front-end only drafts)
  Then on approval the front-end files the approved slices via `capture-work-item` with dependency edges linked
  And routes any spec-change slice to `/livespec:propose-change` instead of the factory
  And the Dispatcher then drains the resulting `ready` slices by dependency layer, re-running `just check` + `/livespec:doctor` + the named scenarios after each layer converges before the next layer dispatches
```

## Scenario 8 — Intake Definition-of-Ready triage

```gherkin
Feature: Intake Definition-of-Ready triage
  As a capture front-end running the intake Definition-of-Ready checklist
  I want to tag each captured item ready, needs-regroom, or not-yet-actionable
  So that only autonomously-dispatchable work reaches the factory

Scenario: A single-acceptance item is tagged ready
  Given a freshly-described single-acceptance item with one coherent "done", autonomously verifiable, autonomy-tiered, dependency-linked, repo-targeted, and above the size floor
  When it is filed via a capture front-end running the intake Definition-of-Ready checklist
  Then it is tagged `ready`
  And it is eligible for autonomous dispatch

Scenario: An epic is tagged needs-regroom
  Given a described epic with more than one coherent "done"
  When it is filed via a capture front-end
  Then it is tagged `needs-regroom`
  And it is surfaced for grooming rather than filed as `ready`

Scenario: A non-autonomously-verifiable or blocked item is tagged not-yet-actionable
  Given an item whose acceptance is not autonomously verifiable (it needs a human judgement call) OR that has open blockers
  When it is filed via a capture front-end
  Then it is tagged `not-yet-actionable`
  And it is not auto-dispatched
```

## Scenario 9 — needs-regroom state and transitions

```gherkin
Feature: needs-regroom state and transitions
  As the grooming realization
  I want every path into and out of needs-regroom to be observable
  So that an oversized item is always surfaced, never silently dropped

Scenario: An intake Definition-of-Ready failure enters needs-regroom
  Given an intake Definition-of-Ready failure
  When capture runs
  Then the item is at `needs-regroom`
  And it is surfaced

Scenario: A non-converging dispatched slice enters needs-regroom
  Given a dispatched slice that will not converge through the janitor gate
  When the Dispatcher bounces it
  Then the item is at `needs-regroom`
  And it is surfaced

Scenario: A groomed-and-approved item transitions out of needs-regroom
  Given a `needs-regroom` item the maintainer has groomed and approved
  When the groom front-end files the approved slices
  Then the slices are `ready`
  And the original item is regroomed-out (not silently dropped)
```

## Scenario 10 — Dispatcher refuses a human-gated item

```gherkin
Feature: Dispatcher refuses a human-gated item
  As the Dispatcher draining ready slices
  I want to refuse to auto-dispatch a human-gated spec-change item
  So that spec change always reaches the maintainer instead of the factory

Scenario: A human-gated slice is surfaced rather than dispatched
  Given a `ready` slice tagged human-gated (spec-change, autonomy tier human-gated)
  When the Dispatcher reaches it in the dependency-layer drain
  Then it is surfaced to the maintainer
  And it is not auto-dispatched into a Fabro sandbox
```

## Scenario 11 — Dispatcher bounces a non-converging slice to needs-regroom

```gherkin
Feature: Dispatcher bounces a non-converging slice to needs-regroom
  As the Dispatcher observing a slice that will not converge
  I want to mark it needs-regroom and surface it
  So that an empirically-too-big slice is escalated, never infinite-retried

Scenario: A non-converging slice is marked needs-regroom and surfaced
  Given a dispatched slice that repeatedly fails the janitor gate (`just check` + `/livespec:doctor`) and will not converge within the fix-loop cap
  When the Dispatcher observes non-convergence
  Then the item is marked `needs-regroom`
  And it is surfaced to the maintainer
  And it is never infinite-retried
```

## Scenario 12 — Dispatcher emits calibration telemetry

```gherkin
Feature: Dispatcher emits calibration telemetry
  As the Dispatcher recording a terminal Fabro run
  I want to write an outcome signal plus mechanical size proxies onto the existing journal
  So that calibration can correlate size against convergence without any new always-on service

Scenario: A terminal run writes outcome and size proxies onto the existing journal
  Given a dispatched slice whose Fabro run reaches a terminal outcome
  When the Dispatcher records the run
  Then an outcome signal (converged?; fix-loop count; outcome class; wall-clock and token/cost; bounced-to-regroom?) is written onto the EXISTING Dispatcher journal record
  And mechanical size proxies (acceptance count; merged-PR diff size; dependency fan-out; spec surface touched; dispatch context size; archetype; repo) are written onto the same record
  And no new always-on service is started
```

## Scenario 13 — Calibration analysis pass proposes advisory thresholds

```gherkin
Feature: Calibration analysis pass proposes advisory thresholds
  As the periodic calibration analysis pass
  I want to correlate outcomes against size proxies and propose ceiling thresholds
  So that the intake size-gate gains advisory numbers a maintainer may later adopt

Scenario: The analysis pass proposes thresholds that stay advisory until adopted
  Given an accumulated journal of run outcomes and size proxies
  When the periodic calibration analysis pass runs
  Then it correlates outcomes against size proxies and proposes ceiling thresholds
  And the proposed thresholds remain advisory (the intake size-gate flags oversized items only advisorily) until a maintainer adopts them
  And they are never auto-enforced
```

## Scenario 14 — Fabro non-convergence routes back to the Dispatcher

```gherkin
Feature: Fabro non-convergence routes back to the Dispatcher
  As the single Fabro workflow-DOT tweak
  I want a fix-loop cap plus a non-converged exit edge within the existing DOT vocabulary
  So that a non-converging slice routes back to the Dispatcher with no Fabro platform change

Scenario: A non-converged Fabro run routes control back to the Dispatcher
  Given a Fabro workflow whose DOT carries a fix-loop cap and a "non-converged" exit edge within the existing DOT vocabulary
  When a dispatched slice hits the fix-loop cap (`max_node_visits` governor) without converging
  Then the "non-converged" exit edge routes control back to the Dispatcher (which marks the item `needs-regroom`)
  And no Fabro platform or setup change was required
```

## Scenario 15 — Dispatcher composes next's ranking

```gherkin
Feature: Dispatcher composes next's ranking
  As the Dispatcher choosing which ready slice to dispatch
  I want to compose `next`'s ranking rather than re-rank inline
  So that `next` remains the single ranking authority

Scenario: The Dispatcher selects via next's ranking
  # Already-satisfied: this behavior is already implemented per in-flight
  # work-item `livespec-impl-beads-i3jiny`, so it is documented and
  # scenario-covered but is NOT a fresh gap.
  Given the Dispatcher must choose which `ready` slice to dispatch
  When it selects the next item
  Then it composes `next`'s ranking (the single ranking authority) rather than re-ranking inline
```

## Scenario 16 — Closed-item-integrity check rejects "closed but unproven"

```gherkin
Feature: Closed-item-integrity check rejects "closed but unproven"
  As the maintainer trusting that a closed gap-tied item is proven
  I want the closed_item_integrity check wired into just check
  So that a closed gap-tied item whose acceptance scenario is unbound, or which lacks the resolution:completed label, surfaces mechanically rather than passing CI green

Scenario: A closed-but-unproven gap-tied item surfaces a finding
  Given a gap-tied work-item is closed and its `gap-id` resolves through the `clauses[]` map to an acceptance scenario whose `tests/heading-coverage.json` entry is still bound to the `TODO` sentinel (or the item lacks the `resolution:completed` label)
  When the `closed_item_integrity` check runs as part of `just check`
  Then it emits a `closed-item-integrity` finding naming that item
  And the finding is a warning in `warn` mode (the default, exit 0) and an error in `fail` mode (`LIVESPEC_CLOSED_ITEM_INTEGRITY=fail`, exit non-zero)

Scenario: A fully-proven closed gap-tied item emits no finding
  Given a gap-tied work-item is closed, carries the `resolution:completed` label, and its `gap-id` resolves through the `clauses[]` map to an acceptance scenario whose `tests/heading-coverage.json` entry binds to a real integration-tier test node id (not `TODO`)
  When the `closed_item_integrity` check runs
  Then it emits NO finding for that item
```
