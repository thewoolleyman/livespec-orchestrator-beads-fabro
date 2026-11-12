---
topic: closing-an-item-that-owns
author: claude-opus-5-5
created_at: 2026-11-12T15:30:00Z
---

## Proposal: A close never strands a heading-coverage TODO row; it refuses, or repoints the rows to a named open successor

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A `test: "TODO"` row in `tests/heading-coverage.json` names, in its `work_item` field, the open item that owes the heading's test. Nothing stops that item from closing while it still owns rows, so the row becomes an unowned debt that the release tier of `check-no-todo-registry` later rejects. This proposal makes every close path of the plugin, and `bd close` through the lifecycle guard, refuse a close of an item that owns a TODO row. The close may instead name an open successor in the repository's own tenant, which takes over the rows before the close completes. An item that owns no row closes exactly as it does today.

### Motivation

Work item bd-ib-7wav65 (plan bd-ib-ax3rds), filed on legacy-coordinator-agent's ruling of 2026-11-11 as the root fix for the heading-coverage TODO-owner class, ranked first in the plan. It is held at spec-change tier for this linked stem: verdict unstated, spec 355, generalization target `## Closed-item integrity`. That section forbids a closed gap-tied item whose scenario is still `TODO`, and `closed_item_integrity` enforces it after the fact; neither says anything about a close of an item that OWNS a TODO row. The topic is the item's linked stem, so the hold links without a relink.

Measured on 2026-11-11: the fleet carried 402 TODO rows whose `work_item` was closed. They were livespec 15, livespec-dev-tooling 122, this repository 61, livespec-overseer 193 and livespec-driver-codex 11. That same night livespec-dev-tooling-yznwz7's two Lane-capacity rows were stranded the same way. Every beads tenant closes items through this plugin's close paths, so the guard belongs at the close, not in an after-the-fact check.

Design choices, stated for the grade:
- **Which tree.** The close reads the rows from the governed repository's default branch, the branch every heading-coverage check grades. A row edited only on an unmerged branch neither blocks nor frees a close.
- **The repoint lands first.** Rows are committed file content and a close is a ledger write, so they cannot be one atomic write. The close therefore completes only once a change repointing every owned row to the successor is on the default branch. Until then it is refused, naming the successor and the rows still owned. This keeps the order "rows move, then the item closes", so no instant exists where a closed item owns a row.
- **The close path does not author the repoint** (a DEPARTURE from the item's Definition of Done bullet 2, stated on the coordinator's grade). The bullet says the close repoints the rows in the same change and then completes. A close is a ledger write, and the rows are committed files that reach the default branch only through a merged pull request, which a close path cannot perform. So the close refuses until the repoint is on the default branch, and the repoint is authored the way every other row edit is. If the bullet must be re-groomed to match, that is the coordinator's call.
- **`close-duplicate` is a close path too** (grade fix 1). It already takes a successor that may live in another tenant, so the own-tenant rule wins only while the duplicate owns rows.
- **Fail closed** (grade fix 3). An unreadable default branch or coverage file refuses the close, naming the cause, and never reads as "owns no row".
- **Own tenant only.** A successor in another tenant cannot be graded by this repository's checks, so it is refused, as is a closed successor.

In-flight alignment, all `align`: #5036 (bd-guard-refuses-a-raw) adds a sibling guard refusal, for create, beside this one, for close; #5042 and #5058 are unrelated to close. Fleet scope: the close paths and the guard rule are the orchestrator's, so every beads tenant inherits them through the plugin. Two cases are OUT of scope. First, a row in ANOTHER repository that names this tenant's item: a close reads only its own repository's rows, so that row is left to that repository's own `check-no-todo-registry` release tier. Second, livespec-orchestrator-git-jsonl's own 6 `TODO` rows and close paths, which need their own item in that tenant.

### Proposed Changes

**1. The close-time half of the invariant (`constraints.md` §"Closed-item integrity").** After the paragraph that begins "A gap-tied work-item marked `resolution:completed` MUST carry…", add:

