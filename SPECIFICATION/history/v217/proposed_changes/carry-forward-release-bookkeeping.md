---
topic: carry-forward-release-bookkeeping
author: claude-opus-5-5
created_at: 2026-10-25T06:26:08Z
---

## Proposal: Carry a verified proof forward across a release-bookkeeping-only refresh

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a release-bookkeeping exception to the proof carry-forward decision: a changed-head pr_refresh whose incoming paths are only the release-please manifest, the changelog, and version-line-only edits of pyproject.toml and uv.lock carries the verified proof forward regardless of whether the proof's steps are inside the direct-read grammar, provided the item's own patch is unchanged and no incoming path is an item path.

### Motivation

Fleet coordinator ruling (gitops-fleet-capacity-monitoring, ledger thread livespec-dev-tooling-dfixhe, 2026-10-25), maintainer-directed top stability: every release-please merge advances master and forces every in-flight run whose proof uses a step outside the direct-read grammar to re-prove, although the release commit touches nothing the item changed or observed. The bd-ib-6sb5cn widening does not help those runs, because the grammar condition still fails. The ruling: carry forward, regardless of proof grammar, when every incoming path is release bookkeeping (.release-please-manifest.json and CHANGELOG.md whole-file; pyproject.toml and uv.lock version-line-only).

### Proposed Changes

In SPECIFICATION/contracts.md, section "Proof carry-forward across a refresh":

1. In the paragraph that opens **The decision.**, change its first sentence's opening from "The decision MUST be `carried_forward` only when all of the following hold:" to "Except as **Release bookkeeping** below provides, the decision MUST be `carried_forward` only when all of the following hold:".

2. Insert a new paragraph immediately after the paragraph that ends "Scenario 229 in `scenarios.md` exercises these sentences." and before the paragraph that opens "`pr` MUST query the exact pull request":

**Release bookkeeping.** When every incoming path is release bookkeeping, no incoming path is among the item paths, and the patch identity of `<new base>..<new head>` equals the patch identity of `<verified base>..<verified head>`, the decision MUST be `carried_forward` whatever the verified record's steps are; the direct-read grammar, observation-scope, blob-identity, read-identity and mechanical-replay conditions of "The decision" do not apply to it. An incoming path is *release bookkeeping* when it is `.release-please-manifest.json` or `CHANGELOG.md`, or when it is `pyproject.toml` or `uv.lock`, `git diff --no-color --no-ext-diff --text --unified=0 <previous base> <new base> -- <path>` prints at least one hunk for it, and every line that command prints as added or removed inside a hunk has the form `version = "<text>"`, so a dependency change made beside a version bump, or a change with no inspectable hunk, is not bookkeeping. A `carried_forward` record written under this rule MUST say that every incoming path is release bookkeeping and that no proof step was graded or replayed. Scenario 246 in `scenarios.md` exercises this paragraph.

3. Append to SPECIFICATION/scenarios.md a new scenario:

## Scenario 246 — A refresh that brings in only release bookkeeping carries the proof forward whatever its steps

```gherkin
Feature: A release does not send in-flight runs back to re-prove
  As the maintainer of a repository that releases with release-please
  I want a refresh that brings in only a release commit to keep the run's proof
  So that every release does not re-prove every run whose proof steps are not direct reads

  Scenario: A version bump, a changelog entry and a release manifest carry forward
    Given a run with verified record R on head V whose one reproduction step is outside the direct-read grammar
    And the default branch advanced with a commit that changes only .release-please-manifest.json, CHANGELOG.md and the version line of pyproject.toml
    When pr_refresh rebases the branch cleanly, the gate passes and the leased push yields head N with an unchanged patch identity
    Then the pull request carries one carried_forward record naming V and N that says every incoming path is release bookkeeping and no proof step was graded or replayed
    And the run proceeds from pr_refresh to pr without visiting proof_capture

  Scenario: A manifest change beyond its version line is not bookkeeping
    Given a run with verified record R on head V whose one reproduction step is outside the direct-read grammar
    And the default branch advanced with a release commit whose pyproject.toml change also adds a dependency
    When pr_refresh rebases the branch cleanly and pushes head N
    Then the pull request carries one reproof_required record naming pyproject.toml as an incoming path outside the inert classes
    And the run enters proof_capture for head N
```

4. Add a tests/heading-coverage.json entry for the new Scenario 246 heading, bound to tests.integration.test_pr_refresh_carry_forward_scenario178.test_a_refresh_bringing_in_only_release_bookkeeping_carries_forward_whatever_the_proof.
