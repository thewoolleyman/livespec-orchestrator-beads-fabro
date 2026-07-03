---
topic: capture-spec-drift-ledger-intent
author: claude-opus-4-8
created_at: 2026-07-03T03:00:08Z
spec_commitments:
  impl_followups:
    - id_hint: capture-spec-drift-ledger-intent-ib
      description: |
        Implement the capture-spec-drift ledger-intent scan: a read-only pass over the work-items store surfacing work-item intent (title/description/acceptance_criteria/closure reason) not reflected in the spec, the optional --since-version scoping flag (default = live items + items captured since the last version), per-finding consent, handoff to /livespec:propose-change, and already-covered suppression — behavior linked clause->scenario->test.
---

## Proposal: capture-spec-drift ledger-intent scan

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Extend capture-spec-drift with a second, read-only drift source: a ledger-intent scan over recent work-items that surfaces work-item intent (title/description/acceptance criteria/closure reason) encoding behavior or decisions absent from the current spec, routed through the existing per-finding consent -> /livespec:propose-change handoff. Adds an optional --since-version <vN> flag (like capture-impl-gaps) scoping the ledger scan; default is live work-items plus those captured since the last version. The scan MUST be read-only, MUST require per-finding consent, and MUST NOT emit findings for intent already reflected in the spec.

### Motivation

Operator request: capture-spec-drift should look at all recent work-items in the ledger (with an optional diff-range like gap-capture's --since-version) to find work-item intent that is missing from the spec. Today capture-spec-drift only detects impl->spec drift from source code; a decision or behavior recorded in a work-item but never written into the spec is an undetected drift direction. Filed against this orchestrator repo because capture-spec-drift's contract is realized here (core owns only the cross-boundary handoff).

### Proposed Changes

Extend `capture-spec-drift` so it detects drift from a SECOND source —
the work-items beads-backed Ledger — in addition to the existing impl→spec
heuristic. Today the operation only compares implementation source to the
spec; work-item *intent* (a decision or behavior captured in a work-item
but never written into the spec) is a real, currently-undetected drift
direction. This proposal adds that source, reusing the existing
per-finding consent → `/livespec:propose-change` handoff.

### `SPECIFICATION/contracts.md` — §"capture-spec-drift"

Amend the operation contract so it reads (in addition to the existing
impl→spec heuristic):

- `capture-spec-drift` MUST detect drift from two sources: (1) the
  existing impl→spec heuristic (implementation source vs. spec), and
  (2) a **ledger-intent scan** — a read-only pass over work-items in the
  beads-backed Ledger that surfaces work-item intent (its `title`,
  `description`, `acceptance_criteria`, and closure `reason`) encoding an
  observable behavior, a decision, or an invariant that is NOT reflected
  in the current spec.
- Each ledger-intent finding MUST be surfaced through the SAME
  per-finding consent flow as the impl→spec findings and, on consent,
  MUST be handed off to `/livespec:propose-change` via the cross-boundary
  handoff. The operation MUST NOT write spec-side state directly. The scan reads the Ledger through the store's read API and never through a raw beads/`.beads/` read.
- `capture-spec-drift` MUST accept an optional `--since-version <vN>`
  flag (mirroring `capture-impl-gaps`). When set, the ledger-intent scan
  MUST consider only work-items captured on or after the cut of spec
  version `<vN>`. When omitted, the scan MUST consider every live
  (non-`done`) work-item plus every work-item captured on or after the
  most-recently-cut spec version (the default "recent" window). The flag
  scopes ONLY the ledger-intent source; the impl→spec heuristic source is
  unaffected.

### `SPECIFICATION/constraints.md` — capture-spec-drift ledger-scan safety

Add (a small section or bullets under the skill-orchestration / forbidden
patterns area):

- The `capture-spec-drift` ledger-intent scan MUST be read-only: it MUST
  NOT mutate, close, re-rank, or otherwise write any work-item.
- `capture-spec-drift` MUST NOT auto-file a propose-change from a
  ledger-intent finding; per-finding user consent MUST precede every
  handoff (escalate, do not auto-apply).
- A work-item whose intent is already reflected in the current spec MUST
  NOT produce a drift finding — the scan SHOULD suppress
  already-covered intent so it does not emit spurious propose-changes.

### `SPECIFICATION/scenarios.md` — new scenario

Add a new scenario (next available number, in this file's house style —
Gherkin `Feature`/`Scenario` blocks) capturing: given a recent beads-backed Ledger work-item whose
description encodes a behavior absent from the current spec, when
`capture-spec-drift` runs (optionally scoped by `--since-version`), then
it surfaces a ledger-intent drift finding, and on user consent hands off
to `/livespec:propose-change`, and it MUST never mutate the work-item or
write spec-side state directly.
