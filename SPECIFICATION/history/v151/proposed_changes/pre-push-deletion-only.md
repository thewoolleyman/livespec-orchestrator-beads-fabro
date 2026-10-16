---
topic: pre-push-deletion-only
author: claude-opus-5-5
created_at: 2026-10-16T19:55:01Z
---

## Proposal: A deletion-only push skips this repository's pre-push aggregate

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Add a plugin-local refinement of the inherited pre-push step ordering: the pre-push gate reads git's ref updates on standard input and, when every update is a deletion (all-zero local object id), exits zero without the green-token check or the just check aggregate. Any other push runs the full gate. Add Scenario 188 exercising it.

### Motivation

Work item bd-ib-qy5wol.1 (P1, admitted by freeze-driver ruling R79 under R34 as burning every run). The Dispatcher's post-run cleanup deletes the run's source branch with a pure ref-deletion push (git push --force-with-lease=refs/heads/livespec/source/<id>:<sha> origin :refs/heads/livespec/source/<id>). This repository's pre-push gate (lefthook 01-check-pre-push, then just check-pre-push, then dev-tooling/just-check-pre-push.sh) never reads the hook's standard input, so that deletion runs the whole just check aggregate. The Dispatcher holds the item's ownership lock until the push returns, which delays every needs-human recovery by 60 to 100 minutes under load; measured on bd-ib-26deyw twice and on bd-ib-izthji, 2026-10-16. livespec-dev-tooling-r4oj47 (closed 2026-10-12) fixed only livespec-dev-tooling's own copy of the gate, and stated no clause of the rule in its spec: its '## Hooks and CI' section, read on that repository's master on 2026-10-16, mentions no deletion handling. No clause of this specification states it either. The inherited constraint fixes only the ORDER of the pre-push steps; this refinement leaves the order unchanged and defines when a push is a deletion that the aggregate does not gate. The skip is driven only by the ref updates themselves and can never be reached by --no-verify, an environment variable or a flag, so it relaxes no check for any push that changes the tree.

### Proposed Changes

In SPECIFICATION/constraints.md, immediately after the section "## Inherited from livespec" (whose list ends with the vendored-dependencies bullet) and before "## Beads substrate constraints", insert this new section:

## Pre-push gate refinements

This section refines the pre-push step ordering inherited from livespec; it adds no step and reorders none.

**A deletion-only push skips the pre-push aggregate.** The repository's pre-push gate (`01-check-pre-push`, run through `just check-pre-push`) MUST read the ref updates git supplies on the hook's standard input, one per line as `<local ref> <local object id> <remote ref> <remote object id>`. When there is at least one line and every line's local object id consists only of zeros, the push only deletes refs: the gate MUST then exit zero without running the green-token check or the `just check` aggregate, and MUST print one line saying the gate was skipped because the push only deletes refs. Any other input, including no input at all and any push that creates or updates even one ref beside its deletions, MUST run the full gate exactly as before. The lefthook pre-push entry MUST pass the hook's standard input through to the gate. This skip MUST NOT be reachable by `--no-verify`, by an environment variable, or by any flag; the ref updates themselves are its only input. Scenario 188 in `scenarios.md` exercises this section.

In SPECIFICATION/scenarios.md, append after the last scenario block:

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

In tests/heading-coverage.json, add these two entries:

```json
{
  "heading": "## Pre-push gate refinements",
  "spec_root": "SPECIFICATION",
  "spec_file": "constraints.md",
  "test": "TODO",
  "reason": "Ratified by the revision that accepts proposal pre-push-deletion-only. Implemented and bound by work-item bd-ib-qy5wol.1, alongside Scenario 188.",
  "work_item": "bd-ib-qy5wol.1"
}
{
  "heading": "## Scenario 188 — A push that only deletes refs skips the pre-push aggregate, and any other push runs it",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "Ratified by the revision that accepts proposal pre-push-deletion-only (plan sandbox-commit-gate-ceiling, epic bd-ib-qy5wol, driver ruling R79). The deletion-only skip is not implemented in this repository's pre-push gate yet; work-item bd-ib-qy5wol.1 implements it and owns binding this heading to its structural test.",
  "work_item": "bd-ib-qy5wol.1"
}
```

In tests/heading-coverage-debt.json, add the two matching rows with work_item bd-ib-qy5wol.1 and first_seen set to the revision date.

Scenario numbers 186 and 187 are skipped deliberately: pending proposals and open spec branches reserve them. If those are rejected or renumbered before this one is revised, keep 188 so the work item's References line stays valid.
