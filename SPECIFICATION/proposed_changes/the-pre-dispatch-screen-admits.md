---
topic: the-pre-dispatch-screen-admits
author: claude-opus-5-5
created_at: 2026-11-14T13:51:59Z
---

## Proposal: A workflow-edit authorization label routes its item to the attended host session before any claim

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A ready work item carrying the `approval:workflow-edit` or `approval:workflow-edit-additive` label is refused by the Dispatcher's admission valve before any claim, WIP slot or sandbox run, with a host-route refusal that names the work item and the label that matched. The label is a declaration that the item's scope requires the withheld `workflows` capability, whatever its description or Definition of Done says. The citation-only scope override cannot clear it.

### Motivation

Work item bd-ib-tgygh6, held at the spec-change tier (topic the-pre-dispatch-screen-admits, generalizing ## Factory sandbox credential constraints, judged partial at 2026-11-14T13:47Z). The ratified text says work needing the withheld `workflows` capability MUST be refused before a sandbox run and MUST name the host-session route. But the only predicate that realizes this for an item with null `factory_safety` is the declared-workflow-edit heuristic over the item's scope TEXT. livespec-dev-tooling-zqrg7d carried `approval:workflow-edit-additive`, yet its description and Definition of Done never named `.github/workflows/` or ci.yml, and it carried no `factory_safety` reason. The heuristic admitted it twice: run 01M71W28B5FX ended in a stage failure, and run 01M72045HB8J ended BLOCKED because `check-no-workflow-edits` could not read the label inside the sandbox. The work was then hand-landed as livespec-dev-tooling#4006. A workflow-edit authorization label is the strongest declaration of scope the ledger carries: it exists only because someone authorized an edit to `.github/workflows/`. Screening on it closes the case the text heuristic cannot see, and it keys on the narrowest surface the constraint allows, because only those two labels match. FLEET SCOPE: every member's orchestrator dispatcher. Each orchestrator that sandboxes agent-written code owns its own admission predicate and implement stage, so each MUST carry the label arm and the diff backstop in its own SPECIFICATION/ (cross-repo placement: realization mechanism belongs in the repo that realizes it). This proposal ratifies the rule for this repository's Dispatcher and implement-work-item workflow.

### Proposed Changes

In `constraints.md` §"Factory sandbox credential constraints", insert after the bullet beginning **Refusal predicates MUST be scoped to the capability, not approximated.** this bullet:

- **An authorization to edit `.github/workflows/` is a declaration of that scope.** A work item carrying a label that authorizes an edit under `.github/workflows/` — `approval:workflow-edit` or `approval:workflow-edit-additive` — MUST be treated as requiring the withheld `workflows` capability, whatever its description, its Definition of Done or its `factory_safety` say. It MUST be refused before any claim or sandbox run, and the refusal MUST name the label that matched. The label exists only because an edit to that directory was authorized, so a screen that reads only the item's text MUST NOT be the only screen. No other label is matched by this rule.

In `contracts.md` §"Work-item beads-issue mapping", in the `factory_safety` entry, after the sentence ending "an agent must not rewrite its own examiner.", append:

  An item carrying either workflow-edit authorization label (`approval:workflow-edit` or `approval:workflow-edit-additive`) is host-routed by the shared factory-safety routing predicate's workflow-edit-label arm even while `factory_safety` is null. That arm reads only the label, never this field, and never writes this field.

In `contracts.md` §"Work-item state semantics", in the `#### set-workflow-scope-override:<id>:citation-only` subsection, replace the paragraph beginning "The admission predicate evaluates non-null `factory_safety` FIRST" with:

The admission predicate — the shared factory-safety routing predicate that the Dispatcher's admission valve, the plan child audit's `HOST-ONLY` classification and `dispatcher.py host-only` all consume — evaluates three arms in this order, and the first that matches decides:

1. a non-null `factory_safety`;
2. the workflow-edit-label arm: the item carries the `approval:workflow-edit` label or the `approval:workflow-edit-additive` label;
3. the declared-workflow-edit heuristic over the item's scope text, unless a `workflow-scope-override:citation-only` label overrides it.

Consequently this assertion can admit only an item refused by the third arm, and can never admit an item that the first or second arm routes. A label authorizing an edit is not a citation of a path. A refusal by the second arm MUST NOT set the `awaits-scope-override` label, because the citation-only override is not its remedy. Its refusal MUST be a host-route refusal that names the work item, the label that matched (`approval:workflow-edit` when the item carries both) and the attended-host-session route. It MUST be issued before the Dispatcher takes any claim, WIP slot, launch mutex or sandbox run for the item. It MUST reach a terminal verdict without an interactive prompt, and it MUST leave the item `ready`, exactly as a first-arm refusal does. `dispatcher.py host-only --item <id> --json` MUST report `host_only: true` for such an item, with a `reason` naming the label, so the fleet launcher's host-only screen makes its non-run exit without re-taking the ticket. It is an explicit operator override of a factory-boundary heuristic, not a general relaxation of factory safety. A work-item introducing a first-class operator verb MUST include specification coverage for that verb in its acceptance criteria, because the action-id grammar is a consumer contract rather than an implementation-private parser.

In `scenarios.md`, in Scenario 48 (`## Scenario 48 — Dispatcher refuses a not-factory-safe item at admission`; heading unchanged, so `tests/heading-coverage.json` needs no heading edit), insert after the scenario "A ready item editing .github/workflows/ is refused pre-dispatch":

```gherkin
  Scenario: A ready item carrying a workflow-edit authorization label is refused before any claim, whatever its text says
    Given a `ready` work-item whose `factory_safety` is null
    And whose description and Definition of Done name no path under `.github/workflows/`
    And which carries the `approval:workflow-edit-additive` label
    And a free WIP slot, cleared dependencies, and a resolvable assignee
    When the Dispatcher's admission valve evaluates it
    Then no claim is taken, the item is not admitted to `active`, and no Fabro sandbox run is launched for it
    And the refusal is a host-route refusal naming the work item, the label `approval:workflow-edit-additive` and the attended-host-session route
    And the refusal reaches a terminal verdict without an interactive prompt
    And the item's published `awaits_scope_override` signal stays false
    And the item stays `ready` (it is not marked `blocked`)
    And `dispatcher.py host-only --item <work-item-id> --json` reports `host_only` true with a `reason` naming the label

  Scenario: The citation-only scope override cannot admit a labelled item
    Given a `ready` work-item whose `factory_safety` is null, carrying the `approval:workflow-edit` label and the `workflow-scope-override:citation-only` label
    When the Dispatcher's admission valve evaluates it
    Then the item is refused with a host-route refusal naming the label `approval:workflow-edit`
    And no Fabro sandbox run is launched for it
```


## Proposal: A run whose own commits reach .github/workflows/ ends at its implement stage with a host-route verdict naming every such file

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

After `commit_green` makes the implement stage's commit, an implement-kind run computes the paths its own commits change, measured against the merge base of its head with the default branch. When any of them is under `.github/workflows/`, the run ends at the implement stage with a host-route verdict naming every such file, instead of continuing through the janitor to publication. The Dispatcher then routes the item to the attended host session automatically and preserves the run's commits.

### Motivation

Work item bd-ib-tgygh6, second Definition-of-Done bullet. The constraint says a workflow edit MUST be refused before a sandbox run, "never discovered at publish after the agent has authored and committed the work". The admission screens are predictive, though: they read labels and text, and an item that passes them can still produce a diff under `.github/workflows/`. Today the only diff-side screen is `publish_draft`'s refusal of run-owned workflow files. That screen runs after the janitor's full check aggregate, so a run that crossed the boundary pays the whole janitor before it is refused, and then it parks at needs_human rather than reaching the host-session route the constraint requires. A backstop at the end of the implement stage catches the same boundary crossing at the earliest point the diff exists. It names the files, spends no janitor, and hands the work to the route that can publish it. `publish_draft`'s refusal stays as the last line of defence for a workflow file a later fix or review_fix turn adds. The path rule (own commits, measured against the merge base, so a workflow change that arrived through the default branch never counts) is the one `publish_draft` already applies to `<spec_root>`. FLEET SCOPE: every member's orchestrator dispatcher. Each orchestrator that sandboxes agent-written code owns its own admission predicate and implement stage, so each MUST carry the label arm and the diff backstop in its own SPECIFICATION/ (cross-repo placement: realization mechanism belongs in the repo that realizes it). This proposal ratifies the rule for this repository's Dispatcher and implement-work-item workflow.

### Proposed Changes

In `contracts.md`, insert this paragraph immediately after the paragraph beginning **The implement stage runs Red and Green as separate nodes.**:

**A run whose own commits reach `.github/workflows/` ends at the implement stage.** In an implement-kind workflow variant, once `commit_green` has committed, and before the run leaves the implement stage for any later stage, the run MUST compute the paths its own commits change, relative to the merge base of its head with the default branch, with engine checkpoint commits folded, so that a workflow change that arrived through the default branch is never counted. When any of those paths is under `.github/workflows/` (that prefix exactly; `.github/actions/` and other `.github/` paths do not match), the stage MUST end with a failed outcome carrying the host-route verdict, and the run MUST NOT enter the janitor, `publish_draft` or any later stage. The verdict is one stderr line, `LIVESPEC_HOST_ROUTE_WORKFLOW_EDIT: <path>[, <path>...]`, naming every such path in sorted order, and the same line is written as the stage cause. The run's commits MUST be preserved on the run's needs-human ref exactly as a needs-human ending preserves them. On the host, when the Dispatcher reconciles a run that ended with this verdict, it MUST route the item to the attended host session without an interactive prompt. It does so by recording `factory_safety` `mutates-host-machinery` on the item through the same journaled path `set-factory-safety` uses, with a rationale naming the run id, every path the verdict named and the preserved ref, and it MUST leave the item `ready`. The item is then refused by the routing predicate's first arm at every later admission, and it reaches the attended host session through `driver-dispatch:<id>`. It MUST NOT be re-dispatched to the factory while that reason stands. `publish_draft`'s refusal of run-owned files under `.github/workflows/` is unchanged and still applies to a path a later stage adds. Scenario 374 in `scenarios.md` exercises this paragraph.

In `scenarios.md`, append (the revise assigns the next free scenario number if 374 is taken by then):

## Scenario 374 — A run whose own commits reach .github/workflows/ ends at its implement stage with a host-route verdict naming every such file

```gherkin
Feature: The diff backstop catches a workflow edit the admission screens could not predict
  Scenario: A Green commit that changes a workflow file ends the run at the implement stage
    Given an implement-kind run admitted for a `ready` work-item whose `factory_safety` is null and which carries no workflow-edit authorization label
    And its `commit_green` commit changes `.github/workflows/ci.yml` and `.github/workflows/release.yml` and a product file
    When the implement stage completes its commit
    Then the stage ends with a failed outcome whose cause is `LIVESPEC_HOST_ROUTE_WORKFLOW_EDIT: .github/workflows/ci.yml, .github/workflows/release.yml`
    And the run never enters the janitor or `publish_draft`
    And no branch is pushed and no pull request is opened
    And the run's commits are preserved on its needs-human ref

  Scenario: The Dispatcher routes the item to the attended host session
    Given a run that ended with a `LIVESPEC_HOST_ROUTE_WORKFLOW_EDIT` verdict
    When the Dispatcher reconciles it
    Then the item's `factory_safety` is `mutates-host-machinery`, journaled with the run id, the named paths and the preserved ref
    And the item stays `ready`
    And its next admission evaluation refuses it with a host-route refusal and launches no sandbox run

  Scenario: A workflow change that arrived through the default branch, or a composite action change, does not trip the backstop
    Given an implement-kind run whose own commits change only `.github/actions/setup/action.yml` and product files
    And whose merge base with the default branch is older than a default-branch commit that changed `.github/workflows/ci.yml`
    When the implement stage completes its commit
    Then the run continues to the janitor without a host-route verdict
```

In `tests/heading-coverage.json`, add an entry for the new heading with `test: "TODO"` and a `reason` naming the integration-tier binding owed by bd-ib-tgygh6's implementation (the implement-stage backstop and the Dispatcher's reconcile routing).

