---
topic: closed-item-integrity
author: claude-opus-4-8
created_at: 2026-06-19T22:30:00Z
---

## Proposal: Forbid "closed but unproven" — a closed-item-integrity invariant

### Target specification files

- SPECIFICATION/constraints.md

### Summary

Add a new `## Closed-item integrity` constraint section to
`SPECIFICATION/constraints.md` codifying a single BCP14 invariant: a
gap-tied work-item marked `resolution:completed` MUST carry the
`resolution:completed` label AND its acceptance scenario MUST be bound
to a real integration-tier-or-above test in `tests/heading-coverage.json`
(never left as the `TODO` sentinel). "Closed but unproven" — a closed
gap-tied item whose acceptance scenario is still unbound (`"test":
"TODO"`), or which lacks the `resolution:completed` label — is forbidden.
The invariant is stated as a normative MUST clause so it is itself a
detectable behavior gap under the mechanical gap-detector, and so the
enforcement behavior in the companion proposal binds to it.

### Motivation

CI-green does NOT prove a scenario-binding / gap epic is complete. Two
states pass CI today while leaving a real gap, and both occurred on
work-item `yfsv4j` (the Dispatcher calibration-telemetry gap) during the
grooming-realization epic:

1. `tests/heading-coverage.json` permits `"test": "TODO"` as an allowed
   state — the `heading_coverage` check is satisfied merely by enumerating
   every `##` (H2) scenario heading, regardless of whether the entry binds
   to a real test. So a delivered behavior's acceptance scenario can be
   bound to NO real test and still pass `just check` and CI. A gap-tied
   item can therefore be closed with its scenario left `TODO`.
2. `resolution:completed` is DERIVED from the label by the reader, not
   ENFORCED at close. So a gap-tied work-item can reach `status: closed`
   without the `resolution:completed` label ever being applied, and
   nothing mechanically rejects that.

Both gaps were caught only by an out-of-band human review of the epic,
i.e. by a "remember-to-verify" instruction rather than a mechanical
guard. This proposal codifies the invariant a mechanical guard enforces
(the guard itself is the companion proposal `closed_item_integrity`).
The existing `## Forbidden patterns` rule "No silent close of
work-items. Every `status: closed` issue MUST carry a `resolution:<enum>`
label" already forbids the label half for ALL closed items; this
invariant ADDS the scenario-binding half SPECIFICALLY for gap-tied items
(whose acceptance is a named scenario) and ties the two halves together
as the single "closed but unproven is forbidden" rule the companion check
enforces. It does not relax or duplicate the existing forbidden-pattern
clause; doctor's existing label check stays the guard for the general
case, and the new `closed_item_integrity` check is the guard for the
gap-tied scenario-binding case.

### Proposed Changes

Add a new `## Closed-item integrity` section to
`SPECIFICATION/constraints.md` (placed after `## Forbidden patterns`,
which it cross-references). The section opens with one sentence framing
it as a closed-item completeness invariant — "closed" must mean "proven",
not merely "status flipped" — then states the invariant as a single
normative clause line (a plain prose line outside any code fence, so the
line-oriented gap-detector sees it as exactly one rule):

> A gap-tied work-item marked `resolution:completed` MUST carry the
> `resolution:completed` label AND its acceptance scenario MUST be bound
> to a real integration-tier-or-above test in `tests/heading-coverage.json`
> (the entry's `test` field is a live test node id, never the `TODO`
> sentinel); a closed gap-tied item whose acceptance scenario is still
> `TODO`, or which lacks the `resolution:completed` label, is "closed but
> unproven" and is FORBIDDEN.

Add a short augmenting prose paragraph (NOT a second MUST line) recording
that: the acceptance scenario of a gap-tied item is resolved from the
item's `gap-id` label through the `clauses[]` gap-id→scenario map in
`tests/heading-coverage.json` (the same map livespec core's
`constraints.md` §"Heading taxonomy" defines and the
`behavior_scenario_link` check consumes); the "real test, not `TODO`"
half is the same `tests/heading-coverage.json` `test`-field state the
existing `heading_coverage` check tolerates as `TODO` but this invariant
does not for closed gap-tied items; and the mechanical enforcement of
this invariant is the `closed_item_integrity` check codified in the
companion proposal in this file.

This proposal targets `constraints.md` ONLY (the invariant). The
companion proposal targets `scenarios.md` (the enforcement scenario) and
carries the `tests/heading-coverage.json` co-edits in its
`resulting_files[]`.

## Proposal: closed_item_integrity check wired into `just check`

### Target specification files

- SPECIFICATION/scenarios.md
- SPECIFICATION/contracts.md

### Summary

