---
topic: tracks-edge-is-an-epic-linkage
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T16:16:21Z
---

## Proposal: A tracks edge to an epic is an epic linkage on every surface that reports one

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Work-item beads-issue mapping" defines epic linkage as the native parent-child edge, while §"Orchestrator-owned attention facts" already ratifies `parent-child` OR `tracks` as the two edge arms of the plan child-enumeration union. So the plan child surface honours tracks and the list-work-items projection does not, and the two would disagree silently the moment a tracks edge exists. This proposal generalizes the mapping bullet so that every surface that reports a parent or enumerates children honours both edge types, extending the arm the spec already ratifies rather than removing it.

### Motivation

Work-item bd-ib-rrhbmm, verified 2026-08-21: commands/_plan_child_edges.py accepts parent-child or tracks, while commands/_list_work_items_projection.py computes the projected parent from parent-child only. The divergence is latent today (zero tracks edges in this tenant), but it has the same shape as the dotted-id gap bd-ib-t2tkko fixed, which shipped a right-sized wrong set before it was found. R290 triage held it because making the surfaces agree is a spec decision. Plan spec-implementation-lockstep R1 batch 2 routes it here, choosing the direction that keeps the ratified union intact.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Work-item beads-issue mapping", replace the bullet beginning "- epic linkage — beads native `parent-child`" with:

> - epic linkage — beads native `parent-child` (`bd create … --parent <epic>` / `bd update <child> --parent <epic>`), or a `tracks` dependency edge from the record to the epic. An epic is a `type: epic` issue whose members are its beads children. Every surface that reports a record's parent or enumerates an epic's children, including the plan child-enumeration union, the `context` envelope's children and the `list-work-items --json` projection's `parent`, MUST honour both edge types, so that no two surfaces disagree on what an epic linkage is. Scenario 215 in `scenarios.md` exercises this bullet.

In the same file, section "`context`", replace "unioned across BOTH the dotted-id hierarchy AND the `parent-child` dependency edge" with "unioned across the dotted-id hierarchy AND every epic-linkage edge of §\"Work-item beads-issue mapping\" (`parent-child` or `tracks`)".

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

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
```