> A close MUST NOT strand a heading-coverage TODO row. Every `tests/heading-coverage.json` row whose `test` is the `TODO` sentinel names, in its `work_item` field, the open work-item that owes that heading's test. A close of a work-item through `accept`, through `reconcile-merged`, through plan-child disposition (`close_plan_child`), through the `close-duplicate:<work-item-id>:<successor-id>` valve, or through `bd close` at the lifecycle guard MUST refuse while that item is the `work_item` of any `TODO` row on the governed repository's default branch. The default branch is read from the forge remote, never from a local ref. When that branch or its `tests/heading-coverage.json` cannot be read, the close MUST fail closed: it refuses, naming the cause, and the item stays open. The refusal MUST name every such heading, and the item MUST stay open. A close MAY name a successor work-item. When the successor is open and held by the repository's own tenant, the close MUST complete only once a change repointing every `TODO` row the closing item owns to that successor is on the default branch. Until then it MUST refuse, naming the successor and each row still owned by the closing item. A close naming a successor that is closed, or that the repository's own tenant does not hold, MUST be refused, naming that successor. `close-duplicate` names its successor in its own route. That successor satisfies this paragraph only when it is open and held by the repository's own tenant. A successor in another tenant cannot own this repository's rows, so while the duplicate owns any `TODO` row this paragraph wins: the valve refuses, naming the rows and the foreign successor, until the rows are repointed to an open own-tenant item. A close of an item that owns no `TODO` row MUST complete exactly as it would without this paragraph. This applies to every closed item, gap-tied or not, and adds nothing to the after-the-fact `closed_item_integrity` check.

**2. The guard half (`contracts.md` §"Beads connection model").** After the bullet "**Pinned lifecycle-guarded entry point.**", add:

> - **A close of an item that owns a heading-coverage TODO row is refused at the guard.** When the lifecycle guard is asked to run `bd close` from a working directory inside a repository, it MUST apply the close-time rule of `constraints.md` §"Closed-item integrity" before invoking its delegate. It MUST refuse, exit non-zero and close nothing when the item owns a `TODO` row on that repository's default branch, naming the same headings the orchestrator's close paths name. A close of an item that owns no such row is passed to the delegate unchanged.

**3. Scenario (`scenarios.md`).** Append the scenario below. Its number is the next free one at revise time; 350 to 359 are claimed by pending proposals and peer drafts.

## Scenario 360 — A close of an item that owns a heading-coverage TODO row refuses, or repoints the rows to a named open successor first

```gherkin
Feature: no close leaves a heading-coverage TODO row without an open owner
  Scenario: a close of an item that owns a TODO row is refused
    Given a work item W that is the work_item of a test "TODO" row on the default branch
    When W is closed through accept, reconcile-merged, close_plan_child or close-duplicate
    Then the close is refused, naming every heading whose TODO row W owns
    And W stays open

  Scenario: a close naming an open successor completes once the rows are repointed
    Given a work item W that owns TODO rows on the default branch
    And an open work item S held by the repository's own tenant
    When W is closed naming S as its successor
    Then the close is refused, naming S and each row W still owns, until a change repointing every such row to S is on the default branch
    And once that change is on the default branch the close completes

  Scenario: a close naming an unusable successor is refused
    Given a work item W that owns TODO rows on the default branch
    When W is closed naming a successor that is closed, or that the repository's own tenant does not hold
    Then the close is refused, naming that successor

  Scenario: close-duplicate with a foreign successor is refused while the duplicate owns rows
    Given a work item W that owns TODO rows on the default branch
    When close-duplicate is driven for W naming a successor held by another tenant
    Then the valve refuses, naming the rows and the foreign successor
    And W stays open

  Scenario: an unreadable default branch fails the close closed
    Given the default branch on the forge remote, or its tests/heading-coverage.json, cannot be read
    When a work item is closed through any close path
    Then the close is refused, naming the cause
    And the item stays open

  Scenario: a close of an item that owns no TODO row is unchanged
    Given a work item that owns no TODO row on the default branch
    When it is closed through any close path
    Then the close completes exactly as it would without this scenario

  Scenario: bd close at the lifecycle guard applies the same rule
    Given a work item W that owns a TODO row on the default branch
    When bd close W is run through the lifecycle guard from inside the repository
    Then the guard refuses without invoking its delegate, naming the same headings
```

**4. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-7wav65"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. If the revise renumbers Scenario 360, the row and entry MUST carry the renumbered heading text.
