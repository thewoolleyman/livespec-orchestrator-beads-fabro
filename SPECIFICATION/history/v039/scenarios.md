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
  Then the skill creates a beads issue via the 2-step append carrying the `origin:gap-tied` label
  And the `gap-id:<stable-id>` label
  And the intake Definition-of-Ready routes it (an item that passes the Definition-of-Ready checklist lands `pending-approval`, approved into `ready` when its effective admission_policy is `auto`; an effective-`manual` item rests at `pending-approval` awaiting the human's explicit `approve`)
  And the user-confirmed title and description
  When the user invokes `/livespec-orchestrator-beads-fabro:next`
  Then the ranker reads the materialized work-items back from `bd`
  And surfaces the newly-filed gap-tied item as the recommendation (the top-ranked `ready` item — earliest `rank`)
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

  Scenario: A blocking finding routes back to the implementer and re-validates
    Given the review gate raised at least one blocking finding
    And the review fix-round budget (dispatcher.review_fix_cap) is not yet exhausted
    When the implementer addresses or rejects each blocking finding with a rationale
    Then the change is re-validated by the janitor and reviewed again

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

## Scenario 21 — Codex skills picker discovers drive by short name

```gherkin
Feature: Codex TUI skill discoverability
  As an operator using the Codex TUI
  I want to find the drive operator skill through the supported /skills picker
  So that the installed plugin is discoverable without knowing internal
    model-facing names

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
  Then the change is merged on green via gh pr merge --rebase --auto
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
  And admission to `active` then follows mechanically when a WIP slot frees, dependencies are clear, and an assignee resolves
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
  And the diagnostic surfaces the App workflows read-write grant among the App-installation requirements

Scenario: A target-local workflow supplies the target's toolchain facts
  Given an adopter repo carrying its own .fabro/workflows/implement-work-item workflow
  And the dispatch is invoked with the --workflow override pointing at it
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
  Given a design-human-gated decision — a drift acceptance, a spec-change slice, a regroom/backlog bounce, or a human-only acceptance — that the LLM could resolve with high confidence
  When the Dispatcher evaluates it
  Then it does not auto-dispose the decision, because the design reserves it to a human
  And the decision is left on its human path — a spec-change to `/livespec:propose-change`, a drift acceptance to the Spec-Plane revise path, a bounce resting in backlog — and surfaced to a human
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

## Scenario 41 — standalone analysis lands in a plan thread, not a root research tree

```gherkin
Feature: analysis placement honors the retired research tree
  As a maintainer recording standalone analysis
  I want new analysis to land in the plan thread store
  So that no root research/ tree re-accretes after its fleet-wide retirement

Scenario: a new analysis note lands under the plan thread store
  Given a maintainer records standalone analysis for topic "t" via the plan front-end
  When the thread stores the reasoning note
  Then the note lands under plan/t/ (or plan/t/research/ for a sub-topic)
  And no root research/ path is created anywhere in the repository
```

## Scenario 42 — list-plan-threads enumerates unarchived plan threads

```gherkin
Feature: list-plan-threads enumerates unarchived plan threads
  As a consumer of the read/awareness surface
  I want open planning threads enumerated as a thin-transport read
  So that an unarchived thread is never invisible to the awareness picture

Scenario: unarchived threads enumerate in lexicographic order; archived threads do not
  Given a governed repo whose plan/ thread store contains unarchived thread directories plan/beta-topic/ and plan/alpha-topic/
  And an archived thread directory plan/archive/old-topic/
  When list-plan-threads --json is run
  Then plan_threads is exactly ["alpha-topic", "beta-topic"]
  And no entry references old-topic or the plan/archive/ path
  And the invocation mutates nothing

Scenario: a repo with no plan directory yields zero plan threads
  Given a governed repo with no plan/ directory
  When list-plan-threads --json is run
  Then plan_threads is empty
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
