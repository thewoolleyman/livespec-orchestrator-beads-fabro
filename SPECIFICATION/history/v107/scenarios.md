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
  And enumerates every MUST/SHOULD rule from spec text alone (no read of the impl)
  And surfaces every rule not yet tracked by a work-item, one at a time
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
    And the item's effective merge_on_review_cap is true
    Then the run ships to the PR stage anyway
    And the still-blocking finding does not gate the change

  Scenario: A capped-out review blocks under the default merge_on_review_cap
    Given the review gate has reached its review fix-round cap (dispatcher.review_fix_cap)
    And the review gate still raises a blocking finding
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
  Then that run yields no cost observation and no gate verdict
  And the Dispatcher does not refuse on its account

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
Feature: The Dispatcher does not spend an allowance it has already observed to be gone
  As a maintainer holding one metered Codex subscription against several Anthropic ones
  I want dispatch refused while a provider window is known exhausted
  So that one exhaustion event costs one run rather than every run that follows it

Scenario: An unexpired observed exhaustion refuses admission without disposing the item
  Given the Dispatcher has observed a provider usage-limit refusal on a completed run against provider "codex"
  And that observation carries an expiry instant in the future
  And a ready work-item whose dispatch would run against provider "codex"
  When the Dispatcher evaluates the admission valve for that item
  Then the item is not admitted
  And no sandbox run is launched
  And the item remains at status "ready"
  And the item is not marked "blocked"
  And the refusal is journaled with the work-item id, the governing condition, the provider and the expiry

Scenario: The record expires and admission resumes
  Given an observed provider-exhaustion record against provider "codex"
  And the record's expiry instant has passed
  And a ready work-item whose dispatch would run against provider "codex"
  When the Dispatcher evaluates the admission valve on a subsequent pass
  Then the item is admitted normally
  And the expired record does not refuse it

Scenario: A provider with no observed record is admitted normally
  Given the Dispatcher holds no unexpired exhaustion record for provider "anthropic"
  And a ready work-item whose dispatch would run against provider "anthropic"
  When the Dispatcher evaluates the admission valve for that item
  Then the item is admitted normally
  And the containment condition refuses nothing

Scenario: The exhaustion signal is never derived from credential material
  Given a provider whose host-side credential file is readable
  And no completed run has reported a usage-limit refusal for that provider
  When the Dispatcher evaluates the admission valve
  Then it does not read the credential file to decide admission
  And it holds no exhaustion record for that provider
  And the item is admitted normally

Scenario: A containment refusal never disposes a needs-human item
  Given a work-item carrying blocked_reason "needs-human"
  And an unexpired observed exhaustion record covering the provider it would dispatch against
  When the Dispatcher evaluates that item
  Then the item is not auto-resolved
  And the item stays surfaced through the needs-attention awareness surface
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

Scenario: A repository with no configuration inherits the fleet default adapters
  Given a dispatch target whose configuration carries no "dispatcher.codex_models" block
  When the Dispatcher renders the workflow adapter inputs
  Then the implementer adapter is the Claude ACP adapter carrying the built-in fleet default model and effort as leading environment assignments
  And the publish adapter is the Claude ACP adapter carrying its own built-in fleet default model and effort as leading environment assignments
  And neither the implementer nor the publish adapter is a Codex adapter absent an explicit tier

Scenario: A repository override replaces only what it names
  Given a dispatch target whose "dispatcher.codex_models" block sets the implementer model only
  When the Dispatcher renders the workflow adapter inputs
  Then the implementer adapter carries the configured model
  And the implementer adapter carries the built-in default reasoning effort
  And the publish adapter is unaffected by the implementer override

Scenario: An empty model renders the adapter byte-identically to the unpinned base
  Given a dispatch target whose configured model for a tier is the empty string
  When the Dispatcher renders that tier's adapter
  Then the rendered adapter equals the base adapter command exactly
  And the rendered adapter carries no model override
  And the rendered adapter carries no reasoning-effort override

Scenario: A malformed tier entry falls back rather than failing the dispatch
  Given a dispatch target whose configured tier entry is not a table
  When the Dispatcher renders that tier's adapter
  Then the adapter carries the built-in fleet default model and reasoning effort
  And the dispatch is not refused on account of the malformed entry
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

