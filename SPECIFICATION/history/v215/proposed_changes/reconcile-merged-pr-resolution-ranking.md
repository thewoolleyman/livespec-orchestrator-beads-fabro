---
topic: reconcile-merged-pr-resolution-ranking
author: claude-opus-5-5
created_at: 2026-10-25T03:24:56Z
---

## Proposal: Merged-PR resolution ranks head ref, then title, then body mention

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

reconcile-merged ranks merged default-branch pull request candidates in three tiers: head ref feat/<id>, then a title carrying the id, then a body mention. It resolves from the highest non-empty tier, and refuses as ambiguous only when that tier holds more than one candidate.

### Motivation

Work-item bd-ib-ob26ab, stability tier (epic livespec-dev-tooling-dfixhe). Closing bd-ib-y7372n on 2026-10-25, reconcile-merged refused as ambiguous over #3607, #3603, #3600 and #3616. Only #3616 carried the item; the others mentioned the id in their bodies. The current rule allows the title/search fallback only when it is unambiguous, so a body mention can veto a correct title match.

### Proposed Changes

In SPECIFICATION/contracts.md section "Dispatcher loop invocation surface", replace:

The valve MUST resolve the PR number and merge SHA from GitHub, by the expected
`feat/<work-item-id>` branch first or a merged PR title/search match carrying the
work-item id only when that fallback is unambiguous on the default branch. The
fallback search MUST include a default-branch base filter. If multiple merged PR
candidates survive filtering, the valve MUST refuse with a clear ambiguous-PR
error listing the candidates rather than silently choosing the first result.

with:

The valve MUST resolve the PR number and merge SHA from GitHub, among pull
requests merged onto the default branch (the search MUST include a
default-branch base filter), by ranking the candidates in three tiers: first a
pull request whose head ref is the expected `feat/<work-item-id>` branch, then
one whose title carries the work-item id, then one whose body mentions the
work-item id. The valve MUST resolve from the highest tier that holds any
candidate and MUST NOT let a candidate of a lower tier make a higher tier's
resolution ambiguous. If that highest tier holds more than one candidate, the
valve MUST refuse with a clear ambiguous-PR error listing that tier's candidates
rather than silently choosing the first result. Scenario 244 in `scenarios.md`
exercises this ranking.

Append to SPECIFICATION/scenarios.md:

## Scenario 244 — reconcile-merged resolves a merged pull request by head ref, then title, then body mention

```gherkin
Feature: Merged pull request resolution ranks how a candidate names the item
  As the operator recovering a merged item with reconcile-merged
  I want a pull request that carries the item to outrank one that merely mentions it
  So that a follow-up or sibling pull request naming the item cannot make a clear resolution ambiguous

  Scenario: A head-ref match outranks title and body matches
    Given an item whose merged pull requests on the default branch include one whose head ref is feat/<work-item-id>
    And others that carry the work-item id in their title or body
    When reconcile-merged resolves the item's merged pull request
    Then it resolves the feat/<work-item-id> pull request

  Scenario: A single title match outranks body mentions
    Given an item with no merged pull request whose head ref is feat/<work-item-id>
    And exactly one merged pull request whose title carries the work-item id
    And other merged pull requests that mention the work-item id only in their bodies
    When reconcile-merged resolves the item's merged pull request
    Then it resolves the pull request whose title carries the work-item id

  Scenario: A single body mention resolves when nothing identifies the item more strongly
    Given an item with no merged pull request that identifies it by head ref or title
    And exactly one merged pull request that mentions the work-item id in its body
    When reconcile-merged resolves the item's merged pull request
    Then it resolves that pull request

  Scenario: A tie in the highest tier holding a candidate refuses
    Given an item whose highest tier holding any merged pull request candidate holds more than one
    When reconcile-merged resolves the item's merged pull request
    Then it refuses with an ambiguous-PR error listing every candidate of that tier
    And the item's status is unchanged
```

