---
topic: a-recorded-drill-closes-through-drill-close
author: claude-opus-5-5
created_at: 2026-11-11T06:20:47Z
---

## Proposal: A recorded scratch-branch drill ends through a drill-close incident transition in a terminal drill-closed phase

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a `drill-closed` row to the incident phase table in contracts.md §"Expedited incident lifecycle", and a paragraph defining the `drill-close` action of the incident authority writer as the ONLY writer of that phase. The `commit-transition` action MUST refuse a `drill-closed` successor with `incident-drill-close-requires-action`. The action takes the same server-side generation fence as every incident transition. It closes only a recorded drill, established from a per-PR forge read: at least one bound carrier pull request, every distinct carrier pr-bound in its latest snapshot, every bound pull request based on an `incident-scratch/**` branch, and no attempt landed commit or recorded revert commit reachable from master. It publishes `done` on the canonical item. Standing, provenance and closure readers report a `drill-closed` head as a terminal drill closure with no repayment outstanding, and grant it no incident receipt. It refuses anything else by name and writes nothing. `drill-closed` is never incident phase `closed`, and it is never reopened. Every incident reader is released and verified to accept the phase before any drill-close write. One new scenario in the repository's Feature/Scenario shape covers the close, the label-only refusal, the no-carrier refusal, the forge-failure refusal and the no-reopen rule.

### Motivation