Codify one enforcement behavior — a new `closed_item_integrity` check
wired into the `just check` aggregate — that mechanically enforces the
closed-item-integrity invariant from the companion proposal. For each
closed gap-tied work-item in the beads store, the check derives the
item's `gap-id`, resolves it to an acceptance scenario via the
`clauses[]` gap-id→scenario map in `tests/heading-coverage.json`, and
asserts BOTH that the resolved scenario's `heading-coverage` entry binds
to a real integration-tier-or-above test (not the `TODO` sentinel) AND
that the item carries the `resolution:completed` label; it emits a
`closed-item-integrity` finding otherwise. The check is always-wired into
`just check` and always-running, with a self-documenting per-check
severity lever `LIVESPEC_CLOSED_ITEM_INTEGRITY=warn|fail` defaulting to
`warn` — never silently skipped. Because this is a load-bearing,
CI-bound behavior, it carries a Gherkin `## Scenario` (the failing and
passing cases). The check REUSES existing primitives — the shared
`livespec_spec_clauses` extractor, the `clauses[]` map, and the beads
reader — and introduces no new gap-id logic.

### Motivation

The companion invariant states what is forbidden; this behavior is the
mechanical guard that makes it un-bypassable, replacing the
"remember-to-verify" review that caught `yfsv4j` after the fact. Wiring
it into `just check` means a closed-but-unproven gap-tied item surfaces
on every local run, in pre-push, and in CI — the same load-bearing safety
net `just check` already is for lint / types / tests / coverage.

The severity lever follows the carve-out-is-a-severity-lever-not-an-
invariant-relax discipline: the check is ALWAYS wired and ALWAYS runs;
the only thing the lever changes is whether an offender is a warning or a
hard failure. It defaults to `warn` (advisory-first) because there may be
already-closed offenders in the store at the time the check lands;
`warn` lets the check ship and surface them without breaking CI, and the
lever flips to `fail` once the backlog of already-closed offenders is
backfilled (their scenarios bound to real tests and their
`resolution:completed` labels applied). The lever is the SEVERITY switch,
NOT a wiring carve-out — the check always enumerates every closed
gap-tied item and always runs regardless of the lever value.

### Proposed Changes

Codify the check in `SPECIFICATION/contracts.md` and add its acceptance
scenario to `SPECIFICATION/scenarios.md`.

=== contracts.md — the enforcement behavior ===

Add a new `### Closed-item-integrity check` subsection (an H3) under an
appropriate contract section — placed at the END of §"Work-item
beads-issue mapping" or in a sibling enforcement subsection alongside the
other doctor / `just check` enforcement behaviors — opening with one
sentence framing it as the mechanical guard for the closed-item-integrity
invariant in `constraints.md` §"Closed-item integrity". Under it, state
the behavior as normative clause lines (plain prose lines outside any
code fence, each its own gap-detectable rule), written against observable
behavior:

- The `closed_item_integrity` check MUST enumerate every closed gap-tied
  work-item in the beads store, derive each item's `gap-id` from its
  `gap-id:<id>` label, resolve that gap-id to an acceptance scenario via
  the `clauses[]` gap-id→scenario map in `tests/heading-coverage.json`,
  and emit a `closed-item-integrity` finding for any such item whose
  resolved scenario's `heading-coverage` entry is still bound to the
  `TODO` sentinel (not a real integration-tier-or-above test node id) OR
  which lacks the `resolution:completed` label.
- The `closed_item_integrity` check MUST be always-wired into the `just
  check` aggregate and always-running; it MUST NOT be silently skipped.
  Its severity is governed by a self-documenting per-check lever — the
  `LIVESPEC_CLOSED_ITEM_INTEGRITY` environment variable — whose only
  recognized values are `warn` and `fail`. In `warn` mode (the DEFAULT)
  the check MUST surface each offender as a warning and exit `0`; in
  `fail` mode it MUST surface each offender as an error and exit non-zero.
  An unset or unrecognized lever value MUST default to `warn`. The lever
  is the SEVERITY switch, not a wiring carve-out: the check always
  enumerates every closed gap-tied item and always runs regardless of the
  lever value.

Add an augmenting prose paragraph (NOT new MUST lines) recording that the
check REUSES existing primitives and introduces NO new gap-id logic: it
derives gap-ids through the shared `livespec_spec_clauses` extractor (the
same primitive impl-beads' `detect-impl-gaps` detector already imports —
single-source gap-id, no duplication), reads the `clauses[]` map already
defined by livespec core's `constraints.md` §"Heading taxonomy", and
reads closed gap-tied items through the existing beads reader (`bd`
store). Note that this check is enforced by `just check-closed-item-integrity`.

