---
topic: drive-close-duplicate-id-successor
author: claude-opus-5-5
created_at: 2026-11-01T21:51:19Z
---

## Proposal: A human close-duplicate valve closes a duplicate item whatever its spec-change-tier hold

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a human-only, status-independent `close-duplicate:<work-item-id>:<successor-id>` drive valve. It closes an item, in any non-closed status and whatever spec-change-tier hold it carries, that duplicates another work item which already carries its behaviour. It records the successor as `superseded_by`, writes a ledger comment and one journal record naming the successor and the invoker, and refuses, writing nothing, on an unresolvable or self successor, an already closed item, or a live run or unreleased dispatch claim. The `done` door rule gains this valve as its second owner, the autonomy-tier bullet points held duplicates at it, and the `superseded_by` mapping states how a cross-tenant successor is recorded. Scenario 31 gains two scenarios; no heading changes.

### Motivation

Work item bd-ib-jbbzxn ("drive close-duplicate:<id>:<successor> valve closes a duplicate item whatever its spec-change tier hold"), handed to plan spec-implementation-lockstep (epic bd-ib-ax3rds) by the kubernetes-observability seat under coordinator legacy-coordinator-agent ruling R301; intake held it at the spec-change tier, verdict unstated, linked topic drive-close-duplicate-id-successor. Measured 2026-11-01: livespec-dev-tooling-ipcm33 duplicates bd-ib-tqzazn (ratified here in v254, Scenario 274), but classify-tier held it as spec-change against the dev-tooling spec. close_plan_child and reparent_plan_child refuse a held child, `drive reject:` is invalid-action-id outside the two valves, release-spec-tier would be a false attestation because the item's own spec has no heading that states it, and resolve-blocked does not close. So the item can be closed only by hand and its epic livespec-dev-tooling-dfixhe cannot archive. A duplicate disposition needs no ratification because the successor already carries the commitment; this is the same category as release-spec-tier, a human way through a misjudged or wrongly-tenanted hold. Generalization target: the existing Status-independent verbs paragraph and the release-spec-tier sentence of the autonomy-tier bullet; no new heading.

### Proposed Changes

In SPECIFICATION/contracts.md, under `#### Per-lane valid operator verb sets`, in the **Status-independent verbs.** paragraph, immediately after the sentence

> `clear-factory-safety:<id>:<rationale>` is its inverse and is likewise
> status-independent and not enumerated per row.

append this new paragraph:

> `close-duplicate:<work-item-id>:<successor-id>` is valid in every lane except `done`, and is likewise not enumerated per row. Driven only by a human, it closes an item that duplicates the work item `<successor-id>`, in any non-closed lifecycle status and whatever spec-change-tier hold the item carries, with no factory run and no change to any other item. It MUST record `<successor-id>` as the item's `superseded_by`, MUST write a durable ledger comment on the item naming the successor and the invoker, and MUST append one dispatch-journal record naming the item, the successor and the invoker, as the other human valves journal theirs. It MUST refuse, naming the reason and writing nothing, when `<successor-id>` does not resolve to a work item in a tenant the Dispatcher can read, when `<successor-id>` equals `<work-item-id>`, when the item is already closed, and while a run of the item is live or the item carries an unreleased dispatch claim. The close is a disposition, not a ratification: it states no behaviour, and a linked proposed-change topic the item carries keeps its own revise decision.

In SPECIFICATION/contracts.md, under `#### Door rules — every transition has exactly one journaled owner`, replace

> - `done` is entered ONLY by `accept`. The move `acceptance → done` is
>   REMOVED — it is an unjournaled duplicate of the accept valve.

with

> - `done` is entered ONLY by `accept`, or by the `close-duplicate` valve for an item another work item supersedes. The move `acceptance → done` is
>   REMOVED — it is an unjournaled duplicate of the accept valve.

In SPECIFICATION/contracts.md, in the autonomy-tier bullet under `### The four maintainer touchpoints` (the one carrying the `release-spec-tier` valve), immediately after the sentence

> The release is not a ratification: the linked proposed-change topic keeps its own revise decision.

insert:

> A held item that duplicates a work item which already carries its behaviour, in this tenant or another, is closed through the human-only `close-duplicate:<work-item-id>:<successor-id>` valve of §"Per-lane valid operator verb sets" → "Status-independent verbs", which needs no ratification and no `release-spec-tier` attestation.

In SPECIFICATION/contracts.md, in the beads field mapping, replace

> - `superseded_by` — beads `supersedes` dependency edge (`bd dep add
>   <superseding> <this> --type supersedes`). Present iff non-null.

with

> - `superseded_by` — beads `supersedes` dependency edge (`bd dep add
>   <superseding> <this> --type supersedes`) when both items live in one tenant; when the superseding item lives in another tenant, which no dependency edge can reach, the item's `metadata.superseded_by` key holding the superseding item's id. Present iff non-null.

In SPECIFICATION/scenarios.md, in `## Scenario 31 — drive human valve actions`, append to the gherkin block, after "Scenario: a manual → auto flip on a pending-approval item does not approve it by itself":

    Scenario: close-duplicate closes a held duplicate and records its successor
      Given a `blocked` item held at the spec-change tier whose behaviour another work item already carries
      When the operator invokes `drive --action close-duplicate:<work-item-id>:<successor-id>`
      Then the item is closed with no factory run and no other item changes
      And the item's superseded_by names the successor
      And a ledger comment on the item and one journal record each name the successor and the invoker

    Scenario: close-duplicate refuses and writes nothing on a bad successor, a closed item or a live claim
      Given an item and a close-duplicate action whose successor does not resolve, equals the item, or whose item is already closed or carries a live run or an unreleased dispatch claim
      When the operator invokes `drive --action close-duplicate:<work-item-id>:<successor-id>`
      Then the valve refuses naming the reason
      And the item, its comments, its edges and the journal are unchanged

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no edit; Scenario 31's existing coverage entry covers the added scenarios.
