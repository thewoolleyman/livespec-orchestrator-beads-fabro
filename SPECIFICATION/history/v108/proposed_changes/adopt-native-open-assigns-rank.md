---
topic: adopt-native-open-assigns-rank
author: claude-agent-sdk
created_at: 2026-09-09T11:30:16Z
---

## Proposal: Adoption of a beads-native `open`/`in_progress` row assigns it a real rank

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Ratify the Dispatcher's existing self-heal that adopts a beads issue row a non-lifecycle writer left at the beads-native `open` status (or `in_progress`) onto its livespec lifecycle status (`backlog` / `active`), and add a NEW requirement that adoption also assigns a real, non-sentinel `rank` when the row has none, so the adopted row satisfies the ratified invariant that every live head issue carries a real rank without needing an on-demand `rebalance-ranks`.

### Motivation

`_NATIVE_STATUS_REMAP` in `commands/_dispatcher_ledger_close.py` already remaps `open` -> `backlog` and `in_progress` -> `active` for any row a CI/off-host SSH write ingress or a raw `bd create` leaves at a beads-native status outside the ratified 2-step `append_work_item` path (SPECIFICATION/contracts.md "Work-item beads-issue mapping"), but this self-heal lives ONLY in code -- the ratified spec is silent on it. That is impl->spec drift per this repo's mutation discipline (CLAUDE.md "never work around an upstream dependency" / spec-ground-truth coupling), and it must be closed. Separately, adoption today performs NO rank assignment: an adopted row with no `metadata.rank` reads back through the shared `BOTTOM_SENTINEL` fallback and therefore VIOLATES the already-ratified invariant "every live (head) issue has a real, non-sentinel rank" (contracts.md "Work-item beads-issue mapping", Invariants block) until a human runs the on-demand `rebalance-ranks` command, which never auto-fires. This proposal closes both gaps in one amendment: it ratifies the existing status remap and adds the new normative requirement that adoption also performs a single bottom-of-order rank insert when the row has none.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "Work-item beads-issue mapping", within the `status` field's beads-home bullet list ("Logical field -> beads home"), add ONE new sub-bullet immediately AFTER the existing "2-step `append_work_item`" sub-bullet (and before the following top-level `- \`title\` -- beads \`title\`. Identity.` bullet), matching the surrounding normative style:

```markdown
  - **Adoption of a row a non-lifecycle writer left `open` assigns it a
    real rank.** A row left at the beads-native `open` status by ANY
    writer that performs no second step -- a CI or off-host SSH write
    ingress, or a raw `bd create` run outside the 2-step path above -- is
    NOT a livespec lifecycle state and MUST NOT rest there. The
    Dispatcher's ledger normalization MUST adopt such a row: `open` ->
    `backlog`, and `in_progress` (the status a raw `bd --claim` stamps)
    -> `active`. On adoption, if the row's `rank` reads back through the
    shared bottom-sentinel fallback (`metadata` carries no real `rank`),
    the normalization MUST ALSO assign it a real, non-sentinel
    `metadata.rank` -- a single bottom-of-order insert -- so the adopted
    row satisfies the "every live (head) issue has a real, non-sentinel
    rank" invariant without an on-demand `rebalance-ranks`. This is a
    single insert performed AT adoption; it does NOT change the standing
    decision that the bulk `rebalance-ranks` command is on-demand only
    and NEVER auto-fires. `deferred` stays parked and is never
    auto-remapped; every OTHER non-lifecycle status (hooked, pinned, or
    any ad-hoc or unknown value) is residual drift, left untouched and
    surfaced only by the ledger status-conformance check, never
    auto-remapped. This normalization runs at four cadences: the
    dispatch loop (`dispatcher.py loop`), the single-dispatch path
    (`dispatcher.py dispatch`), the standalone `dispatcher.py
    ledger-normalize` CLI (an operator self-heal needing no dispatch),
    and the always-run pre-push `dispatcher.py ledger-normalize --gate`
    mode.
```

In `SPECIFICATION/scenarios.md`, append a new `## Scenario 126 -- Ledger normalization adopts a beads-native `open` row and assigns it a real rank` section (Given/When/Then, fenced ```gherkin block, following the file's existing per-scenario style) covering: an `open` row with no rank is adopted into `backlog` and assigned a real, non-sentinel rank via a single bottom-of-order insert; an `in_progress` row is adopted into `active`; an `open` row that already carries a real rank keeps its existing rank unchanged; a `deferred` row is left untouched with no rank assigned; and every one of the four named cadences (dispatch loop, single-dispatch path, standalone `ledger-normalize` CLI, pre-push `ledger-normalize --gate`) adopts the same row identically.

Also add the new scenario heading's registry entry to `tests/heading-coverage.json` (spec_root `SPECIFICATION`, spec_file `scenarios.md`, the new heading, `test: "TODO"`, and a `reason` acknowledging the scenario's future exercising test must be at the integration/consumer tier per the heading taxonomy's pyramid-tier requirement -- following the same baseline-backfill pattern already used for every other scenario heading in this registry), so `heading_coverage` stays green. No implementation change is proposed here: the rank-assignment requirement is NEW and not yet implemented in `_dispatcher_ledger_close.py`; a follow-up impl work-item is expected separately.