PRECONDITIONS (record as augmenting prose so the future revise/impl loop
sees them — NOT as separate invariants): the check requires (a) the
`clauses[]` gap-id→scenario map to be populated in
`tests/heading-coverage.json` for each gap-tied behavior clause (linking
its gap-id to its acceptance scenario's H2 section name) — this is the
core `clauses[]` contract (`constraints.md` §"Heading taxonomy",
`non-functional-requirements.md` §"Behavior-clause-to-scenario link
check") that impl-beads adopts; and (b) the shared `livespec_spec_clauses`
extractor available to impl-beads' dev-tooling. Both are existing
primitives; the impl work-item adopts the `clauses[]` map into
impl-beads' heading-coverage and wires the check, it does not build new
gap-id machinery.

IMPLEMENTATION APPROACH NOTE (record as augmenting prose, NOT a second
invariant): the `resolution:completed` half of the invariant is best
UPHELD by a "pit of success" `close-work-item` wrapper that atomically
closes a work-item AND applies the `resolution:completed` label in one
operation — so the constraints.md §"Closed-item integrity" two-step close
recipe (`bd close --reason …` then `bd update --add-label
resolution:completed`) can never be half-done (closed without the label).
This wrapper is an impl work-item to be built alongside the
`closed_item_integrity` check, not a separate spec invariant; the
invariant states WHAT must hold, the check DETECTS violations, and the
wrapper makes the compliant path the path of least resistance.

=== scenarios.md — the enforcement scenario ===

Add a new `## Scenario 16 — Closed-item-integrity check rejects "closed
but unproven"` H2 heading at the END of `SPECIFICATION/scenarios.md`
(after `## Scenario 15 — Dispatcher composes next's ranking`), its body a
```gherkin block with a `Feature:` line plus two `Scenario:` blocks
written against observable behavior:

- (failing case) Given a gap-tied work-item is closed and its `gap-id`
  resolves through the `clauses[]` map to an acceptance scenario whose
  `tests/heading-coverage.json` entry is still bound to the `TODO`
  sentinel (or the item lacks the `resolution:completed` label); When the
  `closed_item_integrity` check runs as part of `just check`; Then it
  emits a `closed-item-integrity` finding naming that item — a warning in
  `warn` mode (the default, exit 0) and an error in `fail` mode
  (`LIVESPEC_CLOSED_ITEM_INTEGRITY=fail`, exit non-zero).
- (passing case) Given a gap-tied work-item is closed, carries the
  `resolution:completed` label, and its `gap-id` resolves through the
  `clauses[]` map to an acceptance scenario whose
  `tests/heading-coverage.json` entry binds to a real integration-tier
  test node id (not `TODO`); When the `closed_item_integrity` check runs;
  Then it emits NO finding for that item.

=== heading-coverage co-edit (carry out at revise time) ===

This proposal adds ONE new `##` (H2) scenario heading to
`SPECIFICATION/scenarios.md`: `## Scenario 16 — Closed-item-integrity
check rejects "closed but unproven"`. The revise pass that accepts this
proposal MUST, via the same `resulting_files[]` mechanism (path spelled
`../tests/heading-coverage.json` because `--spec-target` is the main
`SPECIFICATION/` tree), add to `tests/heading-coverage.json`:

1. A matching `heading_coverage` entry for the new Scenario 16 heading,
   mirroring the existing Scenario entries' shape — `"spec_root":
   "SPECIFICATION"`, `"spec_file": "scenarios.md"`, `"test": "TODO"`, and
   a `reason` noting it was added by this closed-item-integrity revise
   pass and that the scenario heading binds to an integration / consumer-tier
   (e2e-cli) test exercising the user-observable check behavior, never a
   unit-tier test, per the heading taxonomy's pyramid-tier requirement,
   with the real node id populated by the governed propose-change/revise
   loop once the heading gains an exercising test. (Per the
   closed-item-integrity invariant this proposal codifies, the gap-tied
   impl work-item that builds the check MUST replace this `TODO` with the
   real integration test before its own `resolution:completed` closure —
   the check is its own first subject.)
2. The `clauses[]` link for the new normative clause(s) added to
   `contracts.md` §"Closed-item-integrity check" — each `clauses[]`
   element `{"gap_id": "<gap-id derived by livespec_spec_clauses for the
   clause>", "scenario": "Scenario 16 — Closed-item-integrity check
   rejects \"closed but unproven\""}` attached to the appropriate
   `heading_coverage` registry entry — per livespec core's
   `spec.md` §"Self-application" clause-link co-edit discipline and
   `constraints.md` §"Heading taxonomy" `clauses[]` shape. The
   companion proposal's `constraints.md` §"Closed-item integrity"
   invariant clause similarly gains a `clauses[]` link to Scenario 16.

No existing `##` heading is added elsewhere, renamed, or removed by this
proposal (Scenarios 1–15 keep their headings; the new
`### Closed-item-integrity check` and the companion's `## Closed-item
integrity` are the only new headings — the former an H3 needing no
`heading_coverage` entry, the latter an H2 in `constraints.md` whose
`heading_coverage` entry is added by the companion proposal's accept).

=== Placement rationale ===

This proposal lives in `livespec-impl-beads` (NOT livespec core) because
only impl-beads has the work-items / beads store that supplies the
"delivered" signal — the closed gap-tied items the check enumerates.
Core cannot distinguish a delivered-but-unbound scenario from a
not-yet-implemented one, which is exactly WHY `"test": "TODO"` is
legitimately allowed in core's `heading_coverage` (a scenario may
describe behavior not yet built). The "closed but unproven is forbidden"
invariant is only meaningful where "closed" is observable — the
orchestrator's store — so the invariant, the enforcement behavior, and
its scenario all belong here, per the §Boundary cross-repo placement
split (realization mechanism → the orchestrator's own spec, never core).
