---
topic: raise-a-ready-item-refused
author: claude-opus-5-5
created_at: 2026-11-07T20:33:41Z
---

## Proposal: A ready item refused for the attended-host route is raised once it passes an age bound

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`needs-attention` lists every ready item refused for the attended-host route, with its age, marks it overdue past 24 hours, and keeps listing it during a dispatch freeze or WIP cap.

### Motivation

The admission valve refuses a workflow-editing item and leaves it `ready` (Scenario 48). livespec-dev-tooling-jerpfe sat there, with its cause and saving filed, while the fallback kept costing runner-minutes, because nothing raised its age (research note plan/ci-runtime-and-cost/research/006-coverage-fallback-post-mortem-2026-11-06.md on livespec-dev-tooling). The 24-hour bound is this proposal's choice: one day is long enough for the normal queue and shorter than that item waited. Carries work item bd-ib-vykuby.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "### The needs-attention machine envelope", add this paragraph:

**An item refused for the attended-host route is raised.** The `needs-attention` operation MUST list every `ready` work item whose most recent admission was refused for the attended-host route, with the refusal reason and the item's age since that refusal was first recorded. When that age exceeds 24 hours, the listing MUST mark the item overdue and name the bound. The item MUST still be listed, with its age, while a dispatch freeze or a WIP cap prevents any launch.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario <next free number> — A ready item refused for the attended-host route is raised with its age

```gherkin
Feature: A ready item refused for the attended-host route is raised with its age

  Scenario: A ready item refused for the attended-host route is raised with its age
    Given a `ready` work item whose most recent admission was refused for the attended-host route
    When `needs-attention` runs
    Then it lists the item with the refusal reason and its age since the refusal was first recorded
    And past 24 hours it marks the item overdue and names the bound
    And the item stays listed while a dispatch freeze or a WIP cap prevents any launch
```