Work item bd-ib-z7ckf4, the orchestrator companion of livespec-dev-tooling v188 (livespec-dev-tooling#4117, a43ead6a; proposal no-verb-closes-a-drill; work item livespec-dev-tooling-io6hyk; plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub). v188 ratified that ending a drill incident chain belongs to this orchestrator, whose owning spec MUST govern the terminal phase `drill-closed`, the drill-close verb and its fencing. It also fixed the boundary the verb must honour: the forge-evidence drill test, the two refusal names, and that drill-closed is never counted as completion, repayment or master recovery capability. As ratified here today, a drill can never end. The phase table ends at `closed`. 'No accept, reconcile-merged, close/no-change-needed, proof-only resume or automatic completion path MAY discharge an incident from its expedited merge alone' plus the repayment closure rule forbid closing it. 'Unknown phase/state combinations MUST produce a named configuration refusal' forbids inventing a phase. Measured 2026-11-11: the four dev-tooling drill items feh3s4, lli7hc, sdxw2v and wxeybc rest at phase reverting, generation 4, repayment owed. Their only incident labels are incident:drill and incident:entry, and their carrier PRs #4052, #4054, #4058 and #4062 all merged into base incident-scratch/thhgeg-proof. The pre-filing review of the dev-tooling proposal found that recovery requests here record no target branch (surface `trunk`), that a revert receipt holds only a receipt id and commit, and that a carrier's `target_ref` is its HEAD branch, not its base. So the test reads bound pull requests' BASE branches and master reachability, and it requires at least one bound pull request, because a real incident in `repair` binds none. Independent pre-filing review (2026-11-11, against installed build 8348582ab96a) returned five blockers on the first draft, all applied here. (1) Once `drill-closed` joins the phase set, the generic `commit-transition` action would accept it as a successor, because `closure_successor_allowed` guards only `closed`; that skips the forge test. (2) `receipts_from_history` sets `repayment_outstanding` whenever the last phase is not `closed`, and `completion_obligations` / `closure_obligations_for` would list outstanding obligations, so 'owes no repayment' would be false on every consumer unless the readers are named. (3) 'Reported as closed' collided with lifecycle `done`, which maps to beads status `closed`. (4) The existing rule that readers be released before enablement was not applied to the new phase, so a reader without it hits the unknown-phase configuration refusal. (5) The scenario lacked this repository's Feature/Scenario Gherkin shape. Live code already refuses a reopen of the new phase with `incident-reopen-not-eligible`, because `REOPEN_FROM` omits it. A second review pass caught that judging every attempt SNAPSHOT would refuse every real drill, because a carrier moves forward from branch-reserved to pr-bound and history keeps the early snapshots. The test therefore judges each distinct carrier by its latest snapshot, as dev-tooling v188 does.

### Proposed Changes

In `contracts.md` §"Expedited incident lifecycle", add this row to the incident phase table directly after the `closed` row:

```markdown
| drill-closed | done | The `drill-close` action closed a recorded drill. |
```

Then insert the following paragraph directly after the paragraph that begins "No accept, reconcile-merged, close/no-change-needed, proof-only resume or automatic completion path MAY discharge an incident":

> A recorded drill MUST be able to end, and it MUST end only through the `drill-close` action of the incident authority writer. `drill-close` is a sanctioned incident transition and the only writer of incident phase `drill-closed`: the `commit-transition` action MUST refuse a `drill-closed` successor with the named reason `incident-drill-close-requires-action`. Before any `drill-close` write, every incident reader, including standing, provenance, closure and inspection readers, MUST be released and verified to accept `drill-closed`, as this section already requires of readers before enablement. The action MUST take the same server-side conditional generation fence and immutable operation identity as every incident transition, MUST revalidate the current generation immediately before it writes, and a same-operation retry after a committed write MUST recover the `drill-closed` result rather than refuse. Before it writes, it MUST establish that the item is a recorded drill from an authenticated forge read of each bound pull request number. Four conditions MUST all hold: the item's incident authority history binds at least one carrier pull request; every distinct carrier in that history, identified by its `target_ref`, is `pr-bound` in its latest snapshot, so a carrier never bound to a pull request, or an attempt with no recorded carrier, fails the test; every bound pull request's base branch, as the forge reports it, matches `incident-scratch/**`; and no attempt landed commit and no recorded revert commit in that history is reachable from `master`. A label such as `incident:drill`, a title, a description or a caller's assertion alone MUST NOT make an item a recorded drill. For a recorded drill at incident phase `repair`, `master-observation`, `reverting`, `rollback-conflict` or `collecting-failures`, the action MUST move the item to `drill-closed`, MUST publish canonical lifecycle state `done` on the item, MUST release the incident owner's claim, and MUST drop any rollback-conflict release condition. Standing, provenance and closure readers MUST then report a `drill-closed` head as a terminal drill closure with no repayment outstanding and no incident completion, and no incident receipt MAY admit a new carrier for it; its historical receipts MUST report no repayment outstanding. For any other item, the action MUST refuse with the named reason `incident-not-a-recorded-drill`, naming the first attempt, carrier or commit that failed the test. When a forge read fails or is incomplete, it MUST refuse with the named reason `incident-drill-evidence-unavailable`. In both refusal cases it MUST write nothing, leaving the item's phase, generation, claim and authority history unchanged. The closure requirements of the preceding paragraph govern incident phase `closed` and do not apply to `drill-closed`. A `drill-closed` item MUST NOT be reported as incident phase `closed`, as a completed repayment or as a completed incident. Neither the reopen requirement of the paragraph after the phase table nor the reopen requirement of the preceding paragraph applies to `drill-closed`: a recovery request or regression reopen against a `drill-closed` item MUST refuse with `incident-reopen-not-eligible`, and a regression attributed to its scratch branch is drill evidence only. Inspection MUST report a `drill-closed` item as a drill closure with its full incident authority history.

In `scenarios.md`, add the following scenario directly after `## Scenario: incident completion requires final normal proof rather than an old repair merge`:

~~~markdown
## Scenario: a recorded scratch-branch drill closes through the drill-close action and a master incident is refused

```gherkin
Feature: a recorded scratch-branch drill closes through the drill-close action and a master incident is refused

  Scenario: a recorded scratch-branch drill closes through the drill-close action and a master incident is refused
    Given an incident item at phase reverting whose every carrier reached pr-bound, every one of whose pull requests merged into an incident-scratch/** base branch, with no landed or revert commit reachable from master and repayment owed
    And a second incident item labelled incident:drill whose bound carrier pull request's base branch is master
    And a third incident item in repair whose carrier is still pre-PR
    And a fourth incident item whose bound pull request's base branch the forge cannot read
    When an operator applies the drill-close action to each item
    Then the first item reads incident phase drill-closed with canonical lifecycle state done, and its provenance shows no repayment outstanding
    And the second and third items are refused with incident-not-a-recorded-drill and are unchanged
    And the fourth item is refused with incident-drill-evidence-unavailable and is unchanged
    And a commit-transition naming a drill-closed successor is refused with incident-drill-close-requires-action
    And a recovery request against the first item is refused with incident-reopen-not-eligible
```
~~~

The revise commit MUST add a `tests/heading-coverage.json` row for the new heading, a spec-first `"test": "TODO"` row owned by `bd-ib-z7ckf4`, following this repository's heading-coverage rules. Work item bd-ib-z7ckf4's Definition of Done `References:` line MUST then name the new heading.
