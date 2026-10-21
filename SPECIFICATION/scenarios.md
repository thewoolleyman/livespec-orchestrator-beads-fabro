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
  And the H2 heading that clause sits under has no exercising test in the heading-coverage map
  When the user invokes `/livespec-orchestrator-beads-fabro:capture-impl-gaps`
  Then the skill loads the spec tree's H2 headings via the Spec Reader and the heading-coverage map
  And enumerates every H2 heading whose heading-coverage entry names no exercising test (no read of the impl)
  And surfaces every such heading not yet tracked by a work-item, one at a time
  When the user consents to file a gap
  Then the skill creates a beads issue via the 2-step append carrying the `origin:gap-tied` label
  And the `gap-id:<stable-id>` label
  And the intake Definition-of-Ready routes it (an item that passes the Definition-of-Ready checklist lands `pending-approval`, approved into `ready` when its effective admission_policy is `auto`; an effective-`manual` item rests at `pending-approval` awaiting the human's explicit `approve`)
  And the user-confirmed title and description
  When the user invokes `/livespec-orchestrator-beads-fabro:next`
  Then the ranker reads the materialized work-items back from `bd`
  And surfaces the newly-filed gap-tied item as the recommendation (the top-ranked `ready` item — earliest `rank`)
  When the user invokes `/livespec-orchestrator-beads-fabro:implement` for that work-item
  Then the skill walks Red → Green → closure
  And at closure evaluates the recorded check-path (never `gap_id`)
  And confirms the check passes and its negative control fails
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
  And supplies title, description, and `type: bug`
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
  So that cross-repo work is dispatched in rank order without impl-side `next` encoding cross-repo sequencing

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
  # groom front-end, the `backlog` bounce, the per-slice fields, the
  # calibration journal fields) is this orchestrator's own, codified in
  # §"Grooming and slice-size calibration" of `contracts.md`.
  As a maintainer with an oversized or non-converging work-item
  I want to regroom it into dependency-layered slices via the groom front-end
  So that the Dispatcher can drain the slices by dependency layer

Scenario: An oversized item is regroomed into dependency-layered slices and drained
  Given an item sits in `backlog` needing re-decomposition — either an intake-routed epic (more than one coherent "done") or a Dispatcher non-convergence bounce (a dispatched slice that would not converge through the janitor gate, bounced and surfaced rather than infinite-retried)
  When the maintainer runs the groom front-end (`groom <id>`)
  Then it reads the item, the relevant spec / scenarios, and the ledger
  And DRAFTS candidate slices read-only — each pre-filled with acceptance / autonomy tier / dependency links / repo target / scope, arranged into dependency layers
  When the maintainer edits the cut / acceptance / deps / tiers and approves (or sends it back to re-draft; the maintainer OWNS the cut and the acceptance, the front-end only drafts)
  Then on approval the front-end files the approved slices via `capture-work-item` with dependency edges linked
  And routes any spec-change slice to `/livespec:propose-change` instead of the factory
  And the Dispatcher then drains the resulting `ready` (effective-`auto` or human-approved) slices by dependency layer, re-running `just check` + `/livespec:doctor` + the named scenarios after each layer converges before the next layer dispatches
```

## Scenario 8 — Intake Definition-of-Ready triage

```gherkin
Feature: Intake Definition-of-Ready triage
  As a capture front-end running the intake Definition-of-Ready checklist
  I want to route each captured item into its lifecycle state
  So that only autonomously-dispatchable work reaches the factory

Scenario: A single-acceptance item is routed toward ready
  Given a freshly-described single-acceptance item with one coherent "done", autonomously verifiable, autonomy-tiered, dependency-linked, repo-targeted, and above the size floor
  When it is filed via a capture front-end running the intake Definition-of-Ready checklist
  Then it lands in `pending-approval` and is approved into `ready` when its effective admission_policy is `auto`
  And when its effective admission_policy is `manual` it rests at `pending-approval` awaiting the human's explicit `approve`
  And once `ready` it is eligible for autonomous dispatch

Scenario: An epic lands in backlog
  Given a described epic with more than one coherent "done"
  When it is filed via a capture front-end
  Then it lands in `backlog` for decomposition
  And it is surfaced for grooming rather than filed as `ready`

Scenario: A non-autonomously-verifiable or blocked item does not reach ready
  Given an item whose acceptance is not autonomously verifiable (it needs a human judgement call) OR that has open blockers
  When it is filed via a capture front-end
  Then a not-autonomously-verifiable item lands in `blocked` with `blocked_reason: needs-human`
  And an item with open blockers carries its dependency edges (deriving the `blocked:dependency` lane)
  And it is not auto-dispatched
```

## Scenario 9 — backlog bounce state and transitions

```gherkin
Feature: backlog bounce state and transitions
  As the grooming realization
  I want every path into and out of the backlog re-decomposition state to be observable
  So that an oversized item is always surfaced, never silently dropped

Scenario: An intake Definition-of-Ready epic failure enters backlog
  Given an intake Definition-of-Ready epic failure (more than one coherent "done")
  When capture runs
  Then the item is at `backlog`
  And it is surfaced

Scenario: A non-converging dispatched slice enters backlog
  Given a dispatched slice that will not converge through the janitor gate
  When the Dispatcher bounces it
  Then the item is at `backlog`
  And it is surfaced

Scenario: A groomed-and-approved item transitions out of backlog
  Given a `backlog` item the maintainer has groomed and approved
  When the groom front-end files the approved slices
  Then the slices transit `pending-approval` (approved on into `ready` when a slice's effective admission_policy is `auto`; an effective-`manual` slice rests at `pending-approval` awaiting the human's explicit `approve`)
  And the original item is regroomed-out (not silently dropped)
```

## Scenario 10 — Dispatcher never auto-approves a manual-admission spec-change item

```gherkin
Feature: Manual-admission spec-change items rest at pending-approval
  As the Dispatcher draining ready slices
  I want to leave any spec-change item whose effective admission_policy is manual resting at pending-approval
  So that spec change always reaches the maintainer instead of the factory

Scenario: A manual-admission spec-change slice is surfaced rather than auto-approved
  Given a `pending-approval` slice whose effective admission_policy is `manual` (the spec-change / risky autonomy tier)
  When the Dispatcher reaches it in the dependency-layer drain
  Then it does not auto-approve the slice into `ready`
  And it is surfaced to the maintainer for their explicit `approve`
  And it is not auto-dispatched into a Fabro sandbox
```

## Scenario 11 — Dispatcher bounces a non-converging slice to backlog

```gherkin
Feature: Dispatcher bounces a non-converging slice to backlog
  As the Dispatcher observing a slice that will not converge
  I want to bounce it to backlog and surface it
  So that an empirically-too-big slice is escalated, never infinite-retried

Scenario: A non-converging slice is bounced to backlog and surfaced
  Given a dispatched slice that repeatedly fails the janitor gate (`just check` + `/livespec:doctor`) and will not converge within the fix-loop cap
  When the Dispatcher observes non-convergence
  Then the item is bounced to `backlog`
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
  Then the "non-converged" exit edge routes control back to the Dispatcher (which bounces the item to `backlog`)
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

Scenario: A closed item carrying a heading-derived gap-id resolves through its heading's own coverage entry
  Given a gap-tied work-item is closed with the `resolution:completed` label and a heading-derived `gap-id` naming an H2 heading of `contracts.md`
  And that heading's `tests/heading-coverage.json` entry is still bound to the `TODO` sentinel
  When the `closed_item_integrity` check runs
  Then it emits a `closed-item-integrity` finding naming that item without consulting the `clauses[]` map
  When that heading's entry is bound to a real integration-tier test node id
  And the check runs again
  Then it emits NO finding for that item
```

## Scenario 17 — drive operator-surface defaults

```gherkin
Feature: drive operator surface defaults to the ergonomic path
  As an operator working inside a governed repo
  I want a cwd-default repo and Markdown output
  So that the everyday operator execution step needs no boilerplate
  while scripts and the Dispatcher keep a fully specified invocation

Scenario: An omitted --repo resolves to the current working directory's repo
  Given the operator's current working directory is inside a governed repo
  When the operator invokes `drive --action <action-id>` without `--repo`
  Then the surface resolves the target repo to that current-directory repo
  And an explicit `--repo <path>` still overrides the default when supplied

Scenario: Console output is Markdown by default and JSON only with --json
  Given any `drive` invocation
  When the operator omits `--json`
  Then the surface renders human-readable Markdown
  And passing `--json` renders the same payload as machine-readable JSON
```

## Scenario 18 — Dispatcher projects a non-rotatable subscription credential into a worker sandbox

```gherkin
Feature: Dispatcher projects non-rotatable subscription credentials
  As the Dispatcher running a worker on one or more provider subscriptions
  I want to project credentials the worker cannot rotate
  So that no worker can invalidate the shared credential for the host or peers

Scenario: A dispatched worker receives non-rotatable snapshots for every projected provider
  Given the orchestrator host holds a valid Claude-subscription credential and a valid OpenAI/ChatGPT-subscription credential whose usable lifetimes exceed the worker run budget
  When the Dispatcher dispatches a ready work-item to a worker sandbox
  Then the Dispatcher projects each provider's credential as a non-rotatable snapshot into the same sandbox such that the worker cannot rotate any shared refresh credential
  And the worker authenticates its coding-agent runtimes from those projected snapshots
  And no refresh performed or attempted inside the sandbox invalidates the host's or any peer worker's credential for any provider
```

## Scenario 19 — Dispatcher refuses dispatch when the credential freshness gate fails

```gherkin
Feature: Dispatcher freshness-gates subscription-credentialed dispatch
  As the Dispatcher protecting unattended runs
  I want to refuse dispatch when a covered credential cannot outlive the run
  So that a worker never starts on a credential that may expire mid-run

Scenario: A too-short-lived credential refuses dispatch with a renewal message
  Given a host provider-subscription credential covered by the freshness gate has a usable lifetime that does NOT exceed the worker run budget
  When the Dispatcher considers dispatching a ready work-item
  Then the Dispatcher refuses the dispatch
  And the Dispatcher surfaces that the host credential requires renewal rather than projecting a credential that may expire mid-run
```

## Scenario 20 — Review gate routes a green build through code review before PR

```gherkin
Feature: A senior-engineer review gate reviews a green build before the PR stage
  As the Dispatcher running an unattended implementation loop
  I want a code-review gate between a green janitor and the PR stage
  So that correctness and design defects the mechanical check suite cannot
    catch are surfaced, and a still-blocking change is held for a human unless
    the operator has set merge_on_review_cap

  Background:
    Given the janitor gate (the mechanical check suite) is green

  Scenario: An approved review proceeds to the PR stage
    When the review gate reviews the change and raises no blocking findings
    Then the run proceeds to the PR stage

  Scenario: A blocking finding is adjudicated, and accepted findings are fixed and re-validated
    Given the review gate raised at least one blocking finding
    And the review fix-round budget (dispatcher.review_fix_cap) is not yet exhausted
    When the disposition stage adjudicates each blocking finding — accepting it, or rejecting it with a one-line rationale
    And at least one blocking finding is accepted
    And the fix stage implements each accepted finding and no rejected one
    Then the change is re-validated by the janitor and reviewed again
    And the disposition record is carried to the re-review, which honors each rejection unless it re-confirms a genuine correctness or security defect

  Scenario: A round whose blocking findings are all rejected re-reviews without a fix pass
    Given the review gate raised at least one blocking finding
    And the review fix-round budget (dispatcher.review_fix_cap) is not yet exhausted
    When the disposition stage rejects every blocking finding, each with a rationale
    Then the run routes directly back to review
    And the janitor does not re-run (no code changed)
    And the rejection record is carried to the re-review, which honors it unless it re-confirms a genuine correctness or security defect

  Scenario: A capped-out review ships when merge_on_review_cap is set
    Given the review gate has reached its review fix-round cap (dispatcher.review_fix_cap)
    And the review gate still raises a blocking finding
    And the verdict contains a blocking finding about the tree
    And the item's effective merge_on_review_cap is true
    Then the run ships to the PR stage anyway
    And the still-blocking finding does not gate the change

  Scenario: A capped-out review blocks under the default merge_on_review_cap
    Given the review gate has reached its review fix-round cap (dispatcher.review_fix_cap)
    And the review gate still raises a blocking finding
    And the verdict contains a blocking finding about the tree
    And the item's effective merge_on_review_cap is false (the default)
    Then the change does not ship
    And the item transitions to blocked with blocked_reason needs-human
    And it is surfaced to a human

  Scenario: A terminal dispatch emits review-gate telemetry from Fabro events
    Given a Fabro run has reached any terminal Dispatcher outcome: green, blocked, or failed
    And `fabro events <run-id> --json` contains `edge.selected` events from the review node
    When the Dispatcher observes the terminal outcome
    Then it queries the structured Fabro event stream for that run
    And it emits a `livespec-dispatcher` span carrying `review.verdict`, `review.fix_rounds`, `review.hit_cap`, and `pr.shipped_on_cap`
    And a review-to-PR fallthrough at the review cap is queryable as `pr.shipped_on_cap=true`
```

## Scenario 21 — Codex plugin discovery and full-access posture

```gherkin
Feature: Codex plugin discovery and full-access posture
  As an operator using the Codex TUI and Codex-backed factory review
  I want the orchestrator's Codex plugin to be discoverable and full-access only
    under the manifest-gated contract
  So that official fleet/adopter repos get honest executable review without
    silently changing unrelated external repos

Scenario: The /skills picker renders drive under this plugin
  Given the livespec-orchestrator-beads-fabro Codex plugin is installed
  And the operator opens the Codex TUI
  When the operator opens "/skills"
  And chooses "List skills"
  And searches for "drive"
  Then the picker renders "drive (livespec-orchestrator-beads-fabro)"
  And the rendered row is typed as a Skill
  And the operator does not need to search for the colon-qualified
    "livespec-orchestrator-beads-fabro:drive" form

Scenario: A fleet-listed repository gets Codex full access
  Given the repository's committed "codex_full_access.fleet_listed" marker is
    true, previously derived from the livespec core fleet manifest by the
    "refresh" operation
  And no local opt-out is set
  When the orchestrator's Codex full-access gate is evaluated
  Then the companion-plugin review/rescue chokepoint is rewritten to
    "danger-full-access"
  And the canary classifies the active companion source by matching the exact
    full-access rewrite expression
  And the orchestrator-owned raw "codex exec" credential-refresh command runs
    with the full-access flag and stdin redirected from an EOF-reaching source

Scenario: An unrelated external repository remains default-off
  Given the repository has no committed fleet-listed marker
  And no local Codex full-access opt-in is set
  When the orchestrator's Codex full-access gate is evaluated
  Then the companion-plugin chokepoint is not rewritten by this plugin
  And the orchestrator-owned raw "codex exec" credential-refresh command does
    not infer full access from plugin installation alone

Scenario: A gate that cannot be evaluated denies full access
  Given the gate mechanism cannot be loaded or evaluated
  When a surface governed by the gate is invoked
  Then that surface runs WITHOUT full access
  And the failure does not crash the invoking hook or command
```

## Scenario 22 — Dispatcher admits the top-ranked ready item up to the per-repo WIP cap

```gherkin
Feature: Dispatcher admission valve with a per-repo WIP cap
  As the Dispatcher enforcing the admission valve
  I want to admit the top-ranked (earliest-rank) admission-eligible ready item when a slot frees
  So that work flows up to the per-repo WIP cap and no further

Scenario: Admission fills slots in rank order until the cap is reached
  Given a per-repo wip_cap of 2
  And three admission-eligible ready items with ranks "a0", "a1", "a2"
  When the Dispatcher runs with no active items
  Then it admits the items with ranks "a0" and "a1" first
  And it sets an assignee on each admitted item
  And it transitions each admitted item to active
  And it does not admit the item with rank "a2" until an active slot frees
```

## Scenario 23 — Dispatcher never auto-approves a manual-admission item

```gherkin
Feature: Manual admission policy rests an item at pending-approval
  As the Dispatcher enforcing safe-by-default approval
  I want to refuse to auto-approve an item whose effective admission_policy is manual
  So that risky or irreversible work waits for an explicit human approval

Scenario: A manual-admission item is surfaced rather than auto-approved
  Given a `pending-approval` item whose effective admission_policy is manual
  And no human has explicitly approved it through the operator valve surface
  When the Dispatcher reaches it
  Then it does not transition the item to `ready`
  And it surfaces the item for the maintainer's explicit `approve`
```

## Scenario 24 — complete merges on green into the acceptance state

```gherkin
Feature: Post-merge acceptance — complete merges on green
  As the Dispatcher completing an active item
  I want complete to merge on green and move the item to the acceptance state
  So that acceptance verifies the shipped, observable artifact

Scenario: complete ships on green into acceptance, not straight to done
  Given an active item whose pre-merge just check floor has passed green
  When the doer declares the implementation complete
  Then the change is merged on green via gh pr merge with the resolved merge method and --auto
  And the item transitions to the acceptance state
  And the item does not transition straight to done
```

## Scenario 25 — accept confirms post-ship per acceptance_policy

```gherkin
Feature: Post-merge acceptance — accept honors acceptance_policy
  As the acceptance valve confirming a shipped change
  I want accept to honor the item's effective acceptance_policy — the item's own
    acceptance_policy label, or the global dispatcher.acceptance_mode default
    when the item carries no label
  So that no change reaches done without at least one AI verification pass, that
    pass being a read-and-judge of the merged diff against the item's acceptance
    criteria plus a telemetry watch, yielding a PASS or FAIL verdict (its FAIL
    routes are exercised by Scenario 35)

Scenario: ai-then-human parks in acceptance until a human confirms
  Given an item in the acceptance state whose effective acceptance_policy is ai-then-human
  When the AI acceptance pass PASSES against the shipped artifact and surfaces findings
  Then the item parks in the acceptance state on the ledger
  And it transitions to done only after a human confirms from the console (the `drive --action accept:<id>` valve action)

Scenario: reject from acceptance routes by corrective kind
  Given an item in the acceptance state
  When the reviewer rejects it for rework
  Then the item transitions to active for a fix-forward patch
  And when the reviewer instead rejects it for re-grooming
  Then the merged change is reverted and the item transitions to backlog
```

## Scenario 26 — list-work-items emits lane and lane_reason

```gherkin
Feature: list-work-items emits the derived lane and lane_reason
  As a consumer of list-work-items --json
  I want each item to carry a computed lane and lane_reason
  So that the console consumes the lane instead of re-deriving it

Scenario: lane and lane_reason are computed from lane_of
  Given a stored ready item with an open dependency
  And a stored blocked item whose blocked_reason is needs-human
  And a stored active item
  When list-work-items --json is run
  Then the ready-with-open-dependency item emits lane "blocked" and lane_reason "dependency"
  And the stored blocked item emits lane "blocked" and lane_reason "needs-human"
  And the active item emits lane "active" and lane_reason null
```

## Scenario 27 — next ranks ready items by rank

```gherkin
Feature: next ranks ready items by the rank ordering authority
  As the single ranking authority the Dispatcher composes
  I want next to order ready items by rank then id
  So that the pull order is the deterministic rank order

Scenario: ready candidates are returned in rank order
  Given ready items with ranks "a2", "a0", "a1"
  When next is run
  Then the candidates are returned in the order ranked "a0", "a1", "a2"
  And ties are broken by id lexicographic order
```

## Scenario 28 — append_work_item registers and lands a custom status in two steps

```gherkin
Feature: 2-step append into a beads custom status
  As the beads store adapter writing a work-item
  I want to create then update because bd create cannot land a custom status
  So that an item filed into backlog carries the correct lifecycle status

Scenario: a file create lands open then updates to a custom status
  Given a tenant with the 5 custom statuses registered
  When append_work_item files a new item whose initial state is backlog
  Then bd create lands the issue with status open
  And bd update sets the issue status to the custom backlog status
```

## Scenario 29 — Factory GitHub App token on the dispatch path

```gherkin
Feature: Factory GitHub App installation-token authentication
  As the Dispatcher running the self-contained dispatch path
  I want every automated GitHub operation to authenticate with a freshly-minted App installation token
  So that no dispatch path depends on a fleet PAT or an ambient gh login

Scenario: Dispatch refuses fail-closed when no App environment is resolvable
  Given the App environment (GITHUB_APP_ID + GITHUB_PRIVATE_KEY) is absent
  And the dispatch target repo has no credential_wrapper to re-exec through
  When a dispatch is attempted
  Then the Dispatcher refuses with an actionable diagnostic
  And it does not fall through to a fleet credential or an ambient gh login

Scenario: A credential-seam refusal names the missing variable and the target's own wrapper
  Given a dispatch target whose configured credential_wrapper omits one of the required per-dispatch credentials (App environment, tenant store secret, or the engine LLM credential)
  When the consuming seam on the dispatch path reaches the absent variable
  Then the seam fails closed naming the specific missing variable
  And the diagnostic names the dispatch target's own configured credential_wrapper as the corrective injection path, never a fleet wrapper

Scenario: A long merge-poll survives token expiry via first-class remint
  Given a merge-poll that outlives a single installation token's roughly one-hour validity
  When the Dispatcher spawns each polling subprocess
  Then each subprocess resolves a currently-valid token from the caching provider
  And the operation survives the token expiry transparently

Scenario: The sandbox receives only an ephemeral installation token
  Given a dispatched Fabro worker sandbox
  When the sandbox environment table is materialized
  Then it carries a freshly-minted EPHEMERAL installation token
  And neither the durable App private key nor any long-lived personal access token is projected
```

## Scenario 30 — Dispatch-time baseline conformance gate

```gherkin
Feature: Dispatch-time baseline conformance gate
  As the Dispatcher's Fabro prepare chain
  I want to provision each sandbox to the baseline profile and gate on the shared Verifiers
  So that every dispatched sandbox is conformant by construction

Scenario: A conformant sandbox proceeds to work
  Given the prepare chain installed the canonical commit-refuse hook and declared the sandbox exemption marker
  When the baseline Verifiers run over the provisioned sandbox
  And every Verifier exits zero
  Then the work-item is driven

Scenario: A baseline violation aborts the dispatch before work is driven
  Given a provisioned sandbox where a baseline Verifier exits non-zero
  When the prepare chain gates on the Verifiers
  Then the run aborts before any work is driven
  And the baseline violation surfaces as a failed dispatch rather than silently non-conformant work
```

## Scenario 31 — drive human valve actions

```gherkin
Feature: drive human valve actions
  As the operator (or the console acting on the operator's behalf)
  I want approve, accept, reject, set-admission, and set-acceptance commands on the drive surface
  So that the two human-delegable gates and the policy edits are commanded through the plugin's published surface, never a direct ledger write

Scenario: approve authorizes a resting manual-admission item into ready
  Given a `pending-approval` item whose effective admission_policy is manual
  When the operator invokes `drive --action approve:<work-item-id>`
  Then the item transitions to `ready` (the human approval act — `pending-approval → ready`)
  And admission to `active` then follows mechanically when a WIP slot frees, dependencies are clear, an assignee resolves, and `factory_safety` is null
  And the journal records the actor

Scenario: accept confirms a parked item to done
  Given an item parked in the acceptance state awaiting the human leg of its acceptance_policy
  When the operator invokes `drive --action accept:<work-item-id>`
  Then the item transitions to done

Scenario: reject routes by corrective kind
  Given an item in the acceptance state
  When the operator invokes `drive --action reject:<work-item-id>:rework`
  Then the item transitions to active for a fix-forward patch
    And when the operator instead invokes `drive --action reject:<work-item-id>:regroom`
  Then the merged change is reverted and the item transitions to backlog

Scenario: set-admission edits the policy without touching the status
  Given an item whose stored admission_policy is manual
  When the operator invokes `drive --action set-admission:<work-item-id>:auto`
  Then the item's admission_policy becomes auto
  And the item's status is unchanged
  And the journal records the actor

Scenario: a manual → auto flip on a pending-approval item does not approve it
  Given a `pending-approval` item whose stored admission_policy is manual
  When the operator invokes `drive --action set-admission:<work-item-id>:auto`
  Then the item remains at `pending-approval`
  And moving it to `ready` still requires an explicit `approve:<work-item-id>`
```

## Scenario 32 — Adopter-target dispatch compatibility

```gherkin
Feature: Adopter-target dispatch compatibility
  As the Dispatcher driving an adopter repo (not a fleet member)
  I want per-tenant engine identity, target-toolchain workflows, and default-branch awareness
  So that an adopter dispatch succeeds without fleet-specific assumptions

Scenario: Preflight verifies the serving App reaches the target repo
  Given an adopter target repo the fleet's shared Fabro server App cannot reach
  When the dispatch preflight runs against the serving Fabro server
  Then it refuses before launching with a diagnostic naming the per-tenant server requirement (the target tenant's own App identity)
  And the diagnostic surfaces the App workflows read-write grant as deliberately withheld from the dispatch credential, naming the attended-host-session route

Scenario: A target-local workflow supplies the target's toolchain facts
  Given an adopter repo carrying its own .fabro/workflows/implement-work-item workflow
  And the dispatch names no --workflow override and no --workflow-name
  Then the prepare steps run the target repo's own toolchain facts
  And no fleet-toolchain prepare constant (uv / lefthook / livespec_dev_tooling) is assumed for the target

Scenario: Pull-primary resolves the target's default branch
  Given a target repo whose default branch is main
  When the post-merge janitor's pull-primary stage refreshes the primary checkout
  Then it resolves the target repo's default branch and pulls that ref
  And it never hardcodes master
```

## Scenario 33 — auto_approve_ready governs admission and a per-item label wins

```gherkin
Feature: The auto_approve_ready global default and its per-item override
  As an operator delegating routine approval
  I want an unlabeled routine item auto-approved while a per-item manual label still holds it
  So that admission delegation is granular and never reaches design-human-gated work

  Background:
    Given dispatcher.auto_approve_ready is true

  Scenario: An unlabeled routine item inherits the global and is auto-approved
    Given a routine `pending-approval` item that carries no explicit admission_policy label
    When the Dispatcher reaches it
    Then its effective admission_policy is auto and it is approved into `ready` without a human
    And the auto-approval is journaled with the item id and the setting that governed it

  Scenario: A per-item manual label beats the permissive global
    Given a `pending-approval` item carrying an explicit admission_policy label of manual
    When the Dispatcher reaches it
    Then it does not transition the item to `ready`
    And the item rests at `pending-approval` awaiting the human's explicit `approve`

  Scenario: A spec-change-tier item is never auto-approved
    Given a design-human-gated (spec-change-tier) `pending-approval` item
    When the Dispatcher reaches it
    Then it does not auto-approve the item, regardless of the setting or of any per-item label
    And the item stays escalated to a human
```

## Scenario 34 — acceptance_mode governs the acceptance leg

```gherkin
Feature: The acceptance_mode global default and its per-item override
  As an operator choosing how shipped work is accepted
  I want acceptance_mode to select the acceptance leg, with a per-item label overriding it
  So that acceptance delegation is granular and every path still carries an AI pass

Scenario: ai-only accepts to done on a passing AI pass
  Given dispatcher.acceptance_mode is ai-only
  And an item parked in acceptance that carries no explicit acceptance_policy label
  When the AI acceptance pass PASSES
  Then the item transitions to done without a human
  And the auto-acceptance is journaled with the item id and the setting that governed it

Scenario: ai-then-human parks for the human accept valve
  Given dispatcher.acceptance_mode is ai-then-human (the default)
  And an item parked in acceptance that carries no explicit acceptance_policy label
  When the AI acceptance pass PASSES
  Then the item parks in acceptance for the human `accept` valve action

Scenario: human-only parks for the human with the AI pass advisory
  Given dispatcher.acceptance_mode is human-only
  And an item parked in acceptance that carries no explicit acceptance_policy label
  When the AI acceptance pass runs
  Then the item parks in acceptance for the human
  And the AI pass is advisory — it informs the human and never disposes of the item

Scenario: A per-item acceptance_policy label overrides the global
  Given dispatcher.acceptance_mode is ai-only
  And an item parked in acceptance carrying an explicit acceptance_policy label of human-only
  When the AI acceptance pass PASSES
  Then the item parks in acceptance for the human rather than transitioning to done

Scenario: Every acceptance path carries at least one AI pass
  Given an item parked in acceptance under any of the three acceptance modes
  When the acceptance leg runs
  Then at least one AI acceptance pass has run before the item can reach done
```

## Scenario 35 — A failing AI acceptance pass reworks only in the AI-dispositive modes

```gherkin
Feature: The FAIL route of the AI acceptance pass is scoped to the AI-dispositive modes
  As a maintainer relying on the acceptance valve
  I want a failing AI pass to auto-rework only where the AI is dispositive
  So that no rework loop is unbounded and a human-only item is never disposed of by the machine

Scenario: An AI-dispositive item is auto-reworked on a failing pass
  Given an item in acceptance whose effective acceptance_policy is ai-only or ai-then-human
  When the AI acceptance pass judges the merged artifact against its acceptance criteria and FAILS
  Then the item transitions to active for fix-forward rework without a human
  And the item carries the rework:pending label
  And the disposing dispatch does not itself perform the rework
  And the auto-rework is journaled with the item id and the setting that governed it

Scenario: Repeated failure past the rework cap escalates instead of reworking again
  Given an item whose failed AI acceptance passes have reached dispatcher.acceptance_rework_cap
  When the AI acceptance pass FAILS again
  Then the item is not reworked again
  And it escalates to blocked with blocked_reason needs-human and is surfaced to a human

Scenario: A human-only item's failing AI pass advises but never disposes
  Given an item in acceptance whose effective acceptance_policy is human-only
  When the AI acceptance pass FAILS
  Then the item stays parked in the acceptance state
  And the failure is surfaced to the human as an advisory finding
  And the item is not auto-reworked
  And the human retains the accept / `reject` decision
```

## Scenario 36 — Every needs-human block always escalates

```gherkin
Feature: No dispatcher policy setting auto-disposes a needs-human escalation
  As a maintainer relying on the residual human escalation path
  I want every needs-human block surfaced to a human rather than machine-resolved
  So that no policy setting can turn a human decision into a machine guess

Scenario: A needs-human block is surfaced, never auto-resolved
  Given an item blocked with blocked_reason needs-human
  And any combination of dispatcher policy settings
  When the Dispatcher reaches it
  Then it does not auto-resolve the decision
  And the item remains blocked and is surfaced to a human
  And the escalation is queryable from the journal

Scenario: A design-human-gated decision escalates by design even at high confidence
  Given a design-human-gated decision — a spec-change slice, a regroom/backlog bounce, or a human-only acceptance — that the LLM could resolve with high confidence
  When the Dispatcher evaluates it
  Then it does not auto-dispose the decision, because the design reserves it to a human
  And the decision is left on its human path — a spec-change to `/livespec:propose-change`, a bounce resting in backlog — and surfaced to a human
  And the escalation is queryable from the journal

Scenario: A drift acceptance is routed to the spec lifecycle, never auto-disposed
  Given a drift acceptance that the LLM could resolve with high confidence
  When the Dispatcher evaluates it
  Then it does not auto-dispose the decision
  And the decision is left on the Spec-Plane revise path, where acceptance is human by default and MAY be owned by the consensus tier only under an explicit per-repo `spec_governance.drift_acceptance_mode` opt-in
  And the escalation is queryable from the journal
```

## Scenario 37 — Safe defaults hold when nothing is configured

```gherkin
Feature: The dispatcher policy settings are safe by default
  As a maintainer
  I want the defaults alone to arm no dangerous behavior
  So that a dangerous disposition is never entered by accident

Scenario: An all-default configuration arms nothing
  Given a `.livespec.jsonc` that sets no `dispatcher.*` policy settings
  And no work-item carries a per-item policy label (`admission_policy`, `acceptance_policy`, or the merge-on-review-cap label)
  When the Dispatcher runs
  Then `auto_approve_ready` and `merge_on_review_cap` are false, `acceptance_mode` is ai-then-human, `review_fix_cap` is 3, and `acceptance_rework_cap` is 2
  And no such unlabeled item is auto-approved, no past-cap review ships, and no acceptance reaches done without a human
```

## Scenario 38 — capture-spec-drift surfaces ledger intent missing from spec

```gherkin
Feature: Ledger-intent drift surfaces missing spec behavior
  As a maintainer keeping the spec honest against the Ledger
  I want work-item intent that never made it into the spec surfaced as drift
  So that decisions recorded only in work-items still reach the spec

Scenario: A recent work-item's intent absent from the spec becomes a drift finding
  Given a recent Ledger work-item whose description encodes a behavior not present in the current spec
  When capture-spec-drift runs, optionally scoped by --since-version
  Then it surfaces a ledger-intent drift finding
  And on user consent it hands off to /livespec:propose-change
  And it never mutates the work-item or writes spec-side state directly
```

## Scenario 39 — Ratified lesson injects into dispatch briefs

```gherkin
Feature: dispatch-brief lessons injection
  As the factory operator
  I want human-ratified lessons to reach every dispatch brief
  So that the ratified improvement loop actually changes future dispatch behavior

Scenario: a merged ratified lesson appears in composed briefs
  Given loop-reflection-gate/lessons.md is committed and carries ratified lesson text "L"
  When the Dispatcher composes a dispatch brief for an admitted work-item
  Then the composed brief contains lesson text "L" in its delimited lessons section
```

## Scenario 40 — Unratified or absent lessons never alter briefs

```gherkin
Feature: unratified lessons are inert
  As the maintainer supervising the improvement loop
  I want unratified or absent lessons to leave briefs untouched
  So that only content I merged can steer future dispatches

Scenario: absent or placeholder-only lessons leave the brief unchanged
  Given loop-reflection-gate/lessons.md is absent, or present with no ratified lessons
  When the Dispatcher composes a dispatch brief
  Then the composed brief is identical to one composed with no lessons file
  And no lessons heading or placeholder text appears in the brief

Scenario: an unmerged reflector proposal never injects
  Given an open reflector PR proposes lesson text "M" against loop-reflection-gate/lessons.md
  And the committed loop-reflection-gate/lessons.md does not contain "M"
  When the Dispatcher composes a dispatch brief
  Then the composed brief does not contain "M"

Scenario: an unreadable lessons file fails open
  Given loop-reflection-gate/lessons.md exists but cannot be read or parsed
  When the Dispatcher composes a dispatch brief
  Then the composed brief is identical to one composed with no lessons file
  And the dispatch proceeds normally
```

## Scenario 41 — standalone analysis lands in a plan, not a root research tree

```gherkin
Feature: analysis placement honors the retired research tree
  As a maintainer recording standalone analysis
  I want new analysis to land in the plan store
  So that no root research/ tree re-accretes after its fleet-wide retirement

Scenario: a new analysis note lands under the plan store
  Given a maintainer records standalone analysis for slug "t" via the plan front-end
  When the plan stores the reasoning note
  Then the note lands as write-once research under plan/t/research/
  And no root research/ path is created anywhere in the repository
  And no live handoff.md, supervisor-handoff.md, or mutable plan-state file is created
```

## Scenario 42 — list-plans enumerates unarchived plans

```gherkin
Feature: list-plans enumerates unarchived plans
  As a consumer of the read/awareness surface
  I want open plans enumerated as a thin-transport read
  So that an unarchived plan is never invisible to the awareness picture

Scenario: unarchived plans enumerate in lexicographic order; archived plans do not
  Given a governed repo whose plan/ plan store contains unarchived plan directories plan/beta-topic/ and plan/alpha-topic/
  And an archived plan directory plan/archive/old-topic/
  When list-plans --json is run
  Then plans is exactly ["alpha-topic", "beta-topic"]
  And no entry references old-topic or the plan/archive/ path
  And the invocation mutates nothing

Scenario: a repo with no plan directory yields zero plans
  Given a governed repo with no plan/ directory
  When list-plans --json is run
  Then plans is empty
  And the invocation exits 0
```

## Scenario 43 — loop drains the ranked queue by default

```gherkin
Feature: The dispatch loop drains the ranked queue with no mode flag
  As the Dispatcher draining ready work unattended
  I want the loop to drain the ranked queue by default
  So that an unattended drain needs no arming argument and no run mode

Scenario: An invocation with no --item drains the ranked queue within budget
  Given a ranked queue of dispatch-eligible ready items
  When the Dispatcher loop is invoked with --budget and no --item and no --dry-run
  Then it selects items from the ranked queue in the same order the next surface advertises
  And it dispatches at most --budget items in the run
  And the drain stays bounded by the per-repo wip_cap regardless of --parallel
  And no run-mode argument is passed or recognized

Scenario: --item narrows the ranked selection without bypassing admission
  Given a ranked queue of dispatch-eligible ready items
  And a work-item that is NOT dispatch-eligible because it rests at pending-approval under an effective admission_policy of manual
  When the Dispatcher loop is invoked with --item naming that ineligible work-item
  Then it is not dispatched
  And the run dispatches only named items that are themselves dispatch-eligible
```

## Scenario 44 — --dry-run plans the ranked queue and dispatches nothing

```gherkin
Feature: The dispatch loop can plan a drain without performing it
  As an operator inspecting what the factory would do
  I want a dry run that plans the identical selection and dispatches nothing
  So that a drain can be previewed without launching a run or mutating the ledger

Scenario: A dry run reports the selection it would dispatch and launches nothing
  Given a ranked queue of dispatch-eligible ready items
  When the Dispatcher loop is invoked with --dry-run
  Then it reports exactly the selection the same invocation would dispatch, honoring --budget, the wip_cap, and any --item scoping
  And it launches no Fabro run
  And it mutates no work-item and writes no work-item store
  And it produces no per-run cost signal and therefore no cost-gate verdict
```

## Scenario 45 — Unobservable cost fails closed on an unattended drain and warns on a hand-picked dispatch

```gherkin
Feature: The fail-closed cost gate keys on --item presence, not on a run mode
  As the Dispatcher protecting unattended spend
  I want an unobservable per-run cost to refuse only when no human is present
  So that an unattended drain never burns spend cost-blind, while a hand-picked dispatch is not blocked by a dark cost signal

Scenario: Unobservable cost on an unattended drain refuses under the enforce posture
  Given LIVESPEC_COST_MODE is enforce
  And the Dispatcher loop was invoked with no --item (an unattended queue drain)
  And a dispatched run reached a successful terminal outcome and its run id resolves against the cost source
  When that run's per-run cost signal is unobservable
  Then the gate verdict is a fail-closed refusal and the Dispatcher stops picking
  And a gate record is journaled with the work-item id, the run id, the severity, and the refusal

Scenario: Unobservable cost on a hand-picked dispatch warns rather than refusing
  Given LIVESPEC_COST_MODE is enforce
  And the Dispatcher loop was invoked with --item naming a single work-item (a human is present)
  And that run reached a successful terminal outcome and its run id resolves against the cost source
  When that run's per-run cost signal is unobservable
  Then the gate verdict is a warning and the Dispatcher does not refuse
  And a gate record is journaled

Scenario: An observed cost never trips the unobservable gate
  Given LIVESPEC_COST_MODE is enforce
  When a gated run's per-run cost signal is observable
  Then the unobservable-cost gate does not refuse, whether or not --item was passed

Scenario: An unresolvable run id is journaled as a skipped gate and is fail-open
  Given LIVESPEC_COST_MODE is enforce
  And the Dispatcher loop was invoked with no --item (an unattended queue drain)
  And a dispatched run's run id cannot be resolved against the cost source
  When the cost gate runs
  Then the run is journaled as a skipped gate record naming the work-item and the unresolvable-run-id reason
  And the Dispatcher does not refuse, because this disposition is deliberately fail-open

Scenario: A run that did not reach a successful terminal outcome is not gated
  Given LIVESPEC_COST_MODE is enforce
  And a dispatched run did not reach a successful terminal outcome
  When the cost gate runs
  Then that run yields no gate verdict
  And a provider-limit-released run still yields its attempt-cost observation
  And the Dispatcher does not refuse on that observation's account

Scenario: The default report posture journals a gate record but derives no keyed verdict
  Given LIVESPEC_COST_MODE is unset, empty, or unrecognized, so it resolves to report
  And the Dispatcher loop was invoked with no --item
  When a gated run's per-run cost signal is unobservable
  Then the cost signal is still observed and a gate record is still journaled, carrying the observability of the signal
  And no keyed verdict is derived, the record's severity is report
  And the Dispatcher does not refuse and applies no cost cap
```

## Scenario 46 — Per-item cap overrides set a label or clear to reinherit the global default

```gherkin
Feature: Per-item cap overrides set one label and clear-to-inherit removes it
  As the operator (or the console acting on the operator's behalf)
  I want the three per-item cap-override actions to set or clear exactly one override
  So that a work-item can override, then reinherit, a global dispatcher cap without any status change

Scenario: set-review-fix-cap writes the override without touching the status
  Given a ready work-item carrying no per-item review_fix_cap override
  When the operator invokes `drive --action set-review-fix-cap:<work-item-id>:5`
  Then the item's per-item review_fix_cap override becomes 5
  And the item's status is unchanged
  And the journal records the actor

Scenario: set-merge-on-review-cap takes a boolean value
  Given a work-item carrying no per-item merge_on_review_cap override
  When the operator invokes `drive --action set-merge-on-review-cap:<work-item-id>:true`
  Then the item's per-item merge_on_review_cap override becomes true
  And the item's status is unchanged

Scenario: clear removes the override so the item reinherits the global default
  Given a work-item carrying a per-item acceptance_rework_cap override
  When the operator invokes `drive --action set-acceptance-rework-cap:<work-item-id>:clear`
  Then the per-item acceptance_rework_cap override is removed
  And the item reinherits the global dispatcher.acceptance_rework_cap default
  And the item's status is unchanged

Scenario: clearing an already-absent override is a green no-op
  Given a work-item carrying no per-item review_fix_cap override
  When the operator invokes `drive --action set-review-fix-cap:<work-item-id>:clear`
  Then the action succeeds without error
  And the item still carries no per-item review_fix_cap override
  And the item's status is unchanged
```

## Scenario 47 — The guarded move relocates within the operator-movable statuses only

```gherkin
Feature: The guarded move performs operator queue control without force-shipping
  As the operator commanding hands-on queue control
  I want move to relocate a selected item only among the operator-movable statuses
  So that queue control writes only the status and never force-ships unverified work past the acceptance ship-guard

Scenario: move relocates an item to an allowed status and writes only the status
  Given a work-item at backlog
  When the operator invokes `drive --action move:<work-item-id>:ready`
  Then the item's status becomes ready
  And nothing other than the item's status is changed
  And the journal records the actor

Scenario: move to done is refused
  Given a work-item the operator wants to force to done
  When the operator invokes `drive --action move:<work-item-id>:done`
  Then the action is refused with a clear error
  And the item's status is unchanged
  And done stays reachable only by accepting from acceptance

Scenario: move to acceptance or pending-approval is refused
  Given a work-item at active
  When the operator invokes `drive --action move:<work-item-id>:acceptance`
  Then the action is refused with a clear error
    And when the operator instead invokes `drive --action move:<work-item-id>:pending-approval`
  Then that action is also refused with a clear error
  And acceptance and pending-approval are entered only on their own guarded or entry paths
```

## Scenario 48 — Dispatcher refuses a not-factory-safe item at admission

```gherkin
Feature: A ready work-item whose `factory_safety` is non-null is refused at
  the admission valve before any sandbox launch and surfaced for routing to
  an attended host session that performs it automatically.

  Scenario: A ready item carrying factory_safety needs-host-secrets is refused
    Given a `ready` work-item whose `factory_safety` is `needs-host-secrets`
    And a free WIP slot, cleared dependencies, and a resolvable assignee
    When the Dispatcher's admission valve evaluates it
    Then the item is not admitted to `active`
    And no Fabro sandbox run is launched for it
    And the Dispatcher surfaces an actionable host-route refusal naming the
      `needs-host-secrets` reason
    And the item stays `ready` (it is not marked `blocked`)

  Scenario: A ready item editing .github/workflows/ is refused pre-dispatch
    Given a `ready` work-item whose scope edits a file under `.github/workflows/`
    And ordinary CI executes on GitHub-hosted runners
    And a free WIP slot, cleared dependencies, and a resolvable assignee
    When the Dispatcher's admission valve evaluates it
    Then the item is not admitted to `active`
    And no Fabro sandbox run is launched for it
    And the refusal names the attended-host-session route
    And the refusal is unchanged by the hosted CI execution substrate because the workflow would rewrite the factory's own examiner
    And the refusal reaches a terminal verdict without an interactive prompt
    And the item's published `awaits_scope_override` signal becomes true
    And the item stays `ready` (it is not marked `blocked`)

  Scenario: A citation-only scope override clears the refusal signal
    Given a `ready` work-item whose `factory_safety` is null
    And its published `awaits_scope_override` signal is true after a declared-workflow-edit refusal
    When the operator invokes `set-workflow-scope-override:<work-item-id>:citation-only`
    Then the durable citation-only override is recorded without changing item status
    And the published `awaits_scope_override` signal becomes false
    And the next admission evaluation may admit the item if every other admission condition is satisfied

  Scenario: A citation-only scope override cannot admit intrinsic host-only work
    Given a `ready` work-item whose `factory_safety` is `mutates-host-machinery`
    When the operator attempts `set-workflow-scope-override:<work-item-id>:citation-only`
    Then the action is refused because `factory_safety` is evaluated first
    And `awaits_scope_override` remains false

  Scenario: set-factory-safety records the host-only opt-out reason on a backlog item
    Given a `backlog` work-item whose `factory_safety` is null
    When the operator invokes `set-factory-safety:<work-item-id>:needs-host-secrets`
    Then the item's `factory_safety` is set to `needs-host-secrets`
    And the host-only reason is recorded on the item in the journal
    And the item's lifecycle status is unchanged
    And the item's `admission_policy` is unchanged

  Scenario: set-factory-safety is not gated by lifecycle state
    Given an `acceptance` work-item whose `factory_safety` is null
    When the operator invokes `set-factory-safety:<work-item-id>:mutates-host-machinery`
    Then the item's `factory_safety` is set to `mutates-host-machinery`
    And the item's lifecycle status remains `acceptance`

  Scenario: set-factory-safety requires one of the four canonical factory_safety reasons
    Given a `ready` work-item whose `factory_safety` is null
    When the operator attempts `set-factory-safety:<work-item-id>:not-a-real-reason` with a reason outside the factory_safety enum
    Then the action is refused because the reason is not one of `needs-host-secrets`, `mutates-host-machinery`, `needs-privileged-host`, or `needs-host-only-input`
    And the item's `factory_safety` remains null

  Scenario: A ready item editing .github/actions/ is NOT refused
    Given a `ready` work-item whose scope edits a composite action under
      `.github/actions/` and no file under `.github/workflows/`
    And a free WIP slot, cleared dependencies, and a resolvable assignee
    When the Dispatcher's admission valve evaluates it
    Then the item is admitted to `active`
```

## Scenario 50 — A committed wip_cap of 0 admits nothing (dispatch-off)

```gherkin
Feature: A per-repo wip_cap of 0 is the consumer project's dispatch-off posture
  As a consumer project that has committed a dispatch-off posture
  I want a committed wip_cap of 0 to admit nothing
  So that switching dispatch off is a committed, verifiable fact of the repo

Scenario: No admission-eligible ready item is admitted under a committed wip_cap of 0
  Given a per-repo wip_cap of 0 committed in `.livespec.jsonc`
  And an admission-eligible ready item
  When the Dispatcher runs with no active items
  Then the committed wip_cap of 0 resolves to 0 rather than falling back to the default
  And the Dispatcher admits nothing
  And the item stays `ready`
```

## Scenario 51 — The rework-return valve leaves a durable journal record

```gherkin
Feature: A human rework return from acceptance is attributable in the journal
  As a maintainer auditing how a work-item re-entered `active`
  I want the `reject:rework` valve to journal its transition durably
  So that every rework return into `active` has exactly one journaled owner

Scenario: Rejecting an acceptance item for rework journals the transition
  Given a work-item in `acceptance`
  When the operator invokes `reject:<work-item-id>:rework`
  Then the work-item moves to `active`
  And a durable journal record is written for that transition
  And the record names the acting party, the stage identifier, and the work-item id
  And the record outlives the invocation rather than existing only in the response payload
```


## Scenario 52 — A repository mise tool cannot shadow the lifecycle-guarded bd entry point

Given a beads-backed repository runs on a host with the lifecycle guard installed

And the repository carries project-local developer-tool pins in its mise configuration

When the plugin resolves `bd` from `LIVESPEC_BD_PATH` or its configured default

Then the resolved public entry point MUST be the lifecycle guard

And the repository's mise configuration MUST NOT declare or install `bd`

And normal plugin, ledger, and operator calls MUST NOT invoke the guard's private delegate executable

## Scenario 53 — A dispatch proceeds when the host is busy; the scheduler queues it

```gherkin
Feature: The Orchestrator performs no host-level concurrency check, so host
  throughput is governed solely by the Fabro server's own scheduler

  Scenario: A dispatch is not refused when other runs are already in flight
    Given factory runs already in flight on the shared host
    And an admission-eligible `ready` work-item with a free per-repo WIP slot
    When the Dispatcher evaluates the dispatch
    Then no host-level concurrency check is performed
    And the dispatch is not refused on host-concurrency grounds
    And the run is submitted to the Fabro server

  Scenario: A dispatch past the host's scheduler limit queues rather than failing
    Given the shared host's Fabro server is already at its configured
      concurrency limit
    And an admission-eligible `ready` work-item with a free per-repo WIP slot
    When the Dispatcher dispatches it
    Then the Dispatcher does not exit with a host-capacity refusal
    And the work-item is admitted to `active`
    And the run waits for scheduler capacity rather than being rejected
```

## Scenario 54 — Host-side dispatch runs a released payload, never the working tree

```gherkin
Feature: The host-side Dispatcher executes a released payload, so a dispatcher
  version is usable only once it is past versioning and the release gates

  Scenario: An unreleased working-tree edit does not take effect on the dispatch path
    Given an orchestrator working checkout carrying an unreleased local edit
    And a provisioned released payload that does not carry that edit
    When a host-side dispatch runs
    Then the dispatch executes the released payload
    And the unreleased working-tree edit has no effect on it
    And no promotion into an orchestrator working tree is attempted

  Scenario: A newer provisioned payload is canaried and alarmed, never promoted
    Given a running release and a newer provisioned released payload
    When the Dispatcher evaluates whether a newer payload is available
    Then it compares the running release against the provisioned release
    And it validates the newer payload with a canary on this host
    And a passing canary surfaces that a restart is due
    And a failing canary keeps the last-known-good payload running and alarms a human
    And in neither case does the Dispatcher modify or re-point its own execution artifact

  Scenario: An undeterminable available release is recorded as undetermined
    Given the available release cannot be determined
    When the Dispatcher evaluates whether to update itself
    Then it records that the available release could not be determined
    And that record is distinguishable from recording that no update was available
```

## Scenario 55 — plan archive commissions a missing independent completeness review

```gherkin
Feature: A plan archive gate obtains the independent evidence it requires
  As a maintainer resuming an implementation-complete plan
  I want the plan operation to commission a missing independent review
  So that archive does not depend on a human noticing an evidence gap

Scenario: A mechanically complete plan without review evidence obtains a fresh review
  Given a plan epic whose child requirements and implementation items are all closed
  And the plan ledger timeline carries no independent completeness-review evidence
  When the plan operation resumes the archive attempt
  Then it commissions a fresh independent adversarial completeness reviewer
  And that reviewer has had no role in the plan's implementation
  And the plan remains unarchived until the reviewer records durable evidence
  And an evidence record that does not attest every research requirement including deferrals has no archive authority
```

## Scenario 56 — A not-human-gated decision is taken by the session, never escalated

```gherkin
Feature: The escalation floor has a positive complement no session escalates past
  As a maintainer whose attention is the scarce resource
  I want decisions the design leaves to the session taken by the session
  So that a rule about what MUST escalate cannot be read as a rule that everything escalates

Scenario: A conformance fix to unratified behavior is taken without a human valve
  Given implementation behavior that no ratified clause requires
  And no pending proposed change under proposed_changes/ has that behavior as its subject
  And a change that removes that behavior so the implementation matches the ratified specification
  And the session can confidently resolve the decision
  When a session evaluates the change
  Then it takes the change itself
  And it records the rationale naming the change as conformance
  And it does not route the change to `/livespec:propose-change`
  And it does not escalate the change as a spec-change decision

Scenario: Deleting behavior a pending proposed change would ratify is escalated, not taken
  Given implementation behavior that no ratified clause requires
  And a pending proposed change under proposed_changes/ that would ratify that behavior
  When a session evaluates a change that removes the behavior
  Then it escalates the change to the revise valve that owns the queued question
  And it does not take the deletion itself
  And the Precedence rule never reaches the decision, because deleting the behavior changes no ratified text

Scenario: Deleting behavior a pending proposed change would forbid is also escalated, not taken
  Given implementation behavior that no ratified clause requires
  And a pending proposed change under proposed_changes/ that would forbid that behavior
  When a session evaluates a change that removes the behavior
  Then it escalates the change to the revise valve that owns the queued question
  And it does not take the deletion itself, even though the valve is expected to rule the same way
  And the exclusion holds on the behavior being the subject of a pending change, not on the direction the valve will rule

Scenario: A decision the session cannot confidently resolve is surfaced even inside an enumerated class
  Given a decision that falls in an enumerated not-human-gated class
  And the session cannot confidently resolve that particular decision
  When the session evaluates it
  Then it blocks and surfaces the decision to a human under the floor's cannot-resolve arm
  And the escalation is queryable from the journal
  And the enumeration does not assert that the session can resolve every instance of the class

Scenario: A substantiated class-wide inability still surfaces under the floor's cannot-resolve arm
  Given a decision that falls in an enumerated not-human-gated class
  And the session lacks a concrete capability that every instance of that class would need
  And the recorded rationale names that missing capability
  When the session evaluates the decision
  Then it blocks and surfaces the decision to a human under the floor's cannot-resolve arm
  And the escalation is admitted even though the inability applies to every instance of the class

Scenario: Rote hedging does not satisfy the cannot-resolve arm's record requirement
  Given a decision that falls in an enumerated not-human-gated class
  And the session genuinely cannot confidently resolve that particular decision
  And a recorded rationale that asserts low confidence without naming anything the session lacks
  When the rationale is adjudicated
  Then the rationale does not satisfy the clause, because the inability is unsubstantiated
  And the decision still blocks and surfaces under the floor's cannot-resolve arm, with the cure being a substantiated rationale

Scenario: A hedged escalation from a session that could resolve the decision does not shed the duty to take it
  Given a decision that falls in an enumerated not-human-gated class
  And the decision is not one of the floor's design-human-gated classes
  And it does not change what the specification requires
  And the session can confidently resolve that particular decision
  And a recorded rationale that asserts low confidence without naming anything the session lacks
  When the rationale is adjudicated
  Then the rationale does not satisfy the clause, because the inability is unsubstantiated
  And the duty to take the decision remains with the session, because the cannot-resolve arm never applied

Scenario: An unlisted decision outside the floor is resolved by the governing test, not by its absence from the list
  Given a decision whose class is not enumerated in the not-human-gated set
  And the decision is not one of the floor's design-human-gated classes
  When a session evaluates it
  Then it applies the governing test of whether the decision changes what the specification requires
  And it does not escalate on the sole ground that the class is unlisted

Scenario: A floor decision still escalates even though it changes nothing the specification requires
  Given a regroom or backlog bounce, or a `human-only` acceptance
  And the decision changes nothing that the specification requires
  When a session evaluates it
  Then it escalates the decision on the design-human-gated path
  And the escalation is queryable from the journal
  And the governing test does not admit it, because this rule subtracts nothing from the floor

Scenario: A spec-change-tier child's disposition escalates instead of being taken by the session
  Given a plan child whose autonomy tier is spec-change
  And a decision to close that child or move it to a different parent
  When a session evaluates the decision
  Then it escalates the decision on the design-human-gated path
  And it does not take the disposition itself
  And removing the refusal is not admitted as a conformance fix, because this rule requires the refusal

Scenario: An impl-follow-up child's disposition is taken by the session, not escalated
  Given a plan child carrying a non-null spec_commitment_hint for an already-ratified change
  And the decision is not one of the floor's design-human-gated classes
  And the child's autonomy tier is not spec-change
  And the session can confidently resolve the decision
  When a session evaluates a decision to close it or move it to a different parent
  Then it takes the disposition itself
  And it records the rationale durably
  And it does not escalate the disposition, because the hint marks ratified follow-up work rather than a spec-change slice

Scenario: A freeform child with no spec commitment and no spec-change tier is disposed by the session
  Given a plan child whose spec_commitment_hint is null
  And the decision is not one of the floor's design-human-gated classes
  And the child's autonomy tier is not spec-change
  And the session can confidently resolve the decision
  When a session evaluates a decision to close it or move it to a different parent
  Then it takes the disposition itself
  And it records the rationale durably
  And it does not refuse the disposition, because a null hint is not evidence of a spec-change tier

Scenario: An implementation that cannot determine the autonomy tier refuses the disposition
  Given a plan child whose autonomy tier cannot be determined from any ratified datum
  When an implementation evaluates a decision to close that child or move it to a different parent
  Then it refuses the disposition and surfaces it
  And it does not substitute spec_commitment_hint for the missing datum

Scenario: A fabricated lack passes textual adjudication without invoking the arm or shedding the duty to take
  Given a decision that falls in an enumerated not-human-gated class
  And the decision is not one of the floor's design-human-gated classes
  And it does not change what the specification requires
  And the session can confidently resolve that particular decision
  And a recorded rationale that names a concrete lack the session does not in fact have
  When the rationale is adjudicated
  Then the adjudication admits the record, because the inspection is answerable against the text alone
  And the duty to take the decision remains with the session, because the cannot-resolve arm never applied
  And the record does not satisfy the clause, because the named lack is not one the session has

Scenario: A listed decision that also changes what the specification requires still escalates
  Given a decision in an enumerated not-human-gated class
  And the same decision would also change what a ratified clause requires
  When a session evaluates it
  Then it escalates the decision on the design-human-gated path
  And the escalation is queryable from the journal
  And the enumeration does not override the governing test
```

## Scenario 60 — An observed provider exhaustion refuses admission, and expires

```gherkin
Feature: The Dispatcher skips observed-unavailable candidates and refuses only an exhausted required chain
  As a maintainer holding several non-interchangeable provider allowances
  I want each node's ordered candidates filtered by observed scoped holds
  So that observed exhaustion prevents subsequent admission to covered candidates without defeating an eligible fallback

  Scenario: A held primary with a viable fallback is admitted
    Given a ready work-item whose potentially reachable ACP node has an unexpired domain hold covering candidate zero
    And the same node has an unheld candidate one
    When the Dispatcher evaluates the admission valve
    Then the item is admitted with candidate one selected for that node
    And no sandbox is refused merely because candidate zero is held

  Scenario: An exhausted admission-required chain refuses without disposing the item
    Given a ready work-item with no eligible candidate for one ACP node potentially reachable in the submitted graph
    When the Dispatcher evaluates the admission valve
    Then the item is not admitted
    And no sandbox run is launched
    And the item remains at status "ready" without a claim and is not marked "blocked"
    And the refusal is journaled with the work-item id, governing condition, admission-required node lacking an eligible candidate, and scheduled reevaluation instant
    And applicable hold observations and their expiries are included when present
    And when no hold governs the refusal, the record names the outstanding confirmation, unavailable evidence source, admission-time credential-probe skip, or admission session-headroom skip without inventing a hold identity or expiry

  Scenario: A scoped record expires, a completed confirmation turn re-confirms the candidate, and admission resumes
    Given an observed availability record whose bounded expiry has passed
    And the covered candidate makes an admission-required chain viable
    And an availability confirmation turn through that candidate completes successfully
    When the Dispatcher evaluates the admission valve on a subsequent pass
    Then the expired record does not skip the candidate
    And the item is admitted normally

  Scenario: A legacy provider record remains effective during migration
    Given an unexpired legacy provider-exhaustion record against provider "codex"
    And an admission-required chain whose built-in primary carries the "codex" compatibility alias
    And no fallback remains eligible
    When the Dispatcher evaluates the admission valve
    Then the legacy record exhausts that chain and refuses admission

  Scenario: Credential material never mints an observed hold
    Given a provider whose host-side credential file is readable
    And no candidate attempt has reported an eligible typed condition
    When the Dispatcher evaluates the admission valve
    Then it does not read credential material to mint an observed hold
    And it holds no new availability record

  Scenario: A containment refusal never disposes a needs-human item
    Given a work-item carrying blocked_reason "needs-human"
    And observed holds exhaust an admission-required chain
    When the Dispatcher evaluates that item
    Then the item is not auto-resolved
    And the item stays surfaced through the needs-attention awareness surface

  Scenario: Low session headroom on the primary selects an uncovered fallback
    Given an item whose implement node's primary is a covered candidate under the admission session-headroom clause
    And dispatcher.session_headroom_floor_percent is 20
    And that node lists an uncovered eligible fallback candidate
    And every other admission-required node retains an eligible candidate
    And every other admission-valve condition is satisfied
    And the primary credential's remaining five-hour headroom reads below 20 percent
    When the Dispatcher evaluates admission
    Then the reading is journaled with the work-item id and the opaque credential identity
    And the fallback candidate is selected for the implement node
    And the selection record references the primary's headroom assessment and the governing floor
    And the item is admitted

  Scenario: Low or unobservable session headroom with no eligible candidate waits without a claim
    Given a ready item whose every candidate on one admission-required node is a covered candidate under the admission session-headroom clause
    And dispatcher.session_headroom_floor_percent is 20
    And every other admission-required node retains an eligible candidate
    And every other admission-valve condition is satisfied
    And each of those credentials' remaining five-hour headroom reads below 20 percent or is unobservable
    When the Dispatcher evaluates admission
    Then the item stays ready with no dispatch claim and no blocked_reason
    And its containment refusal record names the assessed credential identity, the reading or unobservable result, the observation time, the governing floor and the skipped candidates
    And the refusal names the admission-required node and scheduled reevaluation instant
    And no observed availability record is created
    And no observed availability record is retired
    And the unattended loop reevaluates automatically after the configured cadence
    And wait attention exposes the recorded assessment without making a live usage request

  Scenario: Unobservable headroom skips a covered primary without defeating a viable fallback
    Given a ready item with a covered primary whose headroom reading is unobservable
    And dispatcher.session_headroom_floor_percent is 20
    And that node has an uncovered eligible fallback
    And every other admission condition is satisfied
    When admission is evaluated
    Then the primary's unobservable result is journaled
    And the fallback is selected and the item is admitted

  Scenario: Equality passes the headroom filter without overriding another gate
    Given a covered candidate with 20 percent remaining headroom
    And dispatcher.session_headroom_floor_percent is 20
    When admission is evaluated
    Then the headroom filter does not skip that candidate
    And all other admission conditions are still applied

  Scenario: A disabled floor retains observation without refusing on unobservability
    Given a covered candidate whose headroom reading is unobservable
    And dispatcher.session_headroom_floor_percent is 0
    When admission is evaluated
    Then the unobservable result is journaled
    And the headroom filter does not skip that candidate
    And all other admission conditions are still applied

  Scenario: A covered primary projected to exhaust within the horizon selects an uncovered fallback
    Given an item whose implement node's primary is a covered candidate under the admission session-headroom clause
    And dispatcher.session_headroom_floor_percent is 20
    And dispatcher.session_headroom_horizon_minutes is 180
    And the earliest assessment of the primary credential journaled between 15 and 90 minutes earlier, for any work-item, read 64.5 percent utilization 30 minutes earlier
    And its current reading is 75 percent utilization, so its remaining headroom of 25 percent passes the floor
    And that node lists an uncovered eligible fallback candidate
    And every other admission condition is satisfied
    When the Dispatcher evaluates admission
    Then the journal records a drain rate of 21 percentage points per hour and a projected exhaustion about 71 minutes after the observation
    And the primary is skipped by projection, not by the floor
    And the fallback candidate is selected for the implement node
    And the selection record references the primary's assessment, the governing floor and the governing horizon as a projection skip

  Scenario: A projected exhaustion beyond the horizon is admitted, and a provider reset claim changes nothing
    Given a covered candidate whose remaining headroom of 25 percent passes a floor of 20
    And its baseline assessment 30 minutes earlier read 72 percent utilization, so the drain rate is 6 percentage points per hour
    And dispatcher.session_headroom_horizon_minutes is 180
    And the reading response carries a provider reset instant 10 minutes away
    When admission is evaluated
    Then the projected exhaustion is about 250 minutes after the observation and no projection skip applies
    And the reset instant is not used for the skip and, if journaled, only as an unverified provider claim
    And all other admission conditions are still applied

  Scenario: A credential with no baseline in this checkout is governed by the floor alone
    Given a covered candidate whose remaining headroom passes the floor
    And this checkout's dispatch journal holds no assessment of its credential identity between 15 and 90 minutes earlier
    When admission is evaluated
    Then the projection is journaled as unavailable with its reason
    And no projection skip applies to that candidate

  Scenario: A reading no higher than its baseline has no projection
    Given a covered candidate whose remaining headroom passes the floor
    And its baseline assessment within the window read a utilization equal to or higher than the current reading
    When admission is evaluated
    Then the projection is journaled as unavailable with its reason
    And no projection skip applies to that candidate

  Scenario: A horizon of zero records the projection without skipping
    Given a covered candidate whose projected exhaustion falls within 180 minutes of its observation
    And dispatcher.session_headroom_horizon_minutes is 0
    When admission is evaluated
    Then the drain rate and projected exhaustion instant are journaled
    And no projection skip applies to that candidate

  Scenario: A passing usage reading cannot clear observed availability evidence
    Given a covered candidate with headroom above the positive floor
    And a live observed hold covers that candidate
    When admission is evaluated
    Then that candidate remains ineligible under the hold
    And no usage reading retires the hold

  Scenario: A hold on one provider does not refuse an item wholly on another
    Given an unexpired domain hold, current or legacy, on the codex availability domain
    And a ready work-item whose every ACP node resolves to candidates outside that domain
    When the Dispatcher evaluates the admission valve
    Then the item is admitted
    And no refusal record names the codex hold

  Scenario: A hold recorded by another repository's run is visible host-wide
    Given a run of another repository on a participating factory recorded an unexpired domain hold on the codex availability domain
    When this repository's Dispatcher evaluates a ready item whose first implement candidate is in that domain
    Then that candidate is skipped exactly as a hold from this repository's own run would skip it
    And no per-repository peer list is consulted

  Scenario: A chain exhausted by live holds waits until scheduled reevaluation
    Given a ready work-item whose candidates for one potentially reachable ACP node are all covered by live holds
    When the Dispatcher evaluates admission
    Then the item's next admission evaluation is scheduled at the earliest expiry among the covering holds
    And the wait is surfaced with that instant and an applicable clearance valve, never resolve-blocked
    And the scheduled wait survives a Dispatcher restart
    And an expired instant does not schedule repeated immediate retries

  Scenario: An availability wait without a live hold remains visible and retries automatically
    Given a ready work-item with no eligible candidate for one potentially reachable ACP node
    And no live hold governs the wait
    And eligibility is prevented by outstanding confirmation, unavailable evidence, or admission-time credential-probe skips
    When the Dispatcher evaluates admission
    Then reevaluation is scheduled after dispatcher.credential_reprobe_interval_seconds
    And attention names the governing condition and scheduled instant with an inspection handoff
    And no nonexistent hold clearance or resolve-blocked action is advertised
    And the wait survives Dispatcher restart without requiring human action
```

## Scenario 61 — A dead implementer does not spend the second vendor

```gherkin
Feature: A dead implementer stops the workflow rather than handing an empty tree to another vendor
  As a maintainer whose Codex exhaustion should not also consume Anthropic allowance
  I want review and disposition skipped when the implementer produced nothing
  So that an exhausted window costs one vendor's allowance rather than two

Scenario: Review and disposition are skipped against an unchanged tree
  Given a factory run whose implementer node terminated without producing any change to the worktree relative to the dispatch base
  When the workflow advances past the implementer node
  Then no review round is executed against that tree
  And no review-fix round is executed against that tree
  And no disposition round is executed against that tree
  And the run is finalized carrying the implementer's own failure as its surfaced cause
  And the truncation is journaled with the work-item id and the governing condition

Scenario: A run whose implementer did change the tree proceeds normally
  Given a factory run whose implementer node produced a change to the worktree relative to the dispatch base
  When the workflow advances past the implementer node
  Then the review round is executed normally
  And the dead-implementer rule truncates nothing
```

## Scenario 64 — Every Codex ACP node runs a pinned model, and the opt-out is a true no-op

```gherkin
Feature: The factory chooses its Codex model rather than inheriting a decode failure
  As a maintainer holding one metered Codex subscription
  I want every Codex node pinned to a chosen model and effort
  So that spend is a decision rather than the residue of a stale baked adapter

Scenario: A repository with no configuration inherits the built-in per-node defaults
  Given a dispatch target whose configuration carries no "dispatcher.acp_nodes" table
  When the Dispatcher renders the workflow adapter inputs
  Then the implementer adapter renders from the structured default naming agent claude-acp, model claude-opus-5 and effort high as leading environment assignments
  And for a groom-kind workflow the publish adapter renders from the structured default naming agent claude-acp, model claude-haiku-4-5 and effort high as leading environment assignments
  And the implementer adapter is not a Codex adapter absent an explicit entry
  And an implementation workflow renders no pr adapter

Scenario: A structured Codex entry pins exactly the node it names
  Given a dispatch target whose "dispatcher.acp_nodes" table sets the implement node to agent codex-acp with a model and an effort
  When the Dispatcher renders the workflow adapter inputs
  Then the implement node's adapter is the Codex adapter carrying that model and model_reasoning_effort inside CODEX_CONFIG
  And every other node's adapter is unaffected by the entry

Scenario: A Codex entry missing model or effort refuses before claim
  Given a dispatch target whose "dispatcher.acp_nodes" table sets a node to agent codex-acp with a model but no effort
  When the Dispatcher validates the configuration
  Then the dispatch refuses before claim naming the node and the missing field

Scenario: The explicit opt-out is the manual form and renders the un-pinned base string
  Given a dispatch target whose "dispatcher.acp_nodes" table sets a node to the manual form whose command is the baked codex-acp path and whose CODEX_CONFIG carries no model key
  When the Dispatcher renders that node's adapter
  Then the rendered adapter equals the un-pinned base string exactly
  And the rendered adapter carries no model override
  And the rendered adapter carries no reasoning-effort override

Scenario: A malformed entry refuses rather than silently falling back
  Given a dispatch target whose "dispatcher.acp_nodes" entry for a node is neither a valid structured entry nor a valid manual entry
  When the Dispatcher validates the configuration
  Then the dispatch refuses before claim naming the node and the offending field

Scenario: The retired codex_models key refuses and prints its replacement
  Given a dispatch target whose configuration still carries a "dispatcher.codex_models" block
  When the Dispatcher validates the configuration
  Then the dispatch refuses before claim
  And the refusal prints the equivalent "dispatcher.acp_nodes" structured entries for every node the retired class covered
```

## Scenario 65 — A provider ceiling is permanent and surfaces the provider's own sentence

```gherkin
Feature: A refusal that retrying cannot fix is not reported as transient
  As an operator reading a failed dispatch
  I want the provider's own ceiling message surfaced and classified permanent
  So that the outcome names the fault instead of the transport that carried it

Scenario: A usage ceiling is classified permanent and flagged as typed state
  Given a failed run whose cause chain carries a provider usage ceiling
  When the Dispatcher derives the failure detail for that run
  Then the failure category is permanent rather than transient infrastructure
  And the failure signature carries the same permanent verdict
  And the failure detail carries the typed provider-limit flag

Scenario: The surfaced cause is the innermost element, not the transport wrapper
  Given a failed run whose cause chain carries a transport wrapper as its outermost element
  And whose innermost element carries the provider's payload
  When the Dispatcher derives the failure detail
  Then the surfaced cause is the innermost element
  And the surfaced cause is not the transport wrapper

Scenario: The provider's embedded sentence is surfaced rather than the raw enclosing text
  Given a provider payload that embeds its message inside a structured object
  When the Dispatcher derives the failure detail
  Then the surfaced cause is the embedded message
  And the surfaced cause names the ceiling and its reset instant

Scenario: A remote-compaction 404 is permanent but is not a spend ceiling
  Given a failed run whose cause chain carries a remote-compaction 404
  When the Dispatcher derives the failure detail
  Then the failure category is permanent rather than transient infrastructure
  And the failure signature carries the same permanent verdict
  And the typed provider-limit flag is not set

Scenario: An ordinary transient failure keeps its classification
  Given a failed run whose cause chain carries no permanent cause of either recognised class
  When the Dispatcher derives the failure detail
  Then the failure category is the one the run reported
  And the failure signature is unchanged
  And the typed provider-limit flag is not set

Scenario Outline: Every measured provider-limit form is detected against its executed candidate and is never transient
  Given a failed run whose failing node attempt ran on a <candidate> candidate
  And that attempt's recorded failure carries <form>
  When the Dispatcher derives the failure detail for that run
  Then the failure category is permanent and not transient_infra
  And the failure detail carries the typed provider-limit flag
  And the provider is attributed as <provider>

  Examples:
    | candidate  | form                                                                               | provider  |
    | claude-acp | the sentence "You've hit your session limit" with structured kind rate_limit       | anthropic |
    | claude-acp | only the message text "You've hit your limit · resets" and no structured payload   | anthropic |
    | claude-acp | only the message text "You've hit your usage limit" and no structured payload      | anthropic |
    | claude-acp | the organisation spend-limit sentence                                              | anthropic |
    | codex-acp  | the structured field codexErrorInfo carrying usageLimitExceeded                    | codex     |
    | codex-acp  | the structured field codex_error_info carrying usage_limit_exceeded                | codex     |
    | codex-acp  | the structured usage-limit field with reordered keys and different JSON whitespace | codex     |
    | codex-acp  | only the message text "You've hit your usage limit" and no structured payload      | codex     |
    | codex-acp  | only the message text "usage limit exceeded" and no structured payload             | codex     |

Scenario: A shared provider sentence is attributed to the candidate that ran
  Given a failed run whose failing node attempt ran on a claude-acp candidate
  And that attempt's recorded failure carries only the message text "You've hit your usage limit"
  When the Dispatcher derives the failure detail for that run
  Then the provider is attributed as anthropic and not as codex
  And the hold recorded for it covers the executed candidate's availability domain only

Scenario: A Claude rate_limit kind without the measured sentence is not a quota exhaustion
  Given a failed run whose failing node attempt ran on a claude-acp candidate
  And that attempt's recorded failure carries structured kind rate_limit and no measured provider-limit sentence
  When the Dispatcher derives the failure detail for that run
  Then the typed provider-limit flag is not set
  And no availability hold is recorded

Scenario: A provider-limit failure routed through the needs_human terminal keeps its typed state
  Given a run that ended at the workflow's needs_human terminal after an ACP node failed on a provider usage ceiling
  And the terminal message carries the needs-human script's output rather than the provider's sentence
  When the Dispatcher derives the outcome
  Then it classifies from the failing node's own recorded failure
  And the outcome carries the typed provider-limit flag, the attributed provider, and the provider's sentence
  And the item does not rest at blocked with blocked_reason needs-human
```

## Scenario 66 — A parked rework item is re-dispatched before new ready work

```gherkin
Feature: The fix-forward rework contract is executable
  As a maintainer relying on the acceptance valve
  I want a rework-routed item to be picked up by the next drain
  So that rework parks visibly and briefly instead of invisibly forever

Scenario: The drain drives a rework-pending item before admitting new ready work
  Given an active item carrying the rework:pending label and holding no live dispatch lock
  And ready items exist in the queue
  And the counted-claim total excluding the marked item's own row is below wip_cap
  When the Dispatcher drain runs
  Then a fix-forward rework dispatch starts for the marked item before any new ready item is admitted
  And starting the rework journals the rework admission and leaves the label in place until the rework dispatch's terminal disposition
  And the merged change is not reverted

Scenario: A rework dispatch that dies before publishing leaves the item re-selectable
  Given a marked item whose rework dispatch acquired a dispatch lock and died before publishing a branch
  When a later drain runs and the lock is no longer live
  Then the item is still marked and is selected for rework again

Scenario: A parked rework item neither holds capacity nor reads as an abandoned claim
  Given an active item carrying the rework:pending label and holding no live dispatch lock
  When the admission accounting runs
  Then the item is classified rework-pending
  And it is excluded from the capacity count
  And it is not recorded as an abandoned claim
  And no stranded-dispatch surface reports it as stranded
```

## Scenario 67 — The human rework reject parks the same selectable state

```gherkin
Feature: The two rework entries do not diverge in selectability
  As an operator using the reject valve
  I want a human rework reject to be picked up exactly like an AI-fail rework
  So that the valve I am offered is not a dead end

Scenario: reject:rework stamps the marker and the operator can drive it immediately
  Given an item parked in acceptance
  When the operator performs reject rework via the drive valve
  Then the item transitions to active carrying the rework:pending label
  And dispatch --item on that item is accepted and drives the fix-forward rework
  And dispatch --item on an active item without the label is refused as a precondition error
```

## Scenario 68 — reconcile-merged refuses a rework-pending item

```gherkin
Feature: The recovery valve stays scoped to dispatches that died mid-flight
  As an operator recovering a stranded dispatch
  I want reconcile-merged to refuse an item whose disposition already completed
  So that a completed rework disposition is never re-run as a recovery

Scenario: A rework-pending item is refused with the rework route named
  Given an item carrying the rework:pending label whose merged PR completed post-run disposition
  When the operator invokes reconcile-merged for that item
  Then the invocation is refused
  And the refusal names the rework re-dispatch route as the remedy
  And force does not bypass the refusal

Scenario: An unmarked merged item remains recoverable
  Given an active item without the rework:pending label whose dispatch died after its PR merged without completing disposition
  When the operator invokes reconcile-merged for that item
  Then it is accepted, because that is the recovery this valve exists for
```

## Scenario 69 — Zero-criteria AI-dispositive work is walled before any spend

```gherkin
Feature: Ungradeable acceptance criteria refuse before the factory, not after the merge
  As a maintainer paying for dispatches
  I want an unverifiable item stopped at ready and at dispatch
  So that a guaranteed acceptance failure is discovered before a single token is spent

Scenario: The pre-dispatch wall refuses with the dedicated exit code
  Given an item whose effective acceptance_policy is ai-only or ai-then-human
  And its effective acceptance criteria parse to zero gradeable assertions
  When the drain or dispatch --item reaches it
  Then the dispatch is refused before any factory run is created
  And the refusal names the item id and states the criteria are empty or ungradeable
  And the exit code is 5, distinct from the precondition exit 3

Scenario: The approve valve refuses and the item rests in place
  Given a pending-approval item with the same empty effective criteria and an AI-dispositive policy
  When a human approves it or an auto admission policy considers it
  Then entry to ready is refused or withheld with the parse result surfaced
  And the item rests at pending-approval

Scenario: Criteria that yield gradeable assertions through the merged read or the fallback pass the wall
  Given an item whose gradeable criteria reach the primitive only through the metadata-merged value, or only through a description section titled Exit criteria
  When the walls evaluate it
  Then its effective criteria parse to at least one gradeable assertion and it is dispatched normally rather than refused
```

## Scenario 70 — Absent evidence parks; it never manufactures a verdict

```gherkin
Feature: The NEEDS_ATTENTION verdict is the absent-evidence disposition under every policy
  As a maintainer relying on the acceptance valve
  I want a pass that cannot observe its evidence to park the item for me
  So that no judgment is rendered with no evidence examined

Scenario: Unobservable telemetry with a readable diff parks instead of failing
  Given an item in acceptance whose run telemetry is unobservable
  And its merged diff is readable
  When the AI acceptance pass runs under any acceptance_policy
  Then the verdict is NEEDS_ATTENTION
  And the item stays parked in acceptance
  And no rework is triggered and acceptance_rework_cap is not consumed
  And the parking is journaled with the absent evidence leg
  And the human disposes of it with the existing accept or reject valve

Scenario: Zero parsed checks past the wall park instead of failing
  Given an item in acceptance whose effective criteria parse to zero gradeable assertions
  When the AI acceptance pass runs
  Then the verdict is NEEDS_ATTENTION and the item is not auto-accepted and not reworked
```

## Scenario 71 — One effective-criteria authority for every gate

```gherkin
Feature: Every gate reads the same effective acceptance criteria
  As an item author
  I want capture advice, the walls, and the acceptance pass to agree on my criteria
  So that a criteria text that passes one gate is never absent at another

Scenario: The same resolution order is used at capture, ready, dispatch, and acceptance
  Given an item whose criteria resolve through the merged criteria value or the description Exit criteria section
  When the capture front-end displays the parse, the ready wall evaluates it, the pre-dispatch wall evaluates it, and the acceptance pass judges it
  Then all four surfaces resolve the identical effective criteria text through the single public primitive
```

## Scenario 72 — Every journal record carries a resolved invoker

```gherkin
Feature: Journal invoker attribution with a defined resolution order
  As an operator reconstructing an incident
  I want every journaled act to say who invoked it and how that identity was resolved
  So that attribution never depends on a writer's honor

Scenario: The flag wins over the environment
  Given a state-changing dispatcher invocation with --invoker set and LIVESPEC_INVOKER set
  When the invocation journals its records
  Then every record carries the flag identity with invoker_source flag

Scenario: The environment is used when no flag is passed
  Given a state-changing dispatcher invocation with only LIVESPEC_INVOKER set
  When the invocation journals its records
  Then every record carries that identity with invoker_source env

Scenario: An unasserted identity is marked, never trusted
  Given a state-changing dispatcher invocation with neither input set
  And dispatcher.require_invoker is false
  When the invocation journals its records
  Then every record carries the derived fallback identity with invoker_source fallback

Scenario: The append layer is the only writer and refuses forged fields
  Given a caller supplying a record that already carries an invoker or invoker_source field
  When the record reaches the append layer
  Then the append is refused as a programming error
  And a mechanical control proves no code appends to the journal path outside the layer
```

## Scenario 73 — The tightened posture refuses before it mutates

```gherkin
Feature: require_invoker refuses unattributed state-changing invocations at startup
  As a maintainer tightening attribution
  I want an unattributed invocation refused before any mutation
  So that the refusal itself never creates a half-performed act or an attribution gap

Scenario: A fallback-only invocation is refused as a precondition error
  Given dispatcher.require_invoker is true in the committed configuration
  And a state-changing dispatcher invocation with neither --invoker nor LIVESPEC_INVOKER
  When the invocation starts
  Then it is refused with the precondition exit code before any store mutation, journal write, or run creation
  And the refusal names the two accepted identity inputs

Scenario: The dial is not in this repo's API-configurable key manifest
  Given the orchestrator's API-configurable key manifest
  When its key set is read
  Then dispatcher.require_invoker is not among the keys
  And changing it requires a committed configuration change
```

## Scenario 74 — The probe demonstrates the loop on a taken item and leaves only explained state

```gherkin
Feature: The loop probe drives one pre-filed item through the whole cycle
  As a maintainer who must report the loop live
  I want a probe that demonstrates the composed cycle with scoped assertions
  So that steady-state ownership is demonstrated, never declared from documents

Scenario: A full probe cycle passes every stage assertion
  Given a work-item filed through capture-work-item with an ai-only acceptance policy, clear dependencies, a resolvable assignee, and a change confined to the .livespec-probe directory
  And a free WIP slot exists
  And the probe is invoked with --item and an asserted invoker identity
  When the probe drives the item through admission, the factory run, merge, and acceptance
  Then every stage assertion passes: non-empty effective criteria, clean journaled step outcomes, an evidence-grounded verdict, and terminal done
  And the probe's journal records carry a non-fallback invoker_source and the probe run identifier
  And no attention item referencing the reserved identifier set remains
  And the unrelated before/after delta is reported without being asserted
  And the operator may then remove the probe artifact without any surface complaining

Scenario: An escaping change fails the probe before the merge
  Given a probe item whose change touches a path outside .livespec-probe
  When the driven cycle verifies confinement before merging
  Then the cycle fails without merging, naming the escaping path

Scenario: A merged escape fails the probe and names the revert obligation
  Given an escaping change that nonetheless merged
  When the probe evaluates the merged diff backstop
  Then the probe fails naming the merged commit and the revert obligation
```

## Scenario 75 — The probe takes; it never files, and absence of evidence never passes it

```gherkin
Feature: The probe respects the consent boundary and fails closed
  As a maintainer relying on the consent discipline
  I want the probe unable to create work and unable to pass on unread state
  So that a health command can never become an unconsented intake path or a false green

Scenario: The probe refuses to run without a designated item
  Given a probe invocation without --item
  When the probe starts
  Then it refuses without creating any work-item

Scenario: The probe refuses an item it cannot drive to done
  Given a designated item whose effective acceptance policy is not ai-only
  When the probe starts
  Then it refuses naming the acceptance policy label to set at filing

Scenario: An unavailable attention source fails the probe
  Given a probe cycle whose attention source cannot be read at the after snapshot
  When the probe evaluates its residue assertions
  Then the probe fails with a source-unavailable outcome
  And nothing is reported cleared or resolved

Scenario: A defect-seeding probe fixture never touches the live Dispatcher
  Given a probe variant that creates an empty-criteria fixture item
  When it runs
  Then it runs against the hermetic fake backend or a disposable tenant only
```

## Scenario 76 — A missing required integration point stops the next dispatch, not silently every dispatch

```gherkin
Feature: Degraded step outcomes persist into refusals
  As a maintainer whose repository must provide the factory's integration points
  I want a known-missing integration point to refuse the next dispatch with the remedy named
  So that the factory degrades loudly once instead of silently forever

Scenario: The next dispatch is refused after a degraded janitor outcome
  Given the journal's latest outcome for the repository names a missing required integration point
  And no committed waiver covers that step
  When the next drain or dispatch --item runs for the repository
  Then the dispatch is refused at the pre-dispatch gate with the precondition exit code
  And the refusal names the missing integration point, the originating outcome record, and the remedy

Scenario: The refusal clears when re-verification observes the point provided
  Given the same journal history
  And the governed repository now provides the named integration point
  When the pre-dispatch re-verification runs
  Then it observes the integration point provided and the dispatch proceeds
  And a clearing record is journaled naming the step identifier and the degraded outcome it clears

Scenario: A committed waiver proceeds visibly
  Given a committed step waiver naming the step, an owner, and a reason
  When a dispatch runs and the waived step fails
  Then the dispatch proceeds
  And the waived failure is journaled as waived with the waiver's owner
```

## Scenario 77 — The master-CI preflight resolves the pipeline the repository declares

```gherkin
Feature: Declared pipeline resolution with a fail-closed default
  As an adopter whose CI workflow is not named CI
  I want to declare my pipeline so the preflight can prove my master green
  So that a conforming repository is not permanently unprovable by naming convention

Scenario: A declared green pipeline proves master health
  Given a repository whose committed dispatcher.master_ci names its workflow and aggregate job
  And the latest run of that workflow on the resolved default branch has a green aggregate job
  When the master-CI preflight runs
  Then the dispatch proceeds with the pass journaled

Scenario: A declared red pipeline refuses
  Given the same declaration with a red aggregate job on the latest resolved-branch run
  When the master-CI preflight runs
  Then the dispatch is refused naming the red run

Scenario: The branch is resolved, never assumed
  Given a repository whose default branch is not named master
  When the master-CI preflight runs
  Then the run lookup targets the resolved default branch

Scenario: An undeclared repository uses the default convention
  Given a repository with no dispatcher.master_ci key and a workflow named CI with a ci-green job
  When the master-CI preflight runs
  Then it resolves the default convention unchanged

Scenario: An unresolvable pipeline refuses, and the old fail-open paths refuse too
  Given a repository whose declared or default pipeline cannot be found, or a host with no usable gh credential, or a repository with no runs yet
  When the master-CI preflight runs
  Then the dispatch is refused with the refusal naming the attempted resolution, the declaring key, and the remedy including the step-waiver escape
```

## Scenario 78 — A temporary throttle carries its own restore work-item

```gherkin
Feature: Temporary setting postures are owned ledger work, not comments
  As a maintainer lowering a setting for a bounded trial
  I want the restore obligation to be first-class tracked work with an owner and criteria
  So that the trial ending cannot leave the throttle in place silently

Scenario: The lowered cap is paired with an owned restore item
  Given an operator deliberately lowers a committed dispatcher setting for a bounded trial
  When the settings change is reviewed for merge
  Then an owned ledger work-item exists naming the setting and the restore target
  And the item carries an owner label naming the responsible party
  And its restore condition is written as gradeable acceptance criteria
  And it carries a dependency edge to the ledger-tracked trigger where one exists

Scenario: A comment-only restore note is the reviewable violation
  Given a committed settings change that lowers a setting with only a configuration comment as the restore carrier
  When the change is reviewed for merge
  Then the review names the missing restore work-item as a violation of this contract
  And no configuration schema offers a temporary variant or restore-condition field to reach for
```

## Scenario 79 — One malformed item never blinds the inbox, and never vanishes silently

```gherkin
Feature: Per-item tolerance on the consumer side, loud validation on the producer side
  As an operator relying on the attention surface
  I want a bad item skipped-and-surfaced by consumers and surfaced loudly by the producer
  So that neither a blinded inbox nor a silently shorter list can read as all-clear

Scenario: A consumer skips and surfaces a malformed item
  Given an envelope holding one malformed item and several well-formed items
  When a conforming consumer parses it
  Then the well-formed items are consumed
  And the malformed item is surfaced as skipped, not silently dropped
  And the envelope is not discarded

Scenario: An unknown kind is a well-formed item
  Given an envelope holding an item whose kind the consumer does not recognize
  When the consumer parses it
  Then the item is treated as well-formed and surfaced generically

Scenario: The producer surfaces a validation failure instead of omitting the candidate
  Given composition inputs holding one candidate that fails the runtime validator and one valid candidate
  When needs-attention composes the envelope
  Then the valid item is emitted
  And the validation failure is surfaced as a visible failure
  And the invalid candidate is not silently absent
```

## Scenario 80 — Every advertised handoff is executable as advertised

```gherkin
Feature: The advertiser and the enforcer are mechanically bound
  As an operator pasting a handoff command
  I want every advertised action to be one the enforcer accepts
  So that the attention surface never routes me into a refusal by construction

Scenario: An advertised drive handoff is accepted by drive
  Given an attention item carrying a drive-kind handoff for an item state
  When the advertised action id is submitted to drive for that item
  Then drive accepts it

Scenario: A state drive refuses is never advertised
  Given an item state for which drive refuses an action by construction
  When needs-attention composes the envelope
  Then no handoff advertising that action for that item is emitted
```

## Scenario 81 — Only a complete successful pass advances the coverage point

```gherkin
Feature: Attempt records and all-or-nothing completed coverage
  As a maintainer relying on detection recency
  I want an aborted or partial detection run to leave the coverage point unchanged
  So that a half-run can never read as coverage and silence detection again

Scenario: A complete pass writes both records and clears staleness
  Given a detection run over its declared scope whose every surfaced candidate is durably disposed
  When it reaches a successful terminal outcome
  Then an attributed attempt record and a completed-coverage record are appended to the designated anchor
  And the staleness fact derived from that coverage point clears

Scenario: An aborted or partial pass leaves the prior point standing
  Given a detection run that exits non-zero, is interrupted, or leaves a surfaced candidate undisposed
  When its records are written
  Then an attempt record is appended and no completed-coverage record is written
  And the prior completed point and the live staleness fact are unchanged

Scenario: The self-bookkeeping exception writes nothing else
  Given a detection run appending its records
  Then no work-item is created and no other ledger record is written or edited by the detection operation
```

## Scenario 82 — Staleness facts surface owned triggers, never headless runs

```gherkin
Feature: Detection recency is computed from completed coverage and surfaced with a handoff
  As an operator owning the operating rhythm
  I want overdue detection surfaced with the skill named
  So that the convergence engine is owned by a surface, not a session recap

Scenario: A ratification without a completed gap capture surfaces the backstop fact
  Given a ratified spec revision newer than the last completed gap-capture coverage point
  When needs-attention composes the snapshot
  Then a gap-capture-staleness fact appears whose handoff names capture-impl-gaps and the stale range
  And no detector is invoked by the composition

Scenario: Merges past the threshold surface the drift fact while the run has not caught up
  Given default-branch merges after the recorded drift frontier at or past the effective threshold
  When needs-attention composes the snapshot
  Then a drift-staleness fact appears naming the merges after the frontier
  And the fact invokes no detector; the reconcile pass is what runs the drift pass
```

## Scenario 83 — Capacity truth is composed from the accounting, never re-derived

```gherkin
Feature: The admission accounting's verdict is readable attention data
  As an operator asking whether a slot is free
  I want the accounting's own verdict composed with each actionable hold explained
  So that three surfaces can never again re-derive capacity from raw statuses and agree on a wrong answer

Scenario: A reached cap with an unreadable-journal hold composes the residue fact
  Given a wip_cap of 2
  And one active item holding a live dispatch lock backed by a watchable run
  And one active item whose dispatch journal cannot be read
  And one active item whose journal shows a green terminal outcome after its last admit
  And one rework-pending parked item
  When needs-attention composes the snapshot
  Then the capacity fact reports 2 counted holds and 0 free slots
  And the unreadable-journal hold appears as its own item naming the holder and an inspection handoff
  And the live-lock item is not reported as a stale claim
  And the rework-pending item is not reported as abandoned
  And no capacity item advertises a status-move handoff for the green-terminal claim
  And composing the snapshot appends no record to the dispatch journal

Scenario: A busy cap backed entirely by live runs emits no capacity item
  Given a wip_cap of 2 and two active items each holding a live dispatch lock backed by a watchable run
  When needs-attention composes the snapshot
  Then no capacity item appears
```

## Scenario 84 — Aged ready work with nothing in flight surfaces an unblock

```gherkin
Feature: Ready-work aging composes when nothing is moving
  As a maintainer whose queue silently stalled for a day
  I want aged ready work surfaced with the unblock named
  So that a stalled repository says so instead of looking busy

Scenario: The aging fact appears past the threshold and clears in flight
  Given admission-eligible ready items whose latest transition into ready is older than the effective threshold
  And no live dispatch lock and no watchable run for this repository
  When needs-attention composes the snapshot
  Then an aging fact appears naming the aged count, the oldest age, and an unblock handoff
  And when a dispatch is in flight the fact does not appear

Scenario: An item whose ready instant is unknowable is reported, never omitted
  Given an admission-eligible ready item whose latest transition into ready cannot be determined
  When needs-attention composes the snapshot
  Then that item is reported as age-unknown
  And an item that only recently entered ready after a long time captured does not count as aged
```

## Scenario 85 — Every enumerated orchestrator-owned wait composes with its unblock

```gherkin
Feature: The enumerated wait set is complete and each wait is actionable
  As an operator scanning one list for everything that is stuck
  I want each orchestrator-created wait present with the action that clears it
  So that a wait cannot hide by living in a surface nobody reads

Scenario: All six enumerated waits compose, and a non-wait does not
  Given a capacity-deferred eligible item
  And a NEEDS_ATTENTION-parked acceptance
  And a blocked item whose blocked reason is needs-human
  And a pending-approval item under an effective manual admission policy
  And a factory-unsafe ready item awaiting host routing
  And a ready item whose admission-required ACP chain is exhausted by unexpired observed holds
  And one healthy ready item admitted for dispatch
  When needs-attention composes the snapshot
  Then each of the six waits appears with an unblock handoff
  And the parked acceptance appears as exactly one item whose handoff carries the accept action
  And that item's summary names both reject dispositions
  And the healthy admitted item produces no wait item
```

## Scenario 86 — The implementer defaults to Claude Opus 5 and an explicit Codex pin still routes to Codex

```gherkin
Feature: The implementer runs Claude Opus 5 unless a repository pins it to Codex
  As a maintainer who wants the strongest implementer by default and a config-only way to stay on Codex
  I want the default implementer adapter to be the Claude adapter pinned to Opus 5
  So that switching the implementer model is a configuration change, never a code change

Scenario: A default dispatch renders the Claude implementer adapter
  Given a dispatch target whose "dispatcher.acp_nodes" table carries no entry for the implement node
  When the Dispatcher renders the acp_adapter input
  Then the rendered adapter is the Claude ACP adapter command rendered from the structured built-in default
  And it carries ANTHROPIC_MODEL set to claude-opus-5 and CLAUDE_CODE_EFFORT_LEVEL set to high as leading environment assignments
  And it carries no context-window suffix on the model name

Scenario: An explicit implementer pin routes the implementer class to Codex
  Given a dispatch target whose "dispatcher.acp_nodes" table sets the implement node to agent codex-acp with a model and an effort
  When the Dispatcher renders the acp_adapter input
  Then the rendered adapter is the Codex adapter carrying that model and its reasoning effort
  And the review_fix adapter is unchanged by the implement entry

Scenario: Publication is independent of the implementer adapter
  Given a dispatch target with no retired pr adapter override
  When the Dispatcher renders the workflow
  Then pr_refresh and pr are command stages with no ACP adapter
  And an explicit per-dispatch ACP override for pr refuses before claim with a removal remedy
Scenario: A shared repository can configure groom publication without changing code publication
  Given a repository with implementation and groom-kind workflows and an acp_nodes.pr override
  When the Dispatcher selects the implementation workflow
  Then it journals the repository override as not-applied without acquiring an adapter or credentials for pr
  And when it selects the groom-kind workflow the override applies normally
  And an explicit per-dispatch pr override on the implementation workflow refuses before claim
```

## Scenario 87 — A node's adapter resolves through three layers and the record names the supplying layer

```gherkin
Feature: Per-node adapter configuration resolves most-specific-wins
  As a maintainer who wants to switch any node to any model with a config change
  I want workflow defaults, per-repository configuration and a per-dispatch argument to layer predictably
  So that the factory's model choice is always a recorded configuration decision

Scenario: A repository entry overrides the workflow default for one node only
  Given a workflow whose acp_adapter default names the Claude adapter
  And a dispatch target whose "dispatcher.acp_nodes" table sets the implement node's command to a different adapter
  When the Dispatcher renders the workflow adapter inputs
  Then the implement node's rendered adapter carries the repository command
  And every other node's rendered adapter carries its workflow default
  And the dispatch record names the repository layer for the implement node's command

Scenario: A per-dispatch argument overrides the repository entry and is journaled
  Given a dispatch target whose "dispatcher.acp_nodes" table sets the implement node's env ANTHROPIC_MODEL
  And a dispatch invoked with an "--acp-node implement=…" argument setting a different ANTHROPIC_MODEL
  When the Dispatcher renders the workflow adapter inputs
  Then the implement node's rendered adapter carries the per-dispatch ANTHROPIC_MODEL
  And the repository's other env keys for that node are preserved
  And the dispatch record carries the argument's redacted structural representation and digest
  And it names the per-dispatch layer for that key without carrying the raw env value

Scenario: A per-dispatch value cannot arrive through the environment
  Given an environment variable that names a model for a node
  And no per-dispatch argument
  When the Dispatcher renders the workflow adapter inputs
  Then the rendered adapter is unaffected by the environment variable

Scenario: A layer naming an unknown node refuses the dispatch
  Given a dispatch target whose "dispatcher.acp_nodes" table names a node the workflow does not declare
  When the Dispatcher prepares the dispatch
  Then it refuses before any run exists naming the unknown node
```

## Scenario 88 — An arbitrary adapter with an env map and args renders without a code change

```gherkin
Feature: Any model behind any provider protocol is a configuration value
  As a maintainer who runs open-weight models behind a local router
  I want a node's adapter expressed as a command, an env map and args
  So that a local or open-source model needs no orchestrator code change

Scenario: A Claude-adapter node pointed at an Anthropic-compatible endpoint renders its env map
  Given a dispatch target whose "dispatcher.acp_nodes" table sets the implement node's env with ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN and ANTHROPIC_MODEL naming a router-qualified model
  When the Dispatcher renders the implement node's adapter
  Then the rendered adapter is the env pairs in sorted key order, then the Claude adapter command
  And no orchestrator code names the endpoint or the model

Scenario: A Codex-adapter node with a provider definition renders its args
  Given a dispatch target whose "dispatcher.acp_nodes" table sets the review_fix node's args to a model_provider definition and a model
  When the Dispatcher renders the review_fix node's adapter
  Then the rendered adapter is the Codex adapter command followed by those args in order

Scenario: The rendering is proven hermetically
  Given a test that renders an adapter against a stub endpoint or the fake backend
  When the test runs
  Then it passes without reaching any real provider over the network
```

## Scenario 89 — Node timeouts resolve from configuration and land as literal durations

```gherkin
Feature: Per-node timeouts are configuration, rendered literally
  As a maintainer whose implementer no longer dies on compaction
  I want each node's timeout to be a configured value with a 30-minute default
  So that the node timeout is the only ceiling and it is always a decision

Scenario: A default target renders every node at 1800 seconds
  Given a dispatch target with no "dispatcher.node_timeouts" table
  When the Dispatcher renders the dispatch payload's workflow graph
  Then every node's timeout attribute is the literal duration 1800s
  And the run's stall_timeout attribute is the literal duration 7200s
  And no timeout attribute contains a template opener

Scenario: A configured node keeps its value and the others keep the default
  Given a dispatch target whose "dispatcher.node_timeouts" sets implement to 7200
  When the Dispatcher renders the dispatch payload's workflow graph
  Then the implement node's timeout attribute is the literal duration 7200s
  And every other node's timeout attribute is the literal duration 1800s
  And the dispatch record names the repository layer for the implement timeout

Scenario: The subprocess ceiling follows the resolved graph
  Given a dispatch target whose resolved node timeouts sum to a longer worst-case path than the default
  When the Dispatcher computes its fabro run subprocess ceiling
  Then the ceiling exceeds that worst-case path by the fixed margin

Scenario: An invalid timeout refuses the dispatch
  Given a dispatch target whose "dispatcher.node_timeouts" sets a node to zero or to a non-integer
  When the Dispatcher prepares the dispatch
  Then it refuses before any run exists naming the key
```

## Scenario 90 — The Codex adapter is identified by its baked path and pinned through its environment

```gherkin
Feature: A reader can predict the rendered Codex adapter string and check it against the run
  As a maintainer auditing which model a factory node actually ran
  I want the Codex adapter identified by a baked path and pinned through its environment
  So that the rendered string cannot name one package while executing another

Scenario: A Codex-pinned review_fix dispatch renders both adapters in their ratified forms
  Given a dispatch whose "dispatcher.acp_nodes" table sets the review_fix node to agent codex-acp with a model and an effort and whose implementer node resolves to the Claude default
  When the Dispatcher renders both adapters
  Then the review_fix adapter is its environment assignments in sorted key order followed by the baked codex-acp path
  And the review_fix adapter carries model and model_reasoning_effort inside CODEX_CONFIG
  And the review_fix adapter carries no "-c model" argument
  And the review_fix adapter's CODEX_CONFIG value parses as JSON after POSIX shell tokenization
  And the implementer adapter is byte-identical to the ratified Claude default string

Scenario: The review_fix adapter declares its agent mode
  Given a dispatch whose "dispatcher.acp_nodes" table sets the review_fix node to agent codex-acp with a model and an effort
  When the Dispatcher renders the review_fix adapter
  Then the rendered adapter carries INITIAL_AGENT_MODE set to agent-full-access

Scenario: A node that performs no writes is rendered read-only
  Given a dispatch target whose "dispatcher.acp_nodes" table routes the review node to the Codex adapter
  When the Dispatcher renders the review node's adapter
  Then the rendered adapter carries INITIAL_AGENT_MODE set to read-only

Scenario: Package-name resolution is never used to identify the adapter
  Given a sandbox image carrying two codex-acp packages that share a global bin link
  When the Dispatcher renders any Codex adapter
  Then the rendered command is the baked path
  And the rendered command does not resolve the adapter through npx by package name
```

## Scenario 91 — The empty-model opt-out renders no model key inside CODEX_CONFIG

```gherkin
Feature: Disabling a Codex pin is a true no-op rather than a differently-spelled default
  As an operator disabling a model pin without deleting its documentation
  I want an empty model to render the un-pinned base string exactly
  So that the opt-out cannot smuggle in an empty model value

Scenario: An empty model omits the key rather than emptying it
  Given a dispatch target whose "dispatcher.acp_nodes" entry for a node is the manual form naming the baked codex-acp path with a CODEX_CONFIG that carries no model key
  When the Dispatcher renders that node's adapter
  Then CODEX_CONFIG carries no model key
  And CODEX_CONFIG carries no model_reasoning_effort key
  And the rendered adapter is byte-identical to the un-pinned base string
```


## Scenario 57 — A capacity refusal names which ceiling it means

```gherkin
Feature: Capacity surfaces distinguish the per-repo claim cap from the Fabro scheduler's host limit
  As an operator reading a dispatch refusal
  I want the refusal to say WHICH ceiling was reached
  So that I do not reason from the host scheduler's unrelated limit

Scenario: A capacity-deferred dispatch identifies the per-repo claim cap and disclaims the host limit
  Given a per-repo wip_cap of 10 committed in `.livespec.jsonc`
  And the Fabro server's `server.scheduler.max_concurrent_runs` is also 10
  And this repo holds 10 counted claims
  When the Dispatcher refuses an admission-eligible ready item on capacity
  Then the refusal identifies the exceeded ceiling as this repo's per-repo claim cap
  And the refusal does not present the value as a host-wide or per-server limit
  And the refusal states that host-run concurrency is governed separately by the Fabro scheduler
```

## Scenario 58 — Rows at status active are not the counted quantity

```gherkin
Feature: The per-repo WIP cap bounds counted claims, not rows at status active
  As a Dispatcher
  I want uncounted active rows to leave capacity available
  So that finished-but-unadvanced bookkeeping cannot strand a repository

Scenario: A repo holding more active rows than wip_cap still admits a ready item
  Given a per-repo wip_cap of 2
  And three work-items at status `active`
  And exactly one of them holds a dispatch lock whose recorded pid is live
  And the other two reached a green terminal outcome and were reclaimed
  And every dispatch journal is readable
  When the Dispatcher evaluates admission for an admission-eligible ready item
  Then the counted claim total is 1
  And the ready item is admitted
  And no admission has exceeded the per-repo WIP cap
```

## Scenario 59 — The hand-picked operator override admits over the cap

```gherkin
Feature: The per-repo WIP cap binds the enforcing paths, not the operator override
  As an operator
  I want a hand-picked dispatch to proceed when I have named one work-item
  So that a saturated cap cannot block a deliberate single dispatch

Scenario: A targeted dispatch is admitted at the cap while an unattended drain admits nothing
  Given a per-repo wip_cap that is already met by counted claims
  And an admission-eligible ready work-item
  When an unattended drain evaluates admission
  Then no work-item is admitted
  And the refusal reports a capacity deferral
  When the operator instead dispatches that same work-item by name through the non-enforcing path
  Then that work-item is admitted
  And the admission is not reported as a violation of the per-repo WIP cap
```

## Scenario 92 — Dry-run reports why a ready item was not picked

```gherkin
Feature: A dry-run's exclusion report distinguishes "would be dispatched"
  from "was ruled out, and why", so a silent absence never reads as "the
  selector never saw this item"

Scenario: A dry-run over a mixed candidate set reports the picks and the exclusions
  Given a ready set exceeding the budget
  And one ready item carrying an open blocking dependency
  When `loop --dry-run --json` runs
  Then the selection carries the picked identifiers
  And the exclusion report names each unpicked ready item exactly once with
    its governing reason
  And the item with the open blocking dependency is reported excluded for
    that reason, not for the budget
```

## Scenario 93 — The janitor-bootstrap step resolves a declared hook-install recipe and falls back to a declared default

```gherkin
Feature: The janitor-bootstrap step's integration point is what the
  governed repository DECLARES, so an adopter satisfies it by declaration
  rather than by adopting the fleet toolchain

Scenario: A declared recipe is resolved and re-verified
  Given a governed repository whose committed `dispatcher.janitor_bootstrap.recipe`
    names a hook-install command that is present and invokable
  When the pre-dispatch re-verification of the janitor-bootstrap integration point runs
  Then it resolves the declared recipe and observes it provided
  And it journals a clearing record for any prior degraded janitor-bootstrap outcome

Scenario: An undeclared key falls back to the fleet default convention
  Given a governed repository that declares no `dispatcher.janitor_bootstrap` key
  When the pre-dispatch re-verification runs
  Then the recipe is resolved against the fleet default convention `just install-commit-refuse-hooks`

Scenario: An unresolvable recipe refuses and names the attempted resolution
  Given a governed repository whose declared or default hook-install recipe is unresolvable
  When the pre-dispatch re-verification runs
  Then the dispatch is refused rather than proceeding unchecked
  And the refusal names which resolution was attempted, declared or default, and the key that declares it

Scenario: An adopter with no recipe satisfies the step through a waiver
  Given an adopter repository that provides no hook-install recipe of any kind
  When it carries a committed `janitor-bootstrap` step waiver
  Then the step proceeds as a journaled waived proceed
  And the adopter is not required to adopt the fleet toolchain to dispatch
```

## Scenario 94 — A provider's availability claim does not extend an exhaustion record's expiry

```gherkin
Feature: No claim a provider makes about its own future availability is
  authoritative, whatever form it takes and whether or not one is offered at
  all, so it must not extend how long the Dispatcher refuses to admit against
  that provider

Scenario: A provider's availability claim does not become the expiry
  Given a dispatch fails with a typed provider usage-limit condition
  And the provider's refusal carries a claim about when it becomes available again
  When the Dispatcher mints the observed-exhaustion record
  Then the record's expiry is the bounded default and NOT the provider's claimed instant
  And the provider's claim is recorded as unverified provenance rather than as an observation

Scenario: No availability claim at all still yields the bounded default
  Given a dispatch fails with a typed provider usage-limit condition
  And the provider's refusal carries no claim about when it becomes available again
  When the Dispatcher mints the observed-exhaustion record
  Then the record's expiry is the bounded default
  And this holds the same way for a commercial vendor, a different account with that vendor, or a self-hosted or free model

Scenario: A later matching node execution expires only the matching record early
  Given the Dispatcher holds an unexpired domain or candidate availability record
  When a node attempt begins after the observation and succeeds against the same domain or exact candidate identity
  Then only the matching older record is expired even though its recorded expiry has not been reached
  And a re-dispatched run's success on a fallback candidate does not clear the held primary
```

## Scenario 95 — Dispatch admission surfaces plugin-currency staleness rather than blocking on it

```gherkin
Feature: Dispatch admission surfaces plugin-currency staleness rather than blocking
  on it, so a release published mid-session never refuses a live session's dispatch,
  while a deliberate operator floor still refuses fail-closed

  Scenario: A release published after session start does not refuse a dispatch from the provisioned build
    Given a session whose executing dispatcher build was the latest release when the session started
    And a newer release is published before the session dispatches
    And no dispatcher.minimum_release floor is configured
    When the Dispatcher admits a ready work-item
    Then the dispatch is not refused on plugin-currency grounds
    And no blocking plugin-currency refusal is journaled
    And a non-blocking dispatcher-currency-staleness fact surfaces that the provisioned build lags the latest release

  Scenario: A deliberate release floor refuses a below-floor dispatch fail-closed
    Given a committed dispatcher.minimum_release floor
    And an executing release below that floor
    When the Dispatcher admits a ready work-item
    Then the dispatch is refused fail-closed with an actionable diagnostic naming the floor

  Scenario: Unobservable currency is recorded as undetermined and does not refuse
    Given the executing build identity or the available release cannot be determined
    When the plugin-currency check runs at dispatch admission
    Then it records that currency could not be determined
    And it does not refuse the dispatch on currency grounds
```

## Scenario 96 — Each governed-repo integration point resolves from a committed declaration, with a fleet default only where one exists

```gherkin
Feature: The janitor check-suite and janitor-core provisioning resolve from what the
  repository DECLARES, running a declared command verbatim; a truly absent key falls back
  to the fleet default only on a field that has one, while a required field with no safe
  default — the janitor-core pinned ref — refuses on absence, so a member and an adopter
  consume the orchestrator identically

  Scenario: A declared janitor check-suite runs verbatim with no wrapper imposed
    Given a governed repository that declares dispatcher.janitor.check_suite as a plain-shell command
    When the post-merge janitor resolves its check-suite invocation
    Then the declared command is invoked verbatim
    And no mise-exec or other tool wrapper is prepended to it

  Scenario: An absent janitor check-suite key resolves to the fleet default convention
    Given a governed repository that declares no dispatcher.janitor.check_suite key
    When the post-merge janitor resolves its check-suite invocation
    Then resolution uses the fleet default convention

  Scenario: A present-but-null janitor check-suite declaration refuses rather than sliding onto the default
    Given a governed repository whose dispatcher.janitor.check_suite key is present but names nothing
    When the janitor-check-suite integration point resolves
    Then the dispatch is refused
    And the refusal names the key and states which resolution was attempted

  Scenario: A committed check-suite declaration is not displaced by the per-invocation override
    Given a governed repository that declares dispatcher.janitor.check_suite
    And a per-invocation --janitor override is supplied
    When the janitor resolves its check-suite invocation
    Then the committed declaration is used, not the per-invocation override

  Scenario: An absent janitor-core pinned declaration refuses rather than silently substituting a moving tip
    Given a governed repository whose compat.pinned declaration is absent or unreadable
    When the janitor resolves the livespec-core clone ref
    Then janitor-core provisioning is a journaled degraded or refused outcome naming the missing declaration
    And it does not silently fall through to a bare moving master or main tip

  Scenario: A declared core ref is honored as declared, including bootstrap master
    Given a governed repository that declares compat.pinned as master during bootstrap
    When the janitor resolves the livespec-core clone ref
    Then the declared value is honored as the repository's explicit choice
    And it is not treated as the forbidden silent default

  Scenario: A present-but-unusable core repository declaration refuses rather than sliding onto the fleet default
    Given a governed repository whose compat.core_repo declaration is present but unusable
    When the janitor resolves the livespec-core clone repository
    Then the dispatch is refused naming the key
    And it does not slide onto the fleet default core repository
```

## Scenario 97 — One up-front validation pass refuses pre-dispatch with the complete unmet list and no silent degrade

```gherkin
Feature: A single validation pass over every governed-repo integration point refuses the
  dispatch before any merge or factory run, enumerating every unmet point at once, so no
  integration premise is discovered one broken dispatch at a time or strands a merged item

  Scenario: The validation pass enumerates every unmet integration point in one pre-dispatch refusal
    Given a governed repository missing two required integration points
    When the Dispatcher runs the up-front integration-contract validation pass at first dispatch
    Then the dispatch is refused as a pre-dispatch precondition error before any merge or factory run
    And the refusal enumerates both unmet points, not the first alone

  Scenario: A fleet-member repository with no declarations passes the validation pass unchanged
    Given a fleet-member repository that declares none of the integration keys
    When the Dispatcher runs the up-front integration-contract validation pass
    Then every point resolves to its fleet default and the pass admits the dispatch

  Scenario: A plugin upgrade that adds an expectation fails fast rather than stranding a mid-pipeline item
    Given an upgraded plugin build that adds a new integration-point expectation
    And a repository that has not yet declared or satisfied it
    When the Dispatcher runs the validation pass
    Then it refuses fast naming the new point
    And an already-admitted mid-pipeline item is not stranded on the newly added expectation

  Scenario: A silent-degrade factory-sandbox premise is disallowed
    Given a factory-sandbox toolchain premise that is neither declared-and-validated nor ratified-as-no-op
    When the dispatch path reaches that premise for an adopter that lacks it
    Then behavior does not silently diverge from a member's
    And the premise is surfaced as an unmet validation point rather than degrading silently
```

## Scenario 98 — The post-merge and reconcile janitor venue is the merged default-branch tip

```gherkin
Feature: The post-merge and reconcile janitor provisions its checkout at the default-branch
  tip that contains the item's merge, not the historical merge sha, so a post-merge
  environment fix clears historical items while the venue still proves the merge is present

  Scenario: A post-merge environment fix clears an item merged before the fix landed
    Given an item merged before a janitor-environment fix landed on the default branch
    When the reconcile-merged janitor provisions its venue at the current default-branch tip
    Then the venue contains both the item's merge and the later environment fix
    And the janitor clears the item without a per-invocation override

  Scenario: A venue tip that does not contain the merge is a degraded post-merge outcome
    Given a resolved default-branch tip that does not contain the item's merge
    When the janitor prepares its venue for that item
    Then the janitor records a degraded post-merge outcome carrying the missing point and remedy
    And it does not silently proceed against the tip that lacks the merge
```

## Scenario 99 — Empty-diff acceptance integrity: a zero-change merge is ungradeable, not delivered

```gherkin
Feature: A merged run that changed no files must not grade as delivered,
  so a zero-change merge parks NEEDS_ATTENTION on the empty-diff evidence leg
  while a real-change merge and a declared change-optional item are unaffected

  Scenario: A real-change merge still grades normally
    Given a merged work-item whose effective acceptance criteria are change-implying
    And the merged diff changes one or more files
    When the post-merge acceptance pass judges the merged diff
    Then the merged-diff leg is observed and gradeable
    And the pass MAY reach PASS on observed evidence exactly as before

  Scenario: A zero-change merge parks NEEDS_ATTENTION on the empty-diff leg
    Given a merged work-item whose effective acceptance criteria are change-implying
    And the merged diff changes zero files
    When the post-merge acceptance pass judges the merged diff
    Then the merged-diff leg is resolved ungradeable because it is empty
    And the verdict is NEEDS_ATTENTION and never PASS
    And the verdict is never NO_CHANGE_NEEDED, because an empty diff is not the observed already-present-or-superseded evidence that verdict requires
    And the item parks in acceptance as exactly one attention item whose summary names the empty-diff evidence leg

  Scenario: A file-scoped check that matched zero files reports vacuity, not success
    Given a file-scoped janitor check under judgment over a diff
    And the check's file scope matched zero files in that diff
    When the check reports its outcome
    Then the outcome is a distinct vacuous-match outcome, not a pass
    And a gate does not count the vacuous-match outcome toward passing
    And a gate does not count the vacuous-match outcome toward failing

  Scenario: A declared change-optional item with an empty diff is not misclassified
    Given a merged work-item explicitly declared change-optional
    And the merged diff changes zero files
    When the post-merge acceptance pass judges the merged diff
    Then the empty-diff refusal does not fire
    And the item grades on its normal path
    And the acceptance journal records the change-optional classification it used
```

## Scenario 100 — The repository integration contract resolves once and projects identically to every seam

```gherkin
Feature: Every governed-repo integration point is a field of one typed schema, read by one
  resolver into a Declared, FleetDefault, or Defective result, resolved once on the host and
  projected into every seam, so no seam re-derives a value and no default can hide a defect

  Scenario: The host janitor and the in-sandbox gate render the same resolved check-suite
    Given a governed repository declaring dispatcher.janitor.check_suite
    When the Dispatcher builds the dispatch plan
    Then the contract is resolved exactly once into a journaled ResolvedIntegrationContract
    And the host janitor argv and the in-sandbox gate input both render that resolved value

  Scenario: A present-but-unusable key resolves to Defective and no seam receives a default
    Given a governed repository whose compat.core_repo key is present but unusable
    When the generic resolver reads the contract
    Then the point resolves to Defective naming the key and reason
    And no seam receives a fleet-default value in its place

  Scenario: An absent key on a required field resolves to Defective, not to a default
    Given a governed repository whose compat.pinned key is absent
    And the schema declares compat.pinned as a required field with no fleet default
    When the generic resolver reads the contract
    Then the point resolves to Defective naming the absence
    And no moving branch tip is substituted in its place

  Scenario: Prompt variables and prepare-step parameters are projections of the resolved contract
    Given a journaled ResolvedIntegrationContract for a dispatch
    When the node prompts and the sandbox prepare steps are rendered
    Then every integration value they carry is read from that resolved object
    And none of them re-derives a value from configuration or a literal

  Scenario: A workflow token without a rendered input fails the seam-equivalence check
    Given the implement-work-item workflow references an inputs token the Dispatcher does not render
    When the CI seam-equivalence check runs
    Then the check fails naming the unmatched token

  Scenario: A rendered input without a workflow token fails the seam-equivalence check
    Given the Dispatcher renders an input the implement-work-item workflow never references
    When the CI seam-equivalence check runs
    Then the check fails naming the unconsumed input

  Scenario: A token in a position neither resolver handles fails the seam-equivalence check
    Given the implement-work-item workflow places an inputs token in a position neither the engine renders nor the Dispatcher's overlay substitutes
    When the CI seam-equivalence check runs
    Then the check fails naming the token and its unresolved position

  Scenario: A token in a prepare-step position is admitted with the overlay recorded as its resolver
    Given the implement-work-item workflow places an inputs token in a run.prepare step position the Dispatcher's overlay substitutes host-side
    When the CI seam-equivalence check runs
    Then the check admits the position and records the overlay as its resolver

  Scenario: An overlay-resolved position whose host-side substitution was removed fails the check
    Given an inputs token in a position previously resolved by the overlay
    And the Dispatcher no longer substitutes that position host-side
    When the CI seam-equivalence check runs
    Then the check fails naming the position and the missing host-side substitution
```

## Scenario 101 — A schema-version mismatch refuses pre-dispatch with every defective point enumerated

```gherkin
Feature: Contract version is schema version, so a build that requires a newer contract than a
  repository declares refuses fast and completely rather than stranding a mid-pipeline item

  Scenario: A newer required contract version refuses pre-dispatch enumerating every defective point
    Given an executing plugin build that requires a contract schema version adding two integration points
    And a repository whose declaration satisfies neither
    When the Dispatcher validates the declaration at first dispatch
    Then the dispatch is refused as a pre-dispatch precondition error
    And the refusal enumerates both defective points in one message

  Scenario: An already-admitted item is not stranded by a later build's new expectation
    Given a mid-pipeline item admitted under an earlier contract version
    When a newer build adding an expectation takes over
    Then the in-flight item is not stranded on the new expectation
```

## Scenario 102 — Members-and-adopters-identical is a failing test

```gherkin
Feature: An adopter fixture with zero fleet tooling and a fleet-toolchain literal ban make
  an undeclared fleet premise fail in CI instead of in an adopter's production

  Scenario: The adopter fixture passes every dispatch-path seam test with zero fleet tooling
    Given the committed adopter fixture declaring its integration points only through the contract schema
    When every dispatch-path seam test runs parametrized over the adopter fixture
    Then every seam test passes with no fleet tooling present

  Scenario: The member fixture passes the same tests on fleet defaults
    Given the committed fleet-member fixture declaring no integration keys
    When the same seam tests run parametrized over the member fixture
    Then every seam test passes on fleet defaults

  Scenario: A reintroduced fleet-toolchain literal fails the gate and the adopter leg
    Given a change adding a fleet-toolchain literal outside the fleet-defaults module
    When just check runs
    Then check-no-fleet-toolchain-literals fails naming the literal
    And the adopter-fixture leg of the affected seam test fails
```

## Scenario 103 — A needs-human outcome terminates the run and routes the decision to the ledger

```gherkin
Feature: The ledger is the only human gate
  As a maintainer running an unattended factory
  I want a needs-human outcome to end the run and rest the item in the ledger
  So that no factory run ever holds a slot waiting for me

  Scenario: A needs-human outcome inside a run
    Given a factory run whose loop cannot auto-resolve the work-item
    When the run reaches its needs-human outcome
    Then the run preserves its work by reference before terminating
    And the run terminates non-green without entering a human-input-required state
    And the Dispatcher rests the work-item at blocked with blocked_reason needs-human
    And the dispatch reports exit code 4
    And no interactive human-decision node exists in the workflow
```

## Scenario 104 — An item closed by any route releases its non-terminal run

```gherkin
Feature: Run-inventory reconciliation
  As a maintainer
  I want a run that outlives its work-item reconciled without my intervention
  So that a hand-implemented or re-dispatched item never leaves a run behind

  Scenario: The item leaves active while its run is non-terminal
    Given a non-terminal run on a declared factory attributed to a work-item
    And that work-item has left active by any route, including a hand close with no Dispatcher process alive
    When reconciliation runs on the loop tick, the dispatch preamble, or the standalone sweep
    Then the Dispatcher exports the run's record and reads the export back
    And only then terminates the run
    And journals one reconciliation record naming the run id, factory, status kind, item, item status, orphan reason, and termination route
    And the work-item's status, blocked_reason, and labels are unchanged

  Scenario: A live run under a matching claim is not an orphan
    Given a running run whose work-item is active and whose journaled run id is that run
    And no Dispatcher process is watching it
    When reconciliation runs
    Then the run is not terminated

  Scenario: An item superseded by a newer dispatch
    Given two non-terminal runs attributed to one active work-item
    And the ledger's newest journaled run id names the second run
    And the item's claim carries a run stamp naming the second run, not a pending stamp
    When reconciliation runs
    Then the first run is reconciled with orphan reason superseded-run
    And the second run is left alone
```

## Scenario 105 — A parked run past its grace period is exported and abandoned, and its item is untouched

```gherkin
Feature: Bounded slot hold for a legacy or foreign parked run
  As a maintainer sharing a factory with other workflows
  I want a run parked in a human-input-required state to release its slot after a bounded grace period
  So that an unattended pool cannot be strangled by parked runs

  Scenario: A parked run with a live item
    Given a run in a human-input-required state whose work-item is blocked with blocked_reason needs-human
    And the run has been parked longer than dispatcher.blocked_run_grace_seconds
    When reconciliation runs
    Then the Dispatcher exports the run's record and reads the export back
    And answers the run's own abandon option so the run terminates
    And the work-item remains blocked with blocked_reason needs-human
    And the reconciliation is journaled

  Scenario: A parked run inside its grace period
    Given a run in a human-input-required state parked for less than dispatcher.blocked_run_grace_seconds
    When reconciliation runs
    Then the run is not terminated
```

## Scenario 106 — Reconciliation addresses every declared factory by its server target

```gherkin
Feature: Reconciliation reads the right pool
  As a maintainer dispatching to remote factories
  I want reconciliation to query each declared factory explicitly
  So that a clean empty answer from the wrong pool is never mistaken for a reconciled one

  Scenario: Two declared factories, one unreachable
    Given dispatcher.factories declares two factories
    And one of them is unreachable
    When reconciliation runs
    Then each factory is queried by its declared server target
    And the unreachable factory produces a journaled reconciliation error
    And reconciliation of the reachable factory completes
```

## Scenario 107 — An adopter's declared merge strategy projects to both the argv and the prompt

```gherkin
Feature: Merge strategy is a typed integration-contract field
  As the maintainer of an adopter repository that merges by squash
  I want the declared merge strategy to drive both the auto-merge argv and the prompt
  So that I never fork the workflow to change how my items land

  Scenario: An adopter declares squash
    Given a governed repository whose declaration sets dispatcher.merge_mode to squash
    When the Dispatcher resolves the integration contract at plan build
    Then the resolved merge strategy is squash
    And the projected gh pr merge argv names the squash method
    And the scripted publication command uses the squash merge method

  Scenario: A fleet member declares nothing
    Given a governed repository whose declaration omits dispatcher.merge_mode
    When the Dispatcher resolves the integration contract at plan build
    Then the resolved merge strategy is the fleet default rebase

  Scenario: An unsupported merge method is defective
    Given a governed repository whose declaration sets dispatcher.merge_mode to a value outside rebase and squash
    When the Dispatcher validates the declaration before dispatch
    Then the merge strategy point resolves to Defective naming dispatcher.merge_mode
    And the dispatch is refused as a pre-dispatch precondition error
```

## Scenario 108 — A governed repository's commit-blocking hook honors the resolved sandbox-exemption marker

```gherkin
Feature: The sandbox commit-refuse exemption marker is a typed integration-contract field
  As the maintainer of a governed repository dispatched to the factory
  I want the sandbox-exemption marker set and honored through the contract
  So that a fresh-clone sandbox can make its Red-Green-Replay commits

  Scenario: The orchestrator sets the resolved marker in the sandbox
    Given a governed repository whose declaration omits dispatcher.sandbox_exempt_marker
    When the Dispatcher resolves the integration contract at plan build
    Then the resolved marker key is the fleet default livespec.sandboxExempt
    And the sandbox prepare step sets that marker to true as a projection of the field

  Scenario: The adopter fixture's commit-blocking hook honors the marker
    Given the adopter fixture carrying a commit-blocking hook and a sandbox-shaped checkout with the resolved marker set to true
    When a Red-Green-Replay commit is attempted
    Then the commit-blocking hook does not refuse it on primary-checkout grounds
    And the Red-Green-Replay gates still run

  Scenario: An adopter fixture whose hook ignores the marker fails
    Given the adopter fixture mutated so its commit-blocking hook ignores the resolved marker
    When the parametrized dispatch-path seam test runs against that fixture
    Then the sandbox-exemption obligation fails on the adopter leg
```

## Scenario 109 — Every epic carries a canonical, tenant-unique `plan_slug`

```gherkin
Feature: plan_slug is the plan identity on every epic
  As a consumer of the ledger
  I want every epic to carry one canonical tenant-unique plan_slug
  So that a plan is resolvable by its handle from any tool

  Scenario: an epic without a slug is reported
    Given a tenant holding an epic whose metadata has no plan_slug
    When the armed plan-record conformance checks run
    Then plan_slug_present reports that epic id with an error verdict
    And the remediation names the canonicalization the slug must satisfy

  Scenario: a duplicated slug is reported on both epics
    Given two epics in one tenant both carrying plan_slug "shared-topic"
    When the checks run
    Then plan_slug_unique reports both epic ids with an error verdict

  Scenario: a non-epic carrying plan_slug is reported while a tenant-qualified plan_ref is accepted
    Given a task carrying plan_slug "some-plan"
    And a bug carrying plan_ref "livespec-orchestrator-beads-fabro/console-control-plane-primitives" that is not a child of that epic
    When the checks run
    Then plan_slug_on_non_epic reports the task and does not report the bug

  Scenario: the front-end and capture routes both write the slug
    Given a plan opened through the plan front-end with slug "alpha-topic"
    And an epic filed through capture-work-item with title "Beta Topic!" and no slug supplied
    When each epic is read from the ledger
    Then the first carries plan_slug "alpha-topic"
    And the second carries plan_slug "beta-topic"

  Scenario: a non-canonical slug is reported
    Given an epic carrying plan_slug "Not_Canonical Slug" that is not equal to its own canonicalization
    When the checks run
    Then plan_slug_canonical reports that epic id with an error verdict
```

## Scenario 110 — The `associated_work_item_id` anchor matches its epic in both directions

```gherkin
Feature: the plan directory and its epic point at each other
  As a maintainer resuming a plan from either side
  I want the directory anchor and the epic slug to agree
  So that neither side can silently drift from the other

  Scenario: a plan opened through the front-end is anchored with the epic id
    Given the plan front-end opens slug "gamma"
    When the plan store is inspected immediately after creation
    Then plan/gamma/associated_work_item_id exists holding exactly the new epic's id on one line
    And no epic.md, handoff.md, or other metadata file is created

  Scenario: a directory whose anchor names the wrong epic is reported
    Given plan/delta/associated_work_item_id holding the id of an epic whose plan_slug is "epsilon"
    When the armed checks run
    Then plan_anchor_consistent reports plan/delta/ with an error verdict

  Scenario: an epic whose slug names a directory anchored elsewhere is reported
    Given an epic with plan_slug "zeta" and a directory plan/zeta/ whose anchor names a different epic
    When the checks run
    Then plan_anchor_consistent reports the epic id and the directory path

  Scenario: unassigned is accepted only while no epic carries the slug
    Given plan/eta/associated_work_item_id holding unassigned and no epic carrying plan_slug "eta"
    When the checks run
    Then no check reports plan/eta/
    And when an epic is then filed carrying plan_slug "eta" and the checks run again
    Then plan_anchor_consistent reports plan/eta/ as unassigned while an epic carries its slug

  Scenario: a missing or malformed anchor is reported
    Given plan/theta/ with no anchor file
    And plan/archive/iota/associated_work_item_id holding two lines
    When the checks run
    Then plan_anchor_present reports both paths with an error verdict
```

## Scenario 111 — Typed `next_action` drives an unattended resume and cannot be truncated by wrapping

```gherkin
Feature: the next action is typed epic metadata
  As the overseer or console resuming a plan without a person present
  I want the next action read from a typed field
  So that a wrapped sentence in a comment can never delete a constraint or a route

  Background:
    Given each impl or spec-op pointer below has an observable required_result and an unexpired budget
    And human and none pointers carry explicit null required_result and budget fields
    And the existing lifecycle and authorization checks still apply

  Scenario: an impl next_action executes as a drive action
    Given an open epic with a live plan directory whose next_action is kind "impl", ref "bd-ib-w3nwz5.1", text "Dispatch b1 through the factory."
    When the plan operation resumes under LIVESPEC_PLAN_UNATTENDED
    Then resume_directive returns ask false and the action impl:bd-ib-w3nwz5.1
    And no handoff comment body is parsed for a marker line

  Scenario: a human next_action raises the picker with its kind as the reason
    Given the same epic with next_action kind "human", empty ref, text "Confirm the anchor filename with the maintainer."
    When the plan operation resumes unattended
    Then resume_directive returns ask true
    And the reason names kind human

  Scenario: a wrapped prose next action no longer decides anything
    Given the same epic with next_action kind "impl", ref "overseer-adclcd.6"
    And a newest handoff comment whose prose next-action line wraps after the word "the"
    When the plan operation resumes unattended
    Then the action taken is impl:overseer-adclcd.6 in full
    And plan_next_action_drift may warn about the comment but no check reports an error

  Scenario: a handoff write updates next_action in the same call
    Given a session appends a handoff naming the next step
    When append_handoff returns
    Then the epic's next_action and last_session reflect that call
    And the handoff comment remains an append-only entry on the timeline

  Scenario: a missing or ill-typed next_action is reported
    Given an open epic with a live plan directory and no next_action
    And another whose next_action has kind "none" and a non-empty ref
    When the armed checks run
    Then plan_next_action_typed reports both epic ids with an error verdict
```

## Scenario 112 — The one-shot anchor migration is complete and idempotent

```gherkin
Feature: existing plans satisfy the new contract before the checks arm
  As the maintainer arming the plan-record checks on a family tenant
  I want one migration to write every missing slug, anchor, and next_action
  So that no existing plan fails the moment enforcement starts

  Scenario: the migration writes anchors from existing slugs
    Given a tenant whose epics carry plan_slug values and whose repository holds plan/<slug>/ and plan/archive/<slug>/ directories with no anchor files
    When the migration runs
    Then every directory whose name matches an epic's plan_slug holds that epic's id in associated_work_item_id
    And every directory with no matching epic holds unassigned
    And the report lists each path written

  Scenario: the migration derives missing slugs and refuses collisions
    Given an epic with no plan_slug whose spec commitment hint is "plan:kappa"
    And an epic with no plan_slug whose title canonicalizes to a slug another epic already carries
    When the migration runs
    Then the first epic gains plan_slug "kappa"
    And the second is reported as refused with both epic ids and left unwritten

  Scenario: the migration seeds next_action from the newest handoff
    Given an open plan-anchored epic whose newest handoff records exactly one next action naming impl:bd-ib-ott6
    And another whose newest handoff records a next action in prose naming no work-item
    And a third with no handoff at all
    When the migration runs
    Then the first epic's next_action is kind impl with ref bd-ib-ott6
    And the second's is kind human carrying the recorded text
    And the third's is kind none
    And each carries last_session naming the migration

  Scenario: a second run changes nothing
    Given the migration has run once on a tenant
    When it runs again
    Then it reports zero writes
    And every anchor file, plan_slug, and next_action is byte-identical to the first run's result
```

## Scenario 113 — A plan epic closed without completeness-review evidence is reported

```gherkin
Feature: the after-the-fact closure gate is a conformance check, not only an operation
  As a maintainer auditing a tenant's plans
  I want an epic closed by any route without completeness-review evidence to be reported
  So that the archive gate's second leg is enforced even when the plan operation did not perform the close

  Scenario: a closed plan epic lacking evidence is reported
    Given an epic whose plan_slug names a live or archived directory
    And the epic is closed with no completeness-review evidence comment on its timeline
    When the armed plan-record conformance checks run
    Then plan_close_evidence reports that epic id with an error verdict

  Scenario: a closed plan epic carrying evidence is not reported
    Given an epic whose plan_slug names an archived directory
    And the epic is closed with a completeness-review evidence comment on its timeline
    When the checks run
    Then plan_close_evidence does not report that epic

  Scenario: an open plan epic is out of scope for the closure check
    Given an open epic whose plan_slug names a live directory and carries no completeness-review evidence
    When the checks run
    Then plan_close_evidence does not report that epic
```

## Scenario 114 — The `context` read primitive assembles a deterministic item-context envelope

```gherkin
Feature: context deterministically assembles an item's full context envelope
  As a maintainer or the console chat pane resuming work
  I want one query-only primitive that assembles an item's full context
  So that a session can resume a plan from the envelope alone

  Scenario: context --json on an epic id populates every envelope field
    Given a fixture tenant with a plan epic carrying comments, children, dependency edges, a typed next_action, and a linked research directory
    When context --json runs for that epic id
    Then the emitted envelope populates the epic, comments, children, dependencies, next_action, research, and spec fields

  Scenario: context --json on a child work-item id emits the same envelope shape
    Given the fixture tenant has a child work-item under that epic
    When context --json runs for the child work-item id
    Then the emitted envelope carries the same field shape as for the epic

  Scenario: context is deterministic and side-effect-free
    Given an unchanged fixture tenant
    When context --json runs twice for the same id
    Then the two emitted envelopes are byte-identical
    And the work-items store is unmodified

  Scenario: context on an unknown id fails naming the missing key
    Given a fixture tenant that has no item with the queried id
    When context --json runs for that id
    Then it fails with a not-found error naming the missing key
    And it does not emit an empty envelope
```

## Scenario 115 — `discuss-work-item` stands by over the context envelope and resumes without chat history

```gherkin
Feature: discuss-work-item is the heavyweight interactive stand-by skill over the context loader
  As a maintainer driving day-to-day work
  I want an interactive skill that assembles context and stands by
  So that it drives only on explicit instruction and resumes from the envelope alone

  Scenario: the skill assembles its subject through the context primitive
    Given a fixture tenant with a plan epic
    When discuss-work-item opens for that epic
    Then it assembles the item context through the context primitive

  Scenario: the skill resumes a plan from the envelope alone
    Given the context envelope for a live plan epic
    When discuss-work-item resumes from that envelope with no chat history
    Then it recovers the plan's next action and current facts from the envelope alone

  Scenario: the skill records a maintainer ruling as a scope event
    Given an open discuss-work-item session over a plan epic
    When the maintainer states a ruling
    Then the skill records the ruling as a plan scope event through the Planning Lane primitives

  Scenario: the skill drives a lifecycle action only on explicit instruction
    Given an open discuss-work-item session over a plan epic
    When the maintainer gives an explicit instruction to drive a lifecycle action
    Then the skill drives that action
    And when the request is implicit or ambiguous the skill stands by and asks for explicit confirmation instead of driving

  Scenario: the skill is registered under the non-colliding name
    Given the plugin's skill registry
    When the discuss-work-item skill is enumerated
    Then it is registered under the name discuss-work-item and not under the name plan
```

## Scenario 116 — An operator retires an exhaustion record before its expiry

```gherkin
Feature: An operator can clear an exact scoped or legacy exhaustion record they know is stale
  As a factory operator
  I want to clear an exhaustion record I know is stale
  So that a provider I have just restored is not held out for a wait sized for someone else's rate limit

Scenario: An operator clearance retires an exact scoped record and admission resumes
  Given an unexpired candidate-scoped record naming an availability key and candidate key
  When the operator clears that exact scope and key with a stated reason and an asserted identity
  Then the clearance is appended to the audit journal carrying the exact record identity, acting identity, time, and reason
  And the original observation record remains readable in the journal
  And the candidate is eligible on the next preflight

Scenario: The legacy provider valve remains scoped to legacy records
  Given an unexpired legacy provider-exhaustion record against provider "codex"
  When the operator clears provider "codex" with a stated reason and asserted identity
  Then the legacy record is retired append-only
  And no current scoped record is cleared by the legacy provider valve

Scenario: A clearance asserting no identity is refused
  Given an unexpired observed provider-exhaustion record against provider "codex"
  When a clearance is attempted by an invocation that asserts no identity
  Then the clearance is refused
  And nothing is appended to the audit journal
  And the record continues to refuse admission for provider "codex"

Scenario: A clearance with no stated reason is refused
  Given an unexpired observed provider-exhaustion record against provider "codex"
  When a clearance is attempted with a blank reason
  Then the clearance is refused
  And nothing is appended to the audit journal

Scenario: A clearance against a provider holding no record is refused
  Given the Dispatcher holds no unexpired exhaustion record for provider "anthropic"
  When a clearance is attempted for provider "anthropic"
  Then the clearance is refused before anything is written
```

## Scenario 117 — Named workflow variants resolve by recorded precedence and refuse before any run

```gherkin
Feature: A dispatch target selects a complete named workflow variant
  As a maintainer whose repository needs a deliberately different Fabro graph
  I want to register the variant by name and select it through recorded configuration
  So that a variant is never an unchecked copy and a retry never silently changes graph

  Scenario: An explicit workflow name wins
    Given a dispatch target whose dispatcher.workflows registers a variant named fast
    And dispatcher.default_workflow names implement-work-item
    When a dispatch is made with --workflow-name fast
    Then the committed workflow resolved is the fast variant's directory
    And the work-item's dispatch_workflow metadata records fast
    And the dispatch record carries workflow_name fast beside workflow_toml

  Scenario: A retry reuses the recorded variant
    Given a work-item whose dispatch_workflow metadata records fast
    And fast is still registered
    When the work-item is dispatched again with no --workflow-name
    Then the committed workflow resolved is the fast variant's directory

  Scenario: The configured default applies when nothing more specific chooses
    Given a dispatch target whose dispatcher.default_workflow names a registered variant
    And a work-item with no dispatch_workflow metadata
    When the work-item is dispatched with no --workflow-name
    Then the committed workflow resolved is that variant's directory

  Scenario: The reserved name resolves target-local then bundle
    Given a dispatch target with no dispatcher.workflows table
    When a work-item is dispatched
    Then the committed workflow resolved is the target's own committed implement-work-item workflow when it exists
    And otherwise the plugin payload's bundled workflow

  Scenario: A repository that declares no registry incurs no new obligation
    Given a dispatch target whose .livespec.jsonc carries no dispatcher.workflows and no dispatcher.default_workflow
    When a work-item is dispatched
    Then no registry refusal is evaluated
    And the dispatch proceeds exactly as it did before the registry existed

  Scenario: An unregistered name is refused before any run
    Given a dispatch target whose dispatcher.workflows does not register a variant named missing
    When a dispatch is made with --workflow-name missing
    Then the dispatch is refused before any Fabro run exists
    And the journal stage names the unregistered variant

  Scenario: An incomplete variant directory is refused before any run
    Given a registered variant whose directory lacks workflow.fabro
    When a dispatch selects that variant
    Then the dispatch is refused before any Fabro run exists
    And the journal stage names the missing file

  Scenario: No environment variable selects the variant
    Given an environment variable naming a registered variant
    When a work-item is dispatched with no --workflow-name
    Then the committed workflow resolved ignores the environment variable

  Scenario: A registered variant declares the six ACP nodes
    Given a registered variant whose graph omits the review_fix node
    And the dispatch target's dispatcher.acp_nodes carries a structured entry for the review_fix node
    When a dispatch selects that variant
    Then the dispatch is refused before any Fabro run exists naming the absent node

  Scenario: A registered variant is held to the bundle's seam parity
    Given this repository registers a variant whose graph carries an integration token in a position the engine does not render
    When the CI seam-equivalence check runs
    Then it reports a finding naming that variant's directory
    And the bundle still passes

  Scenario: A registered variant that references fewer inputs than the bundle fails the seam check
    Given this repository registers a variant whose payload references no default_branch input
    When the CI seam-equivalence check runs
    Then it reports the missing token for that variant's directory
```

## Scenario 118 — A groom workflow variant drafts a cut, parks it in the ledger, and files only on a recorded approval

```gherkin
Feature: The groom cut may be drafted by a factory run without a run ever awaiting a human
  As a maintainer who owns the cut
  I want the groom front-end to delegate drafting to a registered groom variant and park the draft in the ledger
  So that the approval stays a ledger act I perform, and later the consensus tier may perform for a first cut, and no run ever pauses on me

  Scenario: The groom dispatch is the only door and the propose phase files nothing
    Given a backlog item that intake routed there as an epic
    And a registered groom workflow variant
    When the groom front-end performs a groom dispatch of the item under that variant
    Then the dispatch is journaled and the item's dispatch_workflow pin names the groom variant
    And the run terminates at a needs-human outcome carrying the drafted slices
    And no slice is filed
    And the item rests at blocked / needs-human with the draft recorded on it as a ledger comment

  Scenario: The Dispatcher never admits a backlog item on its own
    Given a backlog item and a registered groom workflow variant
    When the Dispatcher loop runs with no operator groom dispatch
    Then the item stays at backlog
    And no groom run exists

  Scenario: A human approval files the approved slices on the apply dispatch
    Given an item resting at blocked / needs-human with a drafted cut and a groom-variant pin
    When an operator answers resolve-blocked with ready and an approval
    Then the approval is a ledger comment on the item written before the transition and naming the invoker
    And the item rests at ready for its apply dispatch
    And the admission valve dispatches it under the groom variant, never under implement-work-item
    And the apply dispatch files the approved slices with dependency edges linked
    And every spec-change slice is routed to propose-change rather than the factory
    And the original item closes as regroomed-out
    And every filed slice and the regroomed-out original carry the approval record in a queryable field

  Scenario: Sending the draft back re-drafts and files nothing
    Given an item resting at blocked / needs-human with a drafted cut
    When an operator answers resolve-blocked with backlog
    Then no slice is filed
    And the item rests at backlog for the groom front-end to dispatch again

  Scenario: A filing without an approval record is refused
    Given a drafted cut and no approval record
    When the filing seam is called
    Then the call is refused
    And no slice is filed
    And the original item keeps its status

  Scenario: Until the consensus tier is ratified only a human operator approves
    Given livespec core has not ratified the consensus tier
    And an item resting at blocked / needs-human with a drafted cut
    When no human operator has answered resolve-blocked
    Then the item stays at blocked / needs-human
    And no dispatch applies the draft

  Scenario: The tier approves only where the repository opted in and only a first cut
    Given the consensus tier is ratified with present, fresh and conforming evidence
    And a repository whose dispatcher.groom_cut_approval is consensus
    And a drafted first cut of an item that intake routed to backlog as an epic
    When the tier approves the draft
    Then the approval is recorded as a ledger comment naming the tier as the invoker
    And the apply dispatch files the slices

  Scenario: The re-groom of a bounced item stays a human's
    Given the consensus tier is ratified and the repository opted in
    And an item the Dispatcher bounced to backlog on non-convergence
    When its draft cut awaits approval
    Then the tier does not approve it
    And the draft rests at blocked / needs-human for a human operator

  Scenario: The regroom cap parks a repeatedly sent-back draft for a person
    Given the tier owns approvals for a repository
    And the tier has already sent one item's draft back for re-drafting as many times as dispatcher.automated_regroom_cap allows
    When a further draft is produced for it
    Then the draft rests at blocked / needs-human for a human operator
    And the tier does not approve or send it back again
```

## Scenario 119 — A per-item merge hold publishes the pull request and merges only on release

```gherkin
Feature: A maintainer holds one item's merge without holding its implementation
  As a maintainer who wants an item implemented now and merged in a window I choose
  I want a per-item hold that the factory honors at the pr stage
  So that dispatch and merge stop being one atomic act, and the hold is visible until I release it

  Scenario: The pr stage publishes but arms nothing while held
    Given a ready work-item carrying the merge-hold label
    When the item is dispatched and its run reaches the pr stage
    Then the branch is pushed and the pull request is opened
    And no auto-merge request exists on the pull request
    And the final reply carries MERGE_HOLD=held beside the PR-number line
    And the run terminates green

  Scenario: A held item stays active, holds no slot, is not stranded, and is surfaced once
    Given an active item whose run terminated green with a held pull request
    When the Dispatcher reconciles runs, the admission accounting counts claims, and needs-attention composes its snapshot
    Then the item remains active
    And its green terminal run is reclaimed so the item holds no capacity slot
    And the run is not treated as an orphan
    And no stranded, abandoned, or leaked-claim finding names the item
    And the snapshot carries exactly one attention id for the hold, hygiene:merge-hold:<work-item-id>, naming the pull request and the release valve

  Scenario: Releasing the hold arms the merge from the host without re-dispatch
    Given an active item with an open unmerged pull request and the merge-hold label
    When an operator drives set-merge-hold:<work-item-id>:off
    Then the merge-hold label is removed and the item's status is unchanged
    And auto-merge is armed on the pull request with the merge method journaled with the dispatch that opened it
    And no new dispatch is created
    And the attention row for the hold disappears from the next snapshot

  Scenario: Setting the hold disarms an already-armed pull request
    Given an active item whose pull request has auto-merge armed
    When an operator drives set-merge-hold:<work-item-id>:on
    Then the merge-hold label is written
    And the auto-merge request is removed
    And the item's status is unchanged

  Scenario: The hold is rendered as a per-item policy input resolved before the sandbox runs
    Given a work-item carrying the merge-hold label
    When its dispatch plan is built
    Then the rendered inputs carry merge_hold true beside the other per-item policy inputs
    And the seam-equivalence check classifies merge_hold in the per-item policy-input family and finds it declared by the bundle and by every registered variant

  Scenario: A hold has no repository-level default
    Given a repository whose .livespec.jsonc declares no merge hold key
    When any work-item without the merge-hold label is dispatched
    Then merge_hold renders false
    And the pr stage arms auto-merge exactly as it did before this section existed
```

## Scenario 120 — An idle factory with dispatchable work surfaces its first dispatch

```gherkin
Feature: Idle-factory visibility composes when work is ready and nothing is moving
  As a maintainer whose factory silently sat idle with a full queue
  I want an idle factory surfaced with the dispatch that starts it
  So that an idle repository says so instead of waiting to be noticed by hand

Scenario: The idle-factory fact appears when ready work is dispatchable and nothing holds it back
  Given at least one admission-eligible ready item under the admission valve's non-capacity conditions
  And the single-authority capacity verdict reports zero counted claims for this repository
  And every ACP node potentially reachable in the submitted graph retains an eligible candidate after observed-hold filtering
  When needs-attention composes the snapshot
  Then exactly one hygiene:idle-factory fact appears at high urgency
  And its summary names the count of admission-eligible ready items and the first ranked id
  And its handoff is a drive-kind handoff carrying impl:<first-ranked-id> that drive accepts for that item's state

Scenario: The idle-factory fact clears when any trigger condition fails
  Given the idle-factory fact would otherwise compose
  When a counted claim occupies a slot for this repository
  Then no idle-factory fact appears
  And when instead observed holds exhaust an admission-required ACP chain the idle-factory fact does not appear
  And when instead only a primary is held but its fallback is eligible the idle-factory fact still appears
  And when instead no admission-eligible ready item exists the idle-factory fact does not appear
```

## Scenario 121 — A refused credential probe re-probes on a cadence instead of exiting, and no clock gates it

```gherkin
Feature: A rate-limited credential re-probes rather than parking the loop on a provider clock
  As a maintainer whose factory sat idle after a transient rate limit
  I want the loop to re-probe the credential on a bounded cadence and resume itself
  So that a recovered credential is used promptly and no provider clock claim strands the drain

Scenario: The loop re-probes and resumes on the first usable result, journaling each refusal
  Given a loop invocation whose budget is unspent
  And whose legacy single-candidate path's admission-time credential-usability probe first returns a provider rate-limit refusal
  When the bounded re-probe cadence elapses and a subsequent probe returns usable
  Then the loop resumes normal admission on that first usable result without having exited
  And each refused probe was journaled as exactly one record
  And the refusal's remedy text carried no provider-stated reset instant as a wait-until-clock instruction

Scenario: A usable probe does not retire an unexpired exhaustion record
  Given unexpired observed availability records exhaust an admission-required chain
  And a credential-usability probe that returns usable
  When admission is attempted
  Then admission remains refused by the exhausted chain
  And the records retire only by bounded expiry, matching node execution, or operator clearance

Scenario: A primary probe refusal skips only that candidate when fallback is viable
  Given a fallback-enabled admission-required node whose primary credential probe returns a provider rate-limit refusal
  And the node has an otherwise eligible fallback candidate
  When the Dispatcher evaluates admission
  Then the probe refusal skips the primary for that evaluation only
  And the item is admitted with the fallback selected
  And no durable availability record is minted from the probe
  And the loop does not enter the re-probe wait
```

## Scenario 122 — An attention item's answer disposition governs who may answer it

```gherkin
Feature: A policy gates who may answer a parked-on-a-question attention item
  As a maintainer governing who resolves a blocked/needs-human item
  I want an answer-disposition policy that gates the resolve-blocked answer press
  So that only the actor class I have allowed may answer, and it is visible in the attention snapshot

  Scenario: Under human disposition an automated press is refused and a human press is admitted
    Given a work-item at blocked with blocked_reason needs-human and effective answer disposition human
    When an automated disposition drives resolve-blocked:<work-item-id>:ready with an answer
    Then drive refuses the press
    And the refusal names the work-item and the effective disposition human
    And a human operator's resolve-blocked:<work-item-id>:ready press with the same answer is admitted and lands the answer as a ledger comment

  Scenario: A per-item answer label overrides the global default and binds the advertiser to the enforcer
    Given a global dispatcher.answer_disposition of consensus and a work-item carrying the answer:human label
    When the effective answer disposition is resolved for that item
    Then it is human
    And the needs-attention resolve-blocked lane does not advertise an answer handoff that drive would refuse

  Scenario: The consensus tier behaves as human until livespec core ratifies it
    Given a work-item at blocked with blocked_reason needs-human and effective answer disposition consensus while livespec core has not ratified the consensus tier
    When an automated disposition drives resolve-blocked:<work-item-id>:ready with an answer
    Then drive refuses the press exactly as under the human disposition

  Scenario: needs-attention carries each attention item's effective answer disposition
    Given a blocked work-item whose blocked_reason is needs-human
    When needs-attention composes its snapshot as JSON
    Then the item's attention entry carries its effective answer disposition
```

## Scenario 123 — The ready ordering breaks equal-rank ties by ready-age past the bound

```gherkin
Feature: A starved ready item is selected ahead of newer equal-rank peers
  As the dispatch scheduler
  I want equal-rank ready ties broken by ready-age past a configurable bound
  So that an item nothing ever selects is eventually picked, while rank stays primary

  Scenario: An aged equal-rank item is ordered ahead of a newer one
    Given two ready items of equal rank where one has been ready longer than dispatcher.ready_aging_threshold_hours and the other has not
    When next ranks the candidates and when the Dispatcher composes its drain order
    Then the aged item is ordered ahead of the newer equal-rank item
    And next and the Dispatcher agree on the ordering

  Scenario: Below the bound the id tiebreak holds
    Given two ready items of equal rank where neither has been ready past dispatcher.ready_aging_threshold_hours
    When next ranks the candidates
    Then the id lexicographic tiebreak orders them

  Scenario: An unknowable ready instant keeps the id tiebreak
    Given an equal-rank ready item whose latest transition into ready is unknowable
    When next ranks the candidates
    Then that item retains the id tiebreak and receives no age-based ordering advantage

  Scenario: Rank stays primary across the tiebreak
    Given a higher-rank item and a lower-rank item that has been ready past dispatcher.ready_aging_threshold_hours
    When next ranks the candidates
    Then the higher-rank item is ordered ahead of the lower-rank aged item
```

## Scenario 124 — The human answer lands as a marked ledger comment before the transition, and a poisoned answer is refused

```gherkin
Feature: The answer route writes a marked comment before transitioning and refuses a poisoned answer
  As an operator answering a blocked needs-human item
  I want my answer written as a marked ledger comment before the item transitions, and a poisoned answer refused
  So that the next run reads who answered and a template-opener answer can never poison future goal renders

  Scenario: A clean answer opens with the marker and is written before the transition
    Given an operator presses resolve-blocked for a blocked needs-human work-item with an answer
    And the answer carries no goal-template opening delimiter
    When the press is applied
    Then the ledger comment opens with the livespec-human-answer marker line naming the invoker, its source, the write instant, and the action id
    And the operator's answer follows the marker line verbatim
    And the comment is written before the item's status transition

  Scenario: A poisoned answer is refused with nothing written and no transition
    Given an operator presses resolve-blocked for a blocked needs-human work-item with an answer
    And the answer carries a goal-template opening delimiter
    When the press is evaluated
    Then the answer is refused with nothing written
    And the item stays blocked with no status transition
```

## Scenario 125 — The needs-attention valve item carries the terminated run's account and fails soft

```gherkin
Feature: The resolve-blocked valve item carries the terminated run's account, absorbing an unreachable factory
  As an operator triaging needs-attention
  I want the valve item's summary to carry the terminated run's account, and to survive an unreachable factory
  So that I can see the run's fate without the enrichment ever costing me the valve

  Scenario: The valve summary carries the run account
    Given a blocked needs-human work-item whose factory run terminated on a needs_human outcome
    When needs-attention renders the item's resolve-blocked valve item
    Then the summary carries the run id, the factory name and its server, that a needs_human termination routed the decision to this valve, why it terminated, what the run reported, the preserved reference, and the available actions

  Scenario: An unreachable factory costs the enrichment and never the valve
    Given a blocked needs-human work-item whose factory is unreachable
    When needs-attention renders the item's resolve-blocked valve item
    Then the run account enrichment is omitted
    And the valve item is still surfaced
```

## Scenario 126 — Ledger normalization adopts a beads-native `open` row and assigns it a real rank

```gherkin
Feature: Adoption of a beads-native row assigns it a livespec status and a real rank
  As the Dispatcher's ledger normalization
  I want a row a non-lifecycle writer left `open` or `in_progress` remapped onto its livespec status, with a real rank assigned when none exists
  So that a CI or off-host SSH write ingress, or a raw `bd create`, never leaves a row resting at a non-lifecycle status or sorting by the bottom-sentinel

  Scenario: An `open` row with no rank is adopted into `backlog` and assigned a real rank
    Given a beads issue at the native `open` status whose metadata carries no `rank`
    When ledger normalization runs
    Then the row's status is remapped to `backlog`
    And the row is assigned a real, non-sentinel `metadata.rank` via a single bottom-of-order insert

  Scenario: An `in_progress` row is adopted into `active`
    Given a beads issue at the native `in_progress` status
    When ledger normalization runs
    Then the row's status is remapped to `active`

  Scenario: An `open` row that already carries a real rank keeps it
    Given a beads issue at the native `open` status whose metadata carries a real, non-sentinel `rank`
    When ledger normalization runs
    Then the row's status is remapped to `backlog`
    And its existing `rank` is left unchanged

  Scenario: A `deferred` row is left untouched
    Given a beads issue at the native `deferred` status
    When ledger normalization runs
    Then the row's status is left unchanged
    And no rank is assigned

  Scenario: Every non-lifecycle cadence adopts the same row identically
    Given a beads issue at the native `open` status whose metadata carries no `rank`
    When the dispatch loop, the single-dispatch path, the standalone `ledger-normalize` CLI, or the pre-push `ledger-normalize --gate` mode runs normalization over it
    Then every cadence remaps the row to `backlog` and assigns it the same real, non-sentinel rank outcome
```

## Scenario 127 — Ordered ACP fallback preserves primary resolution and failure honesty, and re-dispatches past a held provider

```gherkin
Feature: Factory-configurable ACP fallback priority
  As a factory operator
  I want each ACP node dispatched to the first eligible candidate, and a provider-limit failure re-dispatched rather than escalated
  So that an exhausted allowance neither stalls the item nor waits on a human

  Scenario: v107 primary bytes survive absent and fallback-only configuration
    Given the review_fix node has no acp_nodes entry and no new-grammar metadata
    When the Dispatcher resolves its adapter
    Then candidate zero is byte-identically the Claude Opus 5 workflow default rendered from the structured built-in default
    And `fallbacks: []` alone produces the same bytes
    And when the review_fix node carries an explicit structured entry, identity-only or fallback-only fields attach after that primary renders

  Scenario: New grammar is version-gated by the release floor, not by an engine fallback capability
    Given a node carries identity, signature, pricing, or a non-empty fallback field
    When dispatcher.minimum_release is below the first release implementing Dispatcher-level fallback
    Then dispatch refuses before claim or run creation
    But a resolved factory server that advertises no fallback-chain capability does not refuse the dispatch

  Scenario: A domain-held primary is skipped and the first eligible candidate is the node's only adapter
    Given a node whose candidate zero is covered by an unexpired domain hold
    And candidate one is not covered
    When the Dispatcher dispatches the item
    Then candidate one's adapter is the only adapter rendered for that node
    And the per-node selection record names candidate one, the full-chain digest, and the hold that skipped candidate zero
    And a selection for a node the run never reaches emits no fallback warning

  Scenario: Shared and distinct identities scope holds across nodes
    Given two nodes repeat the same availability_key and candidate_key pair
    And a third candidate has either key different
    When a candidate-scoped hold is observed
    Then it skips the repeated identity in both nodes
    And it does not skip the third candidate
    And a domain hold covers a candidate when its key equals the candidate availability_key or one of its declared domain-signature hold_keys

  Scenario: Legacy and unidentified adapters retain the conservative v107 posture
    Given an unexpired legacy provider record
    When a built-in candidate carries that provider alias
    Then the legacy record covers that candidate until retirement
    And an identity-less arbitrary legacy adapter is covered by every live legacy record and continues to mint legacy records

  Scenario: Admission requires an eligible candidate for every potentially reachable ACP node
    Given every ACP node potentially reachable in the submitted graph has an eligible candidate
    When the Dispatcher evaluates admission
    Then it admits the item
    And when instead any potentially reachable ACP node has no eligible candidate, the item is not claimed, stays ready, and carries no blocked reason
    And its next admission evaluation is scheduled
    And no human valve is offered as the remedy

  Scenario: A conditional node with every candidate held causes a ready wait without adapter execution
    Given a conditional repair node potentially reachable in the submitted graph
    And every candidate of that node is covered by a live hold
    When the Dispatcher evaluates admission
    Then the item stays ready without a claim or blocked reason
    And no adapter is rendered or started for any candidate covered by a live hold

  Scenario: A provider-limit failure releases the item and re-dispatches it to the next eligible candidate
    Given a dispatched item whose disposition node ran on a codex-acp candidate
    And the run ended at the needs_human terminal after that node failed with "You've hit your usage limit"
    When the Dispatcher derives the run's outcome
    Then it records a domain hold on that candidate's availability key
    And it journals one provider-limit-release record naming the item, run, factory, node attempt, cause, scope, hold key, failed candidate, and recovery source
    And the item returns to ready with no blocked_reason
    And the next dispatch renders disposition with the first eligible candidate in configured order
    And no rework cap budget and no across-dispatch no-progress count is consumed

  Scenario: Restart between each release step completes recovery once
    Given a provider-limit release interrupted after any one of its hold, release record, cost observation, or ledger transition writes
    When the Dispatcher restarts and reconciliation replays the release keyed by factory, run, and failing node attempt
    Then each write is completed exactly once
    And the original hold expiry is not refreshed
    And no cost is duplicated
    And a newer dispatch claim is not released

  Scenario: A failure the Dispatcher cannot classify keeps the human route
    Given a run whose failing node's recorded failure matches no eligible signature
    When the Dispatcher derives the run's outcome
    Then no availability hold or release is recorded
    And the failure retains its existing route
    And an ordinary needs-human outcome still rests at blocked with blocked_reason needs-human

  Scenario: The recorded removed-model diagnostic re-dispatches but a generic 400 does not
    Given the pinned Codex adapter returns the measured ChatGPT-account HTTP 400 diagnostic naming the exact requested model as unsupported
    When the Dispatcher classifies the failing node's recorded failure
    Then it records a candidate-scoped model_unsupported hold and releases the item for re-dispatch
    And the typed provider-usage-limit flag is not set
    But a generic HTTP 400 or 404 with no exact eligible discriminator keeps its original identity and its existing route

  Scenario: Non-eligible failures outrank configured text overlap
    Given a candidate signature whose literals also appear in an authentication failure, exit 127, signal termination, node timeout, sandbox transport fault, compaction 404, or code or test failure
    When classification runs
    Then the non-eligible class mints no hold and is not released for re-dispatch
    And a runtime multi-match with different dispositions is surfaced as ambiguous, non-eligible, and never first-match selected

  Scenario: A re-dispatch recovers the failed run's preserved work
    Given a run released for a provider-limit failure
    When every published-PR resume precondition passes
    Then the Dispatcher invokes resume under its own invoker identity and does not reclaim the publish branch
    And when instead resume is inapplicable, the re-dispatch is a plain dispatch whose sandbox checks out the recorded commit SHA of the preserved work
    And the seed record names the source run, remote, commit SHA, and preservation reference
    And when the preserved reference cannot be read, the Dispatcher waits and retries rather than dispatching from the default branch
    And only a confirmed absence of preserved work permits a plain dispatch from the default branch, with the loss recorded

  Scenario: A third automatic resume falls back to preserved-tree plain dispatch
    Given a released item whose pull request has already anchored two resumes
    When the Dispatcher re-dispatches it
    Then it does not invoke a third resume
    And it dispatches a plain run seeded from the preserved work's recorded commit SHA
    And it inherits no proof from a different head or Definition of Done

  Scenario: An expired hold is re-confirmed by a completed turn before a real dispatch uses the candidate
    Given a domain hold whose bounded expiry has passed
    When the Dispatcher next evaluates an item whose first candidate that hold covered
    Then it runs one availability confirmation turn with that candidate's pinned adapter version, requested model and effort, and projected worker credential identity
    And only a successfully completed prompt turn makes the candidate eligible for the dispatch
    And a refusal with an eligible provider-limit cause records a new hold whose expiry runs from the probe's occurrence time
    And the provider's advertised reset instant neither schedules nor replaces the probe

  Scenario: A timed-out availability probe skips its candidate and permits an eligible fallback
    Given an expired hold on candidate zero of a node whose candidate one is eligible
    When the availability confirmation turn for candidate zero exceeds dispatcher.availability_probe_timeout_seconds
    Then the unfinished probe work is terminated
    And candidate zero is skipped for this evaluation without a new hold
    And candidate one is selected for the node

  Scenario: An unreadable availability source never becomes an empty hold set
    Given the factory-native run records that hold a candidate's availability evidence cannot be read
    When the Dispatcher evaluates admission
    Then that candidate is not treated as confirmed unheld
    And the unavailable source is surfaced and observation is retried on a bounded cadence
    And no needs-human decision is created

  Scenario: Removing a repository-local journal does not erase host-visible holds
    Given a hold observed by a run of another repository on a participating factory
    And this repository's local dispatch journal has been removed
    When this repository's Dispatcher evaluates admission
    Then the hold is reconstructed from the factory-native run records
    And the covered candidate is skipped

  Scenario: A successful fallback still records the failed primary hold and warning
    Given a primary's provider-limit failure recorded a hold and released the item
    And the re-dispatched run executed that node on candidate one
    When the re-dispatched run later succeeds or fails in another node
    Then the occurrence-time-scoped hold, the provider-limit-release record, and the hygiene:model-fallback repository-node fact remain observable
    And overall run success does not clear the primary

  Scenario: Warning clearance is ordered and generation-safe
    Given a model-fallback warning for a primary generation
    When a later dispatch renders the same primary for that node and that node attempt completes successfully
    Then that warning clears even if the overall run later fails
    But an older concurrent attempt, unrelated candidate success, probe, selection for an unreached node, or unreadable node outcome does not clear it
    And a committed primary replacement appends superseded while a fallback-only edit changes only the full-chain digest

  Scenario: Every failed attempt's cost is recorded once
    Given an item released twice for provider-limit failures whose failed runs both emitted nonzero usage, then completed by a third run
    When cost is derived
    Then each released run has one attempt-cost record with a stable identity, priced or marked cost-unobservable
    And the item's cost across the sequence is the sum of those records and the final run's cost, counted once across reconciliation and resume
    And if any included attempt is cost-unobservable the sequence total is unobservable and any displayed subtotal is labeled incomplete
    And only one trailing -YYYYMMDD date suffix is stripped from emitted model identity
    And pricing resolves through the model catalog entry the candidate's identity names first and a per-candidate explicit table second
    And no attempt-cost record yields a gate verdict

  Scenario: Model and effort are set over the protocol and an unadvertised model refuses before the prompt
    Given a selected structured candidate whose agent catalog entry declares the protocol mechanism
    When the Fabro handler opens the session
    Then it sets model and effort through session/set_config_option before the first prompt
    And the agent.acp.started event carries the confirmed model and effort
    But when the agent does not advertise the requested model the candidate terminates typed before any prompt, mints no hold, and is not released for re-dispatch as a provider-limit failure
    And a dispatch whose selected candidates use no protocol mechanism does not require the config_options capability

  Scenario: A first adapter launch failure is released and re-dispatched without a hold
    Given a dispatched item whose unrecovered implement node attempt records an ordinary ACP process exit before the protocol completed, with an explicitly unknown exit code
    And complete attempt-scoped evidence from the run's recorded factory establishes that the prompt boundary was not crossed under the adapter launch evidence rule
    And the attempt carries no provider evidence and matches none of the excluded failure guards
    And the item's preceding dispatch did not end in an adapter launch failure
    And the failed run has verified preserved work at an immutable commit SHA
    When the run terminates at the workflow's needs_human terminal and the ordinary admission valve next admits the item
    Then the journal carries one adapter-launch-release record naming the item, run id, factory, node attempt, executed candidate, exit code or its explicit absence, preceding dispatch, and recovery source
    And one ledger comment on the item names the run id, the factory, the failing node and the exit code or its explicit absence
    And no availability hold is created and no provider-usage-limit flag is set
    And the item returns to ready with no blocked_reason before admission
    And the release consumes no budget of the three rework caps and neither increments nor resets the across-dispatch item count
    And the next run is a plain dispatch seeded from that preserved commit

  Scenario: A repeated adapter launch failure rests for a human
    Given an item whose preceding dispatch ended in an adapter launch failure
    And the current dispatch's unrecovered implement node attempt also fails as an adapter launch failure
    When the run terminates
    Then the item rests at blocked with blocked_reason needs-human
    And its needs-human cause record names both runs and states that a repeated adapter launch failure is not released automatically
    And the terminal neither increments nor resets the across-dispatch item count

  Scenario: An adapter launch release is replayable without affecting a newer claim
    Given an adapter launch release interrupted after its ledger comment was written
    When reconciliation completes that release and later replays it after a newer dispatch has claimed the item
    Then exactly one adapter-launch-release record and one ledger comment exist for that run
    And the newer dispatch claim and the item's status are unchanged

  Scenario: An adapter exit after the prompt boundary is not a launch failure
    Given an unrecovered ACP attempt that exited before the protocol completed after its agent.acp.started event was recorded
    When the run terminates
    Then no adapter-launch-release record is journaled
    And the failure keeps its existing route

  Scenario: A pre-prompt process exit with eligible provider evidence keeps its availability route
    Given an unrecovered ACP attempt that exited with code 1 before the prompt boundary
    And its recorded process terminal diagnostic matches the configured candidate-scoped unsupported-model signature and no non-eligible guard
    When the run terminates
    Then Provider-limit release and re-dispatch records the candidate hold
    And no adapter-launch-release record is journaled

  Scenario: An excluded process exit is not released as a launch failure
    Given an unrecovered pre-prompt ACP process exit with recorded signal termination and no exit code
    When the run terminates
    Then no adapter-launch-release record is journaled
    And the failure keeps its existing route

  Scenario: Missing launch evidence does not authorize release
    Given a terminal ACP process-exit failure whose attempt event stream cannot be read completely from its recorded factory
    When the Dispatcher evaluates adapter launch release
    Then it surfaces unavailable evidence and schedules another observation
    And it neither journals adapter-launch-release nor creates a needs-human decision from the missing evidence
```

## Scenario 128 — An unrunnable ready item is visible but never advertised for dispatch

```gherkin
Feature: Variant-aware acceptance eligibility is shared by candidate and attention surfaces
  As an operator looking for the next executable item
  I want a physically ready but ungradeable item reported as UNRUNNABLE instead of advertised for dispatch
  So that ranking, attention, and the Dispatcher cannot disagree at the factory boundary

  Scenario: An AI-dispositive item with no gradeable assertion is excluded and surfaced
    Given an already-filed ready item with an AI-dispositive effective acceptance policy
    And its effective acceptance criteria resolve to zero gradeable assertions from a reported source
    And its effective workflow variant is implement-kind
    And the repository is otherwise idle, below capacity, and has viable admission-required ACP candidates
    When next, needs-attention, idle-factory composition, and the Dispatcher drain enumerate candidates
    Then the item is absent from next and its pagination total
    And needs-attention composes no implementation item from next for it
    And it is absent from the idle-factory executable handoff
    And the Dispatcher drain does not select it
    And exactly one hygiene:unrunnable-acceptance fact identifies it as UNRUNNABLE
    And the fact reports the effective-criteria source and zero gradeable assertions
    And the fact names authoring criteria or deliberately selecting human-only as remedies
    And the fact carries no impl action the Dispatcher would refuse

  Scenario: Human-only and groom-kind controls remain eligible
    Given two otherwise identical ready items with zero gradeable assertions
    And one has effective acceptance policy human-only
    And the other selects an effective groom-kind workflow variant
    When the shared variant-aware acceptance-eligibility decision evaluates them
    Then both remain eligible with respect to that decision
    And neither produces an unrunnable-acceptance fact

  Scenario: Adding a gradeable criterion clears the fact and restores every candidate surface
    Given the AI-dispositive implement-kind item currently produces one unrunnable-acceptance fact
    When a gradeable effective acceptance criterion is added without changing its ready state
    Then the unrunnable-acceptance fact clears
    And the item appears exactly once in next and its pagination total
    And needs-attention composes exactly one implementation item from that next candidate
    And the eligible idle-factory set includes it exactly once
    And it appears exactly once in the Dispatcher drain candidate set
```

## Scenario 129 — A structured candidate renders through the catalogs and keeps the manual form as the escape hatch

```gherkin
Feature: Any model from any provider is one structured entry, and anything else is still reachable
  As a factory operator
  I want to name an agent, a model and an effort per node and let the catalogs render the rest
  So that routing a node to a new provider is a copyable line rather than a hand-written adapter command

  Scenario: A structured Codex entry renders from the catalogs with derived identity
    Given an implement entry {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}
    When the Dispatcher resolves the node
    Then the rendered candidate is byte-identical to the codex-acp catalog launch distribution with that model and effort applied
    And its candidate_key is codex-acp/openai/gpt-5.5
    And its availability_key is the codex-acp entry's account domain

  Scenario: A multi-provider agent takes a provider-qualified model
    Given a fallback {"agent": "opencode", "model": "zai/glm-5.2"}
    When the Dispatcher resolves the candidate
    Then the provider-qualified model is passed to the agent
    And identity derives from the agent, provider and model triple

  Scenario: The manual form is accepted unchanged
    Given a fallback in the manual form with an explicit command and explicit identity
    When the Dispatcher resolves the candidate
    Then it is accepted with no field derived from any catalog

  Scenario: Mixed, unknown or unresolvable entries refuse before claim
    Given an entry that mixes agent with command, or names an agent absent from the agent catalog, or names a model the model catalog does not declare for that agent
    When the Dispatcher validates the configuration
    Then the dispatch refuses before claim naming the entry and the offending field

  Scenario: Rendering is deterministic across dispatches
    Given the same catalog snapshot and the same structured entry on two dispatches
    When the Dispatcher renders both
    Then the rendered adapter bytes are identical
```

## Scenario 130 — Dispatch admits only a current, identifiable Fabro base

```gherkin
Feature: Target-aware Fabro currency admission
  As a factory operator
  I want every dispatch to prove the selected server's upstream base is current
  So that a workflow is never claimed onto an obsolete or unidentifiable engine

  Scenario: An exact tagged base inside the publication window admits
    Given the selected factory target serves an integration commit descended from an exact published upstream release tag
    And that tag was published no more than 30 calendar days before the newest observed upstream release
    And the release observation is no more than seven calendar days old
    When any direct, hand-picked, drain, or autonomous-loop dispatch evaluates currency
    Then currency admission succeeds before claim
    And release semantic versions and commit timestamps do not affect the result

  Scenario Outline: A build with no exact release-tag ancestor refuses before claim
    Given the selected factory target's serving build is <build condition>
    When dispatch evaluates currency
    Then dispatch refuses before claim, ledger mutation, or run creation
    And the refusal names the target, serving build when known, failed condition, and corrective route

    Examples:
      | build condition                                                |
      | an untagged upstream commit with no published release ancestor |
      | ancestry-mismatched from every published release tag           |

  Scenario: An out-of-window base refuses with complete evidence
    Given the selected base was published more than 30 calendar days before the newest observed release
    And the Petri transition deadline has passed
    When dispatch evaluates currency
    Then dispatch refuses before claim
    And the refusal names the target, serving integration commit, base tag and publication time, newest release and publication time, observation time, failed window, and corrective route

  Scenario: The one Petri transition expires without renewal
    Given the selected target serves the existing 0.254 carrier with an otherwise current and identifiable release observation
    When currency is evaluated before 2026-11-14T00:00:00Z
    Then the out-of-window base is admitted visibly as the bd-ib-6tcjfx transition
    When currency is evaluated at or after 2026-11-14T00:00:00Z
    Then dispatch refuses on the ordinary 30-calendar-day rule
    And no compatibility hold or warning can renew the exception

  Scenario: Stale release evidence and a failed refresh refuse
    Given the cached upstream release observation is older than seven calendar days
    And refreshing the GitHub Releases observation fails
    When dispatch evaluates currency
    Then dispatch refuses before claim
    And the stale cache is not accepted as proof

  Scenario: Stable and nightly releases use the same publication-time rule
    Given the candidate base is an official nightly or prerelease release tag
    And the newest observed release is stable, prerelease, or nightly
    When dispatch evaluates currency
    Then both publication timestamps participate identically in the 30-calendar-day comparison
    And semantic-version ordering does not privilege either release class

  Scenario: Each factory target is evaluated against its own serving version
    Given two configured factory targets serve different integration commits
    When the same work item is considered for each target
    Then each currency result is derived from that target's own serving commit and release-tag ancestry
    And one target's current base does not admit the other target's stale or unidentified base
```

## Scenario 131 — The Definition of Done gate admits a coherent item, refuses a malformed one host-side, and rests an incoherent one at needs-human

```gherkin
Feature: Definition of Done is validated before any implementation spend
  Scenario: A malformed Definition of Done is refused host-side
    Given a ready item whose description has no Definition of Done section
    When the Dispatcher evaluates it for dispatch
    Then the pre-dispatch wall refuses with exit code 5 naming the missing section
    And no factory run is created
  Scenario: An unresolved reference is a finding
    Given a ready item whose Definition of Done references a scenario heading that does not exist
    When the pre-dispatch wall evaluates it
    Then the refusal names the unresolved heading text
  Scenario: A Human-attested sub-heading without a Reason line blocks ready
    Given an item whose Definition of Done carries a Human-attested sub-heading with no Reason line
    When the approve valve is driven
    Then the item does not enter ready and the refusal names the missing Reason line
  Scenario: An incoherent Definition of Done rests the item at needs-human
    Given a ready item whose Definition of Done parses but whose assertions cannot be judged from its referenced scenario
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending carrying the findings
    And the Dispatcher rests the item at blocked with reason needs-human and the findings as the recorded question
    And no human decision waits inside the run
  Scenario: An implementer that finds the Definition of Done wrong takes the same route
    Given a running implement node that determines the Definition of Done is incomplete
    When the node ends through the structured needs-human ending carrying the proposed amendment
    Then the item rests at blocked with reason needs-human and the amendment as the recorded question
    And no code that differs from the Definition of Done is published
  Scenario: A coherent Definition of Done proceeds to implement
    Given a ready item with a well-formed Definition of Done referencing an existing scenario
    When the dod_gate node evaluates it
    Then the run proceeds to the implement node
```

## Scenario 132 — A factory-captured proof is captured on a draft pull request, reviewed, replayed and published

```gherkin
Feature: Proof of Done is captured and independently reproduced before publication
  Scenario: A draft pull request exists before the first capture
    Given an item whose Definition of Done assertions are all factory_captured
    And the janitor is green
    When the publish_draft node runs
    Then the publish branch is pushed and a draft pull request exists for it
    And a second janitor-green entry does not open a second pull request
  Scenario: Capture after a green janitor
    Given the draft pull request exists
    When the proof_capture node runs
    Then it posts one new Proof of Done captured comment naming every assertion, its steps and its proof
    And every image is stored through the proof asset store under the asset naming form
    And the tree is unchanged
  Scenario: Verify replays after review
    Given review approved the tree and the captured record exists
    When the proof_verify node replays the steps on an adapter distinct from the implementer's
    Then it posts one new Proof of Done verified comment and routes to pr_refresh
    And the pr node marks the pull request ready and arms auto-merge
  Scenario: A non-reproducible proof routes to fix
    Given the proof_verify replay fails to reproduce one assertion
    When the node ends
    Then it posts a not_reproduced record naming that assertion and routes to fix
    And no edge routes the run to pr_refresh or pr
  Scenario: The review-cap escape hatch still replays
    Given merge_on_review_cap is enabled and the review-fix budget is exhausted with a fix verdict
    When the review node ends
    Then the run proceeds to proof_verify and not directly to pr_refresh or pr
  Scenario: The pointer is written after merge
    Given the pull request merged with a verified record
    When the Dispatcher completes the item
    Then the description carries a Proof of Done section holding only the pointer to that record after an unchanged Definition of Done section
    And the acceptance pass grades each factory-captured assertion from that record and not from diff vocabulary
  Scenario: A stale pointer is a hygiene fact
    Given an item whose Proof of Done pointer names a run id that is not the latest verified record on its pull request
    When needs-attention composes hygiene facts
    Then exactly one fact names the item and the pull request as carrying a stale proof pointer
  Scenario: Slow hooks after a post-draft rebase are command work
    Given a draft and verified proof on the run's own recorded head
    And the default branch advanced after publish_draft
    And an incoming commit changes a path outside every inert class
    And the sandbox pre-push aggregate takes longer than the agent foreground timeout
    When pr_refresh rebases the branch
    Then the declared sandbox check suite completes as a foreground command
    And the branch is pushed with an explicit lease on the recorded prior remote head
    And capture, review and replay run for the changed head before scripted pr marks it ready
    And the item's merge hold determines whether auto-merge is armed
  Scenario: Publication refuses unverifiable provenance
    Given the remote publish head differs from the run's recorded publication head
    When pr_refresh runs
    Then it fails closed with a named cause and preserved recovery evidence
    And it does not force-push an unknown head
  Scenario: A conflicted refresh is never resolved by the script
    Given the pr_refresh rebase onto the advanced default branch conflicts
    When pr_refresh runs
    Then it does not resolve the conflict by choosing one side
    And it takes the refresh-repair route that Scenario 176 exercises
  Scenario: Refresh is idempotent and bounded
    Given a refresh already pushed a new head with durable run provenance
    When the same refresh is retried against the matching remote
    Then it resumes from that head and requires proof naming it
    And three completed refreshes followed by more base movement end with an explicit non-convergence cause
  Scenario: Publication renders metadata as data and verifies the exact pull request
    Given the title and body contain shell metacharacters
    When pr executes the deterministic publication recipe
    Then the forge receives those literal strings
    And a matching already-merged pull request is reported as success
    And a closed-unmerged or unexpected-head pull request fails closed
  Scenario: Groom filing-plan publication keeps its distinct adapter behavior
    Given a registered groom-kind workflow whose apply phase produced a cut
    When its pr stage is reached
    Then its existing ACP adapter validates and publishes the filing plan for host-side filing
    And it neither pushes a branch nor opens a pull request
    And subtracting only pr_adapter from its referenced and rendered token sets yields exactly the implementation workflow token set
    And its unreachable pr_refresh carries the reserved refresh command and input references
    And its unreachable pr_refresh command declaration keeps the common timeout table valid
```

## Scenario 133 — A mixed item is refused ai-only from every entry path, parks for its human-attested leg, and the accept valve refuses until the record exists

```gherkin
Feature: Human-attested assertions require a human record before done
  Scenario: Declaration and routing
    Given an item whose Definition of Done has three factory_captured assertions and one assertion under a Human-attested sub-heading with a Reason line
    When the shared acceptance-eligibility decision evaluates it under an ai-only policy
    Then the host-side wall refuses ai-only naming the human-attested assertion and both remedies
    And a direct dispatch --item and the autonomous loop return the same refusal for the same item
  Scenario: A parked policy admits the item
    Given the same item under ai-then-human
    When the shared decision evaluates it
    Then it is admitted and is recorded as parking for its human-attested leg after merge
  Scenario: Parking after merge
    Given the same item merged with a verified record for its three factory-captured assertions
    When the acceptance pass runs
    Then the pass reports PASS for the factory leg with the human-attested assertion listed as pending
    And the item rests in acceptance and needs-attention surfaces the pending human-attested leg with the pull request link
    And the accept valve refuses naming the assertion awaiting attestation
  Scenario: Done after the human record
    Given a human posts a Proof of Done human_attested comment on the pull request
    When the accept valve is driven
    Then the item closes to done and its pointer carries both record links
  Scenario: An unevidenced assertion parks without consuming the rework cap
    Given a merged item whose factory_captured assertion has no verified record for the merging run
    When the acceptance pass runs
    Then the verdict is NEEDS_ATTENTION naming that assertion and the rework counter is unchanged
  Scenario: The deliverable policy refuses a lazy opt-out
    Given an item declaring a web-interface behaviour of its own application as human_attested
    When the dod_gate node evaluates it
    Then it refuses naming the assertion and the sandbox capability that makes it factory-capturable
```

## Scenario 134 — A declared proof credential is projected by name and a withheld, absent, credential-shaped or over-scoped declaration is refused

```gherkin
Feature: Proof credentials are declared by name and bounded by capability
  Scenario: A read-only credential is projected
    Given a repository declaring one proof credential with capability read_only whose value the credential wrapper supplies
    When an item of that repository is dispatched
    Then the sandbox environment carries that name and the dispatch journal records the declaration by name and whether it was minted or copied
  Scenario: A withheld credential is refused before any run
    Given a repository declaring the store credential as a proof credential
    When an item of that repository is dispatched
    Then the Dispatcher refuses before creating a run, naming the declaration
  Scenario: An absent value is refused
    Given a declared proof credential whose value the wrapper does not supply
    When an item is dispatched
    Then the Dispatcher refuses naming the missing name and the target's credential wrapper
  Scenario: A credential-shaped declaration is refused
    Given a declared proof credential whose purpose text contains a credential-shaped value
    When an item is dispatched
    Then the Dispatcher refuses before creating a run, naming the declaration and the position of the value
  Scenario: An over-scoped declaration is refused
    Given a declared proof credential whose capability would let the sandbox execute code on the host substrate
    When an item is dispatched
    Then the Dispatcher refuses before creating a run, naming the declaration and the capability
```

## Scenario 135 — A plan cannot archive until its own Definition of Done is proved against the released build

```gherkin
Feature: A plan is done when its stated outcome was observed, not when its children closed
  Scenario: Plan creation records the maintainer's statement and derives assertions
    Given a maintainer describes a new plan and states what done means
    When the plan front-end creates the plan in an attended session
    Then the epic description's first heading is a Definition of Done section whose assertions the maintainer confirmed
    And the initial research note carries the maintainer's statement verbatim beside the assertions derived from it
  Scenario: An unattended creation records its assertions as session-derived
    Given a plan is created in an unattended session
    When the plan front-end authors the Definition of Done section
    Then the first handoff entry records the assertions as session-derived
  Scenario: A bare plan assertion is host_captured and needs no Reason or reference line
    Given a plan epic whose Definition of Done carries one bullet outside any sub-heading and no References line
    When the effective-criteria primitive parses it with subject plan
    Then the assertion's proof mode is host_captured
    And no finding is reported for a missing Reason line or a missing reference line
  Scenario: A carrier-map event that leaves a plan assertion unmapped is refused
    Given a plan epic with two Definition of Done assertions
    When a scope event carrying a carriers block that maps only one of them is recorded
    Then record_scope_event refuses it naming the unmapped assertion
  Scenario: A complete carrier map is recorded
    Given the same epic
    When a scope event carrying a carriers block that maps one assertion to a child work-item id and the other to plan-level proof is recorded
    Then the carrier-map event is recorded
  Scenario: A carrier-map event on an epic without the section is refused
    Given a plan epic with no Definition of Done section
    When a scope event carrying a carriers block is recorded
    Then record_scope_event refuses it naming the missing section
  Scenario: A ruling without a carriers block is recorded and voids nothing
    Given a plan epic whose latest verified plan Proof of Done record postdates its last carrier-map event
    When a maintainer ruling with no carriers block is recorded as a scope event
    Then the ruling is recorded without restating the carrier map
    And the proof leg still holds
  Scenario: Closed children and a coverage review do not archive an unproved plan
    Given a plan whose children are all closed and whose timeline carries valid completeness-review evidence
    And the epic carries no verified plan Proof of Done record
    When the plan operation attempts the archive
    Then archive_thread refuses naming each unproved plan assertion
    And the plan directory and the epic are unchanged
  Scenario: A record captured against an unreleased tree is not evidence
    Given a plan whose governed repository carries a release tag
    And a captured plan Proof of Done record with no installed build identifier whose build identity states release none
    When the archive gate evaluates the proof leg
    Then the record is rejected naming the missing release identity
  Scenario: A record names a sibling repository's release
    Given a plan whose governed repository does not carry the release tags its records name
    And plan Proof of Done records whose installed build identifier begins with the name of a sibling repository on the same forge owner
    And no clone of the sibling repository exists on the host running the archive gate
    When the archive gate evaluates the proof leg
    Then the record's release tag is judged against the sibling repository's release tags read from its remote
    And a record naming a tag the sibling repository's remote carries is accepted as evidence
    And a record naming a tag the sibling repository's remote does not carry is rejected naming the missing release identity and the sibling repository
  Scenario: An unreachable or unauthenticated forge does not fall back to the governed repository
    Given a plan Proof of Done record whose installed build identifier names a sibling repository
    And the forge cannot be reached or the archive gate holds no credentials it accepts
    When the archive gate evaluates the proof leg
    Then the record is rejected naming the repository it tried to read and the failure
  Scenario: An explicitly named repository that does not exist is rejected
    Given a plan Proof of Done record whose installed build identifier begins with an owner and repository the authenticated forge reports does not exist
    When the archive gate evaluates the proof leg
    Then the record is rejected naming that repository
    And the record is not judged against the governed repository
  Scenario: A first word that names no repository falls back to the governed repository
    Given a plan Proof of Done record whose installed build identifier begins with a bare word the authenticated forge reports is not a repository of the governed repository's owner
    When the archive gate evaluates the proof leg
    Then the record's release tag is judged against the governed repository's release tags read from its remote
  Scenario: A self-verified record is refused
    Given a captured plan Proof of Done record published by one session identity
    When the same session drives the posting primitive to publish a verified record replaying it
    Then the posting primitive refuses the post because the computed identity equals the capturing identity
    And a verified record with that same identity posted by any other route is not evidence for the proof leg
  Scenario: A later human_attested record does not unseat the verified record
    Given a plan with one host_captured assertion and one human_attested assertion
    And a verified record covering the host_captured assertion that postdates the latest captured record and the last carrier-map event
    When a human_attested record covering the other assertion is posted afterwards and the archive gate evaluates the proof leg
    Then the proof leg is met
  Scenario: An unproved plan assertion is not transferable
    Given a plan whose remaining work blockers are all transferred to a named follow-up work item
    And one plan assertion with no verified plan Proof of Done record
    When the plan operation attempts the archive
    Then the archive is refused and the plan stays live with its epic open
  Scenario: A legacy plan gains the section on an attended resume
    Given a plan epic created before this clause with no Definition of Done section
    When the plan is resumed in an attended session
    Then the resume reports plan-definition-of-done missing
    And the section is authored with the maintainer before any further carrier-map event is recorded
  Scenario: An unattended resume of a legacy plan does not author the section
    Given the same legacy epic whose next_action kind is human
    When the plan is resumed unattended
    Then the resume reports plan-definition-of-done missing and sets next_action to kind human naming the gap
    And no assertion is authored on the maintainer's behalf
  Scenario: An unattended resume of a legacy plan still takes an impl next action
    Given the same legacy epic whose next_action kind is impl
    When the plan is resumed unattended
    Then the resume reports plan-definition-of-done missing and takes the impl action
  Scenario: An epic with no plan directory is exempt
    Given an epic filed through capture-work-item with no plan directory
    When the plan-level proof rules are evaluated
    Then no Definition of Done section and no plan Proof of Done record is required of it
  Scenario: plan_close_proof reports an epic closed after ratification without a verified record
    Given an epic whose plan_slug names an archived directory and whose close timestamp is later than 2026-10-04
    And its timeline carries no verified plan Proof of Done record
    When the plan-record conformance checks run
    Then plan_close_proof reports that epic as an error
  Scenario: plan_close_proof does not report an epic closed before ratification
    Given an epic whose plan_slug names an archived directory and whose close timestamp is on or before 2026-10-04
    And its timeline carries a completeness-review evidence comment and no plan Proof of Done record
    When the plan-record conformance checks run
    Then plan_close_proof does not report that epic
    And plan_close_evidence does not report that epic
```

## Scenario 136 — A host-captured assertion holds the item in acceptance until an independent host replay verifies it against the released build

```gherkin
Feature: Proof that needs the released build is captured by an agent on a host, not waved through
  Scenario: A Host-captured sub-heading without a Reason line blocks ready
    Given an item whose Definition of Done carries a Host-captured sub-heading with no Reason line
    When the approve valve is driven
    Then the item does not enter ready and the refusal names the missing Reason line
  Scenario: The item is admitted under ai-only and parks after merge with the host leg pending
    Given an item under an ai-only policy whose factory-captured assertions are verified and which carries one host-captured assertion
    When the item is dispatched, merges, and the post-merge acceptance pass runs
    Then the host-side wall does not refuse ai-only for it
    And the captured and verified records list the host-captured assertion under a heading stating it is pending the host leg
    And the pass reports PASS listing the host-captured assertion as pending the host leg
    And the item rests in acceptance and the rework counter is unchanged
    And needs-attention surfaces the pending host leg naming the item, the pull request and the assertion
  Scenario: The accept valve refuses while the host leg is pending
    Given the same item under ai-then-human with no host_verified record
    When the accept valve is driven
    Then the valve refuses naming the host-captured assertion and the record format
  Scenario: Posting the independent replay re-runs the pass and closes the item
    Given a host_recorded record on the pull request of the latest merged run naming a release tag that contains the merge commit
    When a different session identity publishes host_verified through the posting primitive
    Then the posting primitive drives reconcile-merged for the item, which re-runs the acceptance pass
    And the host-captured assertion is judged passing from the host_verified record
    And under ai-only the item closes to done and its pointer carries the host_verified record link
  Scenario: reconcile-merged driven by hand is the same route
    Given an item resting in acceptance with a host_verified record the pass has not yet observed
    When reconcile-merged is driven for the item by hand
    Then only the acceptance pass is re-run, without a post-merge janitor
  Scenario: A self-replayed host record is refused
    Given a host_recorded record published by one session identity
    When the same session drives the posting primitive to publish host_verified
    Then the posting primitive refuses the post because the computed identity equals the recording identity
    And a host_verified record with that same identity posted by any other route leaves the assertion pending and is reported as not independent
  Scenario: A host replay that does not reproduce is rework input
    Given a host_not_reproduced record from a different session identity naming the host-captured assertion
    When the acceptance pass runs under an AI-dispositive policy
    Then the verdict is FAIL for that assertion and the item returns to active with the rework-pending label
  Scenario: A host record against a build without the merge is not evidence
    Given a host_verified record naming a release tag that does not contain the merge commit
    When the acceptance pass runs
    Then the host-captured assertion stays pending and the pass reports the failed containment check
  Scenario: A host record on an earlier pull request is not evidence
    Given an item reworked onto a new pull request whose only host_verified record sits on the earlier pull request
    When the acceptance pass runs
    Then the host-captured assertion stays pending
  Scenario: A host record does not make the verified pointer stale
    Given an item whose pointer names the latest verified record and whose pull request later gains a host_recorded record
    When needs-attention composes hygiene facts
    Then no stale proof pointer fact is reported for the item
  Scenario: A host-routed item keeps its declared modes
    Given an item carrying factory_safety needs-host-secrets whose assertions are declared with no sub-heading
    When the effective-criteria primitive parses it
    Then every assertion's mode is factory_captured and none is host_captured
  Scenario: The gate refuses a weaker mode than the assertion needs
    Given an assertion declared human_attested that an agent session could exercise on an operator host
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion and the host surface
```

## Scenario 137 — A behavioural assertion is proved by exercising the behaviour, and a sandbox that cannot exercise it says so

```gherkin
Feature: Proof exercises the delivered behaviour through its real surface
  Scenario: A test-existence assertion on a behavioural item is a gate finding
    Given an item delivering a command-line behaviour whose only assertion says tests prove the behaviour
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion
    And the finding's remedy is to restate the assertion as the behaviour
  Scenario: A test-existence assertion is legitimate when the deliverable is a test
    Given an item whose deliverable is a new test module and whose assertion says the module's tests pass against the unchanged implementation
    When the dod_gate node evaluates the rendered goal
    Then no test-existence finding is reported and the run proceeds to the implement node
  Scenario: A behaviour-preserving item names the unchanged behaviour
    Given an item declared behaviour-preserving whose assertion names an existing command and the output it still prints
    When the dod_gate node evaluates the rendered goal and the proof_capture node later runs
    Then the gate reports no finding for the assertion
    And the published steps invoke that command on the delivered artifact
  Scenario: A configuration deliverable names the delivered state
    Given an item whose deliverable is a configuration key and whose assertion names the file and the key it carries
    When the dod_gate node evaluates the rendered goal
    Then the gate reports no finding for the assertion
  Scenario: Capture exercises the behaviour rather than the suite
    Given a behavioural assertion naming a command and its output
    When the proof_capture node runs
    Then the published steps invoke that command on the delivered artifact
    And the record's proof for that assertion is not test-suite output alone
  Scenario: A missing capability ends the run instead of substituting a double
    Given a factory-captured assertion about a terminal multiplexer the sandbox cannot reach with its capabilities
    When the proof_capture node reaches that assertion
    Then the run ends through the structured needs-human ending naming the assertion and the missing capability
    And no record claims the assertion from a test run, a fixture or a test double
  Scenario: Suite-only proof is a blocking review finding
    Given a captured record whose proof of a behavioural assertion is test-suite output alone
    And that defect is the review verdict's only blocking finding
    And the run has issued fewer than two recapture verdicts
    When the review node reviews the record alongside the code
    Then the suite-only proof is a blocking review finding
    And the run re-enters proof_capture with that finding before any replay, through no disposition or review_fix visit
  Scenario: The replay backstop does not call suite-only proof not reproduced
    Given a captured record whose proof of a behavioural assertion is test-suite output alone reaches proof_verify
    When the proof_verify node evaluates the record
    Then the run ends through the structured needs-human ending naming that assertion
    And no not_reproduced record and no verified record is published for it
  Scenario: A proof-record-only verdict re-captures without a fix round
    Given a review verdict whose only blocking finding is that a captured step runs a program the record is required to contain but does not contain
    And the run has issued fewer than two recapture verdicts
    When the review node ends
    Then the run routes to proof_capture with preferred_label recapture
    And no disposition visit, no review_fix visit and no review-fix round is consumed
    And proof_capture publishes a new captured record, current for the publish head, that addresses the finding
  Scenario: The recapture findings arrive by both channels
    Given a review verdict with at least one blocking finding and only proof-record blocking findings
    And the run has issued fewer than two recapture verdicts
    When the run enters proof_capture with preferred_label recapture
    Then the engine preamble of preceding stage output carries the findings
    And the review record on the pull request carries the same findings
  Scenario: proof_capture reads the review record when the preamble is empty
    Given a recapture entry whose engine preamble carries no review finding
    And a review record on the pull request carrying a proof-record finding
    When the proof_capture node runs
    Then it reads that review record
    And the new captured record addresses that finding
  Scenario: An exhausted review-fix budget does not pre-empt recapture
    Given a run whose review fix-round budget (dispatcher.review_fix_cap) is exhausted
    And a review verdict with at least one blocking finding and only proof-record blocking findings
    And the run has issued fewer than two recapture verdicts
    When the review node ends
    Then the run routes to proof_capture with preferred_label recapture
    And the run does not rest at needs-human and does not ship on the review cap
  Scenario: A captured record is self-contained and names its head
    Given a factory-captured assertion whose reproduction step runs a helper program that the repository does not track
    And another step that runs a script the repository tracks, by its path, and an installed tool, by its name
    When the proof_capture node publishes the record
    Then the helper program's text is in the record or in a proof asset the record names
    And the tracked script and the installed tool are not required to be copied into the record
    And the record states the commit sha its steps ran against, equal to the publish branch head at capture time
  Scenario: A checkpoint commit does not make a record stale
    Given a captured record naming the publish head at capture time
    And an engine checkpoint commit that changes no tree lands on the publish branch after proof_capture publishes
    When the review node reviews the record against the new head
    Then the record is current, because the two commits carry the same tree
    And no proof-record finding is raised for its head
  Scenario: A mixed verdict still fixes the tree first
    Given a review verdict with one blocking finding about the tree and one proof-record finding
    And the review fix-round budget (dispatcher.review_fix_cap) is not yet exhausted
    When the disposition stage accepts the finding about the tree
    Then the run routes through review_fix as a fix verdict
    And the proof_capture visit its fix round reaches receives the proof-record finding
  Scenario: A different tree makes the captured record stale
    Given a captured record whose named commit has a different tree from the head under review
    When review evaluates the record
    Then the stale record is a blocking proof-record finding
  Scenario: A printed conclusion is not observed proof
    Given a captured record whose proof merely prints the claimed conclusion instead of observing the asserted behaviour
    When review evaluates the record
    Then the printed conclusion is a blocking proof-record finding
  Scenario: Both recapture laps remain available after the review-fix budget is exhausted
    Given a run that has exhausted its review-fix budget and issued no recapture verdict
    When review issues a first recapture verdict and then a second recapture verdict
    Then each verdict enters proof_capture and returns to review
    And neither returned review visit consumes a review-fix round
    And the engine review visit limit admits both returned visits
    When the returned review issues a third recapture verdict
    Then the run routes to non_converged without entering proof_capture
  Scenario: Re-capture is bounded
    Given a run whose review has ended with preferred_label recapture twice
    When review ends with a recapture verdict a third time
    Then the run routes to non_converged without entering proof_capture
  Scenario: A clean review keeps the approval route
    Given a review verdict with no blocking finding
    When the review node ends
    Then the run takes the approval route and does not route to proof_capture
```

## Scenario 138 — A proof finding reaches the fix stage, and a parked acceptance verdict is recorded with its reason and its pointer

```gherkin
Feature: The proof chain does not lose what it found
  Scenario: A capture finding is the fix stage's work order
    Given a green janitor and a proof_capture node that ends with preferred_label fix naming an assertion
    When the fix node starts
    Then the preamble of preceding stage output carries the assertion, what was observed and what the proof needs
    And the pull request carries a not_captured record naming the assertion and the finding
    And no templated node attribute and no inputs token in an edge condition delivers it
  Scenario: The fix stage reads the pull request when the preamble carries no finding
    Given a fix node entered on a proof finding whose preamble carries no finding
    When the fix node starts
    Then it reads the latest proof record on the pull request and takes the finding from it
  Scenario: A fix visit on a proof finding cannot succeed on an unchanged tree
    Given a fix node entered from proof_verify with a not_reproduced finding
    When the fix node ends without changing the tree
    Then it ends through the structured needs-human ending stating why the finding is wrong
  Scenario: The third capture finding in one run does not converge
    Given a run whose proof_capture node has ended with preferred_label fix twice
    When proof_capture ends with preferred_label fix a third time
    Then the run routes to the non_converged terminal and not to fix
  Scenario: A red janitor still reaches the fix stage as before
    Given a red janitor outcome
    When the fix node starts
    Then it receives the janitor failure output as its reason for entry
  Scenario: A parking verdict is recorded and reported honestly
    Given a merged item whose merging run has a verified record
    And an acceptance pass that returns NEEDS_ATTENTION
    When the dispatch completes
    Then the item carries a ledger comment naming the verdict, the unobserved leg and the action that would move it
    And the item's description carries the Proof of Done pointer
    And the dispatch result reports stage acceptance, verdict NEEDS_ATTENTION and status needs-attention
    And the dispatcher exits with code 1
  Scenario: An unchanged re-run appends nothing
    Given an item parked in acceptance whose ledger carries the parking comment for its verdict and pending-leg set
    When the acceptance pass is re-run and returns the same verdict and pending-leg set
    Then no further ledger comment is appended
  Scenario: A changed pending-leg set is recorded once
    Given an item parked on a PASS with a pending host leg and a pending human leg
    When the pass is re-run after the host leg is verified
    Then exactly one new ledger comment records the PASS with only the human leg pending
  Scenario: A parked PASS reports green at acceptance, not at done
    Given a merged item under ai-then-human whose every leg passes
    When the dispatch completes
    Then the item carries a ledger comment naming the PASS verdict and the accept valve as the action that would move it
    And the dispatch result reports stage acceptance, verdict PASS and status green, and the dispatcher exits with code 0
  Scenario: A human-only PASS and an advisory FAIL are recorded
    Given a merged item under human-only
    When the advisory acceptance pass returns PASS, and on another such item returns FAIL
    Then each item rests in acceptance carrying a ledger comment naming its verdict and its evidence legs
    And each dispatch result reports stage acceptance with its verdict and status green
  Scenario: Only a closed item reports done
    Given a merged item under ai-only whose every leg passes with no pending leg
    When the dispatch completes
    Then the item closes and the dispatch result reports stage done
  Scenario: A missing pointer on a verified item is surfaced and repaired
    Given an item in acceptance whose merging run has a verified record and whose description has no pointer
    When needs-attention runs and reconcile-merged is then driven for the item
    Then needs-attention reports the missing pointer as a hygiene fact naming the item and the pull request
    And reconcile-merged writes the pointer
  Scenario: A record stamped with the dispatch id is attributed to the merging run
    Given a merged item whose verified record's first line carries the dispatch id the Dispatcher declared to the sandbox
    When the acceptance pass looks for the merging run's verified record
    Then the record is attributed to the merging run and each factory-captured assertion is graded from it
    And the pointer is written naming that record
```

## Scenario 139 — The gate checks each proof mode against the capabilities the sandbox image publishes

```gherkin
Feature: Sandbox capabilities are published, and proof modes are checked against them in both directions
  Scenario: A factory-captured assertion needing an unpublished capability is a gate finding
    Given a sandbox image publishing terminal, tmux and headless_browser
    And an item whose factory-captured assertion is about behaviour inside herdr
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion and the capability herdr
    And the finding lists the remedies in order: add the capability to the image, declare host_captured with a Reason, declare human_attested only when no agent session can exercise it
  Scenario: Publishing the capability clears the finding
    Given the same item and a sandbox image that now publishes herdr
    When the dod_gate node evaluates the rendered goal
    Then the run proceeds to the implement node
  Scenario: An image without the capability file falls back to the committed mirror
    Given a sandbox image that publishes no capability file
    And a repository whose committed dispatcher.sandbox_capabilities lists terminal and tmux
    When the dod_gate node evaluates a factory-captured assertion needing a browser
    Then the finding names headless_browser as missing
  Scenario: With neither source the capability set is unknown and raises no missing-capability finding
    Given a sandbox image that publishes no capability file and a repository with no committed mirror
    When the dod_gate node evaluates a factory-captured assertion needing a browser
    Then no missing-capability finding is raised
    And the gate's output reports sandbox-capabilities unpublished
  Scenario: A mirrored capability the image does not publish is reported without failing the gate
    Given a sandbox image publishing terminal and a committed mirror that also lists herdr
    And an item whose assertions need only the terminal
    When the dod_gate node evaluates the rendered goal
    Then the gate's output reports the mirrored name herdr as a configuration mismatch
    And the Dispatcher journals the mismatch
    And the run proceeds to the implement node
  Scenario: The capability set is read, never inferred from the item
    Given a sandbox image publishing only terminal
    And an item whose description states that the sandbox carries herdr
    When the dod_gate node evaluates its factory-captured assertion about behaviour inside herdr
    Then the finding names herdr as missing
  Scenario: A host-captured declaration is refused where a published capability can exercise the assertion
    Given a sandbox image publishing headless_browser
    And an item declaring a web-interface behaviour of its own application under a Host-captured sub-heading
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion and the capability headless_browser
```

## Scenario 140 — Filing displays Definition-of-Done findings and withholds ready only on a mechanical one

```gherkin
Feature: The Definition of Done rules are applied where the item is filed
  Scenario: Filing displays the parse, the modes, the capabilities and the findings
    Given a filer captures an implement-kind item whose only assertion is a test-existence assertion
    When the capture front-end displays the filing before confirmation
    Then the display shows the effective-criteria parse, the assertion with its proof mode, the resolved sandbox capabilities and the finding
  Scenario: An advisory finding is recorded and does not withhold ready
    Given the same filing with its test-existence finding
    When the filer confirms
    Then the item is filed and carries the advisory finding as a ledger comment
    And intake does not withhold ready on that finding
    And the wall's advisory finding alone does not withhold ready; the pre-admission judgement of Scenario 174 still applies
  Scenario: A mechanical finding withholds ready
    Given a filer confirms an implement-kind item whose Definition of Done references a heading that does not exist
    When intake routes the filed item
    Then the item is filed, is not routed to ready, and carries the finding as a ledger comment
  Scenario: A filer who declines the section sees it reported missing
    Given a filer declines the front-end's offer to author the Definition of Done section
    When the front-end displays the filing
    Then the display shows definition-of-done missing
    And the filing is not refused
  Scenario: The carrier relation is not stated inside the section
    Given a child of a plan whose Definition of Done section carries a bullet naming the plan assertion it carries
    When the host-side wall evaluates the section
    Then the bullet is reported as a Definition-of-Done finding
    And the same statement as prose before the Definition of Done heading is not a finding
  Scenario: Ready items with an advisory finding are surfaced before dispatch
    Given a ready item whose reference line names only a generic heading while a scenario heading states its behaviour
    When needs-attention composes hygiene facts
    Then a hygiene fact names the item and its advisory Definition-of-Done finding
```

## Scenario 141 — The referenced scenario governs the proof, and the record names it

```gherkin
Feature: Proof steps are tied to the scenario that states the behaviour
  Scenario: A generic reference where a scenario exists is a gate finding
    Given an item whose assertion names a behaviour that a scenario heading of scenarios.md states
    And whose reference line names only a non-scenario heading
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the scenario heading that governs the assertion
  Scenario: A non-scenario reference is valid when no scenario states the behaviour
    Given an item whose assertion names a behaviour no scenario heading states and whose reference line names a contracts heading
    When the dod_gate node evaluates the rendered goal
    Then no scenario-reference finding is reported
  Scenario: The record names the governing scenario
    Given an assertion whose reference line names a scenario heading
    When the proof_capture node publishes its record
    Then the record names, for that assertion, the referenced heading and the title of the scenario its steps exercise
  Scenario: The record states when no scenario governs an assertion
    Given an assertion that no referenced scenario heading governs
    When the proof_capture node publishes its record
    Then the record states for that assertion that no scenario governs it
```

## Scenario 142 — A run that terminated after publishing is resumed at its first unfinished stage from its pull request, and nothing it completed runs again

```gherkin
Feature: A published run is finished, not rebuilt
  Scenario: The resume enters at the stage the earlier run was executing when it terminated
    Given a ready item whose earlier run published a draft pull request, published a captured record and a verified record naming the published head, and then terminated while executing the pr stage
    And the pull request's current head equals that head and the item's Definition of Done equals the earlier run's dispatch-time snapshot
    And the factory the earlier dispatch names reports the earlier run as terminal
    When the operator drives resume for the item
    Then the item is admitted through the ordinary admission valve and a new run of the earlier run's recorded workflow starts
    And the new run's sandbox is a checkout of the publish branch at that head
    And the new run enters the workflow at the pr_refresh command stage before pr
    And when pr_refresh leaves the head unchanged the new run's record shows no visit to dod_gate, implement, janitor, publish_draft, proof_capture, review or proof_verify
    And the dispatch journal carries one resume record naming the earlier run's identifiers, the pull request number, the head, the resumed-at stage and the source that decided it
    And the item's dispatch_workflow metadata is what it was before the resume
  Scenario: A run that terminated during review resumes at review on the captured record
    Given a ready item whose earlier run published a draft pull request and a captured record and then terminated while executing the review node
    When the operator drives resume for the item
    Then the new run enters the workflow at the review stage
    And no proof_capture visit precedes that review visit in the new run, and the captured record remains the latest record on the pull request when the review node starts
    And no implement stage runs
  Scenario: The resumed-at stage falls back to the pull request's latest record when the factory no longer holds the earlier run
    Given a ready item whose earlier run's factory answers that it no longer holds the run, and whose pull request's latest proof record is a captured record
    When the operator drives resume for the item
    Then the new run enters the workflow at the review stage
    And the resume record names the pull request's latest record as the source that decided the stage
  Scenario: A run that terminated inside a fix loop resumes at fix
    Given a ready item whose earlier run's factory no longer holds the run, and whose pull request's latest proof record is a not_captured record
    When the operator drives resume for the item
    Then the new run enters the workflow at the fix stage and no implement stage runs
  Scenario: A stall-cancelled run with no proof record resumes from its cancel record
    Given a ready item whose latest dispatch's run completed publish_draft and was cancelled by the watchdog while executing proof_capture, leaving no proof record on its pull request
    And that dispatch's watchdog-stall-cancel record names a head equal to the pull request's current head
    And the factory authoritatively reports that it no longer holds that run
    When resume runs for the item
    Then the new run enters the workflow at proof_capture on that head and no dod_gate, implement or janitor stage precedes it
    And the resume record names the cancel record as the source that decided the stage
    And the dispatch journal carries neither a publish-branch-reclaim record nor a publish-branch-reclaim-held record for the resume
  Scenario: A run that republished after its latest proof record resumes at proof_capture on the head it published
    Given a ready item whose earlier run published a captured record naming one head, then completed review_fix and a second publish_draft that pushed a descendant of that head, and terminated while executing proof_capture
    And the factory the earlier dispatch names still holds that run and the published head its terminal checkpoint carries equals the pull request's current head
    When the operator drives resume for the item
    Then the new run enters the workflow at proof_capture on the pull request's current head and no dod_gate, implement or janitor stage precedes it
    And the resume record names the pull request's current head as the published head and the factory record as the source that decided the stage
    And the dispatch journal carries neither a publish-branch-reclaim record nor a publish-branch-reclaim-held record for the resume
  Scenario: The earlier run's records are attributed to the resumed run and the pointer names both
    Given an item resumed from a pull request whose verified record carries the earlier run's identifier
    When the resumed run merges the pull request and the acceptance pass runs
    Then the pass attributes the verified record to the merging dispatch and grades each factory-captured assertion from it
    And the Proof of Done pointer names that record, its run id and the resumed run's identifier
  Scenario: A resumed run is resumed again and attribution follows the chain
    Given an item whose resumed run published a verified record and then terminated at the pr stage
    When the operator drives resume for the item a second time and the new run merges the pull request
    Then the acceptance pass attributes the verified record to the merging dispatch through the two resume records
  Scenario: A factory record names the head it was captured on
    Given a proof_capture or proof_verify node that publishes its record
    When the record is read back from the pull request
    Then it names the full commit sha of the publish-branch head the steps were executed on
  Scenario: A resume leaves the surviving publish branch alone
    Given a ready item whose earlier run's publish branch survives on origin with its draft pull request open
    When the operator drives resume for the item
    Then no preservation ref is created and the publish branch is not deleted
    And the dispatch journal carries neither a publish-branch-reclaim record nor a publish-branch-reclaim-held record for the resume
  Scenario: A resumed run's later stages behave as in a first run
    Given a resumed run entered at the review stage whose review requests changes
    When the review_fix node ends with a tree change
    Then the run re-enters janitor, publish_draft and proof_capture before review, exactly as a first run does
  Scenario: A resumed publication refreshes proof after a changed head
    Given a terminated run with verified proof on its published head
    And origin still names that head but the default branch has advanced
    And an incoming commit changes a path outside every inert class
    When resume enters pr_refresh and rebases the publish branch
    Then the declared gate runs before the leased push
    And fresh capture, review and replay run for the new head before pr
    And the three-refresh count starts at zero for this run
    And the existing two-resume host bound remains in force
```

## Scenario 143 — A resume refuses, naming the mismatch, when the head moved, the earlier run is live, or the pull request is closed or merged

```gherkin
Feature: A resume never continues from a state the records do not describe
  Scenario: The pull request head no longer equals the head the record names
    Given a ready item whose pull request head differs from the head its latest proof record names, and whose earlier run's factory record does not show that run publishing the pull request head after that record
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists
    And the refusal names both heads and names a plain dispatch as the remedy
    And the item, the publish branch and the pull request are unchanged
  Scenario: A republication the factory can no longer show does not anchor a resume
    Given a ready item whose pull request head differs from the head its latest proof record names
    And the factory the earlier dispatch names answers that it no longer holds the earlier run
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming both heads and a plain dispatch as the remedy
  Scenario: The earlier run is still live
    Given an item active under a live claim whose journaled run its factory reports as not terminal after the preamble's reconciliation
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before the admission valve and before any run exists, naming the run id and its status
  Scenario: The item is not ready
    Given an item resting at blocked with blocked_reason needs-human after its earlier run terminated
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming the status and resolve-blocked as the remedy
    And the item remains blocked
  Scenario: Every applicable refusal is named
    Given an item active under a live claim whose journaled run its factory reports as not terminal
    When the operator drives resume for the item
    Then the refusal names the status with its remedy and the live run id with its status, in that order
  Scenario: A live ownership lock is refused
    Given a ready item whose dispatch-scoped ownership lock exists and whose recorded process id is alive
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming the lock age
  Scenario: The Definition of Done changed after the earlier run
    Given a ready item whose Definition of Done section differs from the earlier run's dispatch-time snapshot
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming the difference and a plain dispatch as the remedy
  Scenario: The pull request is closed
    Given a ready item whose earlier run's pull request is closed without merging
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming the pull request state and a plain dispatch as the remedy
  Scenario: The pull request is merged
    Given an item whose earlier run's pull request is merged
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming the pull request state and reconcile-merged as the remedy
    And reconcile-merged for the item still requires that real merge
  Scenario: Nothing to resume from
    Given a ready item whose publish branch carries no open pull request, or whose pull request carries no proof record naming a head and whose latest dispatch left no watchdog-stall-cancel record that anchors one
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming what is missing and a plain dispatch as the remedy
  Scenario: A third resume from the same pull request is refused
    Given a ready item whose pull request has already anchored two resumes
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming both earlier resumes and a plain dispatch as the remedy
  Scenario: A factory that no longer holds the run is an answer, not an outage
    Given a ready item whose earlier run's factory answers that it holds no run with the journaled id
    When the operator drives resume for the item
    Then the resume does not refuse on liveness and derives the resumed-at stage from the pull request's latest record
  Scenario: An unanswerable measurement is a refusal, not a proceed
    Given the forge cannot report the pull request head, or the factory's liveness query errors or goes unanswered
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming the measurement it could not take
```

## Scenario 144 — A plain re-dispatch of an item whose run died after publishing reclaims the stale publish branch and holds when it cannot measure

```gherkin
Feature: A dead run's publish branch does not block the item's next dispatch, and is never deleted blind
  Scenario: The dead head is preserved and the branch cleared before the run exists
    Given a ready item for which this checkout's dispatch journal records an earlier dispatch with a run id
    And origin carries the item's publish branch at the head that dispatch pushed
    And every factory the journal names for the item answers that it holds no non-terminal run for it
    When the item is dispatched again through dispatch or loop
    Then before the run exists the ref refs/livespec/preserved-publish/<item>/<head> is created on origin at that head
    And the publish branch is deleted on origin and its draft pull request is closed with its records still readable
    And the dispatch journal carries a publish-branch-reclaim record naming the branch, the head and the preservation ref
    And the new run's publish_draft stage pushes a plain fast-forward and opens a draft pull request
  Scenario: Reclaiming the same head twice rewrites nothing
    Given a preservation ref already exists for the item at the surviving head
    When the reclaim runs again for that head
    Then the preservation ref is unchanged and the reclaim completes
  Scenario: A first dispatch asks origin nothing
    Given an item for which no dispatch journal of any worktree sharing the repository's git common directory records a dispatch with a run id or a declared dispatch id
    And every such journal can be read
    When the item is dispatched
    Then no query to origin for a surviving publish branch is made
  Scenario: A live earlier run holds the reclaim
    Given a ready item whose publish branch survives and whose journaled run a factory the journal names reports as not terminal after the preamble's reconciliation
    When the item is dispatched again
    Then the publish branch is left exactly as it stands
    And the dispatch journal carries a publish-branch-reclaim-held record naming the reason live-run and the live run id
    And the dispatch proceeds and publish_draft refuses the non-fast-forward push as it did before the reclaim existed
  Scenario: Every measurement that cannot be taken holds
    Given origin cannot be asked whether the branch survives, or a factory the journal names cannot be asked whether the run is live, or the preserve or the delete fails
    When the item is dispatched again
    Then the publish branch is left exactly as it stands
    And the dispatch journal carries a publish-branch-reclaim-held record naming which measurement stopped the reclaim
    And the dispatch is not refused by the reclaim
  Scenario: The reclaim is a host-side act and publish_draft is unchanged
    Given a dispatched run whose publish_draft stage runs with no refresh-repair round before it
    When it pushes the publish branch
    Then the push is a plain fast-forward and no other ref is rewritten
```

## Scenario 145 — A failed post-merge janitor retains its complete output and exit code as a private artifact the journal names

```gherkin
Feature: A red post-merge janitor can be diagnosed from what it retained
  Scenario: A non-zero janitor retains both complete streams and the exit code
    Given a janitor-check-suite command that writes distinct stdout and stderr each longer than the journal row's bounded excerpt and exits with a distinctive non-zero code
    When the Dispatcher runs the post-merge janitor for a dispatch
    Then a JSON artifact with mode 0600 exists outside the janitor checkout, under the dispatch-journal directory, at a path naming the dispatch id and the stage
    And the artifact's stdout, stderr and exit_code keys carry the complete captured stdout, the complete captured stderr and that exit code
    And the journal row for the stage carries its existing bounded excerpt, the artifact path and the sha256 of the artifact's bytes
    And the sha256 of the file at that path equals the digest the row names
  Scenario: A second failure retains a second artifact
    Given a dispatch whose janitor-check-suite stage already retained an artifact
    When the same stage fails again in the same dispatch
    Then a second artifact exists under its own path and the first is byte-identical to what it was
    And each journal row names its own artifact
  Scenario: A write failure is journaled and changes nothing else
    Given the artifact location cannot be written
    When a post-merge janitor command exits non-zero
    Then the journal row for the stage says the artifact was not retained and names the reason
    And the stage's verdict is what it would be without retention
    And the command's argv, environment, umask and exit code are what they would be without retention
  Scenario: A passing janitor retains nothing extra
    Given a post-merge janitor command that exits zero
    When the Dispatcher runs the post-merge janitor
    Then no artifact is written for the stage and the journal row carries no artifact path
  Scenario: A killed or timed-out command is retained as a failure
    Given a janitor-check-suite command the runner ends by its timeout
    When the stage is journaled
    Then an artifact is retained whose timed_out key is set beside its exit_code
  Scenario: The reconcile-merged janitor is covered the same way
    Given reconcile-merged driven for an item whose janitor-check-suite command exits non-zero
    When the janitor stage is journaled
    Then the row names a retained artifact under a path naming the reconcile-merged invocation's journaled identifier and the stage
  Scenario: The artifact stays private to the invocation
    Given a retained artifact
    When the dispatch completes
    Then no ledger comment, pull request comment or dispatch result carries any of the artifact's content beyond the journal row's bounded excerpt
```

## Scenario 146 — Authoritative result readers distinguish fulfillment from observation failure

Governing clause: `contracts.md` §"Shared authoritative result reader".

```gherkin
Feature: one authoritative result reader for deadline and relay callers
  Scenario Outline: each typed result uses the named source and its exact effect
    Given a canonical repository and a typed <kind> result with fulfilled and unmet examples
    When the shared reader observes both targets through their configured source
    Then the fulfilled example is satisfied and the unmet example is unsatisfied
    And both carry repository, target, observation time and authoritative evidence identity
    Examples:
      | kind               |
      | item_status        |
      | item_comment       |
      | pull_request_state |
      | verified_proof     |
      | file_on_branch     |

  Scenario: observation failures cannot become a result
    Given two repositories with discriminating positive controls for each target kind
    When authentication, network, source resolution or malformed evidence prevents a read
    Then the result is unobservable and the obligation remains outstanding
    And the failed source is named after a bounded read
    And a stale local branch file cannot satisfy the remote blob result
    And a comment saying verified cannot satisfy a typed verified proof
    And a query to the wrong repository cannot discharge the requested target
```

## Scenario 147 — A plan deadline survives pointer rewrites and permits causal recovery

Governing clause: `contracts.md` §"Required result, budget and progress epoch".

```gherkin
Feature: the original obligation budget survives activity
  Scenario: every writer retains the first budget
    Given an unsatisfied required result with an absolute UTC deadline and positive max_handoffs
    When ordinary handoffs, supervisor handoffs and direct next_action writes repeat or change wording
    Then accepted handoffs consume units and direct pointer writes consume none
    And the original deadline and existing consumed units are unchanged
    When either exact budget boundary is reached
    Then continued work without fresh causal recovery is refused before a partial handoff or pointer mutation
    And expiry is observable even if no subsequent handoff is written

  Scenario: a fresh causal attempt permits bounded recovery, not a new original deadline
    Given an expired unmet result and measured item, host or unknown cause evidence
    When an authorized typed attempt names the previous epoch, executable next operation, unique attempt id and bounded attempt deadline
    Then it permits one cause-appropriate recovery attempt and retains the original obligation deadline
    And attempt registration, claim, actual command execution and fulfillment remain separately observable
    And unknown causes require diagnosis and known host causes do not alter the item repetition count
    When a repair child merges, a target is renamed, a relay is acknowledged, or approach prose changes
    Then none of those observations postpones the deadline or fulfills the original target
    And an old attempt, concurrent stale writer or duplicate operation cannot reset the budget
    And a partial write must be reconciled before dispatch
```

## Scenario 148 — Unattended resume observes expired, legacy and unobservable progress

Governing clause: `contracts.md` §"Required result, budget and progress epoch".

```gherkin
Feature: tracking findings preserve obligations without invented decisions
  Scenario: expired or unreadable results require authorized recovery
    Given an expired or unobservable obligation on an unattended plan resume
    When resume_directive evaluates the pointer
    Then it reports the precise finding and preserves the original budget and target
    And it does not blindly auto-dispatch the exhausted or unobservable action
    And it exposes an authorized causal diagnosis or recovery action to the independent consumer
    And human escalation requires a genuine human decision or authorization deficit
    And existing admission, HOLD and Red-Green guards remain enforced

  Scenario: legacy reads do not invent budgets
    Given a well-typed legacy three-key next_action
    When it is read
    Then it remains readable with a missing-tracking finding and no invented ledger write
    When its next sanctioned write occurs
    Then an impl or spec-op pointer requires valid required_result and budget fields
    And human or none pointers require explicit null tracking fields
    And any unmet prior obligation remains in history
```

## Scenario 149 — Acknowledgment cannot discharge a target-effect relay

Governing clause: `contracts.md` §"Relay delivery".

```gherkin
Feature: transport and target fulfillment have different evidence
  Scenario: timeout retains sender ownership until the target changes
    Given a stable relay id, expected result, original UTC deadline and sender obligation
    And queue delivery, peer receipt and consumption are acknowledged while the target is unchanged
    When the relay primitive records or rechecks the relay
    Then it remains unfulfilled and retains its sender and original deadline
    When that deadline expires with no new handoff
    Then the independent consumer performs bounded authorized recovery with the obligation retained
    And only an authoritative observation of the requested target effect discharges it

  Scenario: operation retries and target rechecks are distinguishable
    Given an existing relay observation
    When the same operation identity is retried
    Then it returns that recorded observation without extending the deadline
    When a distinct recheck observes the real effect
    Then delivery carries the new authoritative target evidence
    And a conflicting target requires explicit causal supersession preserving the original disposition
    And unobservable sources and wrong-repository observations never establish fulfillment
```

## Scenario 150 — Plan attention names missing results despite busy repair work

Governing clause: `contracts.md` §"Attention without confusing activity with results".

```gherkin
Feature: activity does not hide the required result
  Scenario: unrelated progress does not clear original expiry
    Given an expired unmet required result and a newly merged ancillary repair
    When needs-attention composes the normal attention envelope
    Then it retains the overdue-result fact with target, original budget, observation and sanctioned recovery action
    And the independently readable obligation remains available without another handoff

  Scenario: the historical window counts only attributable new effects
    Given an explicit configured window and handoff threshold with deterministic current time
    And dotted-id and explicit-edge children, an old closure and a legacy pointer
    When the window has threshold handoffs but no new attributable merged PR, closed child or verified proof
    Then the report names UTC window bounds, entry count and last required result or legacy marker
    When a new attributable milestone is observed
    Then only the historical-window condition clears while an unmet expired result remains overdue
    And unreadable sources yield unobservable findings rather than a confident no-result claim
    And missing or invalid policy produces a configuration finding rather than an invented limit
```

## Scenario 151 — Repeated item failures require a causal dispatch attempt

Governing clause: `contracts.md` §"Across-dispatch required-result progress".

```gherkin
Feature: comparable flat item failures are bounded before another claim
  Scenario: each attempt is compared with the high-water mark that preceded it
    Given comparable terminal history from each run's recorded remote factory
    And a positive configured redispatch_no_progress_limit
    When that many item-attributable non-advancing attempts follow the baseline
    Then the next drive refuses before claim with the relevant run ids, causes and high-water milestone
    And it requires a fresh typed causal recovery attempt before another epoch
    And the original required-result deadline is retained

  Scenario: controls discriminate progress, causes and observation artifacts
    Given histories that advance, fail for a known host cause, have an unknown cause, duplicate an event, include an active run or use incomparable workflows
    When admission classifies those histories using dependency-ordered successful milestones
    Then advancing history resets the flat count and a known host failure neither increments nor resets it
    And unknown causes and incomparable variants require diagnosis
    And duplicate observations and active runs do not count as terminal attempts
    And a local default factory cannot substitute for the run's recorded remote evidence
    And a repeated recovery-attempt identity cannot rearm the next dispatch
    And missing or invalid repetition policy refuses with a configuration diagnostic
```

## Scenario 152 — Independent recovery executes after Codex turn completion without wait registration

Governing clause: `contracts.md` §"Independent consumer across active and parked states".

```gherkin
Feature: the actual Codex-in-Herdr incident remains covered across turn completion
  Scenario Outline: real turn completion does not orphan the registered obligation
    Given normally installed released artifacts with a real authenticated Codex coordinator in Herdr
    And dispatch or delegation has registered its canonical unfinished result, original deadline and verified independent consumer
    And no explicit wait was registered and the pointer still names a completed diagnostic
    When that coordinator completes its actual turn and becomes <state>
    And the detached gate later fails or the original deadline expires
    Then the independently running consumer reconciles the stale pointer and executes the supported authorized recovery command once within 60 seconds
    And gate time, observation, claim, actual execution and resulting ledger action have distinct captured evidence
    And the original sender obligation remains until the authoritative target effect is fulfilled
    Examples:
      | state |
      | idle  |
      | gone  |

  Scenario: loss and duplicate events do not turn receipts into execution
    Given the same real Codex-in-Herdr scenario
    When the waiter is absent or killed, notification is dropped, or the first consumer owner is lost
    Then the independently supervised takeover path still meets the bounded recovery requirement
    And duplicate events, repeated scans and consumer restart converge on one observable supported command effect
    And an ambiguous execution result is reconciled before retry
    And unavailable consumer coverage is explicitly unmonitored and cannot pass incident proof

  Scenario: protected work defers mutation without dropping the obligation
    Given a valid human HOLD, running commit hook or open Red-Green pair on that scenario
    When failure or expiry is observed
    Then a specific safety deferral is recorded within 60 seconds and no prohibited command runs
    And the obligation and original deadline remain observable
    When the actual protected condition clears through its authorized path
    Then one still-authorized recovery executes within 60 seconds of observed clearance

  Scenario: the actual runtime and effect are the proof instruments
    Given the released host capture and its separate independent replay
    When a Claude Stop hook, simulated session, prompt submission, acknowledgment or claim is offered as the evidence
    Then it cannot satisfy the real Codex-in-Herdr recovery assertion
    And unsupported Codex no-wait recovery explicitly leaves this incident uncovered and the assertion unmet
    And other runtime results are labeled independently
    And renamed targets, repair milestones, acknowledgments and prose-only approaches do not extend the original deadline
    And unknown and known-host causes route to diagnosis without item-attributable increments
```

## Scenario 153 — An adopted assertion ceiling requires an attributed exception without waiving other gates

```gherkin
Feature: Conditional adopted assertion-count admission ceiling
  Scenario: No adoption preserves ordinary routing
    Given no committed dispatcher.adopted_assertion_count_ceiling
    When capture, groom, approval or dispatch considers an item with many assertions
    Then ordinary routing remains unchanged and analysis adopts no ceiling
  Scenario: Invalid adoption refuses before mutation
    Given a committed ceiling that is zero, negative, a boolean or not an integer
    When capture, groom, approval or dispatch resolves configuration
    Then it refuses before lifecycle mutation and names the invalid setting
  Scenario: Above-ceiling work without an exception returns for decomposition
    Given an adopted ceiling of 6 and an item with 7 sanctioned-parser assertions
    And the item carries no size_justification
    When capture, groom, approval or any factory dispatch entry path considers it
    Then it routes to backlog rather than ready or dispatch
    And the result names ceiling 6, observed count 7 and missing justification
  Scenario: The boundary itself is admitted to the remaining gates
    Given an adopted ceiling of 6 and an item with 6 sanctioned-parser assertions
    When capture, groom, approval or dispatch considers it
    Then it proceeds through the ordinary gates without a size exception
  Scenario: An attributed exception waives only the conditional size gate
    Given an above-ceiling item with exactly non-empty rationale, author and valid ISO-8601 at strings in size_justification
    When the item is considered for admission
    Then coherence, autonomous-verifiability, dependency, repository-target, acceptance-policy and approval gates still apply
    And a successful dispatch emits tdd.size_justified=true on its calibration span
  Scenario: A malformed exception is not a waiver
    Given an above-ceiling item whose size_justification has a missing or extra key, wrong-typed or blank value, or invalid timestamp
    When the item is considered for admission
    Then it routes to backlog and surfaces the missing-justification reason
  Scenario: A consensus first cut retains its stricter ceiling
    Given a consensus-approved first-cut candidate above the adopted ceiling with a valid size_justification
    When the cut is evaluated
    Then the candidate is not approved by the consensus tier
    And the ordinary attributed exception does not waive the consensus ceiling
```

## Scenario 154 — The first completed gate wakes a bounded multi-target wait

```gherkin
Feature: The first completed gate wakes a bounded multi-target wait
  Scenario: A later-listed failed gate wakes before a still-running sibling
    Given a bounded host wait watches a running gate A and a gate B that fails first
    And a third target was frozen from a pointer before that pointer changed
    When B reaches its terminal verdict
    Then the wait returns B and its actual exit code before A finishes
    And it reports all targets with their last observation and freshness
    And the third target remains the originally frozen identity
    And command outcome is distinct from B's exit code
  Scenario: Retargeting and cancellation preserve target safety
    Given a frozen target identity is reused or replaced
    When observation detects the identity mismatch
    Then it refuses retargeting and reports the diagnostic
    When the waiter is cancelled
    Then its target processes remain untouched
```

## Scenario 155 — A pane wait ends on non-working, missing and uncertain states

```gherkin
Feature: A pane wait ends on non-working, missing and uncertain states
  Scenario Outline: Only working continues a Herdr wait
    Given a pane qualified by backend, server instance, pane id and process generation
    When the pane is <state>
    Then the wait ends with a distinct observed or diagnostic outcome
    And uncertainty is not represented as success
    Examples:
      | state |
      | done |
      | blocked |
      | idle |
      | unknown |
      | missing |
      | unreadable |
      | server generation changed |
      | process generation changed |
```

## Scenario 156 — The shared deadline bounds stalled probes and telemetry

```gherkin
Feature: The shared deadline bounds stalled probes and telemetry
  Scenario: Invalid deadline is refused
    Given a missing, non-positive or non-finite deadline budget
    When wait is requested
    Then arming is refused before blocking
  Scenario: Hung probes and exporter do not serialize completion
    Given a finite monotonic deadline, a hung first probe and a finished sibling
    And an exporter is blocked
    When wait observes its targets
    Then the sibling is independently observable with cadence no slower than one second
    And all observations and final return share the original deadline
    And hung probe work is cancelled at expiry without cancelling the target
    And the result reports unfinished targets and timestamped stale observations
```

## Scenario 157 — Inventory distinguishes produced and acknowledged wake-ups

```gherkin
Feature: Inventory distinguishes produced and acknowledged wake-ups
  Scenario: Atomic registration precedes blocking
    Given concurrent waiters on the primary repository
    When each arms and one waiter dies or its process id is reused
    Then each schema-versioned inventory record survives independently
    And it preserves session/wait identity, frozen targets, deadline, process generation and observation sequence
    When inventory re-observes a completed target
    Then it reports ended-but-unacknowledged, overdue or running-without-waiter as appropriate
    And corrupt, unsupported and unreadable records are explicitly unavailable
    When the receiving owner invokes ack
    Then receipt acknowledgement is recorded separately from execution consumption and fulfillment
    And receipt-only mismatch clears without discharging the outstanding result
    And unacknowledged records survive until explicit disposition
    And acknowledged retention and export queues remain bounded
```

## Scenario 158 — The host turn-end check exposes outstanding wait mismatches

```gherkin
Feature: The host turn-end check exposes outstanding wait mismatches
  Scenario: A real owning turn cannot hide unfinished work with no wait
    Given an ended unacknowledged target or unresolved dispatch obligation
    When the installed check runs before its owning session finishes the turn
    Then it cross-checks launch obligations, actual target evidence and independent wake/consumer registration
    And a missing wait record does not hide outstanding work
    And unsupported coverage is an explicit unmonitored finding
    And existing stricter supervised completion refusals are preserved
  Scenario: Runtime capability is stated honestly
    Given automatic completion-hook support is claimed for a runtime
    When installed-runtime proof is evaluated
    Then that exact runtime's hook must have been exercised
    And missing hooks require explicit check guidance and launch-time independent consumer coverage
    And factory execution guidance excludes blocking host waits
```

## Scenario 159 — Wait inventory and measurements arrive in Honeycomb without controlling liveness

```gherkin
Feature: Wait inventory and measurements arrive in Honeycomb without controlling liveness
  Scenario: Lifecycle and empty snapshots have queryable scrubbed identities
    Given the configured livespec host-local enrichment/scrub and Honeycomb route
    And a unique session/wait with known work-item, dispatch and run associations
    When arming, observation changes, return, inventory and receipt acknowledgement occur
    Then identity-linked OTLP events and typed numeric measurements arrive in Honeycomb
    And service is livespec-dispatcher, namespace livespec-family and scope livespec.orchestrator.session_wait with a version
    And snapshots carry observation time and identity, including a zero-count summary
    And unchanged observation exports occur at most once per minute
    And lifecycle changes remain immediately distinguishable
    And unknown associations are not invented and secrets or raw commands never leave the host
  Scenario Outline: Export degradation does not control recovery
    Given export is <condition>
    When wait, inventory or obligation recovery executes
    Then local deadlines, results and recovery remain effective
    And configured failure, partial rejection or drops are reported locally without recursive telemetry
    And absent configuration is explicitly local-only
    Examples:
      | condition |
      | unconfigured |
      | unavailable |
      | partially rejecting |
      | queue full |
```

## Scenario 160 — Dispatch obligations survive coordinator FINAL without wait registration

```gherkin
Feature: Dispatch obligations survive coordinator FINAL without wait registration
  Scenario: Real Codex in Herdr finishes before its gate fails
    Given normally installed releases and a real authenticated Codex coordinator in Herdr
    And an authorized detached dispatch has a canonical required result, original deadline and independently verified consumer
    And launch intent is recorded before the effect and attached to the actual gate identity
    When Codex completes its actual turn including FINAL without ever invoking wait
    And the detached gate later fails
    Then the independent consumer discovers the obligation while the coordinator is idle or gone
    And refreshes the stale pointer to an already completed diagnostic
    And executes the same authorized work's supported recovery command once within 60 seconds without human input
    And records execution evidence and the resulting authorized next action
    And an alert, queued prompt, acknowledgement or idle replacement does not satisfy the assertion
    And a Claude Stop hook or simulated session cannot satisfy this Codex/Herdr proof
    And other runtime results are labeled independently
  Scenario: Unsupported Codex coverage cannot pass the incident proof
    Given Codex no-wait protection is unsupported on the host
    When the incident proof evaluates its result
    Then the incident is explicitly uncovered and its proof assertion remains unmet
  Scenario: A partial launch recovers its intent without duplicating the effect
    Given a crash after recording launch intent or after launching but before attaching the gate identity
    When reconciliation resumes with the stable operation identity
    Then it queries the real effect and completes the original obligation attachment idempotently
    And preserves the original deadline, epoch and authority without killing the target
```

## Scenario 161 — Independent recovery survives notification and owner loss

```gherkin
Feature: Independent recovery survives notification and owner loss
  Scenario Outline: Durable obligations survive lost transient control
    Given the real Codex/Herdr released-host obligation and installed independently supervised recovery service
    When the gate fails or its original result deadline expires
    And <loss> occurs
    Then the normal reconciliation or service takeover path executes authorized recovery within 60 seconds
    And stale owner generations are fenced
    And inventory/check names the verified runtime, backend, service, recovery route and bounded polling/takeover budgets
    Examples:
      | loss |
      | no waiter was ever created |
      | waiter dies |
      | notification is dropped |
      | coordinator is gone |
      | first recovery owner dies |
  Scenario: Missing all recovery coverage is not prevention
    Given independently verifiable owner and takeover coverage is absent
    When protected launch or completion is requested
    Then an explicit unmonitored refusal or finding is reported
    And the host proof remains unmet
    And an unreadable authority is unobservable rather than an empty obligation set
```

## Scenario 162 — Receipt is distinct from consumed recovery and fulfilled work

```gherkin
Feature: Receipt is distinct from consumed recovery and fulfilled work
  Scenario: Receipt and claim do not execute work
    Given a produced notification, receipt acknowledgement and claimed recovery with no execution
    When inventory and canonical result readers inspect it
    Then recovery remains unconsumed and the original result outstanding
    When actual execution evidence and its resulting next action are recorded
    Then execution consumption is separately observable
    And only the authoritative canonical result reader can establish target fulfillment
    And original deadline and epoch are preserved
    And identity-linked OTLP observations distinguish each transition and actual latency
```

## Scenario 163 — Duplicate and stale recovery reconcile safely

```gherkin
Feature: Duplicate and stale recovery reconcile safely
  Scenario: Duplicate triggers converge on one supported command effect
    Given duplicate events and competing recovery generations for the same canonical attempt
    And a stale diagnostic or failed local gate whose remote PR already merged
    When the consumer re-reads scope, authorization, safety, epoch, ledger, forge and recorded remote factory
    Then it selects a typed sanctioned action based on current authoritative evidence
    And serialized generation-fenced ownership yields one supported command effect
    And no blind redispatch follows solely from the local gate failure
    And a declared changed approach does not reset the original result deadline
  Scenario: An ambiguous execution receipt requires effect lookup
    Given execution may have completed before its receipt was recorded
    When a replacement consumer recovers the attempt
    Then it queries the durable command effect before retrying
    And an unobservable lookup preserves uncertainty rather than executing twice
    And the system claims no universal exactly-once arbitrary shell execution
```

## Scenario 164 — Human HOLD and commit safety barriers retain recovery obligations

```gherkin
Feature: Human HOLD and commit safety barriers retain recovery obligations
  Scenario Outline: Real safety barriers defer mutation without losing work
    Given the real Codex/Herdr released-host obligation and <barrier>
    When a failure or original deadline expiry occurs
    Then observation continues and the original obligation and deadline are retained
    And a specific safety-deferral observation is recorded within 60 seconds of the trigger
    And recovery mutation is queued without interrupting or abandoning protected work
    When the actual authorized safety barrier clears
    Then one still-authorized recovery command executes within 60 seconds of clearance
    Examples:
      | barrier |
      | human HOLD with authority, reason, owner and release condition |
      | running commit hook |
      | open Red-Green pair |
  Scenario: Idle state is not an invented human block
    Given an idle session, unanswered notification, prose deadline or stale completed diagnostic
    When recovery evaluates safety
    Then those facts alone do not create a HOLD
    And expiry triggers authorized diagnosis
    And only a genuine decision outside current authority routes to a person
```

## Scenario 165 — Completed-cycle measurements explain runtime non-convergence

```gherkin
Feature: Runtime progress is measured from the dispatched work, not inferred from a merge

  Scenario: A converging run exposes replayable completed-cycle measurements
    Given a dispatched item with two effective assertions and two verified Red-Green pairs
      And each pair has readable source trees and valid capture and verification times
    When terminal calibration is recorded after the ordinary acceptance gates pass
    Then the journal and span expose two distinct completed cycles in one-based order
      And each cycle identifies its source pair, changed product logical lines and elapsed seconds
      And added plus removed product logical lines exclude test, documentation and formatting-only changes
      And both projections expose the dispatched assertion count and measurement method
      And no progress-deficit bounce is reported

  Scenario: Failed and unmerged work retains observable progress
    Given a dispatched run has not merged but has a preserved verified Red-Green pair
    When the Dispatcher evaluates runtime progress
    Then it measures that pair without requiring a merged PR
      And duplicate observations, open Reds, suite-green-only commits and unrelated history do not increase the completed-cycle count

  Scenario: An observed deficit contributes only at the existing fix-loop cap
    Given an item has three effective assertions and one observed completed cycle
    When the existing configured fix-loop cap is reached
    Then the item returns to backlog through the sanctioned non-convergence path
      And its reason names the cap, one completed cycle and three effective assertions
      And the terminal journal and span identify the progress deficit as a bounce contributor
    But before that cap the same count difference alone does not trigger a bounce

  Scenario: Ordinary acceptance at the cap does not waive the progress gate
    Given an item's ordinary acceptance first passes on the cap-th allowed attempt
      And its observed completed-cycle count remains below its effective assertion count
    When convergence is evaluated at that boundary
    Then the additional progress condition still returns the item to backlog
      And the reason names the observed deficit rather than claiming ordinary acceptance failed

  Scenario: Sufficient cycle count does not prove acceptance
    Given an item's completed-cycle count equals its effective assertion count
      And an ordinary acceptance gate still fails through the existing fix-loop cap
    When non-convergence is evaluated
    Then the ordinary backlog bounce still applies
      And a completed-cycle deficit is not falsely reported as its cause

  Scenario Outline: Only an adopted runtime ceiling can contribute a measured breach
    Given a maintainer has separately adopted the committed <setting> value of 10
      And a completed cycle has an observed corresponding measurement of <observed>
      And the item carries a valid intake size justification
    When runtime limits are evaluated at the pre-merge convergence verification boundary
    Then the runtime ceiling result is <result>
      And a breach uses the sanctioned backlog bounce and names the setting, both values and cycle identity
      And the intake exception does not waive a runtime breach
    Examples:
      | setting                                           | observed | result    |
      | dispatcher.adopted_cycle_product_lloc_ceiling       | 10       | no breach |
      | dispatcher.adopted_cycle_product_lloc_ceiling       | 11       | breach    |
      | dispatcher.adopted_cycle_duration_seconds_ceiling   | 10       | no breach |
      | dispatcher.adopted_cycle_duration_seconds_ceiling   | 11       | breach    |

  Scenario: Absence of adoption leaves size and duration observational
    Given neither runtime ceiling setting is present
    When a run records large completed-cycle measurements
    Then no runtime ceiling breach is manufactured
      And existing cap-based non-convergence and ordinary gates remain effective
      And calibration analysis does not adopt a numeric threshold

  Scenario Outline: Invalid runtime policy refuses before mutation
    Given either runtime ceiling is configured as <value>
    When the Dispatcher resolves policy before claiming an item
    Then configuration resolution refuses before claim or lifecycle mutation
    Examples:
      | value         |
      | zero          |
      | negative      |
      | boolean       |
      | non-integer   |

  Scenario: Runtime adoption cannot be changed through the API policy surface
    Given either runtime ceiling is named in an API policy update
    When the public configuration update surface validates the requested setting
    Then it refuses that non-API-configurable setting without changing committed policy

  Scenario: An observed empty series differs from an unreadable series
    Given the current dispatch's complete readable series contains zero verified completed pairs
      And its effective assertion count is positive
    When the existing fix-loop cap is reached
    Then zero is recorded as an observed completed-cycle count
      And the observed deficit contributes to the backlog bounce

  Scenario: Missing evidence is not a healthy-looking zero or a fabricated deficit
    Given a run's source series or assertion count cannot be established
    When it reaches the existing fix-loop cap
    Then the progress comparison is reported unobserved with a reason
      And ordinary cap-based non-convergence still applies
      And journal nulls and omitted numeric span attributes agree with explicit absence diagnostics

  Scenario: A missing individual measurement does not erase known completed progress
    Given a verified completed-pair count is independently established
      And its product counter is unsupported or its duration timestamps are invalid or reversed
    When terminal calibration and runtime ceilings are evaluated
    Then only the affected measurements are unobserved with reasons
      And the established pair count is retained
      And absent measurements do not manufacture an adopted-ceiling breach
```

## Scenario 166 — Successful terminal evidence survives an engine terminal-event persistence failure

Governing clause: `contracts.md` §"Dispatcher successful terminal evidence".

```gherkin
Feature: reconcile successful completion separately from run-store loss
  Scenario Outline: authenticated successful completion reaches normal publication reconciliation
    Given the latest structured checkpoint identifies the current run and its successful published head
      And every required stage on its configured successful terminal route succeeded
      And the checkpoint <terminal_shape>
      And the expected repository and publish branch have a matching pull request at that head
      And the engine reports a zero-status worker exit before a terminal run event was persisted
    When the Dispatcher classifies the run through its ordinary dispatch path
    Then it continues normal pull-request and merge reconciliation for that pull request
      And it reports the observed publication or merge state without a false implementation failure
      And the journal identifies the run and both evidence legs separately from the conflicting engine conclusion
      And ordinary merge, proof, janitor and acceptance guards still apply
    Examples:
      | terminal_shape                                           |
      | records the successful exit completed                    |
      | records the final successful stage with next node at exit |

  Scenario Outline: insufficient or contrary evidence cannot establish successful completion
    Given an engine conclusion reports failure for the current run
      And <defect>
    When the Dispatcher evaluates the terminal evidence conflict
    Then the ordinary non-green disposition remains
      And no stale or unavailable evidence is reported as successful completion
    Examples:
      | defect                                                       |
      | the latest checkpoint is unavailable                         |
      | the checkpoint belongs to another run                        |
      | only an earlier attempt has a successful checkpoint          |
      | the latest checkpoint is intermediate                        |
      | a required stage failed                                      |
      | the run was cancelled                                        |
      | the terminal route is needs-human or non-converged            |
      | the matching pull request is absent or cannot be observed     |
      | the pull request has a different head, branch or repository   |
      | the pull request is closed without merging                   |
      | the worker exited nonzero                                    |

  Scenario: successful classification does not grant merge or acceptance
    Given both successful terminal evidence legs qualify despite the engine conclusion
      And the pull request is held from merging or a later ordinary check fails
    When the Dispatcher continues reconciliation
    Then the hold or failure has its ordinary disposition
      And successful workflow classification does not force a green dispatch or close the item
```

## Scenario 167 — A failed janitor names the aggregate runner's failed targets

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Failed post-merge janitor target attribution".

```gherkin
Feature: report failure attribution from the aggregate summary
  Scenario Outline: complete failed-target names survive unrelated later output
    Given a real janitor command exits nonzero and emits a structured Failed targets summary
      And its summary names <targets> on stdout before later output exceeds the diagnostic tail bound
      And its stderr tail names a passing recipe not in that summary
    When the Dispatcher reports the post-merge janitor result
    Then the outcome detail and janitor-post-merge journal row name every summarized failed target
      And they do not attribute the failure to the passing recipe
      And the journal names the retained private complete-output artifact and its digest
      And the original nonzero exit and ordinary item disposition are preserved
    Examples:
      | targets                                  |
      | two distinct failing targets             |
      | a target list longer than the tail bound |

  Scenario: absence of a structured summary does not invent a cause
    Given a real failed janitor emits distinct stdout and stderr without a structured Failed targets summary
    When the Dispatcher reports its result
    Then it labels bounded excerpts from both streams as observations
      And it does not claim a recipe in either excerpt caused the failure
      And the full private artifact remains the deep-diagnosis reference when retention succeeds

  Scenario: retention failure does not erase the observed attribution
    Given a failed janitor emitted a structured Failed targets summary
      And its private artifact cannot be written
    When the Dispatcher reports its result
    Then it still names the observed failed targets and journals the retention-write failure reason
      And the command exit code and ordinary non-green disposition are unchanged
      And it does not fabricate a retained artifact path or digest
```

## Scenario 168 — An authorized plan resume continues to the archive without a picker, and the typed next action names every remaining step

Governing clause: `contracts.md` §"Typed `next_action` and `last_session`".

```gherkin
Feature: a plan session drives to the archive under a recorded authorization
  As a maintainer who has told a plan session to finish the plan
  I want every resume to take the recorded next step until the plan archives
  So that the plan does not stop at the last closed child or wait on a question nobody asked

  Scenario: a continuation ruling lets an attended resume take the pointer
    Given an open plan epic carrying a current continuation ruling until archive
    And next_action kind impl with a non-empty ref and an unexpired budget
    When the plan operation resumes attended
    Then resume_directive returns ask false and the action impl:<ref>
    And the reason names the continuation ruling

  Scenario: without a ruling the attended picker still shows the default
    Given the same epic with no continuation ruling
    When the plan operation resumes attended
    Then resume_directive returns ask true
    And the picker's default is the recorded next_action

  Scenario: a human pointer raises the picker even under a ruling
    Given the same epic with a current ruling and next_action kind human
    When the plan operation resumes attended
    Then resume_directive returns ask true with the kind as the reason

  Scenario: the proof, review and archive steps are typed pointers
    Given a plan whose children are all closed
    When the session records the next action
    Then while no verified record covering every plan assertion that is not human_attested postdates both the latest captured record and the last carrier-map event, and the newest plan record is not a captured one, the pointer is kind proof with ref capture:<epic-id>
    And while that verified record is absent and the newest plan record is captured the pointer is kind proof with ref verify:<epic-id>
    And once that verified record exists, while a human_attested plan assertion lacks a human_attested record postdating the last carrier-map event, the pointer is kind human naming that assertion and no capture or verify is recorded
    And once the proof leg is met, while the timeline holds no valid completeness-review evidence the pointer is kind review
    And once all three archive legs are met the pointer is kind archive and no further capture is recorded
    And a not_reproduced record newer than every verified record unmeets the proof leg and returns the pointer to kind proof with ref capture:<epic-id>

  Scenario: a wait on another plan's record is a typed pointer with a deadline
    Given a plan assertion carried by another plan's host record that does not exist yet
    When the session records the next action
    Then the pointer is kind await with ref epic:<other-epic-id>, a required result of kind verified_proof on that epic and a budget deadline
    And a resume after the deadline reports the obligation expired rather than waiting again

  Scenario: a stale pointer is reconciled, not executed
    Given next_action kind impl whose required_result is item_status closed for the item its ref names
    And that item is already closed
    When the plan operation resumes
    Then the pointer is reported stale with the observed status closed
    And the resume advances to the next step derived from the ledger instead of dispatching the closed item

  Scenario: a pointer at a live run reattaches instead of re-dispatching
    Given next_action kind impl whose ref names a work item with a live factory run
    And its required_result is still unsatisfied on the authoritative reader and its tracking checks permit continuation
    When the plan operation resumes
    Then the pointer becomes kind await with ref run:<id>
    And its required result, epoch, original deadline and handoff count are unchanged
    And no second dispatch is started

  Scenario: an unsatisfied wait within budget is not stale
    Given next_action kind await whose required result is unsatisfied and whose budget is unexpired
    When the plan operation resumes
    Then the pointer is reported as waiting with the observation
    And it is not rewritten

  Scenario: the primitive refuses a continuation ruling from an unattended session
    Given a session running under LIVESPEC_PLAN_UNATTENDED
    When it records a plan-continuation: authorized ruling
    Then the scope-event primitive refuses naming the unattended session

  Scenario: a hand-written ruling is a finding and is not acted under
    Given a plan-continuation: authorized comment lacking the recorded-attended line the primitive writes
    When the plan_continuation_ruling check runs
    Then it reports the ruling
    And an attended resume presents the picker instead of acting under it
```

## Scenario 169 — A dispatch naming a catalog environment runs the catalog's image, and the journal names the image source

```gherkin
Feature: Sandbox image source

  Scenario: the catalog environment's image is the image the container runs
    Given a factory declaring catalog environment livespec-ci whose image is image A
    And dispatcher.fabro_sandbox_image set to image B
    When the Dispatcher launches a dispatch to that factory
    Then the launch carries image A
    And the dispatch journal records the image source catalog_environment livespec-ci

  Scenario: a factory with no catalog environment uses the committed image
    Given a factory declaring no catalog environment
    And dispatcher.fabro_sandbox_image set to image B
    When the Dispatcher launches a dispatch to that factory
    Then the launch carries image B
    And the dispatch journal records the image source dispatcher.fabro_sandbox_image
```

## Scenario 170 — A failed engine checkpoint commit names its node and cause and rests the item at needs-human

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Failed engine checkpoint commit attribution".

```gherkin
Feature: attribute a failed engine checkpoint commit and route its decision to the ledger
  Scenario Outline: a hook refusal names the node, the failed hook command and every failed target
    Given a dispatched run ends workflow_error because the engine checkpoint commit of node <node> failed
      And the run's checkpoint.failed event carries an output tail with carriage-return line-feed line endings
      And that tail carries a structured Failed targets summary naming <targets>
      And the hook runner's summary marks hook command <hook> failed
      And recipe error lines outside the summary name other recipes
    When the Dispatcher reports the dispatch result
    Then the outcome is blocked at stage fabro-run
      And the outcome detail names the run, node <node>, the engine's checkpoint error, hook command <hook> and every one of <targets>
      And it does not attribute the failure to a recipe outside the summary
      And the checkpoint-failure journal row carries node <node>, attribution failed-targets, failed_hook_commands <hook> and failed_targets <targets>
      And the item rests blocked with blocked_reason needs-human and a needs-human-blocked journal row
      And a livespec-checkpoint-failure ledger comment on the item names the same node, hook command and targets
      And the dispatch reports exit code 4
    Examples:
      | node       | hook                | targets                                    |
      | implement  | 03-check-pre-commit | check-master-ci-green                      |
      | review_fix | 03-check-pre-commit | check-per-file-coverage and check-coverage |

  Scenario: a commit-msg refusal without a Failed targets summary names only the failed hook command
    Given a dispatched run's engine checkpoint commit of node fix failed with git commit failed (exit 1)
      And its checkpoint.failed tail has no Failed targets summary
      And the hook runner's summary marks hook command 01-red-green-replay failed
    When the Dispatcher reports the dispatch result
    Then the outcome detail and the checkpoint-failure journal row name node fix and hook command 01-red-green-replay
      And failed_targets is empty
      And the item rests blocked with blocked_reason needs-human

  Scenario: a tail with no recognized summary is labelled as an observation
    Given a dispatched run's engine checkpoint commit failed with git commit failed (exit 1)
      And its checkpoint.failed tail carries neither a Failed targets summary nor a recognized hook runner summary
    When the Dispatcher reports the dispatch result
    Then the checkpoint-failure journal row has attribution observation and a bounded observation_excerpt
      And the outcome detail labels the excerpt as an observation
      And it does not claim any hook, target or recipe in the excerpt caused the failure
      And the ledger comment carries no excerpt of the captured output

  Scenario: a checkpoint budget expiry names the node, the configured budget and the engine's measurement
    Given the dispatch submitted a run configuration whose run.checkpoint commit_timeout is 15m
      And the run ends because the checkpoint operation budget was exceeded on node fix with git commit timed out after 900004ms
    When the Dispatcher reports the dispatch result
    Then the outcome detail and the checkpoint-failure journal row name node fix, the timed-out operation git commit, configured_budget_seconds 900 and engine_reported_elapsed 900004ms
      And the engine's figure is labelled as the engine's measurement, not as the configured budget
      And the checkpoint-failure journal row has attribution budget-expiry
      And the item rests blocked with blocked_reason needs-human

  Scenario: a git add failure with no output tail is attributed to the engine error alone
    Given a dispatched run's engine checkpoint of node dod_gate failed with git add failed
      And its checkpoint.failed event carries no output tail
    When the Dispatcher reports the dispatch result
    Then the checkpoint-failure journal row has attribution engine-error, node dod_gate and checkpoint_error git add failed
      And failed_targets and failed_hook_commands are empty
      And the item rests blocked with blocked_reason needs-human

  Scenario: the uncommitted work is recorded by reference
    Given a run ended on a failed engine checkpoint
      And its run.failed event carries a terminal patch
      And the run's export holds no stage diff artifact
    When the Dispatcher records the dispatch
    Then the checkpoint-failure journal row and the livespec-checkpoint-failure comment carry the terminal patch's byte size and sha256 digest
      And the preserve-by-reference pointer for the run is written as for any non-green run

  Scenario: unreadable events still produce the disposition without invented targets
    Given a run's terminal failure message reads git checkpoint commit failed for node implement: git commit failed (exit 1)
      And the run's events cannot be read from the dispatch's resolved factory
    When the Dispatcher reports the dispatch result
    Then the outcome is blocked and names node implement and the engine's checkpoint error
      And the checkpoint-failure journal row records events_read as the failure reason
      And terminal_patch_bytes and terminal_patch_sha256 are null and both records state the terminal patch is unavailable rather than absent
      And failed_targets is empty and no cause is asserted
      And the item rests blocked with blocked_reason needs-human

  Scenario: an earlier classification keeps its route
    Given a run whose output carries the needs_human terminal's sentinel
    When the Dispatcher reports the dispatch result
    Then no checkpoint-failure journal row is written
      And the needs_human terminal's existing outcome stands
```

## Scenario 171 — A still-running master CI run makes the preflight wait, not refuse

```gherkin
Feature: Master-CI preflight waits on a pending run instead of treating it as failed
  As an operator dispatching work while the default branch's CI is still running
  I want the preflight to wait for that run's verdict
  So that a run that has not failed is never reported as a failure

  Scenario: a pending run that concludes green lets the dispatch proceed
    Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
    When that job concludes green within the bounded wait
    Then the dispatch proceeds and the journaled pass names the run that concluded green

  Scenario: a pending run that concludes red refuses as red
    Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
    When that job concludes red within the bounded wait
    Then the dispatch is refused naming the red run with the reason master-ci-red

  Scenario: a newer run replaces the one being waited on
    Given the preflight is waiting on an in-progress run
    When a newer run starts on the default branch and concludes green within the original bounded wait
    Then the preflight waits on the newer run and the journaled pass names the newer run

  Scenario: a run still pending at the bound is deferred, not failed
    Given the latest default-branch run stays in progress for the whole bounded wait
    When the bound expires
    Then the dispatch does not start and the work item is not claimed
      And the journal records reason master-ci-pending with status deferred
      And the operator text says the run is still running and has not failed, without the ERROR prefix or the red-default-branch recovery text
```

## Scenario 172 — A stall-watchdog cancel is never non-convergence: a first cancel is released and recovered, a second rests for a human

```gherkin
Feature: A stall-watchdog cancel keeps the work it can and asks a human only on a repeat
  Scenario: The watchdog does not cancel a run inside an open command node
    Given a dispatched run whose last agent stage completed and whose event stream shows the janitor command node started and not completed
    And the heartbeat has not advanced for longer than the stall window
    When the watchdog samples the run before the janitor node's resolved timeout has elapsed
    Then it does not cancel the run
  Scenario: A newer event is not masked by an older heartbeat
    Given a dispatched run whose heartbeat's newest beat is older than the newest event in its event stream
    When the watchdog samples the run
    Then the sample reports the newer event's instant as the run's progress
  Scenario: A run with no progress and no open command node is still cancelled
    Given a dispatched run whose heartbeat and event stream both stay unchanged for the full stall window with no command node open
    When the watchdog samples it
    Then it cancels the run as stalled-no-progress
  Scenario: A first stall cancel after publishing is released and resumed
    Given a dispatched item whose run completed publish_draft, pushing a head to an open draft pull request
    And the watchdog cancels the run as stalled-no-progress while it executes proof_capture
    And the item's preceding dispatch did not end stalled-no-progress
    When the Dispatcher records the outcome
    Then the journal carries a watchdog-stall-cancel record naming the run id, the factory, proof_capture as the stage, the pull request and that head
    And a ledger comment on the item names the run id, the factory, the stage, the pull request and the head
    And the item is returned to ready with no blocked_reason, is not moved to backlog, and no non-convergence-bounce record is journaled
    And the next dispatch of the item invokes resume and journals neither a publish-branch-reclaim record nor a publish-branch-reclaim-held record
    And when the resumed run's review approves, its record shows no visit to dod_gate, implement or janitor
  Scenario: A first stall cancel before publishing is released and recovered from preserved work
    Given a dispatched item whose run the watchdog cancels as stalled-no-progress while it executes implement
    And the item's preceding dispatch did not end stalled-no-progress
    And the failed run has verified preserved work at an immutable commit SHA
    When the Dispatcher records the outcome and the ordinary admission valve next admits the item
    Then a ledger comment on the item names the run id, the factory and implement as the stage
    And the dispatch claim is released and the item returns to ready with no blocked_reason before admission
    And the item is not moved to backlog and no non-convergence-bounce record is journaled
    And the next run is a plain dispatch seeded from that preserved commit
    And its seed record names the source run, remote, immutable commit SHA and preservation reference

  Scenario: A first stall release is replayable without affecting a newer claim
    Given an interrupted first-stall release for a recorded factory and run
    When reconciliation completes that release and later replays it after a newer dispatch has claimed the item
    Then the original release is completed without duplicate cancel records
    And the newer dispatch claim is not released
    And the released stall consumes no budget of the three rework caps
    And it neither increments nor resets the across-dispatch non-progress count

  Scenario: A second stall is an item-attributable terminal
    Given an item whose preceding dispatch ended stalled-no-progress
    And the current attempt ends stalled-no-progress without advancing beyond its established progress high-water mark
    When the Dispatcher records the terminal
    Then the item rests at blocked with blocked_reason needs-human
    And the terminal increments the across-dispatch non-progress count once
    And replaying the same observation does not increment it again

  Scenario: The cancel record uses the run's last published head
    Given a run that completed publish_draft twice and is cancelled between its last completed publish_draft and proof_capture
    And origin has since moved to a different head
    When the Dispatcher journals watchdog-stall-cancel
    Then the record names the work-item, dispatch id, run id, factory and proof_capture as the selected next stage
    And it names the pull request and the head pushed by the run's last completed publish_draft
    And it does not substitute origin's current head

  Scenario: An unreadable published head is explicit
    Given a cancelled run whose event stream records a completed publish_draft
    And the head pushed by that node cannot be read from the run's record
    When the Dispatcher journals watchdog-stall-cancel
    Then the record explicitly states that the published head could not be read
    And that record cannot anchor a resume

  Scenario: A cancel between publication and capture can anchor resume
    Given a ready item whose latest dispatch was cancelled between its last completed publish_draft and proof_capture
    And no proof record carries that dispatch's identifier
    And its cancel record names the unchanged published head
    And all other resume preconditions pass
    When resume runs for the item
    Then the cancel record anchors the published head and the new run enters at proof_capture

  Scenario: A proof record takes precedence over a cancel anchor
    Given a ready item whose latest dispatch has both a proof record and a watchdog-stall-cancel record
    And the proof record carries that dispatch's identifier and names a head
    And all other resume preconditions pass
    When resume selects its anchor
    Then it uses the proof record rather than the cancel record

  Scenario Outline: A cancel during rework cannot anchor resume
    Given a ready item whose latest dispatch was cancelled at <stage> after an earlier completed publish_draft
    And no proof record on the pull request names a head
    And its cancel record names the earlier published head
    When resume runs for the item
    Then it refuses before any run exists and names a plain dispatch as the remedy

    Examples:
      | stage         |
      | janitor       |
      | fix           |
      | publish_draft |
  Scenario: A second consecutive stall cancel rests for a human
    Given an item whose preceding dispatch ended stalled-no-progress
    When the watchdog cancels the item's current run as stalled-no-progress
    Then the item rests at blocked with blocked_reason needs-human
    And its ledger comment names both cancelled runs, their factories and stages, and the remedy the resume refusal ladder computes
    And no further dispatch or resume is invoked automatically
  Scenario: Calibration does not read a stall cancel as non-convergence
    Given a journal holding a stall-cancelled dispatch and a fix-loop-cap non-convergence
    When the calibration analysis pass runs
    Then it counts the fix-loop-cap dispatch as a non-convergence observation
    And it does not count the stall-cancelled dispatch as one
```

## Scenario 173 — The progress watchdog observes its bound run by id and never lists the factory's run history

```gherkin
Feature: The watchdog's poll cost does not grow with the factory's run history
  Scenario: A bound run is polled by id
    Given a dispatch whose run id the Dispatcher has bound
    When the watchdog polls the run
    Then the poll reads that run by its id from the factory
    And the poll does not list the runs the factory holds
  Scenario: Discovery before the id is bound is unchanged
    Given a dispatch whose run id the Dispatcher has not yet bound
    When the watchdog polls for the run
    Then it may list the runs the factory holds to discover the run
  Scenario: A terminal run is still detected
    Given a dispatch whose bound run reaches a terminal state
    When the watchdog polls the run by its id
    Then it reports the run's terminal state exactly as it does when it lists runs
  Scenario: A disappeared run is still detected
    Given a dispatch whose bound run the factory no longer holds
    When the watchdog polls the run by its id and the factory reports no such run
    Then it reports the run as disappeared from the server
  Scenario: A failed per-run read is not a disappearance
    Given a dispatch whose bound run is still held by the factory
    When a per-run read of the run fails or returns an answer the watchdog cannot interpret
    Then the watchdog does not report the run as disappeared
    And it treats the poll as unobservable
```

## Scenario 174 — The Definition-of-Done judgement runs before admission and holds an item it would rest at needs-human

```gherkin
Feature: A judged Definition-of-Done defect is found before a dispatch is spent on it
  Scenario: An item the judgement would rest at needs-human is held out of ready
    Given an implement-kind item whose References line omits the scenario that governs its assertion
    When intake routes the item toward ready
    Then the pre-admission judgement runs against its effective criteria and referenced headings
    And the item is not routed to ready
    And its verdict, with each remedy, is appended to the item as a ledger comment
  Scenario: An item the judgement admits moves to ready as before
    Given an implement-kind item whose Definition of Done the judgement admits
    When intake routes the item toward ready
    Then the item moves to ready exactly as it would without the judgement
  Scenario: A judgement that cannot run does not hold the item
    Given the pre-admission judgement cannot run for an item
    When intake routes the item toward ready
    Then the item is routed as it would be without the judgement
    And a ledger comment records that the pre-admission judgement did not run and why
  Scenario: Held items are surfaced
    Given an item held by the pre-admission judgement
    When needs-attention composes hygiene facts
    Then a hygiene fact names the item and its verdict's first remedy
  Scenario: An item that reached ready without admission is judged before dispatch
    Given an implement-kind item released to ready through resolve-blocked whose References line omits the scenario that governs its assertion
    When the Dispatcher selects the item for a dispatch
    Then the Definition-of-Done judgement runs before any claim is taken
    And the dispatch is refused before any factory run is created, naming the judgement's finding text
    And the verdict, with each remedy, is appended to the item as a ledger comment
    And the item remains ready
  Scenario: A judgement that cannot run before dispatch does not refuse the dispatch
    Given the pre-dispatch judgement cannot run for a selected item
    When the Dispatcher dispatches the item
    Then the dispatch proceeds as it would without the judgement
    And a ledger comment records that the pre-dispatch judgement did not run and why
  Scenario: A refused item is not judged or commented again while it is unchanged
    Given an item whose pre-dispatch judgement refused it and whose effective criteria and referenced headings are unchanged since
    And no specification revision has been ratified since that verdict was taken
    When the Dispatcher's drain enumerates dispatch candidates
    Then the item is excluded from the candidates
    And no further judgement runs and no further ledger comment is appended for it
    And needs-attention lists the item with its verdict's first remedy
  Scenario: A refused item re-enters enumeration and is judged once after its criteria change or a revision is ratified
    Given an item excluded from drain candidates by a pre-dispatch refusal
    And its effective criteria or referenced headings have changed, or a specification revision has been ratified, since that verdict was taken
    And the judgement of its current criteria would still rest the item at needs-human
    When the Dispatcher's drain enumerates dispatch candidates
    Then the item is included among the candidates
    And the pre-dispatch judgement runs exactly once against the item's current criteria and the ratified specification before any claim is taken
    And the dispatch is refused before any factory run is created
    And exactly one new verdict comment is appended to the item
  Scenario Outline: The judgement authenticates with the account a dispatch would use
    Given the account-selection process has published a selected account whose credential is present in the environment
    And the environment's unnumbered Claude credential names a different account
    When the <phase> judgement runs its Claude model on the host
    Then the judge is started with the selected account's credential

    Examples:
      | phase         |
      | pre-admission |
      | pre-dispatch  |

  Scenario Outline: The judgement falls back to the unnumbered credential and says so
    Given <selection state>
    And the unnumbered Claude credential is present in the environment
    When the <phase> judgement runs its Claude model on the host
    Then the judge is started with the unnumbered Claude credential
    And one stderr line names that fallback and its reason

    Examples:
      | phase         | selection state                                                                 |
      | pre-admission | no account selection is published                                               |
      | pre-dispatch  | no account selection is published                                               |
      | pre-admission | a selected account is published but its credential is absent from the environment |
      | pre-dispatch  | a selected account is published but its credential is absent from the environment |
```

## Scenario 175 — A run past the whole-run wall budget is exported, cancelled and rested for a human

```gherkin
Feature: One factory run holds a slot no longer than the whole-run wall budget
  Scenario: A run past the budget parks at needs-human with its work preserved
    Given a dispatch whose resolved dispatcher.run_wall_budget_seconds is 21600
    And its run has been running for more than 21600 seconds since the factory first reported it running
    When the watchdog samples the run
    Then the Dispatcher writes and reads back the run's preserve-by-reference pointer before it cancels the run
    And the run is cancelled and no longer holds a factory slot
    And the journal carries one run-wall-budget-exceeded record naming the work-item, the dispatch id, the run id, the factory, the stage, the elapsed seconds, the budget, the layer that supplied it and the preserve-by-reference pointer
    And the journal carries no watchdog-stall-cancel record for the run
    And the item rests at blocked with blocked_reason needs-human
    And its ledger comment names the run id, the factory, the stage, the elapsed seconds, the budget, the preserve-by-reference pointer and the remedy resolve-blocked:<id>:ready
  Scenario: A budget cancel is not non-convergence and leaves the progress count alone
    Given an item whose across-dispatch non-progress count is 1
    And the watchdog cancels its run as run-wall-budget-exceeded
    When the Dispatcher records the outcome and the calibration analysis pass runs
    Then no non-convergence-bounce record is journaled and the item is not moved to backlog
    And the calibration pass does not count the dispatch as a non-convergence observation
    And the item's across-dispatch non-progress count is still 1
  Scenario: A budget-rested item is not dispatched automatically
    Given an item resting at blocked with blocked_reason needs-human after a budget cancel
    When the next admission pass runs
    Then the item is not admitted or dispatched
  Scenario: The budget is exceeded only past it
    Given a run whose slot-holding time equals its budget exactly
    When the watchdog samples the run
    Then it does not cancel the run on the budget
  Scenario: Queue time does not count against the budget
    Given a run that waited as runnable before the factory first reported it running
    And the time since it first ran is less than the budget while the time since it was submitted is more
    When the watchdog samples the run
    Then it does not cancel the run on the budget
  Scenario: The start instant comes from the run's record, else from the first poll that saw it running
    Given a run whose record carries the instant it first ran
    When the watchdog measures the run's slot-holding time
    Then it measures from that recorded instant
    And for a run whose record carries no such instant it measures from the first watchdog poll that observed the run running
  Scenario: An unmeasured start is not a cancel
    Given a run whose record carries no running instant and which no watchdog poll has yet observed running
    When the watchdog samples the run
    Then it does not cancel the run on the budget
  Scenario: A progressing run is still bounded
    Given a run whose event stream shows a command node started and not completed
    And its slot-holding time exceeds the budget while that node's resolved timeout has not elapsed
    When the watchdog samples the run
    Then it exports and cancels the run as run-wall-budget-exceeded
  Scenario: A published run names its pull request and head
    Given a run past the budget whose event stream records a completed publish_draft whose pushed head can be read from the run's record
    When the Dispatcher journals run-wall-budget-exceeded
    Then the record and the ledger comment name the pull request and the head the run's last completed publish_draft pushed
  Scenario: An unreadable published head is explicit
    Given a run past the budget whose event stream records a completed publish_draft whose pushed head cannot be read from the run's record
    When the Dispatcher journals run-wall-budget-exceeded
    Then the record explicitly states that the published head could not be read
  Scenario: A budget cancel between publication and capture can anchor resume
    Given an item whose latest dispatch was cancelled as run-wall-budget-exceeded between its last completed publish_draft and proof_capture
    And no proof record carries that dispatch's identifier
    And its record names the unchanged published head
    And all other resume preconditions pass
    When resume runs for the item
    Then the run-wall-budget-exceeded record anchors the published head and the new run enters at proof_capture
  Scenario: An export that cannot be read back holds the cancel until it can
    Given a run past the budget whose preserve-by-reference pointer cannot be read back
    When the watchdog samples the run
    Then it does not cancel the run
    And the journal carries a run-wall-budget-held record naming the run, the elapsed seconds, the budget and the failed measurement
    And the export is re-attempted on the immediately following poll
    And while that re-attempt's read-back fails the run is still not cancelled
    And once a re-attempt's read-back succeeds the run is cancelled as run-wall-budget-exceeded
  Scenario: The budget takes precedence over a simultaneous stall
    Given a run whose slot-holding time exceeds its budget
    And whose heartbeat and event stream have both stayed unchanged for the full stall window with no command node open
    When the watchdog samples the run
    Then it exports and cancels the run as run-wall-budget-exceeded
    And the journal carries no watchdog-stall-cancel record and the item rests at blocked with blocked_reason needs-human
    And while the run's budget export is held pending its read-back it is not cancelled as stalled-no-progress
  Scenario: A budget below a node timeout is refused before any run exists
    Given a dispatch target whose resolved dispatcher.run_wall_budget_seconds is smaller than its resolved implement node timeout
    When the Dispatcher prepares the dispatch
    Then it refuses before any run exists, naming dispatcher.run_wall_budget_seconds, dispatcher.node_timeouts.implement and both values
  Scenario Outline: The budget resolves from the most specific layer
    Given the built-in default budget of 21600 seconds
    And a dispatch target whose .livespec.jsonc sets dispatcher.run_wall_budget_seconds to <configured>
    And a dispatch invoked with --run-wall-budget-seconds <argument>
    When the Dispatcher prepares the dispatch
    Then the resolved budget is <resolved> seconds and the dispatch record names the <layer> layer

    Examples:
      | configured | argument | resolved | layer                 |
      | unset      | unset    | 21600    | default               |
      | 25200      | unset    | 25200    | repository            |
      | 25200      | 28800    | 28800    | per-dispatch argument |

  Scenario Outline: An invalid budget is refused before any run exists
    Given a dispatch whose <source> supplies the budget value <value>
    When the Dispatcher prepares the dispatch
    Then it refuses before any run exists, naming <named>

    Examples:
      | source                                  | value | named                             |
      | .livespec.jsonc run_wall_budget_seconds | 0     | dispatcher.run_wall_budget_seconds |
      | .livespec.jsonc run_wall_budget_seconds | -60   | dispatcher.run_wall_budget_seconds |
      | .livespec.jsonc run_wall_budget_seconds | 90.5  | dispatcher.run_wall_budget_seconds |
      | --run-wall-budget-seconds argument      | 0     | --run-wall-budget-seconds          |
      | --run-wall-budget-seconds argument      | -60   | --run-wall-budget-seconds          |
      | --run-wall-budget-seconds argument      | 90.5  | --run-wall-budget-seconds          |
```

## Scenario 176 — A green run whose refresh conflicts with a moved default branch is repaired and published instead of ending at needs-human

```gherkin
Feature: A janitor-green run survives a default branch that moved under it
  As the maintainer of a repository dispatched to the factory
  I want a refresh conflict or a post-refresh gate failure repaired inside the run
  So that hours of finished, green work are not discarded at publication

  Scenario: A conflicted publish_draft refresh routes to a repair turn
    Given a run whose janitor stage succeeded at head H
    And origin's default branch has advanced with a commit that conflicts with the run's work
    When publish_draft refreshes the run onto the default branch
    Then publish_draft aborts the rebase and the run's working branch is at H
    And a refresh-repair brief names H, the conflicted paths and the run commit being applied
    And the run enters the fix node rather than needs_human
    And after the fix turn the run re-enters janitor, then publish_draft, then proof_capture

  Scenario: A refreshed head that fails the gate is restored and repaired
    Given a run whose janitor stage succeeded at head H
    And the refresh onto the advanced default branch completes without conflict
    And the repository-declared gate rejects the refreshed head
    When publish_draft publishes
    Then the run's working branch is reset to H
    And the run enters the fix node with a brief naming each failed gate target
    And the run does not end at needs_human

  Scenario: A conflicted pr_refresh routes to a repair turn and counts as a refresh
    Given a run whose proof was verified on its published head P
    And origin's default branch has advanced with a commit that conflicts with the run's work
    When pr_refresh refreshes the run
    Then the run's working branch is at P and the run enters the fix node
    And that pr_refresh visit counts as one of the run's three refreshes
    And after the repair the run passes janitor, publish_draft, proof_capture, review and proof_verify before pr_refresh runs again

  Scenario: A resumed run restores its resume provenance head
    Given a run resumed from a published pull request whose validated resume provenance names head P
    And the run has no janitor visit of its own
    When its pr_refresh rebase conflicts
    Then the run's working branch is at P and the brief names P as the pre-refresh head

  Scenario: A repaired pr_refresh republishes over the run's own published head
    Given a run whose previously published head on origin is P, established from its publication record when it has one and otherwise from its validated resume provenance
    And its pr_refresh rebase conflicted and the fix turn integrated the default branch into a repaired head R that does not contain P
    When the run re-enters publish_draft after janitor passes on R
    Then publish_draft pushes R with an explicit lease against the recorded remote head of this run's own publish branch, P
    And the run enters proof_capture for R rather than needs_human

  Scenario: publish_draft still refuses a foreign divergent tip after a repair
    Given a run that re-enters publish_draft after a refresh-repair round with repaired head R and previously published head P
    And origin's publish branch tip is T, which is neither an ancestor of R nor equal to P
    When publish_draft publishes
    Then publish_draft fails closed with its divergent-prior-run cause and pushes nothing

  Scenario: A repair round leaves the review-fix budget untouched
    Given a run that has used one review-fix round
    When a publish_draft refresh conflict routes the run to a refresh-repair round
    Then the run still has the same number of review-fix rounds remaining as before the repair

  Scenario: Repaired and clean refreshes share the non-convergence bound
    Given a run whose pr_refresh has refreshed cleanly twice
    And whose third pr_refresh refresh conflicted and was repaired
    When the default branch advances again before pr
    Then the run ends with the explicit non-convergence cause and preserved work

  Scenario: The repair budget is bounded
    Given a run that has already taken two refresh-repair rounds across publish_draft and pr_refresh
    When its next refresh conflicts again
    Then the stage fails closed to needs_human with the cause refresh-repair-exhausted
    And the recovery artifact pointer names that stage's pre-refresh head

  Scenario: A push origin refuses is not repaired
    Given a run whose refresh applied cleanly and whose gate passed
    When origin refuses the push with an authentication failure
    Then publish_draft fails closed with its existing push-failure cause
    And the run does not enter the fix node
```

## Scenario 177 — A repository hook that outlives its limit is reaped and named, and publish_draft's limit is configurable

```gherkin
Feature: Repository hooks inside a sandbox stay within, and are named against, their limits
  As the maintainer of a repository whose full gate runs in its commit and push hooks
  I want an over-limit hook reaped, recorded by name, and its stage limit configurable
  So that a loaded factory host does not turn a green run into an unexplained needs-human

  Scenario: publish_draft resolves its timeout from configuration
    Given a dispatch target whose "dispatcher.node_timeouts" sets publish_draft to 3600
    When the Dispatcher renders the dispatch payload's workflow graph
    Then the publish_draft node's timeout attribute is the literal duration 3600s

  Scenario: An over-limit commit hook is reaped before the next commit
    Given an implement-stage agent whose git commit tool call is ended by its tool-call limit while the commit hook is still running
    When the agent starts its next git commit in the same sandbox
    Then no process of the earlier hook run is still running
    And the dispatch journal carries a hook-over-limit row naming the implement node, the commit operation, the limit and the elapsed milliseconds

  Scenario: A command node's over-limit push is named
    Given a publish_draft push whose pre-push hook is still running when the node's resolved timeout ends it
    When the run ends at needs-human
    Then the dispatch journal carries a hook-over-limit row naming publish_draft, the push operation and the resolved timeout
    And the needs-human cause recorded on the item names hook-over-limit, publish_draft and the push operation
    And the run's work is preserved before it terminates

  Scenario: A push that times out after its hook finished is not a hook-over-limit event
    Given a publish_draft push whose pre-push hook has already finished when the node's resolved timeout ends it
    When the run ends at needs-human
    Then the dispatch journal carries no hook-over-limit row for that push
    And the push keeps its existing failure classification

  Scenario: A recovered hook-over-limit event is not the cause of a later stop
    Given an implement-stage commit whose hook-over-limit event was recorded and whose retried commit then succeeded
    When a later stage ends the run at needs-human for a different cause
    Then the needs-human cause recorded on the item names that later cause
    And the dispatch journal still carries the earlier hook-over-limit row
```

## Scenario 178 — A refresh carries verified proof forward only when the deterministic carry-forward conditions hold

```gherkin
Feature: A pr_refresh re-proves only when the incoming commits could change what the proof observed
  As the maintainer of a repository dispatched to the factory
  I want a verified proof carried across a refresh whose incoming commits cannot affect it
  So that a run is not sent round capture, review and replay for changes it cannot observe

  Scenario: A refresh that brings in only plan notes carries a file-read proof forward
    Given a run whose verified record on head V states Working directory: . and has the single reproduction step grep -n "ledger comment" AGENTS.md with its read identity line for AGENTS.md
    And the item's diff changes only AGENTS.md
    And the default branch advanced with commits that change only paths beneath plan/
    When pr_refresh rebases the branch cleanly, the gate passes, the leased push yields head N with an unchanged patch identity, and the mechanical replay prints exactly the captured proof
    Then the pull request carries one carried_forward record naming V, N, the incoming range and paths, the observation scope AGENTS.md and both patch identities
    And the run proceeds from pr_refresh to pr without visiting proof_capture, review or proof_verify
    And pr marks the draft ready for head N

  Scenario: An incoming change outside the inert classes re-proves
    Given a run whose verified record on head V reads only AGENTS.md
    And the run has not yet re-proved after a changed-head refresh
    And the default branch advanced with a commit that changes a Python module the item does not touch
    When pr_refresh rebases the branch cleanly and pushes head N
    Then the pull request carries one reproof_required record naming that module as an incoming path outside every inert class
    And the run enters proof_capture for head N, then review and proof_verify, before pr

  Scenario: A proof that runs an operation is outside the direct-read grammar
    Given a run whose verified record has a reproduction step that invokes list-plans --json
    And the default branch advanced with commits that change only paths beneath plan/
    When pr_refresh rebases the branch cleanly and pushes head N
    Then the reproof_required record names that step as outside the direct-read grammar
    And the run enters proof_capture for head N

  Scenario: A recursive or directory read is outside the direct-read grammar
    Given a run whose verified record has the reproduction step grep -rn "Scenario 178" SPECIFICATION/
    When pr_refresh pushes a changed head
    Then the reproof_required record names that step as outside the direct-read grammar

  Scenario: A glob in a reproduction step is outside the direct-read grammar
    Given a run whose verified record has the reproduction step cat plan/*/research/001.md
    When pr_refresh pushes a changed head
    Then the reproof_required record names that step as outside the direct-read grammar

  Scenario: A non-canonical path is canonicalized before it is compared
    Given a run whose verified record has the reproduction step cat ./plan//topic/research/001.md
    And the default branch advanced with a commit that changes plan/topic/research/001.md
    When pr_refresh pushes a changed head
    Then the reproof_required record names plan/topic/research/001.md as an incoming path inside the observation scope

  Scenario: A parent segment in a path operand is rejected
    Given a run whose verified record has the reproduction step cat docs/../AGENTS.md
    When pr_refresh pushes a changed head
    Then the reproof_required record names that path operand as rejected

  Scenario: A path read through a symbolic link is rejected
    Given a run whose verified record has the reproduction step cat alias/note.md where alias is a symbolic link to plan/sub at both heads
    When pr_refresh pushes a changed head
    Then the reproof_required record names that path operand as rejected

  Scenario: A substitution hidden in a double-quoted pattern is outside the direct-read grammar
    Given a run whose verified record has the reproduction step grep -n "$(cat plan/topic/pattern.txt)" AGENTS.md
    And the default branch advanced with a commit that changes only plan/topic/pattern.txt
    When pr_refresh pushes a changed head
    Then the reproof_required record names that step as outside the direct-read grammar
    And the run enters proof_capture

  Scenario: A verified record that does not state the repository root as its working directory re-proves
    Given a run whose verified record has the reproduction step cat note.md and no Working directory: . line
    When pr_refresh pushes a changed head
    Then the reproof_required record names every step as outside the direct-read grammar

  Scenario: A read with no file operand is outside the direct-read grammar
    Given a run whose verified record has the reproduction step cat with no operand
    When pr_refresh pushes a changed head
    Then the reproof_required record names that step as outside the direct-read grammar

  Scenario: An option-shaped grep pattern is outside the direct-read grammar
    Given a run whose verified record has the reproduction step grep -F '-fplan/topic/pattern.txt' AGENTS.md
    And the default branch advanced with a commit that changes only plan/topic/pattern.txt
    When pr_refresh pushes a changed head
    Then the reproof_required record names that step as outside the direct-read grammar

  Scenario: A dash operand is outside the direct-read grammar
    Given a run whose verified record has the reproduction step cat -
    When pr_refresh pushes a changed head
    Then the reproof_required record names that step as outside the direct-read grammar

  Scenario: A git show of an unchanged file carries forward
    Given a run whose verified record states Working directory: . and has the single reproduction step git show HEAD:AGENTS.md
    And the item's diff changes only AGENTS.md
    And the default branch advanced with commits that change only paths beneath plan/
    When pr_refresh rebases cleanly and pushes head N with an unchanged patch identity
    Then the carried_forward record names AGENTS.md as the observation scope
    And the run proceeds from pr_refresh to pr

  Scenario: A git show of a changed file re-proves
    Given a run whose verified record has the reproduction step git show HEAD:plan/topic/note.md
    And the default branch advanced with a commit that changes plan/topic/note.md
    When pr_refresh pushes a changed head
    Then the reproof_required record names plan/topic/note.md as an incoming path inside the observation scope

  Scenario: A rebased diff that differs from the verified diff re-proves
    Given a run whose verified record on head V reads only AGENTS.md
    And the default branch advanced with commits that change only paths beneath plan/
    When the rebased item diff's patch identity differs from the verified diff's
    Then the reproof_required record names both patch identities
    And the run enters proof_capture for the new head

  Scenario: An observed file whose bytes changed re-proves even when the patch identity is equal
    Given a run whose verified record states Working directory: . and has the single reproduction step wc -c AGENTS.md
    And the default branch advanced with commits that change only paths beneath plan/
    When pr_refresh rebases cleanly and the rebased AGENTS.md differs from the verified head's only in whitespace
    Then the stable patch identities are equal but the blob identities of AGENTS.md differ
    And the reproof_required record names AGENTS.md as a path whose blob identity differs
    And the run enters proof_capture for the new head

  Scenario: An observed file whose working-tree bytes differ from the verified read re-proves even when its blob is unchanged
    Given a run whose verified record states Working directory: . and has the single reproduction step wc -c AGENTS.md with the read identity line for AGENTS.md
    And the verified sandbox materialized AGENTS.md with CRLF line endings while the refreshed sandbox materializes it with LF
    And the default branch advanced with commits that change only paths beneath plan/
    When pr_refresh rebases cleanly and pushes head N with unchanged patch and blob identities
    Then the reproof_required record names AGENTS.md as a path whose read identity differs from the new head's working-tree bytes
    And the run enters proof_capture for head N

  Scenario: A verified record without read identities re-proves
    Given a run whose verified record states Working directory: . and has the reproduction step cat AGENTS.md but no read identity line for AGENTS.md
    When pr_refresh pushes a changed head
    Then the reproof_required record names AGENTS.md as a path whose read identity is missing

  Scenario: A step whose mechanical replay output differs from its captured proof re-proves
    Given a run whose verified record states Working directory: . and has the single reproduction step grep -i 'é' AGENTS.md with its read identity line and a captured proof of two lines
    And the verified execution ran under a locale in which the search matched both lines
    And the default branch advanced with commits that change only paths beneath plan/
    When pr_refresh rebases cleanly and the mechanical replay under LC_ALL=C.UTF-8 prints output that differs from the captured proof
    Then the reproof_required record names that step as one whose mechanical replay did not reproduce its captured proof
    And the run enters proof_capture for the new head

  Scenario: A step whose mechanical replay cannot execute re-proves
    Given a changed-head pr_refresh whose path, patch, blob and read identities all match
    When the mechanical replay cannot execute a step's command at the new head
    Then the reproof_required record names that step as one whose mechanical replay did not reproduce its captured proof
    And the run enters proof_capture for the new head

  Scenario Outline: A step whose captured proof is not exactly one fenced text block re-proves
    Given a parseable verified record whose step cat AGENTS.md is followed by <count> fenced text blocks
    When pr_refresh pushes a changed head
    Then the reproof_required record names that step as one whose captured proof is not exactly one fenced text block
    And the run enters proof_capture for the new head

    Examples:
      | count |
      | 0     |
      | 2     |

  Scenario: An unreadable input re-proves and names the input
    Given a changed-head pr_refresh whose verified record cannot be parsed
    When the stage decides whether the proof covers the new head
    Then the decision is reproof_required and the record names the unparseable verified record as the unreadable input
    And the run enters proof_capture

  Scenario: A repaired refresh is never carried forward
    Given a pr_refresh whose rebase conflicted and took a refresh-repair round
    When the repaired run is published again
    Then no carried_forward record is posted for the repaired head
    And the run passes proof_capture, review and proof_verify before pr_refresh runs again

  Scenario: A second carry-forward is measured against the verified diff
    Given a run that carried its proof from verified head V to head N1
    And the default branch advanced again with commits that change only paths beneath plan/
    When pr_refresh pushes head N2
    Then the carried_forward record for N2 names V as the verified head and compares N2's patch identity with V's
    And pr marks the draft ready for head N2

  Scenario: A carry-forward whose record cannot be posted re-proves
    Given a changed-head pr_refresh whose decision inputs satisfy every carry-forward condition
    When posting the carried_forward record on the pull request fails
    Then the run enters proof_capture for the new head
    And the stage output names the failed post

  Scenario: A re-proof decision whose record cannot be posted still re-proves
    Given a changed-head pr_refresh whose decision is reproof_required
    When posting the reproof_required record on the pull request fails
    Then the run still enters proof_capture for the new head
    And the stage output names the failed post

  Scenario: A carried-forward head anchors a resume and the pointer
    Given a run that carried its proof from verified head V to head N and then terminated before pr
    And the pull request's head is N and its latest proof record is the carried_forward record naming N
    When the operator drives resume for the item
    Then the resume anchors at head N and enters pr_refresh before pr
    And after merge the Proof of Done pointer names both the verified record and the carried_forward record
    And the acceptance pass grades the factory-captured assertions from the verified record

  Scenario: A reproof_required record is skipped by every reader of the latest proof record
    Given a pull request whose latest record is a reproof_required record that follows a verified record naming head V
    When resume or the acceptance pass reads the latest proof record
    Then it reads the verified record naming head V and not the reproof_required record

  Scenario: pr refuses a head no proof record names
    Given a run whose latest verified record names head V and whose pull request carries no carried_forward record for head N
    When pr runs with the pull request at head N
    Then pr does not mark the draft ready and fails closed naming head N
```

## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict

```gherkin
Feature: A factory agent's commit leg is not bounded by one tool call
  As the maintainer of a repository whose full gate runs in its commit hook
  I want a sandbox commit to reach its hook's verdict however long the hook runs
  So that a loaded factory host does not turn a verified change into a lost run

  Scenario: A Green amend whose hook outlasts one tool call completes
    Given an implement-stage agent whose Green amend fires a commit hook that runs longer than one of its tool calls
    When the agent starts the amend through the sandbox commit runner and repeats bounded waits in later tool calls
    Then the amend completes with the hook's own verdict
    And the resulting commit carries every trailer the hook wrote
    And the final wait reports the passed state, exit status zero and the resulting commit id

  Scenario: A commit refused by its hook is reported as failed
    Given a commit started through the sandbox commit runner whose hook refuses it
    When the agent waits on it until it is terminal
    Then the wait reports the failed state and the commit process's exit status
    And HEAD is unchanged

  Scenario: A commit that dies without a verdict is not a commit
    Given a commit started through the sandbox commit runner whose process is ended by a signal before it exits on its own
    When the agent waits on it
    Then the wait reports the no-verdict state
    And no passed state is reported for that commit run

  Scenario: A second commit does not start while one is running
    Given a commit started through the sandbox commit runner that is still running
    When the agent starts another commit through the runner
    Then the runner refuses the start and names the running commit run
```

## Scenario 180 — A sandbox agent cannot remove the run's working tree, and ordinary removals still run

```gherkin
Feature: The run's protected paths survive the agent inside the factory sandbox
  As the maintainer of a repository dispatched through the factory
  I want an agent command that would delete the run's working tree refused before it runs
  So that a finished implementation is not lost to a checkpoint that cannot find its working directory

  Background:
    Given the implement-stage agent's ACP adapter runtime offers a hook that runs before each shell command

  Scenario: removing the sandbox root is refused before it runs
    Given an implement-stage agent inside a factory sandbox whose working directory is /workspace/<repository>
    When the agent runs a shell command "cd /tmp && rm -rf /workspace && mkdir -p /workspace"
    Then the command is refused before any part of it executes
    And the refusal names /workspace as the protected path
    And the run's working directory still exists

  Scenario: a relative removal from a parent directory is refused
    Given an implement-stage agent inside a factory sandbox whose working directory is /workspace/<repository>
    When the agent runs a shell command "cd / && rm -rf workspace/"
    Then the command is refused and the refusal names /workspace as the protected path

  Scenario: removals under a scratch directory and inside the repository still run
    Given an implement-stage agent inside a factory sandbox
    When the agent runs "rm -rf /tmp/layout-sim" and then removes a file inside the repository tree
    Then neither command is refused

  Scenario: a command that also removes a protected path is refused
    Given an implement-stage agent inside a factory sandbox whose working directory is /workspace/<repository>
    When the agent runs a shell command "rm -rf /tmp/layout-sim /workspace"
    Then the command is refused and the refusal names /workspace as the protected path

  Scenario: a protected path mentioned only as data is not refused
    Given an implement-stage agent inside a factory sandbox
    When the agent runs a shell command that passes "rm -rf /workspace" to echo, or writes it in a here-document body
    Then the command is not refused
```

## Scenario 181 — A ledger write from this repository prints no auto-backup warning

```gherkin
Feature: The tenant's client backup lane stays disabled
  As an operator reading the output of a ledger call
  I want no auto-backup failure warning from a lane the shared server will always refuse
  So that a warning about backups means a real backup problem

  Scenario: A successful ledger write with the key committed
    Given this repository's committed .beads/config.yaml sets backup.enabled: false
    And the repository has a git remote
    When a bd write made through the plugin from the repository root under the credential wrapper succeeds
    And reading the written change back from the tenant returns it
    Then that write's stderr carries no auto-backup failed warning
    And the next hourly dolt-backup.service run still reports every tenant synced
```

## Scenario 182 — A registry-backed factory resolves its address from the host registry, and an unresolvable one refuses before claim

```gherkin
Feature: Factory addresses come from a host registry, not from committed configuration
  As the maintainer of a fleet whose factories move between machines
  I want a committed factory entry to name no machine
  So that moving a factory is a provisioning change, never a repository change

  Background:
    Given dispatcher.factories declares a factory named "petri" with "registry": true and no server
    And LIVESPEC_FABRO_FACTORY is unset

  Scenario: A registry-backed factory dispatches to the address the registry names
    Given the factory registry maps "petri" to a server address
    When an item is dispatched to "petri"
    Then the Fabro run is created on the server address the registry maps "petri" to
    And the item's dispatch-factory record names "petri" and that server address

  Scenario: Resume resolves the same address
    Given the factory registry maps "petri" to a server address
    And an item whose dispatch to "petri" left a resumable run
    When the item is resumed
    Then the resume addresses the server address the registry maps "petri" to

  Scenario Outline: The registry path is the override when it is set and non-empty, and the default path otherwise
    Given LIVESPEC_FABRO_FACTORY_REGISTRY is <override>
    And the file at <read path> maps "petri" to a server address
    And the file at <other path> holds no entry for "petri"
    When an item is dispatched to "petri"
    Then the Fabro run is created on the server address the file at <read path> maps "petri" to

    Examples:
      | override                 | read path                          | other path                         |
      | set to a test file       | that test file                     | /etc/livespec/fabro-factories.json |
      | unset                    | /etc/livespec/fabro-factories.json | a test file                        |
      | set to the empty string  | /etc/livespec/fabro-factories.json | a test file                        |

  Scenario Outline: An unresolvable registry refuses before any ledger write and never falls back
    Given the factory registry <registry state>
    When an item is dispatched to "petri"
    Then the dispatch is refused naming "petri" and the registry path
    And the item's status, metadata and comments are unchanged
    And no Fabro run is created on any server

    Examples:
      | registry state                                         |
      | file is absent                                         |
      | file exists but cannot be read                         |
      | file does not parse as JSON                            |
      | file's top-level value is a list                       |
      | file has no entry named "petri"                        |
      | file maps "petri" to a string rather than an object    |
      | file maps "petri" to an object with no server          |
      | file maps "petri" to an object whose server is a number |
      | file maps "petri" to an object whose server is "   "   |
      | file maps "petri" to an object with a valid server and a docker_host of "   " |
      | file maps "petri" to an object with a valid server and a docker_host that is a number |

  Scenario Outline: An explicit selection naming an undeclared factory refuses before any ledger write and never falls back
    Given dispatcher.factories declares no factory named "hp"
    When an item is dispatched with <selection>
    Then the dispatch is refused naming "hp" and every factory name dispatcher.factories declares
    And the item's status, metadata and comments are unchanged
    And no Fabro run is created on any server

    Examples:
      | selection                          |
      | --factory hp                       |
      | LIVESPEC_FABRO_FACTORY set to "hp" |

  Scenario: Only the selected entry is validated
    Given the factory registry maps "petri" to a server address and maps "legacy" to null
    When an item is dispatched to "petri"
    Then the Fabro run is created on the server address the registry maps "petri" to

  Scenario Outline: An entry declaring the registry together with a committed address refuses before any ledger write
    Given dispatcher.factories instead declares "petri" with "registry": true and a <committed key> value
    And the factory registry maps "petri" to a server address
    When an item is dispatched to "petri"
    Then the dispatch is refused naming "petri"
    And the item's status, metadata and comments are unchanged
    And no Fabro run is created on any server

    Examples:
      | committed key |
      | server        |
      | docker_host   |

  Scenario: The registry entry's docker_host is the factory's container-daemon address
    Given the factory registry maps "petri" to an object carrying a server address and a docker_host value
    When the reconcile pass sweeps the sandbox containers of every declared factory
    Then it reads "petri"'s containers through that docker_host value

  Scenario: A registry entry with no docker_host declares no container-daemon address
    Given the factory registry maps "petri" to an object carrying only a server address
    When the reconcile pass sweeps the sandbox containers of every declared factory
    Then the sweep reports "petri"'s sandbox containers as unobserved, naming "petri"
    And it opens no container-daemon connection for "petri"

  Scenario: The reconcile survey reports an unresolvable registry-backed factory as unobservable and still observes the others
    Given dispatcher.factories also declares a factory "legacy" with a server value whose Fabro server answers and holds one run
    And the factory registry has no entry named "petri"
    When the Dispatcher surveys every declared factory's runs
    Then the survey reports "petri" as unobservable, naming it
    And it does not report "petri" as holding no runs
    And it reports the one run "legacy" holds

  Scenario: A journal liveness read of an unresolvable registry-backed factory is unobservable
    Given the factory registry has no entry named "petri"
    And a dispatch journal row names "petri" as the factory of a run
    When the Dispatcher asks whether that run is live
    Then the answer is unobservable, naming "petri"
    And the run is not treated as gone

  Scenario: An availability-evidence read of an unresolvable registry-backed factory is unobservable
    Given the factory registry has no entry named "petri"
    When the ACP fallback availability evidence for "petri" is read
    Then that evidence is reported unobservable, naming "petri"
    And it is not read as an available or exhausted provider

  Scenario: The needs-human valve survives an unresolvable registry-backed factory
    Given the factory registry has no entry named "petri"
    And an item rests at a needs-human valve whose run was dispatched to "petri"
    When the needs-human valve list is assembled
    Then the item is listed at its valve
    And only that item's run enrichment is missing

  Scenario: A registry-backed factory is classified as remote for run-turn telemetry
    Given the factory registry maps "petri" to a server address
    And "petri" declares no run-turn telemetry export
    When the run-turn telemetry observability of "petri" is assessed
    Then "petri" is classified as a remote factory, exactly as an entry carrying a server value is

  Scenario: A recorded pin to an undeclared name still falls back to the default
    Given the factory registry maps "petri" to a server address
    And an item whose recorded dispatch factory is "hp"
    And dispatcher.factories no longer declares "hp"
    And dispatcher.default_factory names "petri"
    When the item is dispatched with no --factory flag
    Then it is dispatched to "petri"

  Scenario: Switching the default instance renames nothing
    Given dispatcher.factories also declares a registry-backed factory "next"
    And the factory registry maps both "petri" and "next" to server addresses
    And an unpinned item and an item whose recorded dispatch factory is "petri"
    When dispatcher.default_factory is changed from "petri" to "next"
    And both items are dispatched with no --factory flag
    Then the unpinned item is dispatched to "next"
    And the item recorded to "petri" is dispatched to "petri"
```

## Scenario 183 — A checkpoint-failed run whose tree nothing else carries is published to a preservation ref

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Failed engine checkpoint commit attribution".

```gherkin
Feature: The work of a run that ended on a failed engine checkpoint survives the run
  As the maintainer of a repository dispatched through the factory
  I want the changed files of a checkpoint-failed run published to a ref when no terminal patch carries them
  So that finished work is recoverable after the run's sandbox is gone

  Scenario: the changed files are published as one commit on a preservation ref
    Given a dispatched run that ended on a failed engine checkpoint commit of node implement
    And an earlier node of the run left a stage diff artifact
    And its terminal run.failed event carries no terminal patch
    When the Dispatcher reports the dispatch result
    Then it reads the run's changed files from the dispatch's resolved factory target
    And the forge carries a ref refs/livespec/preserved-publish/<work-item-id>/<commit-sha> whose commit's parent is the run's base commit and whose tree reflects every change the run made, removals included
    And no git push and no repository hook ran for that publication
    And a livespec-preserved-tree ledger comment names the run id, the factory, the preservation ref and its commit id
    And the item rests blocked with blocked_reason needs-human
    And the dispatch reports exit code 4

  Scenario: a failed preservation is reported and the item still rests at needs-human
    Given a dispatched run that ended on a failed engine checkpoint commit and whose terminal event carries no terminal patch
    And the factory refuses the read of the run's changed files
    When the Dispatcher reports the dispatch result
    Then no preservation ref is created
    And a livespec-preserved-tree ledger comment states that the tree was not preserved and names the files read as the step that failed
    And the item rests blocked with blocked_reason needs-human
    And the dispatch reports exit code 4

  Scenario: a run whose events cannot be read is still published
    Given a dispatched run that ended on a failed engine checkpoint commit
    And the run's events cannot be read from the dispatch's resolved factory target
    When the Dispatcher reports the dispatch result
    Then it attempts the publication of the run's changed files to a ref under refs/livespec/preserved-publish/<work-item-id>/
    And the item rests blocked with blocked_reason needs-human

  Scenario: a run whose terminal patch carries its work gets no preservation ref
    Given a dispatched run that ended on a failed engine checkpoint commit
    And its terminal run.failed event carries a terminal patch
    When the Dispatcher reports the dispatch result
    Then no ref under refs/livespec/preserved-publish/<work-item-id>/ is created for that run
    And the existing preserve-by-reference pointer and the terminal patch's size and digest are recorded as before
```

## Scenario 184 — The default branch advancing between pr_refresh and the arming re-enters pr_refresh, and an armed pull request it overtakes rests at needs-human with a named cause

```gherkin
Feature: Default-branch movement after pr_refresh is absorbed inside the run, and never merges an unproved head
  As the maintainer of a repository dispatched to the factory
  I want default-branch movement that arrives after the refresh handled like movement that arrives before it
  So that a proof-verified run is not ended for a human because master moved a few seconds too late

  Scenario: A refreshable advance before the arming re-enters pr_refresh and then arms
    Given a run whose latest verified record names head H
    And the default branch advances to tip T, which is not an ancestor of H, with a commit that does not conflict with the run's commits
    When pr marks the draft ready and the forge rejects the head-bound arming as not rebaseable
    Then pr records the refresh-route marker and pr_route routes the run to pr_refresh, which counts one refresh toward the three-refresh bound and takes no refresh-repair round
    And the refreshed head takes the carry-forward decision before pr is entered again
    And pr reports the pull request already ready and arms auto-merge for the head its latest verified or carried_forward record names

  Scenario: A conflicting advance before the arming re-enters pr_refresh and takes refresh repair
    Given a run whose latest verified record names head H
    And the default branch advances to tip T with a commit that conflicts with the run's commits
    When pr marks the draft ready and the forge rejects the head-bound arming as not rebaseable
    Then the run enters pr_refresh, which restores head H and records a refresh-repair brief naming each conflicted path together with the run commit being applied, and routes to fix

  Scenario: A rejected arming with no default-branch advance fails closed naming the forge's cause
    Given a run whose latest verified record names head H, and the default branch's tip is an ancestor of H
    When the forge rejects the head-bound arming
    Then pr fails closed, and its output names the forge's rejection message, the pull request state, its mergeability, that the head equals H, and the default branch's tip
    And the output does not state that the head differs from the verified head

  Scenario: An armed pull request overtaken by a conflicting commit rests at needs-human with a named cause
    Given a run that armed auto-merge for head H and terminated through exit
    And a later default-branch commit conflicts with the pull request
    When two consecutive merge-wait polls report the pull request OPEN and conflicting with the default branch
    Then the dispatch ends blocked at stage merge-poll with the cause base-advanced-after-arming and exit code 4
    And the item rests at blocked with blocked_reason needs-human, with one livespec-base-advanced-after-arming comment and one needs-human-blocked journal row
    And the outcome detail names resolve-blocked for the item and then resume

  Scenario: Resuming an overtaken armed pull request disarms it before refreshing
    Given that item resolved to ready and resumed
    When the resumed run enters pr_refresh at the default branch's advanced tip
    Then pr_refresh disarms the pull request's auto-merge request before it rebases or routes to refresh repair
    And the pull request is armed again only by pr, for a head named by a verified or carried_forward record of the resumed run

  Scenario: A merge-hold release cannot arm a head that no proof record names
    Given an item under a merge hold whose pull request head is H2
    And the latest verified or carried_forward record of the item's latest run names H1, not H2
    When the operator releases the hold
    Then the release refuses, naming the head comparison that failed, and the pull request stays unarmed
```

## Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch

```gherkin
Feature: Recovery routing for an automatically released item

  Scenario: A first-stall-released item in a drain wave resumes while its wave-mates dispatch plainly
    Given a ready item released after a first stall cancel whose cancel record anchors a resume
    And a second ready item in the same drain wave with no earlier dispatch
    When the drain routes, admits and launches the wave
    Then the released item's resume preconditions are graded while it is ready, before admission
    And the released item's run enters at the anchored node on the anchored head under the Dispatcher's own invoker identity
    And the journal carries a resume record and neither a publish-branch-reclaim nor a publish-branch-reclaim-held record for it
    And the second item's run starts at start on the default branch with no resume head

  Scenario: An unanchorable released item is seeded from verified preserved work
    Given a ready released item whose resume is inapplicable and whose failed run has a verified preserved commit
    When the Dispatcher routes and launches it
    Then its run checks out the recorded commit SHA
    And its seed record names the source run, remote, immutable commit SHA and preservation reference
    And the publish branch is reclaimed only after that preservation is verified

  Scenario: A capacity-deferred released item is untouched
    Given a ready released item that recovery routing assigned the resume route
    When the admission valve defers it for capacity
    Then its publish branch and pull request are unchanged and no resume record is journaled
    And no recovery-held record is journaled for it

  Scenario: An unobservable measurement holds the item without reclaim
    Given a ready released item whose forge or factory measurement cannot be taken
    When the Dispatcher routes it
    Then the item stays ready and is not admitted in that pass
    And the journal carries a recovery-held record naming the measurement
    And no publish-branch reclaim runs for it

  Scenario: A live ownership lock holds a released item that has preserved work
    Given a ready released item whose resume is inapplicable and whose failed run has a verified preserved commit
    And the item's dispatch-scoped ownership lock exists and its process is alive
    When the Dispatcher routes it
    Then the route is held, not seeded
    And the journal carries a recovery-held record naming the live ownership lock, its age and the wait-or-confirm-liveness remedy
    And the item is not admitted in that pass and no publish-branch reclaim runs for it
    And under dispatch --item the dispatch exits with code 3 naming the live ownership lock before any run exists

  Scenario: A merged pull request holds a released item and keeps the reconcile-merged remedy
    Given a ready released item whose publish branch carries a merged pull request
    And its failed run has a verified preserved commit
    When the Dispatcher routes it
    Then the route is held, neither seeded nor fresh
    And the journal carries a recovery-held record naming the merged state and the remedy reconcile-merged --item
    And no publish-branch reclaim runs for it
```

## Scenario 186 — A provider exhaustion observed on one credential account does not refuse dispatch on another account of the same vendor

```gherkin
Feature: An exhaustion record observed under one credential identity does not hold out another account of the same vendor
  As a maintainer whose credential rotation moves a vendor's candidates onto an account with headroom
  I want an exhaustion record to refuse only dispatches on the account that observed the limit
  So that a rotation is not defeated by records minted by runs still finishing on the exhausted account

  Scenario: A record names the credential identity the observing dispatch projected
    Given a dispatch whose admission projected credential identity "A" ends with a typed provider usage-limit outcome for provider "anthropic"
    When the Dispatcher mints the observed provider-exhaustion record
    Then the record names provider "anthropic" and credential identity "A"

  Scenario: A newer record for one identity does not retire another identity's record
    Given an unexpired provider-exhaustion record for provider "anthropic" naming credential identity "A"
    And a newer unexpired provider-exhaustion record for provider "anthropic" naming credential identity "B"
    When the Dispatcher reads the live provider-exhaustion records
    Then both records are live

  Scenario: A dispatch on another credential identity is admitted while the record is live
    Given an unexpired provider-exhaustion record for provider "anthropic" naming credential identity "A"
    And a ready work-item whose covered candidates project credential identity "B"
    When the Dispatcher evaluates the admission valve
    Then the record does not refuse the item

  Scenario: A dispatch on the same credential identity is refused while the record is live
    Given an unexpired provider-exhaustion record for provider "anthropic" naming credential identity "A"
    And a ready work-item whose covered candidates project credential identity "A" with no eligible fallback
    When the Dispatcher evaluates the admission valve
    Then the item is refused naming the record and its expiry

  Scenario: A record without a credential identity keeps vendor-wide coverage
    Given an unexpired provider-exhaustion record for provider "anthropic" that names no credential identity
    And a ready work-item whose covered candidates project credential identity "B" with no eligible fallback
    When the Dispatcher evaluates the admission valve
    Then the item is refused naming the record and its expiry

  Scenario: An unreadable credential identity fails closed
    Given an unexpired provider-exhaustion record for provider "anthropic" naming credential identity "A"
    And a ready work-item whose projected credential identity is absent
    When the Dispatcher evaluates the admission valve
    Then the record refuses the item
```

## Scenario 187 — A priority-epic idle-slot audit surfaces dispatchable priority work while the factory queue is empty, and a blocker with a live run is not a stale edge

```gherkin
Feature: The idle-slot audit measures the priority queue against the factory board
  As a factory driver whose slots sat idle for hours while priority work was dispatchable
  I want every priority-epic child classified against the live board across tenants
  So that idle capacity beside dispatchable work is surfaced instead of assumed away

Scenario: An empty factory queue beside a dispatchable priority child produces the finding and the attention fact
  Given a committed dispatcher.idle_slot_audit naming a factory and a priority epic in another tenant's checkout
  And the factory board shows 1 live row and no runnable row
  And one child of that epic is ready with no open blocks dependency and is admitted by its tenant's admission-eligibility verdict with capacity excepted
  When the idle-slot audit runs
  Then that child is classified DISPATCHABLE-NOW
  And the output ends with a finding line naming the factory, 1 live row attributed to the Fabro server, and that child's id
  And the needs-attention snapshot carries exactly one hygiene:idle-slot fact whose handoff runs the idle-slot audit
  And no ledger, dispatch journal, or factory was written

Scenario: A ready child whose only blocker is active with a live run is BLOCKED, not STALE-EDGE
  Given a ready priority child whose only open blocks dependency is on an active item
  And a live board row is attributed to that active blocker
  When the idle-slot audit runs
  Then the child is classified BLOCKED
  And when instead no live row is attributed to that active blocker the child is classified STALE-EDGE

Scenario: A hold the admission verdict refuses is HELD, and prose cannot hold a ready child
  Given a ready priority child with no open blocks dependency that its tenant's admission-eligibility verdict does not admit
  When the idle-slot audit runs
  Then the child is classified HELD with the verdict's reason beside it
  And a ready child whose only hold is written in a comment is classified DISPATCHABLE-NOW

Scenario: A queued run or an unobservable board yields no finding
  Given a configured audit with a DISPATCHABLE-NOW priority child
  When the factory board shows one runnable row
  Then no finding line is printed and no hygiene:idle-slot fact composes
  And when instead the board cannot be read it is reported unobservable with unknown live and queued counts, and no finding line is printed
```

## Scenario 188 — A push that only deletes refs skips the pre-push aggregate, and any other push runs it

```gherkin
Feature: A ref deletion is not gated like a change to the tree
  As the Dispatcher deleting a run's source branch after the run
  I want a push that only deletes refs to return without running the full check aggregate
  So that a pure deletion does not hold an item's ownership lock for the length of a full check

  Scenario: A push whose every ref update is a deletion skips the gate
    Given a push whose pre-push standard input lists only ref updates with an all-zero local object id
    When the repository's pre-push gate runs
    Then it exits zero without running the green-token check or the just check aggregate
    And it prints that the gate was skipped because the push only deletes refs

  Scenario: A push that updates a ref beside deletions runs the gate
    Given a push whose pre-push standard input lists a deletion and an update with a non-zero local object id
    When the repository's pre-push gate runs
    Then it runs the full pre-push gate

  Scenario: A push with no ref updates on standard input runs the gate
    Given a pre-push invocation whose standard input is empty
    When the repository's pre-push gate runs
    Then it runs the full pre-push gate
```

## Scenario 189 — The post-merge and reconcile janitor's check run inherits none of the dispatcher's routing and attribution variables

```gherkin
Feature: The janitor's check verdict depends on the merge, not on how the dispatch was routed,
  so a dispatcher routed or attributed through its environment cannot turn a green merge red

  Scenario: A dispatch routed through LIVESPEC_FABRO_FACTORY gets the janitor verdict its merge earns
    Given a dispatcher whose environment carries LIVESPEC_FABRO_FACTORY and LIVESPEC_INVOKER
    And a merged item whose check aggregate passes at the janitor venue when run without those variables
    When the post-merge janitor runs the repository's check aggregate
    Then the check run's environment carries neither LIVESPEC_FABRO_FACTORY nor LIVESPEC_INVOKER
    And the janitor reports the aggregate's own passing verdict
    And the janitor-post-merge journal row names LIVESPEC_FABRO_FACTORY and LIVESPEC_INVOKER as removed

  Scenario: The reconcile-merged janitor applies the same scrub
    Given a reconcile-merged invocation whose environment carries LIVESPEC_INVOKER
    When the reconcile janitor runs the repository's check aggregate
    Then the check run's environment does not carry LIVESPEC_INVOKER

  Scenario: A dispatcher with no routing variables records an empty removal list
    Given a dispatcher whose environment carries none of the dispatcher's routing or attribution variables
    When the post-merge janitor runs
    Then the janitor-post-merge journal row records an empty list of removed variables
```

## Scenario 190 — The post-merge janitor runs its check suite where dispatcher.janitor.venue selects, and a cluster gate that reaches no verdict is red

```gherkin
Feature: Only an exact cluster_job declaration moves the janitor's check suite to the cluster,
  where the gate client's suite resolution governs and the verdict is the state word on standard error

  Scenario: An absent or unrecognised venue keeps the check suite on the dispatching host
    Given a governed repository whose .livespec.jsonc declares no dispatcher.janitor.venue, or declares an unrecognised value
    When the post-merge janitor runs the check suite for a merged item
    Then the check suite resolved from dispatcher.janitor.check_suite runs on the dispatching host in the janitor checkout
    And its exit code is the janitor's verdict

  Scenario: On the cluster venue the gate client's suite resolution governs, not dispatcher.janitor.check_suite
    Given a governed repository whose .livespec.jsonc declares dispatcher.janitor.venue as cluster_job
    And whose .livespec.jsonc declares a dispatcher.janitor.check_suite command
    And whose pyproject.toml declares a different gate_check_suite in its [tool.livespec_dev_tooling] block
    When the post-merge janitor runs
    Then the gate client is run in the janitor checkout and the declared dispatcher.janitor.check_suite command is not run

  Scenario: A cluster gate that reports PASSED reads green even when the client exits non-zero
    Given a governed repository whose .livespec.jsonc declares dispatcher.janitor.venue as cluster_job
    And a delegated gate client whose last state-bearing standard-error line reports state PASSED and which exits non-zero
    When the post-merge janitor runs
    Then the janitor verdict is green

  Scenario: A PASSED state word on standard output alone is not a verdict
    Given a governed repository whose .livespec.jsonc declares dispatcher.janitor.venue as cluster_job
    And a delegated gate client that prints a state PASSED line on standard output and no state-bearing line on standard error
    When the post-merge janitor runs
    Then the janitor verdict is red
    And the red detail says the cluster gate reached no verdict

  Scenario: A cluster gate that reports FAILED reads red as a failed Job
    Given a governed repository whose .livespec.jsonc declares dispatcher.janitor.venue as cluster_job
    And a delegated gate client whose last state-bearing standard-error line reports state FAILED
    When the post-merge janitor runs
    Then the janitor verdict is red
    And the red detail says the cluster gate Job reported a FAILED verdict

  Scenario: A cluster gate that reaches no verdict reads red, not degraded
    Given a governed repository whose .livespec.jsonc declares dispatcher.janitor.venue as cluster_job
    And a delegated gate client whose standard error carries no state-bearing line
    When the post-merge janitor runs
    Then the janitor verdict is red and not janitor-env-degraded
    And the red detail says the cluster gate reached no verdict
    And the item does not close
```

## Scenario 191 — The janitor-post-merge journal row names the venue that ran and, on the cluster, the gate's reading

```gherkin
Feature: A reader can tell from the janitor-post-merge row alone where the check suite ran, which rule chose it,
  and what the cluster gate said

  Scenario: A host-local janitor row names its venue, suite source and start and carries no gate fields
    Given a governed repository whose check-suite venue resolves to host_local
    When the post-merge janitor runs
    Then the janitor-post-merge row carries venue host_local, suite_source dispatcher.janitor.check_suite and a started_at timestamp
    And the row carries no gate_state, gate_tree_hash, job_name, namespace, job_started_at or job_finished_at

  Scenario: A cluster janitor row carries the gate's state word and the submitted tree
    Given a governed repository whose check-suite venue resolves to cluster_job
    And a delegated gate client whose verdict line on standard error reports state PASSED
    When the post-merge janitor runs
    Then the janitor-post-merge row carries venue cluster_job, suite_source gate_check_suite, gate_state PASSED and a started_at timestamp
    And the row's gate_tree_hash equals the full tree hash of the janitor checkout's HEAD

  Scenario: A cluster janitor row names gate_check_suite as its suite source even when dispatcher.janitor.check_suite is declared
    Given a governed repository whose check-suite venue resolves to cluster_job
    And whose .livespec.jsonc declares a dispatcher.janitor.check_suite command
    When the post-merge janitor runs
    Then the janitor-post-merge row carries venue cluster_job and suite_source gate_check_suite

  Scenario: A cluster janitor row copies only the Job keys the verdict line carries, including an explicit null
    Given a governed repository whose check-suite venue resolves to cluster_job
    And a delegated gate client whose verdict line carries job_name, namespace and job_started_at with the value null, and no job_finished_at
    When the post-merge janitor runs
    Then the janitor-post-merge row carries the reported job_name and namespace and carries job_started_at with the value null
    And the row carries no job_finished_at

  Scenario: A cluster gate with no verdict line records a null state word and still names the attempted venue and submitted tree
    Given a governed repository whose check-suite venue resolves to cluster_job
    And a delegated gate client whose standard error carries no state-bearing line
    When the post-merge janitor runs
    Then the janitor-post-merge row carries venue cluster_job and gate_state null
    And the row's gate_tree_hash equals the full tree hash of the janitor checkout's HEAD
```

## Scenario 192 — A turn cut by its node timeout leaves its commit run to finish or be named, and a hook still executing at the cut is a hook-over-limit event

```gherkin
Feature: A node-timeout cut neither discards a commit under way nor hides its cause
  As an operator recovering a needs-human run
  I want a commit run interrupted by a node timeout to finish or be named, and the cut to name its limit
  So that a proved repair is preserved and the stop is not presented as an agent's decision

  Scenario: A commit run that passes after the cut is preserved and named
    Given a fix turn that started a commit run through the commit runner
    And the fix node's resolved timeout ends the turn while that commit run is running
    When the commit run reaches passed before the needs_human node begins preservation
    Then the preserved tree's history contains that commit run's resulting HEAD commit
    And the item's needs-human cause names node-timeout, the fix node, its resolved timeout in seconds, and the commit run's identity with state passed

  Scenario: A commit run still running when the bounded wait ends is stopped before preservation
    Given a fix turn ended by its node's resolved timeout while a commit run it started is running
    When the needs_human node's bounded wait ends with that commit run still running
    Then the commit run is stopped before the preservation commit starts
    And the item's needs-human cause names the commit run with state no-verdict

  Scenario: An in-turn commit whose hook is still executing at the cut is a hook-over-limit event
    Given a fix turn that runs git commit inside its own tool call rather than through the commit runner
    And the fix node's resolved timeout ends the turn while that commit's hook run is executing
    When the run records the event
    Then the dispatch journal has a hook-over-limit row naming the fix node, the git commit operation and the node's resolved timeout in seconds
    And every process of that hook run is terminated before the next git commit or push in the sandbox starts
```

## Scenario 194 — A conflicted pyproject.toml does not make the repository's agent hooks refuse every tool call

```gherkin
Feature: The repository's agent hooks survive an unparseable project manifest
  As an agent repairing a refresh conflict in this repository
  I want the repository's PreToolUse hooks to leave my tools usable while pyproject.toml is conflicted
  So that the repair can fix the file whose conflict would otherwise disable it

  Scenario: A conflicted pyproject.toml lets a guarded tool call through and says so
    Given this repository's pyproject.toml carries unresolved merge-conflict markers
    When an agent makes a Bash, Write, Edit or MultiEdit call that a uv-launched PreToolUse hook command of this repository guards
    Then that hook command allows the call
    And it writes one line to standard error naming pyproject.toml as unparseable and stating that its guard was skipped for that call

  Scenario: A parseable pyproject.toml leaves every guard decision unchanged
    Given this repository's pyproject.toml parses
    When an agent makes a tool call that a uv-launched PreToolUse hook command of this repository guards
    Then that hook command returns the same allow or refuse decision it returned before this scenario was ratified
```

## Scenario 195 — A verified record is graded per assertion before the run advances, and a record-wide verdict line re-enters proof_verify

```gherkin
Feature: The verified record is graded per assertion before publication
  Scenario: A verified record with a verdict line in every assertion section advances
    Given proof_verify posted a verified record whose every factory_captured assertion section carries a prose Reproduced: yes line
    When the proof_grade node runs
    Then it exits zero and the run proceeds to pr_refresh
  Scenario: A record-wide verdict line is not a per-assertion verdict
    Given fewer than two proof_grade failures are recorded for the run
    And proof_verify posted a verified record whose only Reproduced: line sits under a trailing summary heading
    When the proof_grade node runs
    Then it records a failure and exits non-zero naming every factory_captured assertion
    And proof_grade_route re-enters proof_verify without visiting review or fix
    And proof_verify posts a new record without editing the earlier one
  Scenario: A verdict line inside a fenced proof is not a verdict
    Given proof_verify posted a verified record whose only Reproduced: yes line for an assertion is printed inside that assertion's fenced proof output
    When the proof_grade node runs
    Then it exits non-zero naming that assertion
  Scenario: Ungradeable records are bounded by the proof_grade failure count
    Given two proof_grade failures are already recorded for the run
    And the re-posted verified record is still ungradeable
    When the proof_grade node runs
    Then it records the third failure and proof_grade_route routes the run to non_converged
```

## Scenario 196 — Reconciliation releases or completes a stranded dispatch claim on its owning host, and holds with a named reason every claim it cannot prove stranded

```gherkin
Feature: The claim half of run reconciliation
  As a maintainer whose dispatch died before applying its terminal disposition
  I want the owning host's reconciliation to finish what that dispatch left undone
  So that the item is never stranded at active, and a claim that may still be live is never touched

  Background:
    Given an item active with assignee fabro, carrying neither rework:pending nor a merge-hold: label
    And its ledger run stamp names its run id, a declared factory, and this host as the dispatching host

  Scenario: A first absent run with no live owner is released
    Given the factory, queried by its declared server target, positively reports that the run does not exist
    And every ownership lock location for the item on this host was read and none is held by a live process
    And the forge reports no merged pull request for the item
    And the item's predecessor history is available and its preceding dispatch did not end in an absent-run release
    When a reconcile-runs pass runs
    Then the item is ready with no blocked_reason and no fabro assignee
    And one stranded-claim-release journal record names the item, the run id, the factory and the reason run-absent
    And one ledger comment on the item names the same facts

  Scenario: A second consecutive absent run rests for a human
    Given the factory positively reports that the run does not exist
    And no live owner is established and the forge reports no merged pull request
    And the item's predecessor history shows its preceding dispatch ended in an absent-run release
    When a reconcile-runs pass runs
    Then the item rests at blocked with blocked_reason needs-human
    And a ledger comment names both runs and the reason run-absent-repeated

  Scenario: A terminal failed run with no live owner receives the Dispatcher's own terminal disposition
    Given the run is terminal and failed, and no live owner is established
    And its recorded failure classifies as an eligible provider-limit cause
    When a reconcile-runs pass runs
    Then the item takes the provider-limit release of Factory-configurable ACP fallback priority, with its provider-limit-release record
    And a replay of the same pass writes no second release record and no second ledger comment

  Scenario: A first-stall cancel with no live owner is completed as a first-stall release
    Given the run is terminal, cancelled by the progress watchdog as the item's first stall, and no live owner is established
    When a reconcile-runs pass runs
    Then the item takes the first-stall release of Dispatcher progress watchdog

  Scenario: A repeated adapter launch failure keeps its retained route
    Given the run is terminal and failed, and no live owner is established
    And its unrecovered failing attempt is an adapter launch failure whose preceding dispatch also ended in an adapter launch failure
    When a reconcile-runs pass runs
    Then no adapter-launch-release record is written
    And the item rests at blocked with blocked_reason needs-human and its needs-human cause comment

  Scenario: An ordinary failed run rests for a human with its cause
    Given the run is terminal and failed with a failure no release route of Factory-configurable ACP fallback priority or Dispatcher progress watchdog claims, and no live owner is established
    When a reconcile-runs pass runs
    Then the item rests at blocked with blocked_reason needs-human
    And a needs-human cause comment names the run id and its innermost cause

  Scenario Outline: A claim that cannot be proved stranded is held with the reason of its first failing condition
    Given every condition graded before <reason> in the hold order passes
    And <condition>
    When a reconcile-runs pass runs
    Then the item stays active with assignee fabro and its labels unchanged
    And the pass lists the claim in held with the reason <reason>

    Examples:
      | condition                                                                        | reason                        |
      | the item carries no readable run stamp                                           | claim-unattributable          |
      | the item carries a pending stamp with no run id                                  | attribution-pending           |
      | the run stamp names another host as the dispatching host                         | owner-elsewhere               |
      | the declared factory cannot be reached                                           | factory-unobservable          |
      | the factory reports the run running, blocked or queued                           | run-live                      |
      | the run is terminal and one ownership lock location for the item cannot be read  | liveness-unobservable         |
      | the run is terminal and a live process holds the item's ownership lock           | dispatch-live                 |
      | the run is terminal and succeeded                                                | run-succeeded                 |
      | the run is absent and the forge cannot be asked                                  | forge-unobservable            |
      | the run is absent and a merged pull request exists for the item                  | merged-pr                     |
      | the run is absent and the preceding dispatch's outcome cannot be established     | history-unavailable           |
      | the run failed and its failure evidence cannot be read                           | terminal-evidence-unavailable |
      | the run is absent and the item is re-stamped with a different run before writing | claim-changed                 |
      | the run is absent and the presence of the journal record cannot be read          | effect-unobservable           |

  Scenario: The earliest failing condition names the hold
    Given the run stamp names another host as the dispatching host
    And the declared factory cannot be reached
    When a reconcile-runs pass runs
    Then the pass lists the claim in held with the reason owner-elsewhere

  Scenario: A claim owned by a live dispatch on another host is never released here
    Given the run stamp names host A as the dispatching host, and a Dispatcher on host A is alive and owns the item
    And the factory positively reports that the run does not exist
    When a reconcile-runs pass runs on host B
    Then the item stays active with assignee fabro
    And host B lists the claim in held with the reason owner-elsewhere

  Scenario: Marked and held items are not surveyed
    Given one active fabro item carries rework:pending and another carries a merge-hold: label
    And neither item's stamped run exists on its factory
    When a reconcile-runs pass runs
    Then neither item changes status
    And held lists neither item

  Scenario Outline: Every reconciliation surface releases a qualifying absent-run claim
    Given a freshly prepared claim that satisfies every condition of the first absent-run release scenario
    When reconciliation runs as <surface>
    Then the item is ready with no fabro assignee and one stranded-claim-release record names the reason run-absent

    Examples:
      | surface                         |
      | a Dispatcher loop tick          |
      | the dispatch preamble           |
      | the standalone reconcile-runs sweep |

  Scenario: A claim re-stamped between the comment and the transition is not overwritten
    Given a qualifying absent-run claim for run R whose journal record and ledger comment the recovery has written
    And the item's ledger run stamp names a different run S when the recovery re-reads it immediately before the transition
    When the recovery reaches the transition
    Then no status transition is written and the item keeps its claim for run S
    And the pass lists the claim in held with the reason claim-changed

  Scenario: Two reconcilers in different checkouts on the owning host recover a claim once
    Given two reconciliation passes start together on the owning host from different checkouts of the tenant's repository
    And both survey the same qualifying absent-run claim
    When both passes run
    Then exactly one stranded-claim-release journal record and one ledger comment exist for that item and run
    And the item is ready exactly once

  Scenario: An interrupted recovery resumes from its first missing effect
    Given a recovery wrote the stranded-claim-release journal record for a qualifying claim and stopped before the ledger comment
    When the next reconcile-runs pass runs
    Then it writes the ledger comment and then the status transition
    And no second journal record is written

  Scenario: An unreadable effect lookup writes nothing
    Given a recovery wrote the stranded-claim-release journal record for a qualifying claim and stopped before the ledger comment
    And the presence of the ledger comment cannot be read
    When the next reconcile-runs pass runs
    Then no ledger comment and no status transition is written
    And the pass lists the claim in held with the reason effect-unobservable

  Scenario: A newly admitted dispatch that has not learned its run is not mistaken for the old claim
    Given an item whose earlier claim for run R was moved to ready by a human valve
    And the item was then admitted again, and its admission wrote a pending stamp naming the new dispatch with no run id
    When a reconcile-runs pass runs while the factory reports run R absent
    Then the item stays active with assignee fabro
    And the pass lists the claim in held with the reason attribution-pending, naming the move valve as the remedy

  Scenario: A human valve that lands before the final re-read is respected
    Given a qualifying absent-run claim for run R whose recovery has written its journal record and ledger comment
    And a human valve moved the item to blocked before the recovery's final re-read
    When the recovery reaches the transition
    Then no status transition is written and the item stays blocked
    And the pass lists the claim in held with the reason claim-changed

  Scenario: A second recovery of the same claim writes nothing
    Given a qualifying absent-run claim that one reconcile-runs pass has already released
    When another reconciliation surface on the same host runs before any new dispatch
    Then no second stranded-claim-release record and no second ledger comment is written
    And the item stays ready
```

## Scenario 197 — A sandbox agent cannot remove the clone's repository or empty its whole tree, and ordinary in-tree removals still run

Governing clause: `contracts.md` §"ACP node timeouts" → "The run's repository survives the agent." and "One decision covers the run's protections."

```gherkin
Feature: The clone's repository and its whole tree survive the agent inside the factory sandbox
  As the maintainer of a repository dispatched through the factory
  I want an agent command that would destroy the clone's repository or empty its tree refused before it runs
  So that the engine's next checkpoint commit neither fails nor deletes the run's work

  Background:
    Given the implement-stage agent's ACP adapter runtime offers a hook that runs before each shell command
    And an implement-stage agent inside a factory sandbox whose clone is <clone>
    And the top level of <clone> holds the directory .git, the directories src and build, and the file README.md

  Scenario: removing the clone's .git directory is refused before it runs
    When the agent runs a shell command "rm -rf <clone>/.git"
    Then the command is refused before any part of it executes
    And the refusal names <clone>/.git as the protected path

  Scenario: emptying the clone's top level through a glob is refused
    When the agent runs a shell command "cd <clone> && rm -rf ./*"
    Then the command is refused and the refusal names <clone> as the protected path

  Scenario: an allowed removal does not exempt a refused one in the same command
    When the agent runs a shell command "rm -rf <clone>/build <clone>/.git"
    Then the command is refused and the refusal names <clone>/.git as the protected path

  Scenario: removals that leave a top-level entry still run
    When the agent runs "rm -rf <clone>/build" and then "rm <clone>/README.md"
    Then neither command is refused
    And <clone>/src still exists

  Scenario: the clone's .git directory mentioned only as data is not refused
    When the agent runs a shell command that passes "rm -rf <clone>/.git" to echo
    Then the command is not refused
```

## Scenario 198 — A sandbox agent cannot signal the sandbox's PID 1 or its own adapter, and signals to its own processes still run

Governing clause: `contracts.md` §"ACP node timeouts" → "The run's sandbox processes survive the agent." and "One decision covers the run's protections."

```gherkin
Feature: The sandbox's PID 1 and the agent adapter survive the agent's signals inside the factory sandbox
  As the maintainer of a repository dispatched through the factory
  I want an agent command that would signal the sandbox's PID 1 or its own adapter refused before it runs
  So that a cleanup step cannot kill the sandbox the engine still needs

  Background:
    Given the implement-stage agent's ACP adapter runtime offers a hook that runs before each shell command
    And a factory sandbox whose PID 1 command line is "/bin/bash -lc mkdir -p /workspace && sleep infinity"
    And the ACP agent adapter process has process id <adapter-pid> and the command line "node /usr/local/lib/claude-agent-acp/dist/index.js"
    And the guard can read the command lines of PID 1 and of the ACP agent adapter process
    And the agent started "python3 -m http.server 8765" in the background and recorded its process id <own-pid>
    And neither the name nor the command line of PID 1 or of the ACP agent adapter process matches the pattern "http.server 8765"

  Scenario: a pattern that matches PID 1's command line is refused
    When the agent runs a shell command "pkill -f 'sleep'"
    Then the command is refused before any part of it executes
    And the refusal names PID 1 and the pattern sleep

  Scenario: a selection filter does not remove a pattern's match on PID 1
    When the agent runs a shell command "pkill -f -P <own-pid> 'sleep'"
    Then the command is refused and the refusal names PID 1 and the pattern sleep

  Scenario: signalling PID 1, or every process, by id is refused
    When the agent runs a shell command "kill -TERM 1" or "kill -TERM -- -1"
    Then each command is refused and the refusal names the protected process and the operand it matched

  Scenario: signalling the adapter by id or by pattern is refused
    When the agent runs a shell command "kill <adapter-pid>" or "pkill -f 'claude-agent-acp'"
    Then each command is refused and the refusal names the ACP agent adapter process and the operand or pattern it matched

  Scenario: an allowed segment does not exempt a refused one in the same command
    When the agent runs a shell command "rm -rf /tmp/layout-sim; kill -TERM 1"
    Then the command is refused and the refusal names PID 1

  Scenario: signalling a process the agent started still runs
    When the agent runs "kill <own-pid>", "kill -1 <own-pid>" and "pkill -f 'http.server 8765'"
    Then none of the commands is refused
```

## Scenario 199 — A fix turn runs the check suite once per tree and counts a commit hook's full green run

```gherkin
Feature: A fix turn does not spend its time limit on a duplicate check suite
  As the maintainer of a repository dispatched to the factory
  I want a fix turn to count a commit hook's full green suite run as the turn's suite run
  So that two full runs of a long suite do not exhaust the fix node's time limit

  Scenario: A commit whose hook ran the full suite green ends the turn's suite obligation for that tree
    Given a fix turn that commits its change
    And the repository pre-commit hook ran the full check suite to a passing result on the committed tree
    When the fix turn completes successfully on that tree
    Then the fix prompt directs no second run of the suite on that tree in the same turn

  Scenario: A partial hook run or a later change still requires a full run
    Given a fix turn whose only commit took the hook's partial fast path, or whose tree changed after its last full passing run
    When the fix turn completes successfully
    Then the fix prompt directs a full run of the check suite before the turn ends

  Scenario: A refresh-repair round applies the same rule to the integrated tree
    Given a fix turn entered with a refresh-repair brief
    And its commit on the integrated tree ran the full check suite green through the pre-commit hook
    When the turn completes the repair successfully
    Then the fix prompt directs no second run of the suite on that integrated tree in the same turn
```

## Scenario 200 — A refresh whose conflicts lie only in declared record files merges them without a repair round

```gherkin
Feature: Concurrent additions to shared record files do not cost a run a repair round
  As the maintainer of a repository dispatched to the factory
  I want conflicts confined to declared record files merged entry by entry during a refresh
  So that two changes that each add their own records do not send a run to the fix agent or to a human

  Scenario: Different objects changed by each side of a declared JSON record merge cleanly
    Given a repository whose committed dispatcher.record_files declares tests/heading-coverage-debt.json with format json-array and key spec_root, spec_file and heading
    And the default branch removed the object for one heading while the run removed the object for a different heading
    When pr_refresh rebases the run onto the default branch and the rebase conflicts only in that file
    Then the stage merges the file with both objects removed, completes the rebase and runs the repository-declared gate on the refreshed head
    And the stage records the merged file with its format and the count taken from each side
    And no refresh-repair round is counted and the run does not enter fix

  Scenario: Insertions by both sides at the same place in a declared Markdown record keep both
    Given a repository that declares tests/integration/CLAUDE.md with format markdown-insertions
    And the default branch and the run each inserted a section at the same position in that file
    When publish_draft or pr_refresh refreshes the run and the refresh conflicts only in that file
    Then the merged file holds the default branch's inserted lines followed by the run's inserted lines
    And the stage proceeds as after a refresh that did not conflict

  Scenario: The same object changed differently by both sides takes refresh repair
    Given a declared json-array record in which both the default branch and the run changed the object with the same key to different values
    When pr_refresh rebases the run and the rebase conflicts in that file
    Then the stage restores the pre-refresh head, records a refresh-repair brief naming the file, and routes to fix

  Scenario: A conflict outside the declared record files takes refresh repair
    Given a refresh that conflicts in a declared record file and in a Python module
    When pr_refresh rebases the run
    Then the stage merges nothing, restores the pre-refresh head, and routes to fix with a refresh-repair brief naming both paths

  Scenario: A merged head the gate rejects takes refresh repair
    Given a refresh whose conflicts were all resolved by the record-file merge
    When the repository-declared gate rejects the refreshed head
    Then the stage restores the pre-refresh head and routes to fix with a refresh-repair brief naming each failed gate target
```

## Scenario 201 — A clock-fired work supply drains a tenant on its interval without an interactive session, resolves the plugin build at each firing, and does not wait on a long pass

```gherkin
Feature: Factory work supply does not depend on an interactive session
  As a maintainer whose factory sat idle for hours with ready work because no session ran a drain
  I want a timer to start an unattended drain pass for each tenant on an interval
  So that ready work reaches the factory whether or not any session is running

Scenario: A firing starts one unattended drain pass for its tenant
  Given the work-supply timer is installed for tenant repository "T" with an operator-chosen interval
  And no interactive session is running a drain
  And "T"'s first-ranked admission-eligible ready item has a free counted-claim slot under wip_cap
  When the timer fires with a budget of at least one
  Then the service runs loop --repo T with that budget and no --item argument
  And that first-ranked item is dispatched under the same ranked queue, wip_cap and unattended cost gate as any unattended drain
  And when instead wip_cap or the budget leaves no room, the item is journaled with the exclusion reason the admission conditions assign it, and is not dispatched

Scenario: The installer refuses an instance whose wrapper is not executable
  Given an operator installing a work-supply instance for tenant "T" whose named credential wrapper is not an executable file on the host
  When the installer runs
  Then it refuses that instance, naming the instance and the wrapper path

Scenario: The installer refuses an interval below the documented minimum
  Given an operator installing a work-supply instance for tenant "T" with a firing interval shorter than the installer's documented minimum
  When the installer runs
  Then it refuses that instance, naming the instance, the interval given and the minimum

Scenario: Each firing executes the tenant's registered plugin build
  Given the work-supply timer is installed for tenant "T"
  And the registered plugin install for "T" moves to a newly released build
  When the timer next fires
  Then the pass executes the newly registered build without the unit being reinstalled
  And when instead no registered install exists for "T" the firing refuses, naming "T", and executes no build

Scenario: A long pass does not stop the next firing
  Given a work-supply pass for tenant "T" whose dispatched run is still in progress
  When the next interval elapses
  Then the timer starts a new pass
  And the new pass is governed by wip_cap as any unattended drain
```

## Scenario 202 — An agent stage follows only its stage prompt, never publishes, and commits through the repository hooks

```gherkin
Feature: An agent stage does not act on instructions its stage prompt never gave
  As the maintainer of a repository dispatched to the factory
  I want implement, fix and review_fix turns to take instruction only from their stage prompt
  So that a run is not lost to a step that a file on its own branch or its own deliverable described

  Scenario: A prompt file the work item changes does not instruct the run carrying it
    Given a work item whose branch changes the fix prompt to require a commit mechanism that is not yet released
    When a fix turn of that work item's run makes its commit
    Then the turn commits with an ordinary git commit that runs the repository hooks
    And the turn does not wait for or report the absence of the unreleased mechanism

  Scenario: An agent stage never pushes or publishes
    Given an implement, fix or review_fix turn whose work is committed
    When the turn ends
    Then the turn has pushed no ref to origin and has opened or changed no pull request
    And publication happens only in publish_draft, pr_refresh or pr

  Scenario: The stage prompts state the three rules
    Given the implement, fix and review_fix prompts of the released implement-work-item workflow
    When each prompt is read
    Then each states that the stage prompt is the turn's only instruction, that the turn never pushes or publishes, and that commits are ordinary git commits through the repository hooks unless the stage prompt names another mechanism
```

## Scenario 203 — An unpinned dispatch goes to the least-utilized declared factory that has a free scheduler slot

```gherkin
Feature: Unpinned dispatches overflow to the least-utilized declared factory
  As a maintainer whose default factory is saturated while a second declared factory sits idle
  I want an unpinned dispatch to go to whichever declared factory's own scheduler is least utilized and has a free slot
  So that every seat's ordinary dispatches use the second factory without any seat choosing it by hand

Scenario: The less-utilized overflow factory receives the dispatch
  Given dispatcher.default_factory names factory "A" and dispatcher.overflow_factories is ["B"]
  And factory "A"'s server reports 6 non-terminal runs and a max_concurrent_runs of 10
  And factory "B"'s server reports 0 non-terminal runs and a max_concurrent_runs of 2
  And the item carries no recorded factory and no explicit factory is selected
  When the Dispatcher dispatches the item
  Then the run is submitted to factory "B"
  And the item's dispatch-factory record names factory "B"
  And one overflow-selection journal record lists "A" with 6 of 10 and "B" with 0 of 2, chosen "B", reason least-utilized-free-slot

Scenario: The less-utilized default factory keeps the dispatch
  Given the same configuration but factory "A"'s server reports 4 of 10 and factory "B"'s server reports 1 of 2
  When the Dispatcher dispatches the item
  Then the run is submitted to factory "A"
  And the overflow-selection journal record names chosen "A", reason least-utilized-free-slot

Scenario: Equally utilized candidates go to the earlier candidate
  Given the same configuration but factory "A"'s server reports 5 of 10 and factory "B"'s server reports 1 of 2
  When the Dispatcher dispatches the item
  Then the run is submitted to factory "A"
  And the overflow-selection journal record names chosen "A", reason least-utilized-free-slot

Scenario: With no free slot anywhere the dispatch goes to the default factory and is not refused
  Given the same configuration but factory "A"'s server reports 10 of 10
  And factory "B"'s server reports 2 of 2, or its read fails
  When the Dispatcher dispatches the item
  Then the run is submitted to factory "A" and queues in "A"'s scheduler
  And the overflow-selection journal record names chosen "A", reason no-candidate-free-default
  And when "B"'s read failed, the journal record names the reason "B"'s read failed in place of its counts
  And the dispatch is neither refused nor deferred

Scenario: A pinned dispatch reads no capacity and journals no selection
  Given the dispatch is invoked with --factory "A", or LIVESPEC_FABRO_FACTORY names "A", or the item's recorded factory is "A"
  When the Dispatcher dispatches the item
  Then the run is submitted to factory "A" without reading either server's run count or max_concurrent_runs
  And no overflow-selection journal record is written
```

## Scenario 204 — An implement turn that reports its work incomplete fails the implement stage

```gherkin
Feature: An incomplete implement turn is not recorded as a success
  As the maintainer of a repository dispatched to the factory
  I want an implement turn that stops partway to end the implement stage as failed
  So that the run does not publish and prove an incomplete change as if it were finished

  Scenario: A turn that reports partial progress fails the stage
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
    And the run takes the implement stage's failure edge, and the dispatch outcome detail carries that cause

  Scenario: A turn with no completion field is treated as incomplete
    Given an implement turn whose final output carries no completion field
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress

  Scenario: A turn that reports its work complete keeps its routing
    Given an implement turn whose final output's completion field reports the Definition of Done complete
    When the implement stage ends
    Then the stage outcome is succeeded and the run proceeds to implementation_diff as before
```

## Scenario 205 — Gap detection enumerates headings without an exercising test

```gherkin
Feature: The gap signal is heading coverage, not clause tracking
  As a maintainer keeping the spec and its tests in lockstep
  I want gap detection to name the spec headings no test exercises
  So that every candidate it surfaces is a real, bounded piece of work

  Scenario: An uncovered heading is a gap and a covered one is not
    Given a governed spec tree whose heading-coverage map marks one H2 heading TODO and names an existing test for another
    When detect-impl-gaps runs with --json
    Then it emits exactly one gap, whose gap-id derives from the uncovered heading's spec file and heading path
    And the covered heading produces no gap
    And no MUST or SHOULD clause is enumerated

  Scenario: A heading with no coverage entry at all is a gap with a stable id
    Given a governed spec tree with one H2 heading that has no entry in the heading-coverage map
    When detect-impl-gaps runs with --json twice
    Then each run emits exactly one gap for that heading
    And both runs emit the same gap-id

  Scenario: An entry naming a test that does not exist is an uncovered heading and a finding
    Given a heading-coverage entry whose test names a test node that does not exist
    When detect-impl-gaps runs with --json
    Then it emits one gap for that heading
    And surfaces a finding naming the dangling entry, never a clean absence

  Scenario: An incomplete entry is an uncovered heading and a finding, unlike an absent one
    Given one H2 heading whose identifying coverage entry has no test value
    And another H2 heading with no coverage entry at all
    When detect-impl-gaps runs with --json
    Then it emits one gap for each of the two headings
    And surfaces a finding naming the incomplete entry and its missing field
    And surfaces no finding for the heading with no entry

  Scenario: An entry that identifies no heading is a finding and never a gap
    Given a coverage entry with test TODO and no heading value
    And a coverage entry naming a heading the live spec tree does not contain
    When detect-impl-gaps runs with --json
    Then it surfaces one finding for each of the two entries
    And neither entry produces a gap or a gap-id
    And every live H2 heading without an identifying entry is still emitted as a gap

  Scenario: Coverage entries match on spec root, spec file and heading together
    Given contracts.md and scenarios.md each carry an H2 heading with the same text
    And the coverage map names an existing test for that heading under scenarios.md only
    When detect-impl-gaps runs with --json
    Then it emits one gap, for the contracts.md heading
    And the scenarios.md heading produces no gap

  Scenario: A filed gap names the heading and the coverage entry to fill
    Given the uncovered heading above
    When the user consents to file it through capture-impl-gaps
    Then the filed item carries the origin:gap-tied label and the heading-derived gap-id label
    And its title names the heading verbatim and its description names the coverage entry to fill

  Scenario: Clause-derived gap ids are migrated to heading-derived ones
    Given a live gap-tied item filed under the clause enumeration
    When the change landing this clause runs its migration
    Then the item carries the heading-derived gap-id of the heading its clause sits under
    And livespec core's gap-tracking-one-to-one and no-stale-gap-tied invariants pass
    And a closed item keeps its historical clause-derived label
```

## Scenario 209 — A provider refusal booked as a successful turn is released, not left for a human

```gherkin
Feature: A provider refusal delivered as turn text is a failed attempt of its candidate
  As the maintainer of a repository dispatched to the factory
  I want a turn that ends with a measured provider refusal to count as that candidate's failure
  So that a transient provider condition releases the item for re-dispatch instead of losing the run to a human gate

  Scenario: A codex-acp capacity refusal on review releases the item
    Given a review node attempt on the codex-acp candidate that the engine recorded as succeeded
    And the attempt's recorded turn output is "I'm reviewing the branch and its latest captured proof against the six stated acceptance assertions. I'll make no changes.Selected model is at capacity. Please try a different model."
    And the run ended at the needs_human terminal through that attempt's unmatched review outcome edge
    And no later attempt of any node failed
    When the Dispatcher reconciles the terminal run
    Then it records a candidate hold with cause provider_capacity for that codex-acp candidate
    And it journals one provider-limit-release record whose source is turn.final_output
    And the item returns to ready with no blocked reason and no needs-human decision

  Scenario: Refusal words that are not the output's tail do not match
    Given a succeeded agent node attempt whose output contains "Selected model is at capacity. Please try a different model." and then continues with a review verdict
    When the Dispatcher classifies the attempt
    Then no turn.final_output signature matches and the attempt remains a success

  Scenario: An output ending with an explicitly marked quotation of the refusal does not match
    Given a succeeded codex-acp agent node attempt whose output ends with: The adapter reported "Selected model is at capacity. Please try a different model."
    And another whose output ends with: The adapter reported: Selected model is at capacity. Please try a different model.
    When the Dispatcher classifies each attempt
    Then no turn.final_output signature matches either attempt and each remains a success

  Scenario: An unmarked reproduction of the refusal at the end of the output matches
    Given a succeeded codex-acp review attempt whose output is "Review passed. The adapter diagnostic is reproduced verbatim below. Selected model is at capacity. Please try a different model."
    And the run reaches its successful exit
    When the Dispatcher reconciles the run
    Then the capacity form matches the attempt and it records the candidate hold for that codex-acp candidate
    And the run keeps its successful outcome and the Dispatcher journals no provider-limit-release record

  Scenario: A later failure keeps its own route
    Given a codex-acp review attempt reclassified as a failed attempt by the capacity form
    And a later command node attempt in the same run failed with a test failure that determined the run's terminal
    When the Dispatcher reconciles the terminal run
    Then it records the candidate hold for the codex-acp candidate
    And it journals no provider-limit-release record for the run
    And the item keeps the test failure's existing route

  Scenario: A reclassified attempt does not retire a hold
    Given a live candidate hold on the codex-acp candidate
    And a later attempt on that candidate whose recorded turn output ends with the measured capacity refusal
    When the Dispatcher evaluates hold retirement
    Then the hold is not retired by that attempt

  Scenario: The codex-acp form does not match a claude-acp attempt
    Given a succeeded claude-acp attempt whose recorded turn output ends with "Selected model is at capacity. Please try a different model."
    When the Dispatcher classifies the attempt
    Then the built-in codex-acp capacity form does not match it
```

## Scenario 210 — Reconciliation clears a stale fabro assignee from a ready item, and holds with a named reason every one it cannot clear

```gherkin
Feature: A ready item still assigned fabro is a stale assignee, not a dispatch claim
  As a maintainer whose ownership surveys read an item's status and assignee
  I want reconciliation to clear the fabro assignee a finished claim left behind on a ready item, and its next dispatch to go through recovery routing
  So that a ready item is not read as both available and owned, its published work is resumed when the resume preconditions pass and otherwise routed by recovery routing, and one that may still be owned is never touched

  Background:
    Given an item ready with assignee fabro, carrying neither rework:pending nor a merge-hold: label

  Scenario: A stale assignee whose run failed is cleared without a terminal disposition
    Given its ledger run stamp, which is not pending, names its run id, a declared factory, and this host as the dispatching host
    And every ownership lock location for the item on this host was read and none is held by a live process
    And the factory, queried by its declared server target, reports the run terminal and failed
    When a reconcile-runs pass runs
    Then the item is ready with no fabro assignee, and its labels and run stamp are unchanged
    And one stale-assignee-clear journal record names the item, the run id, the factory and the run state failed
    And one ledger comment on the item names the same facts
    And no provider-limit-release record, no stranded-claim-release record and no needs-human rest is written

  Scenario: A stale assignee whose run is absent is cleared
    Given its run stamp names its run and this host, and no live owner is established
    And the factory positively reports that the run does not exist
    When a reconcile-runs pass runs
    Then the item is ready with no fabro assignee
    And one stale-assignee-clear journal record names the run state absent

  Scenario: A cleared stale assignee whose run published an open pull request resumes it
    Given its run stamp names its run and this host, and no live owner is established
    And the factory reports the run terminal and succeeded, and the run's pull request is open
    And every published-pull-request resume precondition passes for that pull request
    When a reconcile-runs pass runs and the item is next dispatched
    Then the pass clears the stale assignee with one stale-assignee-clear record naming the run state succeeded
    And recovery routing grades the next dispatch and takes the resume route from that pull request rather than a fresh dispatch

  Scenario Outline: A stale assignee that cannot be cleared is held with the reason of its first failing condition
    Given every condition graded before <reason> in the stale assignee hold order passes
    And <condition>
    When a reconcile-runs pass runs
    Then the item stays ready with assignee fabro and its labels unchanged
    And the pass lists the item in held with the reason <reason>

    Examples:
      | condition                                                                       | reason                |
      | the item carries no readable run stamp                                          | claim-unattributable  |
      | the item carries a pending stamp with no run id                                 | attribution-pending   |
      | the run stamp names another host as the dispatching host                        | owner-elsewhere       |
      | the declared factory cannot be reached                                          | factory-unobservable  |
      | the claim half observes the run running, blocked or queued                      | run-live              |
      | the run is terminal and one ownership lock location for the item cannot be read | liveness-unobservable |
      | the run is terminal and a live process holds the item's ownership lock          | dispatch-live         |
      | the run failed and the presence of the journal record cannot be read            | effect-unobservable   |

  Scenario: A human move before the assignee write is respected
    Given its run stamp names its run and this host, and no live owner is established
    And the factory reports the run terminal and failed
    And the clearance has written its journal record and ledger comment
    And a human valve moved the item to backlog before the clearance's final re-read
    When the clearance reaches the assignee write
    Then no assignee write is made and the item stays backlog with assignee fabro
    And the pass lists the item in held with the reason claim-changed

  Scenario: A held stale assignee is still graded by recovery routing
    Given a stale assignee the pass has listed in held with the reason owner-elsewhere
    And the run's pull request is open, and the factory cannot be reached when the item is next dispatched
    When the item is next dispatched
    Then recovery routing grades the dispatch and routes it held because a measurement cannot be taken
    And no fresh dispatch is started for the item

  Scenario: A merged pull request is recovered by reconcile-merged from ready
    Given a ready item, cleared or held as a stale assignee, whose latest dispatch's pull request has merged
    When the item is next dispatched
    Then recovery routing holds the dispatch for the merged pull request, naming reconcile-merged as the remedy
    And reconcile-merged for the item runs its post-merge janitor and, when the janitor is green, moves the item from ready to acceptance
    And when a guarded precondition of reconcile-merged fails, the item stays ready

  Scenario: A pending-stamp stale assignee is held and admitted as any ready item
    Given its ledger stamp is a pending stamp with no run id
    When a reconcile-runs pass runs
    Then the item stays ready with assignee fabro and the pass lists it in held with the reason attribution-pending
    And the item is not released for recovery, and its next admission replaces the pending stamp as any admission of a ready item does

  Scenario: An interrupted clearance resumes from its first missing effect
    Given its run stamp names its run and this host, no live owner is established, and the factory reports the run terminal and failed
    And a clearance wrote the stale-assignee-clear journal record and stopped before the ledger comment
    When the next reconcile-runs pass runs
    Then it writes the ledger comment and then the assignee write
    And no second stale-assignee-clear journal record is written

  Scenario: A pull request that merges after clearance is recovered by reconcile-merged
    Given a stale assignee cleared while its run's pull request was open
    And that pull request merged before the item's next dispatch
    When the item is next dispatched
    Then recovery routing holds the dispatch for the merged pull request, naming reconcile-merged as the remedy
    And reconcile-merged for the item, which is ready with no assignee, runs its post-merge janitor and, when the janitor is green, moves the item from ready to acceptance

  Scenario: A second pass over a cleared stale assignee writes nothing
    Given a stale assignee that one reconcile-runs pass has already cleared
    When another reconciliation surface on the same host runs before any new dispatch
    Then no second stale-assignee-clear record and no second ledger comment is written
    And the item stays ready with no assignee
```

## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification

```gherkin
Feature: New behaviour gets new spec before it is built
  As the maintainer keeping the implementation and the specification in lockstep
  I want every feature whose behaviour the spec does not state to wait for its proposal to ratify
  So that implementation never runs ahead of the specification while bugs and chores keep their leeway

  Scenario: An unstated feature is held and the wall refuses it
    Given an implement-kind item typed feature whose asked-for behaviour the spec-stated judgement reports unstated
    When the item is filed
    Then the verdict, the generalization target and the proposed-change topic it must link are recorded on the item
    And the item is spec-change tier and is not routed to ready
    And a dispatch of the item is refused with exit code 5 naming the unratified topic

  Scenario: A bug is routed as today
    Given an implement-kind item the judgement classifies bug
    When the item is filed
    Then it is routed through intake exactly as an item not subject to the tier

  Scenario: Ratification releases the hold without a human valve
    Given a held spec-change-tier item whose linked topic now has a revision record with decision accept
    And the judgement re-run against the ratified spec returns stated for its asked-for behaviour
    And the item's effective admission_policy is auto
    When the next intake or drain pass reaches the item
    Then the item is no longer spec-change tier and is routed to ready with no human valve

  Scenario: Ratification releases the hold but leaves a manual admission policy in force
    Given a held spec-change-tier item whose linked topic now has a revision record with decision modify
    And the judgement re-run against the ratified spec returns stated for its asked-for behaviour
    And the item's effective admission_policy is manual
    When the next intake or drain pass reaches the item
    Then the spec hold is released and the item rests at pending-approval for the approve valve

  Scenario: A rejected or narrowed proposal does not release the hold
    Given a held spec-change-tier item whose linked topic has a revision record with decision reject
    When the next drain pass reaches the item
    Then the item stays held and the refusal names the topic

  Scenario: A follow-up to a ratified change is not held
    Given an implement-kind item carrying a spec_commitment_hint from a ratified proposal
    And the judgement reports its asked-for behaviour stated
    When the item is filed
    Then it is not spec-change tier

  Scenario: A commitment hint does not exempt unstated behaviour
    Given an implement-kind item typed feature carrying a spec_commitment_hint from a ratified proposal
    And the judgement reports part of its asked-for behaviour unstated
    When the item is filed
    Then it is spec-change tier and is held for a linked proposal

  Scenario: A classification that cannot run records itself and leaves the backstop
    Given the classification cannot run for a filed feature
    When intake routes the item
    Then the item is routed as it would be without the classification and the did-not-run cause is recorded on it
    And the dod_gate node refuses the item before implement when the judgement in-run reports the behaviour unstated

  Scenario: A citation that does not govern is remedied with the judgement's heading
    Given a ready item whose References line names a heading that does not govern its assertions
    When the pre-admission judgement runs
    Then the item is held with the governing heading the spec-stated judgement returned as the remedy
```

## Scenario 207 — The drift run processes each merge behind a contiguous frontier and files proposals it never accepts

```gherkin
Feature: Implementation that outruns the specification is caught at every merge
  As the maintainer keeping the specification honest against the implementation
  I want every default-branch merge judged against the ratified spec and its unstated behaviour proposed
  So that the feedback loop turns without a session and without a human accepting anything by machine

  Scenario: A merge adding unstated behaviour files one proposal and advances the frontier
    Given a recorded drift frontier and one later default-branch merge whose diff adds a behaviour the spec-stated judgement reports unstated
    When the reconcile pass runs
    Then one proposed change with a drift origin is filed naming the generalization target
    And a completed drift coverage record names that merge as the frontier

  Scenario: A failed merge stops the frontier under a later success
    Given two merges after the frontier where the pass over the first fails and the pass over the second succeeds
    When the reconcile pass runs
    Then the frontier does not advance past the first merge
    And an attempt record names the failed merge
    And the drift-staleness fact still names both merges

  Scenario: A retried pass files no duplicate
    Given a merge whose finding was already filed under its finding identity
    When the reconcile pass processes the merge again
    Then no second proposed change is filed for that finding

  Scenario: Findings beyond the queue cap are held, not filed
    Given dispatcher.drift_proposal_queue_cap open drift-origin proposals
    When a merge adds another unstated behaviour
    Then the finding is held on the detection-coverage anchor with its identity
    And the frontier does not advance past that merge
    And needs-attention lists the held finding with a handoff naming revise

  Scenario: A merge no janitor saw is processed
    Given a spec pull request merged by hand after the frontier
    When the next reconcile pass runs
    Then that merge is processed exactly as a dispatched merge

  Scenario: The pass never accepts a proposal
    Given a drift-origin proposed change filed by the pass
    When the pass completes
    Then the proposal rests under proposed_changes for revise and the pass takes no decision on it
```

## Scenario 211 — An unmet plan obligation is superseded only by a typed event whose cause verifies, and keeps its original budget

```gherkin
Feature: A wrong obligation can be retired without letting a rename evade expiry
  As the maintainer whose plan pointer was overwritten by a derivation
  I want an evidenced supersession that the ledger can verify
  So that a mis-derived or disposed obligation is replaced while the original budget still binds

  Scenario: A mis-derived obligation is superseded with its deriving operation as evidence
    Given an unmet plan obligation written by the plan-resume actor in a recorded epoch transition
    And it names an impl step whose target work-item already carried a factory-safety label when that transition was recorded
    When set_next_action carries a supersession with cause misderived naming that operation identity and a replacement result
    Then a plan-progress-event of kind supersession is recorded before the pointer changes
    And the replacement result carries the superseded obligation's original deadline and consumed handoff count

  Scenario: A rename without a verified cause is refused
    Given an unmet plan obligation written by an accepted handoff
    When set_next_action carries a supersession with cause misderived
    Then the write is refused because no derivation wrote that obligation
    And the pointer and the obligation are unchanged

  Scenario: A correctly derived obligation is not misderived
    Given an unmet plan obligation written by the plan-resume actor naming an impl step whose target carries no factory-safety label
    When set_next_action carries a supersession with cause misderived
    Then the write is refused and the obligation is unchanged

  Scenario: A label applied after the derivation does not make it misderived
    Given an unmet plan obligation written by the plan-resume actor naming an impl step whose target was factory-eligible when it was derived
    And a factory-safety label was applied to that target after the deriving transition
    When set_next_action carries a supersession with cause misderived
    Then the write is refused and the obligation is unchanged

  Scenario: A supersession to an already satisfied result is refused
    Given an unmet plan obligation that qualifies for supersession
    When the supersession names a replacement result that is already satisfied
    Then the write is refused and the original obligation and its budget stand

  Scenario: A disposed target is superseded with its ledger record as evidence
    Given an unmet plan obligation whose target work-item is closed as superseded
    When append_handoff carries a supersession with cause disposed naming that record
    Then the supersession is recorded and consumes no handoff unit of its own
    And the handoff itself consumes its one unit against the inherited count

  Scenario: A retried supersession records nothing new
    Given a recorded supersession under an operation identity
    When the same operation identity is retried
    Then the recorded event is returned and no second event is written
```

## Scenario 212 — The sandbox-images command reports the sandbox image sources a dispatch without an explicit workflow path resolves, through dispatch resolution, and changes nothing

```gherkin
Feature: Read-only sandbox image enumeration
  As the operator of a docker factory host's image-warm timer
  I want the sandbox image sources of every dispatch without an explicit workflow path, across the defined repositories and builds
  So that the host holds each tag before the first run that needs it
  Scenario: A factory with a catalog environment reports the environment, not an image
    Given a repository whose dispatcher.factories entry for factory F declares a catalog environment E
    When dispatcher.py sandbox-images --factory F --repo <that repository> --json runs
    Then it prints one entry for that repository with source catalog_environment and environment E
    And that entry carries no image of its own
  Scenario: The configured-image resolver wins over every workflow pin, environment first
    Given a repository R with no catalog environment for factory F that sets dispatcher.fabro_sandbox_image to I and commits its own implement-work-item workflow.toml
    And LIVESPEC_FABRO_SANDBOX_IMAGE is J in the command's environment
    When the command runs for factory F and R
    Then it calls the same configured-image resolver a dispatch calls
    And it prints one entry for R with image J and source dispatcher.fabro_sandbox_image
  Scenario: Each declared named variant and the reserved workflow are reported
    Given a repository R with neither a catalog environment nor a configured image that declares named variants V1 and V2 under dispatcher.workflows
    And R commits its own implement-work-item workflow.toml pinning image J
    When the command runs for factory F and R
    Then it calls the same workflow resolver a dispatch calls
    And it prints one named_variant entry for V1 and one for V2, each with that variant's docker pin and the path of its workflow.toml
    And it prints one committed_run_config entry with image J and the path of that workflow.toml
  Scenario: Executing builds form a host-wide deduplicated union
    Given a repository R with neither a configured image, its own workflow nor named variants, whose registered build is B1
    And B1 has only a stale lease
    And a live session for another repository holds a lease on B2
    And a running Dispatcher executes B3 without a live lease
    And another running Dispatcher executes B2
    And B4 has only a stale lease and no other inclusion route
    When the command runs for factory F and R
    Then it reports exactly one bundled_run_config entry each for B1, B2 and B3, each with that build's bundled docker pin
    And it reports none for B4
    And each entry names R, its build identity and its workflow path
  Scenario: Default discovery uses this plugin's project registrations
    Given this plugin has install records with projectPath roots R1 and R2
    And another plugin alone is registered for R3
    When the command runs without --repo
    Then it enumerates exactly R1 and R2
  Scenario: Explicit repositories replace registry discovery
    Given this plugin is registered for R1 and R2
    When the command runs with --repo R3 --repo R4
    Then it enumerates exactly R3 and R4
  Scenario: An undeclared factory is a successful report
    Given repository R does not declare factory F
    When the command runs for F and R
    Then it reports source factory_undeclared naming R with no image
    And it exits zero
  Scenario: JSON output contains every repository-labelled entry
    Given multiple repositories produce multiple entries including an unreadable entry
    When the command runs with --json
    Then stdout is one JSON array containing every entry as an object
    And every object names its repository
  Scenario Outline: Unreadable dependencies do not truncate enumeration
    Given an entry depends on a <source> that <failure>
    And other entries have readable dependencies
    When the command runs
    Then it reports source unreadable naming the failed path and repository
    And it reports every other entry
    And it exits non-zero

    Examples:
      | source                  | failure          |
      | .livespec.jsonc         | cannot be read   |
      | .livespec.jsonc         | cannot be parsed |
      | named variant workflow  | cannot be read   |
      | committed workflow      | cannot be parsed |
      | bundled workflow        | cannot be read   |
      | bundled workflow        | cannot be parsed |
  Scenario: The command changes nothing
    Given any repositories and factory F
    When the command runs
    Then no ledger record, dispatch-journal row or Fabro run is created
    And no image is pulled, built or tagged
    And no file is created, modified or deleted, including any lease file
```

## Scenario 227 — Fabro event reads are bounded in size, retries and concurrency

```gherkin
Feature: The Dispatcher's Fabro event reads cannot become unbounded factory load
  As an operator of a shared factory
  I want every events read bounded
  So that a long run's slow event log does not draw continuous re-reads

  Scenario Outline: Later reads are bounded for every caller
    Given <caller> has already read a run's events
    When that Dispatcher process reads the run again
    Then the read is bounded to events after the newest observed instant or to a bounded tail

    Examples:
      | caller                |
      | progress watchdog     |
      | ACP projection        |
      | ACP reconcile replay  |
      | review-gate reader    |
      | cost reader           |

  Scenario: Bounded samples preserve established liveness state
    Given the watchdog has established a run's progress instant
    And a command node started before the read boundary and has not completed
    When a successful bounded read contains no newer progress or command-node transition
    Then the sample retains the established progress instant
    And it still reports that command node as open
    And an older event instant does not mask a newer heartbeat instant

  Scenario: A completion updates carried command-node state
    Given an earlier sample established an open command node
    When a successful bounded read contains that node's completion and no new command-node start
    Then the sample no longer reports that command node as open

  Scenario: Watchdog sample cost is independent of total event count
    Given two runs with the same bounded observation data and established liveness state
    And one run has a larger historical event log
    When the watchdog samples each run
    Then the sample cost does not grow with the larger total event count

  Scenario Outline: Failed reads are journaled and remain unobservable
    Given a fabro events read <failure>
    When the Dispatcher handles the result
    Then it journals exactly one fabro-events-read-failed record
    And the record names the work-item, run id, factory, reading caller, elapsed seconds, consecutive attempt number and next-read backoff
    And that caller does not read that run again before the backoff expires
    And the failure is an unobservable sample
    And the failure is not evidence of disappearance or lack of progress

    Examples:
      | failure             |
      | times out           |
      | exits non-zero      |
      | returns zero bytes  |

  Scenario: Consecutive failures increase backoff and success resets it
    Given a caller's first failed read of a run
    When further consecutive reads by that caller fail
    Then the first backoff is at least 60 seconds
    And each subsequent backoff is at least twice the preceding backoff
    And the consecutive attempt number increases on each failure
    When a read succeeds and the following read fails
    Then the new failure has consecutive attempt number 1
    And its backoff is at least 60 seconds

  Scenario: Repeated projection read failures are exhausted durably
    Given the ACP projection's read of a run has failed on four consecutive attempts
    When its fifth consecutive attempt fails
    Then reconcile-runs journals exactly one acp-projection-exhausted record
    And the record names the work-item, run id, factory, attempt count 5 and last failure reason
    And the projection failure remains visible as exhausted
    When later reconcile-runs passes run
    Then none reads that run's events
    And none duplicates the exhaustion record or clears the failure
    When a new dispatch creates a new run for the same work-item
    Then the earlier run's exhaustion does not prevent reading the new run

  Scenario: A reconcile pass deduplicates reads of one run
    Given multiple reconciliation paths require events from the same run
    When one reconcile-runs pass executes
    Then it issues at most one fabro events read for that run

  Scenario: Concurrent reads are capped across processes on one host
    Given two fabro events reads against one factory are already in flight from different Dispatcher processes on this host
    When another Dispatcher process needs to read a run on that factory
    Then it does not start a third concurrent read
    And if it cannot start within its caller's timeout it is handled as a failed events read
    And that failure is journaled and backed off under the failed-read rules
```

## Scenario 228 — The credential freshness requirement is the smaller of the execution allowance and the bounded credential-use window

```gherkin
Feature: A proof-loop edge cannot price a fresh credential out of dispatch
  As an operator of a factory that routes nodes to Codex
  I want the freshness requirement bounded by limits the factory enforces
  So that a ratified graph change does not refuse every Codex dispatch

  Scenario: The bounded window governs when it is smaller
    Given the resolved workflow's execution allowance is 902955 seconds
    And dispatcher.credential_queue_allowance_seconds resolves to 86400 and the whole-run wall budget to 21600
    And the documented margin is 3600 seconds
    When codex-cred-status reports the requirement
    Then the required lifetime is 111600 seconds, naming the bounded credential-use window as the governing figure
    And a credential with 864000 seconds of remaining life passes the freshness gate and the dispatch creates a run

  Scenario: The worker deadline uses the same figure
    Given a dispatch whose governing figure is 108000 seconds
    When the credential is projected at instant P
    Then the worker's credential-use deadline is P plus 108000 seconds
    And a coding agent still running at that deadline is stopped

  Scenario: A long queue is refused at agent launch and rests for resume
    Given a dispatch whose credential queue allowance is 86400 seconds and whose whole-run wall budget is 21600 seconds
    And the run is first launched more than 108000 seconds after projection
    When the first coding-agent node launches
    Then the launch is refused naming the credential-use deadline
    And the dispatch journal carries one credential-use-deadline-reached record with cause queue-exceeded
    And before termination the Dispatcher exports the run record and writes and reads back the preserve-by-reference pointer
    And exactly one credential-use-deadline-reached record names the run id, factory, node, projection instant, deadline, queue time consumed, governing figure, pointer and cause
    And the item rests at blocked with blocked_reason needs-human
    And its ledger comment names the run, node, deadline, cause and pointer
    And the ending is neither a plain failed run nor counted toward any non-convergence or rework bound

  Scenario: A queue between the allowance and the deadline is refused before any turn starts
    Given a dispatch whose credential queue allowance is 86400 seconds and whose whole-run wall budget is 21600 seconds, projected at instant P
    And the run's first coding-agent launch is at P plus 90000 seconds, so 18000 seconds remain before the deadline
    When the start check runs
    Then it refuses the launch because 18000 seconds is less than the 21600-second budget, naming the deadline, the remaining time and the budget
    And no coding-agent turn starts, so no agent is stopped in the middle of a turn
    And the dispatch journal carries one credential-use-deadline-reached record with cause queue-exceeded
    And before termination the Dispatcher exports the run record and writes and reads back the preserve-by-reference pointer
    And exactly one credential-use-deadline-reached record names the run id, factory, node, projection instant, deadline, queue time consumed, governing figure, pointer and cause
    And the item rests at blocked with blocked_reason needs-human
    And its ledger comment names the run, node, deadline, cause and pointer
    And the ending is neither a plain failed run nor counted toward any non-convergence or rework bound

  Scenario: A run whose wall budget is held past it ends at the guard deadline with its work preserved
    Given a dispatch whose governing figure is 108000 seconds, projected at instant P
    And the run has published a draft pull request with head H
    And the run's whole-run wall budget is unmeasured, so the watchdog does not cancel it
    And the run is executing proof_capture immediately after its completed publish_draft
    And no proof record on the pull request carries this dispatch's identifier
    And the pull request's current head is H
    When a coding agent is still running at P plus 108000 seconds
    Then the guard stops the agent at that deadline
    And the pointer names the pull request and head H
    And the dispatch journal carries one credential-use-deadline-reached record with cause killed-mid-node
    And before termination the Dispatcher exports the run record and writes and reads back the preserve-by-reference pointer
    And exactly one credential-use-deadline-reached record names the run id, factory, node, projection instant, deadline, queue time consumed, governing figure, pointer and cause
    And the item rests at blocked with blocked_reason needs-human
    And its ledger comment names the run, node, deadline, cause and pointer
    And the ending is neither a plain failed run nor counted toward any non-convergence or rework bound
    And resume --item is anchored on that record

  Scenario: The status surface shows queue time consumed
    Given a dispatch in flight whose credential queue allowance is 86400 seconds
    And its first agent launched 3600 seconds after projection
    When codex-cred-status is read
    Then it reports 3600 seconds of queue time consumed against the 86400-second allowance

  Scenario Outline: Invalid queue allowances are rejected before submission
    Given dispatcher.credential_queue_allowance_seconds is <value>
    When dispatch admission resolves its configuration
    Then admission rejects the value naming dispatcher.credential_queue_allowance_seconds
    And no run exists

    Examples:
      | value |
      | 0     |
      | -1    |
      | 1.5   |
      | "bad" |

  Scenario Outline: Reporting uses the execution allowance when it is smaller
    Given the execution allowance is 60000 seconds
    And the credential queue allowance is 86400 seconds and the wall budget is 21600 seconds
    And the documented margin is 3600 seconds
    And the first agent launched 3600 seconds after projection
    When <surface> reports this dispatch in flight
    Then it reports a governing budget of 60000 seconds and required lifetime of 63600 seconds
    And it names the execution allowance as governing
    And it reports 3600 seconds consumed against the 86400-second queue allowance

    Examples:
      | surface           |
      | codex-cred-status |
      | manual-renewal    |

  Scenario: Credential lifetime is checked independently of queue capacity
    Given the first launch has at least the whole-run wall budget remaining before the deadline
    And the projected credential's remaining lifetime fails the freshness requirement
    When the start check runs
    Then it refuses the launch for insufficient credential lifetime
    And no coding-agent turn starts

  Scenario: A later launch at the deadline receives the deadline disposition
    Given the run has already launched a coding agent successfully
    When a later coding-agent launch is attempted at the credential-use deadline
    Then the launch is refused
    And the dispatch journal carries one credential-use-deadline-reached record with cause launch-refused
    And before termination the Dispatcher exports the run record and writes and reads back the preserve-by-reference pointer
    And exactly one credential-use-deadline-reached record names the run id, factory, node, projection instant, deadline, queue time consumed, governing figure, pointer and cause
    And the item rests at blocked with blocked_reason needs-human
    And its ledger comment names the run, node, deadline, cause and pointer
    And the ending is neither a plain failed run nor counted toward any non-convergence or rework bound
```

## Scenario 229 — A non-overlapping refresh after one re-proof carries the proof forward

```gherkin
Feature: A run stops chasing an advancing default branch once it has re-proved
  As the maintainer of a repository dispatched to the factory
  I want a re-proved run to keep its proof across a clean refresh that cannot touch what it proved
  So that a run is not sent round capture, review and replay for every base advance

  Scenario: A second clean refresh with non-inert, non-overlapping paths carries forward
    Given a run that re-proved after one changed-head pr_refresh, with verified record R on head V
    And the default branch advanced again with a commit that changes a Python module that is neither an item path nor in R's observation scope
    And every reproduction step in R is inside the direct-read grammar
    And every observation-scope path and item path has the same blob identity at V and N, or is absent at both
    And every working-tree read operand has a read identity in R matching its bytes at N
    And mechanical replay at N reproduces every step's single captured proof block byte for byte
    When pr_refresh rebases the branch cleanly, the gate passes and the leased push yields head N with an unchanged patch identity
    Then the pull request carries one carried_forward record naming V and N that says the incoming paths were not all inert and that the run's one re-proof covered them
    And the run proceeds from pr_refresh to pr without visiting proof_capture

  Scenario: An overlapping refresh still re-proves
    Given a run that re-proved after one changed-head pr_refresh
    And the default branch advanced with a commit that changes a path in the verified record's observation scope
    When pr_refresh rebases the branch cleanly and pushes head N
    Then the pull request carries one reproof_required record naming that path
    And the run enters proof_capture for head N
```

## Scenario 232 — needs-attention surfaces an item labelled approval:workflow-edit

```gherkin
Feature: The workflow-edit approval label is the maintainer's notice
  As the maintainer authorizing an edit to .github/workflows/
  I want every open item carrying approval:workflow-edit to appear in needs-attention
  So that the advisory workflow-edit control has a surface where it is noticed

  Scenario: An open labelled item is surfaced
    Given an open work-item carrying the approval:workflow-edit label
    When the needs-attention snapshot is composed
    Then it carries hygiene:workflow-edit-approval:<work-item-id> naming the item, its status and its title
    And its handoff opens the item for review

  Scenario: A closed or unlabelled item is not surfaced
    Given a closed work-item carrying the label and an open work-item without it
    When the needs-attention snapshot is composed
    Then neither item yields a workflow-edit-approval fact
```

## Scenario 230 — An item whose input exists only on the host is host-routed

```gherkin
Feature: Host-only input is an honest factory_safety reason
  As an operator filing work whose authoritative input lives only on the host
  I want a factory_safety reason that says so
  So that the item is host-routed instead of dispatched into a sandbox that cannot read its input

  Scenario: needs-host-only-input host-routes the item
    Given a ready work-item whose authoritative input is a non-secret review verdict held only in a gitignored host file
    And that input cannot be committed to the repository or fetched into the sandbox
    When the operator invokes set-factory-safety:<work-item-id>:needs-host-only-input
    Then the item's factory_safety is needs-host-only-input and its lifecycle status is unchanged
    And the Dispatcher refuses to dispatch it to a factory and names the reason
```

## Scenario 233 — A node routed to a different adapter does not inherit the replaced adapter's env

```gherkin
Feature: A cross-adapter override renders one model
  As an operator reading which model a factory node ran
  I want a node routed to a different adapter to carry only that adapter's env
  So that the rendered adapter names exactly one model

  Scenario: A changed command discards the inherited env
    Given a node whose workflow default renders the claude-acp command with ANTHROPIC_MODEL in its env
    And dispatcher.acp_nodes sets that node to the codex-acp command with its own env
    When the Dispatcher resolves the node's adapter
    Then the rendered adapter carries no ANTHROPIC_MODEL and names only the Codex model

  Scenario: An override that keeps the command still merges env
    Given a node whose workflow default renders the claude-acp command with ANTHROPIC_MODEL and CLAUDE_CODE_EFFORT_LEVEL in its env
    And dispatcher.acp_nodes sets only ANTHROPIC_MODEL for that node and no command
    When the Dispatcher resolves the node's adapter
    Then the rendered adapter carries the override's ANTHROPIC_MODEL and the inherited CLAUDE_CODE_EFFORT_LEVEL

  Scenario: A changed command for the same adapter restates its env
    Given a node whose workflow default renders the claude-acp command with CLAUDE_CODE_EFFORT_LEVEL in its env
    And dispatcher.acp_nodes sets that node to a differently pinned claude-acp command with only ANTHROPIC_MODEL in its env
    When the Dispatcher resolves the node's adapter
    Then the rendered adapter carries ANTHROPIC_MODEL and no inherited CLAUDE_CODE_EFFORT_LEVEL
```

## Scenario 234 — A stalled run whose sandbox was OOM-killed names the kill and the memory limit

```gherkin
Feature: Memory exhaustion is named, not hidden behind a stall
  As an operator triaging a stalled factory run
  I want the dispatch to say when the factory reported the sandbox OOM-killed
  So that I fix the memory limit instead of investigating the work

  Scenario: A reported OOM kill is named on the stalled outcome
    Given a dispatched run whose sandbox container the factory reports OOM-killed with a memory limit
    When the progress watchdog cancels the run as stalled-no-progress
    Then the watchdog-stall-cancel record, the dispatch result and the item's ledger comment name the OOM kill, the run id and the memory limit
    And the item is not bounced to backlog and no non-convergence observation is recorded

  Scenario: An unreported memory limit is recorded as unobservable
    Given a dispatched run whose sandbox the factory reports OOM-killed without a memory limit
    When the progress watchdog cancels the run as stalled-no-progress
    Then the watchdog-stall-cancel record names the OOM kill and records the memory limit as unobservable

  Scenario: No OOM kill is inferred when the factory reports none
    Given a dispatched run that stalls and whose factory reports no OOM kill
    When the progress watchdog cancels the run as stalled-no-progress
    Then no record, result or comment names an OOM kill
```

## Scenario 231 — Admission skips a Claude candidate whose seven-day allowance is exhausted

```gherkin
Feature: A weekly-exhausted account is never dispatched into a refusal
  As an operator running Claude-routed factory nodes
  I want admission to read the seven-day allowance beside the five-hour one
  So that a run is not launched on an account the provider will refuse

  Scenario: A seven-day exhaustion skips the candidate
    Given dispatcher.session_headroom_floor_percent is 20
    And a covered claude-acp candidate whose five-hour remaining headroom is above the floor
    And the same provider response reports the seven-day status as rejected
    When admission assesses the candidate
    Then the candidate is skipped by a seven-day skip and per-node selection continues to the next eligible candidate
    And the journal records the seven-day utilization and status beside the five-hour figures

  Scenario: A warning or absent seven-day reading skips nothing
    Given dispatcher.session_headroom_floor_percent is 20
    And a covered claude-acp candidate whose five-hour remaining headroom is above the floor
    And the provider response reports the seven-day status as a warning, or carries no seven-day reading
    When admission assesses the candidate
    Then the candidate is not skipped by a seven-day skip
    And the journal records the seven-day reading, or records it as unobservable when it is absent

  Scenario: A floor of 0 disables the seven-day skip
    Given dispatcher.session_headroom_floor_percent is 0
    And the provider response reports the seven-day status as rejected for a covered candidate
    When admission assesses the candidate
    Then no seven-day skip applies and the reading is still journaled
```

## Scenario 215 — A tracks edge links a record to its epic on every surface

```gherkin
Feature: Epic linkage reads the same on every surface
  As an operator reading an epic's children
  I want every surface to agree on which records belong to it
  So that a linkage mechanism one surface models never vanishes from another

  Scenario: A tracks-linked record is a child everywhere
    Given a record linked to an epic only by a tracks dependency edge
    When the epic is read through list-work-items --json, context and the plan child enumeration
    Then list-work-items reports the epic as the record's parent
    And context and the plan child enumeration both list the record among the epic's children

  Scenario: A tracks-linked child closed inside the window is attributed to its plan
    Given an open live plan epic and a record linked to it only by a tracks dependency edge
    And the record was closed inside the plan-progress observation window
    When the no-result-window fact is evaluated for that window
    Then the record's closure counts as a new closed child of the plan in that window
```

## Scenario 216 — The read projections publish a plan epic's identity keys

```gherkin
Feature: A plan roster can be built from the read surfaces alone
  As a consumer that never derives plan facts locally
  I want the read projections to carry a plan epic's identity keys
  So that a plan record renders without reading raw metadata

  Scenario: An epic carries its plan keys and other records carry nulls
    Given a plan epic carrying plan_slug, next_action and last_session, and one non-epic work-item
    When list-work-items --json runs
    Then the epic's record carries all three keys with their stored values
    And the non-epic record carries null for all three

  Scenario: The context envelope carries last_session
    Given the same plan epic
    When context runs for its plan_slug with --json
    Then the envelope carries last_session beside next_action
```

## Scenario 213 — The plan timeline reports the record kinds it does not return

```gherkin
Feature: A narrow timeline reader never manufactures an absence
  As a session verifying that a plan record was written
  I want the timeline to say which record kinds it left out
  So that an omitted kind is never mistaken for a lost write

  Scenario: Skipped record kinds are counted
    Given a plan epic holding handoff entries, scope events and two plan-child-disposition comments
    When the timeline is read
    Then the handoff entries and scope events are returned oldest first, each labelled with its kind
    And the result reports plan-child-disposition with a count of 2

  Scenario: An epic holding only returned kinds reports no omissions
    Given a plan epic holding only handoff entries and scope events
    When the timeline is read
    Then the result reports no omitted record kinds
```

## Scenario 214 — A plan resume returns the epic's rulings beside the typed next action

```gherkin
Feature: A resuming session reads the binding rulings before it acts
  As the maintainer whose rulings are recorded as scope events
  I want every resume to return them with the next action
  So that a session cannot act on the pointer while a ruling it never read binds it

  Scenario: Rulings are returned oldest first
    Given a plan epic carrying two maintainer-ruling scope events and one carrier-map event
    When resume_directive runs
    Then it returns the two ruling scope events oldest first beside the typed next_action
    And it does not return the carrier-map event among them

  Scenario: An epic without rulings resumes as before
    Given a plan epic carrying no scope event other than carrier-map events
    When resume_directive runs
    Then it returns an empty rulings list
    And its ask, next_action and reason are the same as they would be without the rulings list
```

## Scenario 217 — A host-routed item's factory_captured assertion is an advisory finding

```gherkin
Feature: A host-routed item never carries a proof mode it can never satisfy
  As an operator filing work that only a host can run
  I want the wall to flag a factory_captured assertion on it
  So that the item does not park at acceptance waiting for a factory run that never comes

  Scenario: A factory_captured assertion on a host-routed item is flagged
    Given a work-item whose factory_safety is mutates-host-machinery
    And its Definition of Done carries a factory_captured assertion
    When its filing is displayed
    Then an advisory Definition-of-Done finding names that assertion and the factory_safety reason
    And the finding names the remedy of moving it under a Host-captured sub-heading with a Reason line
    And the finding does not withhold ready

  Scenario: A host-routed item may declare a sandbox-exercisable assertion host-captured
    Given a work-item whose factory_safety is non-null
    And its Host-captured assertion names behaviour a published sandbox capability could exercise
    When its filing is displayed
    Then no Definition-of-Done finding refuses the Host-captured declaration

  Scenario: A factory-eligible item keeps the sandbox-capability refusal
    Given a work-item whose factory_safety is null
    And its Host-captured assertion names behaviour a published sandbox capability could exercise
    When the gate grades it
    Then the gate refuses the Host-captured declaration naming that sandbox capability
```

## Scenario 223 — A run attributed to an item under a pending stamp is not an orphan

```gherkin
Feature: A sibling sweep never cancels a run its own dispatch just created
  As an operator running two dispatcher engines on one host
  I want a just-launched run protected until its stamp lands
  So that a sibling's reconcile pass does not cancel live work

  Scenario: A pending stamp protects a fresh run
    Given an item admitted with a pending stamp and a previous journaled run id from an earlier dispatch
    And a non-terminal run attributed to that item whose run stamp has not been written yet
    When another Dispatcher's reconcile-runs pass runs
    Then the run is not classified an orphan and is not terminated

  Scenario: A run superseded by a stamped run is still an orphan
    Given an item that is active under a claim whose run stamp names run B
    And a non-terminal run A attributed to the same item
    When a reconcile-runs pass runs
    Then run A is classified an orphan with reason superseded-run
```

## Scenario 224 — A refused publish_draft push names the cause that refused it

```gherkin
Feature: A publication refusal sends triage to the right remedy
  As an operator triaging a run that could not publish
  I want the refusal to say what refused the push
  So that a hook failure is never mistaken for a stale publish branch

  Scenario: A pre-push hook refusal names its failed targets
    Given a publish_draft push the repository pre-push hook refuses with a Failed targets summary naming lint and format
    When publish_draft reports the failure
    Then its output names the pre-push hook as the cause and names lint and format
    And the run fails closed before proof capture

  Scenario: A non-fast-forward rejection points at the stale branch
    Given a publish_draft push origin rejects as non-fast-forward
    When publish_draft reports the failure
    Then its output names the non-fast-forward rejection and directs reconciling the stale publish branch

  Scenario: An unreachable origin is named
    Given a publish_draft push that cannot reach origin
    When publish_draft reports the failure
    Then its output names the unreachable origin as the cause
```

## Scenario 225 — The publish-branch reclaim finds an earlier dispatch journaled in another worktree

```gherkin
Feature: A re-dispatch from a secondary worktree reclaims the surviving branch
  As an operator re-dispatching from a canary worktree
  I want the reclaim to see a dispatch journaled in the primary checkout
  So that publish_draft does not refuse on a branch the reclaim exists to clear

  Scenario: An earlier dispatch in the primary is found from a worktree
    Given an item whose earlier dispatch is journaled only in the repository's primary checkout
    And its publish branch survives on origin with no live run
    When the item is re-dispatched from a secondary worktree of the same repository
    Then the reclaim preserves the branch to its preserved-publish ref and deletes it from origin

  Scenario: An unreadable worktree journal holds
    Given a worktree of the repository whose dispatch journal cannot be read
    When the reclaim looks for an earlier dispatch
    Then it journals publish-branch-reclaim-held with reason journal-unobservable naming that path
```

## Scenario 226 — An unchanged refresh strips the run's empty commits and carries the proof forward

```gherkin
Feature: Engine checkpoint commits never reach the merged history
  As a maintainer reading merged history
  I want a run's empty checkpoint commits dropped before publication
  So that only the work reaches the default branch

  Scenario: Empty commits are stripped under lease and the proof carries forward
    Given a published head that already contains the default branch and carries two of the run's empty commits
    When pr_refresh runs
    Then it republishes the head without the empty commits under an explicit lease on the run's publish branch
    And the proof decision is carried_forward because the tree is unchanged

  Scenario: A head with no empty commits is left alone
    Given a published head that already contains the default branch and carries none of the run's empty commits
    When pr_refresh runs
    Then it republishes nothing and the head proceeds to pr
```

## Scenario 220 — An exhausted merge-poll budget on an open pull request rests the item for resume

```gherkin
Feature: A succeeded run never strands its claim while its pull request waits
  As an operator whose armed pull request merges slowly
  I want an exhausted merge wait to rest the item where resume can reach it
  So that no claim sits active with no run behind it

  Scenario: An open, non-conflicting pull request rests the item
    Given a run that succeeded and armed auto-merge on its pull request
    And the merge wait's poll budget is exhausted while the forge reports the pull request OPEN and not in conflict
    When the Dispatcher records the outcome
    Then the item rests at blocked with blocked_reason needs-human and the cause merge-poll-budget-exhausted
    And the outcome detail names resolve-blocked then resume as the recovery chain

  Scenario: A pull request merged at expiry is not rested
    Given the poll budget is exhausted
    And the forge reports the pull request MERGED on the final read
    When the Dispatcher records the outcome
    Then it proceeds exactly as for a merge observed within the budget
```

## Scenario 218 — A brief pointing at another work-item's evidence carries an advisory finding

```gherkin
Feature: The implementer is never sent to evidence it cannot read
  As a filer writing a successor item
  I want the wall to flag a pointer to another item's comments
  So that the evidence travels with the item the factory runs

  Scenario: A pointer to a predecessor's comments is flagged
    Given a work-item whose description says its evidence is in the comments of work-item bd-ib-example
    When its filing is displayed
    Then an advisory Definition-of-Done finding names bd-ib-example
    And the finding names the remedy of copying that evidence onto this item
    And the finding does not withhold ready
```

## Scenario 219 — A rendered goal larger than the configured bound carries an advisory finding

```gherkin
Feature: An author sees what recorded evidence costs the brief
  As an operator recording measurements on a work-item
  I want an oversized rendered goal flagged
  So that the item does not silently become too large to finish unattended

  Scenario: A goal over the bound is flagged without refusing
    Given dispatcher.goal_size_warning_bytes is committed as 8000
    And a ready work-item whose rendered goal, comments included, is 10862 bytes
    When the Dispatcher renders its goal
    Then an advisory finding names the item and 10862 bytes on stderr and in the dispatch journal
    And the dispatch proceeds

  Scenario: No bound means no finding
    Given dispatcher.goal_size_warning_bytes is not set
    When the Dispatcher renders any goal
    Then no goal-size finding is reported
```