Scenario: Merges past the threshold surface the drift fact
  Given default-branch merges since the last completed drift coverage point at or past the effective threshold
  When needs-attention composes the snapshot
  Then a drift-staleness fact appears whose handoff names capture-spec-drift
  And the consent-gated dialogue remains the only way the detector runs
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
  And a ready item held by an unexpired observed provider-exhaustion record
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
  Given a dispatch target whose configuration carries no "dispatcher.codex_models" implementer entry
  When the Dispatcher renders the acp_adapter input
  Then the rendered adapter is the Claude ACP adapter command
  And it carries ANTHROPIC_MODEL set to claude-opus-5 and CLAUDE_CODE_EFFORT_LEVEL set to high as leading environment assignments
  And it carries no context-window suffix on the model name

Scenario: An explicit implementer pin routes the implementer class to Codex
  Given a dispatch target whose "dispatcher.codex_models" block carries an implementer entry naming a model
  When the Dispatcher renders the acp_adapter input
  Then the rendered adapter is the Codex adapter carrying that model and its reasoning effort
  And the publish adapter is unchanged by the implementer entry

Scenario: The publish class is unaffected by the implementer default
  Given a dispatch target with no "dispatcher.codex_models" block
  When the Dispatcher renders the pr_adapter input
  Then the rendered adapter is the Claude publish default adapter pinned to Claude Haiku 4.5
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
  And the dispatch record carries the per-dispatch argument and names the per-dispatch layer for that key

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
  Given a dispatch target whose "dispatcher.acp_nodes" table sets the pr node's args to a model_provider definition and a model
  When the Dispatcher renders the pr node's adapter
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

Scenario: A Codex-pinned publish dispatch renders both adapters in their ratified forms
  Given a dispatch whose publish node is pinned to the Codex tier by an explicit "dispatcher.codex_models.pr" table and whose implementer node resolves to the Claude default
  When the Dispatcher renders both adapters
  Then the publish adapter is its environment assignments in sorted key order followed by the baked codex-acp path
  And the publish adapter carries model and model_reasoning_effort inside CODEX_CONFIG
  And the publish adapter carries no "-c model" argument
  And the publish adapter's CODEX_CONFIG value parses as JSON after POSIX shell tokenization
  And the implementer adapter is byte-identical to the ratified Claude default string

Scenario: The publish adapter declares its agent mode
  Given a dispatch whose publish node is pinned to the Codex tier by an explicit "dispatcher.codex_models.pr" table
  When the Dispatcher renders the publish adapter
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
  Given a dispatch target whose Codex tier sets "model" to the empty string
  When the Dispatcher renders that tier's adapter
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

Scenario: A successful dispatch expires the record early
  Given the Dispatcher holds an unexpired exhaustion record for a provider
  When a dispatch against that same provider succeeds
  Then the record is expired even though its recorded expiry has not been reached
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
    And the pr.md prompt variable for the merge method is squash

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
Feature: An operator can clear an exhaustion record they know is stale
  As a factory operator
  I want to clear an exhaustion record I know is stale
  So that a provider I have just restored is not held out for a wait sized for someone else's rate limit

Scenario: An operator clearance retires the record and admission resumes
  Given an unexpired observed provider-exhaustion record against provider "codex"
  When the operator clears that provider's record with a stated reason and an asserted identity
  Then the clearance is appended to the audit journal carrying the provider, the acting identity, the time, and the reason
  And the original observation record remains readable in the journal
  And a dispatch against provider "codex" is admitted normally

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
    And the dispatch target's dispatcher.codex_models declares an implementer tier
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
  And no unexpired observed provider-exhaustion record is held for the default dispatch provider
  When needs-attention composes the snapshot
  Then exactly one hygiene:idle-factory fact appears at high urgency
  And its summary names the count of admission-eligible ready items and the first ranked id
  And its handoff is a drive-kind handoff carrying impl:<first-ranked-id> that drive accepts for that item's state

Scenario: The idle-factory fact clears when any trigger condition fails
  Given the idle-factory fact would otherwise compose
  When a counted claim occupies a slot for this repository
  Then no idle-factory fact appears
  And when instead an unexpired observed provider-exhaustion record is held the idle-factory fact does not appear
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
  And whose admission-time credential-usability probe first returns a provider rate-limit refusal
  When the bounded re-probe cadence elapses and a subsequent probe returns usable
  Then the loop resumes normal admission on that first usable result without having exited
  And each refused probe was journaled as exactly one record
  And the refusal's remedy text carried no provider-stated reset instant as a wait-until-clock instruction

Scenario: A usable probe does not retire an unexpired exhaustion record
  Given an unexpired observed-exhaustion record held for the provider
  And a credential-usability probe that returns usable
  When admission is attempted
  Then admission remains refused by the exhaustion record
  And the record retires only by bounded expiry, a dispatch outcome, or an operator clearance
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
