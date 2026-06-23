# scenarios.md — livespec-orchestrator-beads-fabro

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
  When the user invokes `/livespec-orchestrator-beads-fabro:capture-impl-gaps`
  Then the skill loads the rule set via the Spec Reader
  And walks each rule against the impl
  And surfaces uncaptured gaps one at a time
  When the user consents to file a gap
  Then the skill creates a beads issue via `bd create` carrying the `origin:gap-tied` label
  And the `gap-id:<stable-id>` label
  And `status: open`
  And the user-confirmed title and description
  When the user invokes `/livespec-orchestrator-beads-fabro:next`
  Then the ranker reads the materialized work-items back from `bd`
  And surfaces the newly-filed gap-tied item as the recommendation (gap-tied beats freeform at equal priority)
  When the user invokes `/livespec-orchestrator-beads-fabro:implement` for that work-item
  Then the skill walks Red → Green → closure
  And at closure re-runs `capture-impl-gaps` in dry-run mode
  And confirms the `gap_id` is no longer detected
  And closes the issue IN PLACE with `bd close --reason …`
  And `bd update` sets the `resolution:completed` label
  And the `AuditRecord` (`verification_timestamp`, `commits`, `files_changed`, `merge_sha`, optional `pr_number`) is written into the issue's `metadata` column
```

## Scenario 4 — Freeform bug fix

```gherkin
Feature: Freeform bug fix
  As a user who spots a bug unrelated to any open gap
  I want to file it as a freeform work-item and fix it
  So that it closes without any gap re-detection

Scenario: A freeform bug is filed, implemented, and closed
  Given the user spots a bug unrelated to any open gap
  When the user invokes `/livespec-orchestrator-beads-fabro:capture-work-item`
  And supplies title, description, `type: bug`, and `priority: 2`
  Then the skill creates a beads issue carrying the `origin:freeform` label and no `gap-id:` label
  When the user invokes `/livespec-orchestrator-beads-fabro:implement` for that item
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
  So that the work-item structural invariants are evaluated deterministically

Scenario: Doctor reads spec directly and invokes the thin-transport query skills
  Given the user invokes `/livespec:doctor` in a consumer project
  When doctor's static phase runs
  Then it reads `<spec-root>/` directly
  When doctor's cross-boundary phase runs
  Then it invokes `/livespec-orchestrator-beads-fabro:list-work-items --json` for the work-item structural invariants
  And the invocation reads the tenant DB through `bd`
  And completes deterministically with the contract-mandated JSON schema
  And a missing or malformed plugin surface fires a `fail` finding (no silent skips)
  And in hermetic / CI contexts the in-memory fake backend stands in for a live tenant DB and satisfies the same schema
```

## Scenario 6 — Cross-repo dispatch via the Dispatcher

```gherkin
Feature: Cross-repo dispatch via the Dispatcher
  # Cross-reference: the Dispatcher (`dispatcher.py` `dispatch` / `loop`)
  # is the dispatch surface for routine cross-repo work — it polls the
  # beads Ledger for ready work-items and drives each through Fabro
  # autonomously. This plugin's `next` skill provides the impl-side ranking
  # the Dispatcher consumes; it MUST NOT bake a cross-repo sequencing or
  # cross-side weighting in — cross-repo sequencing and empty-queue
  # handling are the Dispatcher's concern, not this skill's.
  As the Dispatcher draining ready impl-side slices
  I want to consume this plugin's `next` surface for impl-side ranking
  So that cross-repo work is dispatched in priority order without impl-side `next` encoding cross-repo sequencing

Scenario: The Dispatcher consumes next for impl-side ranking
  Given the Dispatcher is dispatching impl-side slices
  When it invokes `/livespec-orchestrator-beads-fabro:next --json`
  Then it obtains an impl-side ranked candidate list
  And gap-detection and drift-detection invocations (`/livespec-orchestrator-beads-fabro:capture-impl-gaps`, `/livespec-orchestrator-beads-fabro:capture-spec-drift`) are Dispatcher-side concerns invoked outside `next`'s ranking — `next` ranks materialized work-items only

Scenario: Empty-queue handoff offers a hygiene fallback
  Given `/livespec-orchestrator-beads-fabro:next` emits an empty `candidates: []` array (the no-work signal)
  When the Dispatcher or operator reaches the empty-queue handoff
  Then it SHOULD offer a hygiene fallback — at minimum a `/livespec:doctor` pass and a `/livespec:critique` pass
  And it MAY also offer `/livespec:prune-history` if `next.prune_history_threshold` would otherwise have suppressed it
  And the hygiene fallback is a Dispatcher / operator concern that is NEVER baked into the `next` emission itself
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

## Scenario 17 — orchestrate operator-surface defaults

```gherkin
Feature: orchestrate operator surface defaults to the ergonomic path
  As an operator working inside a governed repo
  I want bare `orchestrate`, a cwd-default repo, and Markdown output
  So that the everyday cross-side selection loop needs no boilerplate
  while scripts and the Dispatcher keep a fully specified invocation

Scenario: A bare orchestrate invocation walks the operator through the choices
  Given a governed repo whose spec-side and impl-side `next` surfaces are reachable
  When the operator invokes `orchestrate` with no subcommand
  Then the surface presents an interactive walkthrough of the available `actions[]`
  And it does NOT error on a missing subcommand
  And selecting an action composes the same read-only plan -> select -> run flow without introducing new ranking logic

Scenario: An omitted --repo resolves to the current working directory's repo
  Given the operator's current working directory is inside a governed repo
  When the operator invokes `orchestrate plan` without `--repo`
  Then the surface resolves the target repo to that current-directory repo
  And an explicit `--repo <path>` still overrides the default when supplied

Scenario: Console output is Markdown by default and JSON only with --json
  Given any `orchestrate plan` or `orchestrate run` invocation
  When the operator omits `--json`
  Then the surface renders human-readable Markdown
  And passing `--json` renders the same payload as machine-readable JSON
```

## Scenario 18 — Dispatcher projects a non-rotatable subscription credential into a worker sandbox

```gherkin
Feature: Dispatcher projects a non-rotatable subscription credential
  As the Dispatcher running a worker on a provider subscription
  I want to project a credential the worker cannot rotate
  So that no worker can invalidate the shared credential for the host or peers

Scenario: A dispatched worker receives a non-rotatable credential snapshot
  Given the orchestrator host holds a valid provider-subscription credential whose usable lifetime exceeds the worker run budget
  When the Dispatcher dispatches a ready work-item to a worker sandbox
  Then the Dispatcher projects a non-rotatable credential snapshot into the sandbox such that the worker cannot rotate the shared refresh credential
  And the worker authenticates its coding-agent runtime from that projected snapshot
  And no refresh performed or attempted inside the sandbox invalidates the host's or any peer worker's credential
```

## Scenario 19 — Dispatcher refuses dispatch when the credential freshness gate fails

```gherkin
Feature: Dispatcher freshness-gates subscription-credentialed dispatch
  As the Dispatcher protecting unattended runs
  I want to refuse dispatch when the credential cannot outlive the run
  So that a worker never starts on a credential that may expire mid-run

Scenario: A too-short-lived credential refuses dispatch with a renewal message
  Given the host provider-subscription credential's usable lifetime does NOT exceed the worker run budget
  When the Dispatcher considers dispatching a ready work-item
  Then the Dispatcher refuses the dispatch
  And the Dispatcher surfaces that the host credential requires renewal rather than projecting a credential that may expire mid-run
```
