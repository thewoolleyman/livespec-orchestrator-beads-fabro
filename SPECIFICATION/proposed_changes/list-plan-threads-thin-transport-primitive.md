---
topic: list-plan-threads-thin-transport-primitive
author: claude-opus-4-8
created_at: 2026-07-06T20:52:21Z
spec_commitments:
  impl_followups:
    - id_hint: list-plan-threads-primitive
      description: |
        Implement the list-plan-threads thin-transport primitive (the impl sub-slice of OR2): a bin/list_plan_threads.py wrapper plus its livespec_orchestrator_beads_fabro command module that enumerates the unarchived thread directories under the governed repo's plan/ store (every direct child of plan/ except plan/archive/), emitting {"plan_threads": [<topic>, ...]} in ascending lexicographic order on --json and one topic per line on the default human path; degrades to plan_threads: [] with exit 0 on a missing or empty plan/; is read-only (no tenant-DB writes, no plan-store writes, no ledger reads, no user prompts). Add the plugin's thin SKILL.md binding(s) (Claude Code + Codex) that pass through to the wrapper with zero orchestration (per contracts.md Thin-transport skills), and the integration test that Scenario 42 maps to, binding the tests/heading-coverage.json TODO to a real node id.
---

## Proposal: Add the list-plan-threads thin-transport primitive

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- SPECIFICATION/README.md
- tests/heading-coverage.json

### Summary

Add list-plan-threads as a fourth thin-transport primitive — a pure read-and-emit enumerator, sibling of list-work-items, that lists the open (unarchived) plan/<topic>/ planning threads under the governed repo's plan/ thread store. It enumerates one entry per unarchived thread directory (every direct child of plan/ except the plan/archive/ subtree) in ascending lexicographic topic order, emits {"plan_threads": [<topic>, ...]} on --json, is strictly read-only (no store or ledger writes, no prompts, directory enumeration only), and degrades to an empty result with exit 0 when plan/ is missing or empty. The proposal sweeps every place that restates the thin-transport count or names the set (the authoritative skill inventory, the section heading, the query-only and zero-orchestration lists, and the spec-tree README), names the primitive from the existing needs-attention forward reference, and ratifies the behavior in a new Scenario 42 with its heading-coverage co-edit.

### Motivation

This is the SPEC sub-slice of work-item OR2. The read/awareness surface (needs-attention) must compose "plan threads" (already named in contracts.md §"next" scope-asymmetry as part of the wider primitive set it composes), but no canonical primitive supplies them: impl-side next is a pure implement-only ranker of ready ledger work and never scans the filesystem, and the retired orchestrate plan is gone. The settled rules for surfacing unarchived plan threads (unarchived-visible / archived-invisible split, lexicographic ordering, read-only directory enumeration, degrade-gracefully on a missing plan dir) were established in the now-rejected-superseded proposal orchestrate-plan-surfaces-unarchived-plan-threads (SPECIFICATION/history/v031/proposed_changes/orchestrate-plan-surfaces-unarchived-plan-threads.md and its -revision.md), whose rejection note redirects that intent into "a future list-plan-threads thin-transport primitive per the needs-attention design record". The design record (livespec/plan/needs-attention/research/design.md §"Read primitives needs-attention composes") defines list-plan-threads as the NEW thin-transport primitive, sibling of list-work-items, that absorbs that rejected proposal's role. This proposal lifts those settled rules onto the primitive rather than the retiring orchestrate plan. Spec-first ordering: the contract text must name the primitive before the impl wrapper is built, or building it first would create impl->spec drift that capture-spec-drift would flag; the impl wrapper + bindings + test are declared as the spec_commitments impl follow-up list-plan-threads-primitive.

### Proposed Changes

All target text below is quoted verbatim from the live spec at branch
`or2-spec-list-plan-threads` (off `master` @ v0.12.0). This proposal
adds ONE new thin-transport primitive, `list-plan-threads`, as a sibling
enumerator of `list-work-items`, and sweeps every place that restates the
thin-transport count or names the set. No `## ` (H2) heading in
`contracts.md`/`constraints.md` is added, changed, or removed; the only
new H2 is `## Scenario 42` in `scenarios.md`, whose
`tests/heading-coverage.json` co-edit is item I.

**A. Skill-inventory count — `SPECIFICATION/contracts.md` §"The skill
surface".** In the sentence establishing the ONE authoritative skill
inventory, the parenthetical `(six heavyweight + one operator + three
thin-transport)` MUST become `(six heavyweight + one operator + four
thin-transport)`. (Verbatim target: "this enumeration (six heavyweight +
one operator + three thin-transport) is the ONE authoritative skill
inventory".)

**B. Thin-transport section heading — `SPECIFICATION/contracts.md`.** The
H3 heading `### Thin-transport skills (3)` MUST become `### Thin-transport
skills (4)`. (This is an H3, not an H2 — no `tests/heading-coverage.json`
entry tracks it; the repo's heading-coverage registry enumerates H2
headings only.)

**C. New `list-plan-threads` subsection — `SPECIFICATION/contracts.md`
§"Thin-transport skills".** A new `#### list-plan-threads` subsection MUST
be inserted immediately AFTER the `#### list-work-items` subsection and
BEFORE the `#### next` subsection, with exactly this content:

#### `list-plan-threads`

CLI surface: `list-plan-threads [--json] [--project-root <path>]`. No
`--filter` flag — the skill emits the complete set of open (unarchived)
plan threads.

`--project-root <path>` — override the base whose `plan/` thread store
is enumerated. Default: `Path.cwd()`. Used by the awareness surface's
(and any other consumer's) cross-boundary handoffs to invoke this skill
from outside the consumer project root.

This skill is the plan-thread enumerator sibling of `list-work-items`: a
pure read-and-emit pass-through that enumerates the open planning threads
under the governed repo's `plan/` thread store (per §"The
`plan/<topic>/` thread store"). It exists so the read/awareness surface
can compose "plan threads" (per §"`next`" scope-asymmetry) from a single
canonical primitive rather than re-scanning `plan/` inline.

The skill MUST enumerate exactly one entry per **unarchived** thread
directory — every direct child directory of `plan/` EXCEPT the archive
subtree `plan/archive/` — in ascending lexicographic topic order. An
**archived** thread (`plan/archive/<topic>/`) MUST NOT surface. The scan
is directory enumeration only: it MUST NOT read thread contents, rank,
filter beyond the unarchived/archived split, or consult the ledger —
whether a thread's anchoring epic state matches its archived/unarchived
placement remains the Conformance Pattern's concern (§"Archive on epic
close"), not this skill's.

`--json` output: a top-level JSON object with one key, `plan_threads`,
whose value is an array of unarchived thread topic strings (the thread
directory names) in ascending lexicographic order:

```json
{
  "plan_threads": ["alpha-topic", "beta-topic"]
}
```

Default human output: one line per thread topic. Each topic `<topic>` is
the natural key from which a consumer derives the thread path
(`plan/<topic>/`) and the `/livespec-orchestrator-beads-fabro:plan
<topic>` handoff; the skill emits neither derived form (per
`constraints.md` §"Forbidden patterns" no-off-substrate / derive-on-read
discipline).

Degrade-on-missing: a missing or empty `plan/` directory MUST yield
`plan_threads: []` and MUST exit `0` — an absent thread store is a valid
zero-thread state, never an error. This is the same per-source degraded
tolerance the ranking and listing primitives already carry.

The skill MUST NOT mutate any store: it MUST NOT write the tenant DB,
MUST NOT write or reorder the `plan/` thread store, and MUST NOT prompt
the user. It is query-only by contract (per `constraints.md` §"Forbidden
patterns").

**D. Awareness-surface cross-reference — `SPECIFICATION/contracts.md`
§"`next`" (Scope asymmetry paragraph).** So the existing forward
reference names the new primitive symmetrically with `list-work-items`,
the clause "composes a wider primitive set (the human-valve lanes via
`list-work-items`, plus plan threads and hygiene) in the read/awareness
surface" MUST become "composes a wider primitive set (the human-valve
lanes via `list-work-items`, plan threads via `list-plan-threads`, plus
hygiene) in the read/awareness surface".

**E. Out-of-scope (query-only) set — `SPECIFICATION/contracts.md`
§"Out-of-scope surfaces".** The sentence "The three thin-transport skills
(`list-work-items`, `next`, `detect-impl-gaps`) are query-only by
contract (per `constraints.md` §"Forbidden patterns") and never write to
the store" MUST become "The four thin-transport skills (`list-work-items`,
`next`, `detect-impl-gaps`, `list-plan-threads`) are query-only by
contract (per `constraints.md` §"Forbidden patterns") and never write to
the store". (The `list-plan-threads` scan reads the filesystem `plan/`
store, not the tenant DB; it writes nothing either way.)

**F. Zero-orchestration set — `SPECIFICATION/constraints.md` §"Skill
orchestration constraints".** The clause "Thin-transport skills
(list-work-items, next, detect-impl-gaps) carry ZERO orchestration in
SKILL.md beyond a one-line invocation of the wrapper script" MUST become
"Thin-transport skills (list-work-items, next, detect-impl-gaps,
list-plan-threads) carry ZERO orchestration in SKILL.md beyond a one-line
invocation of the wrapper script". (The existing no-mutating-flags rule
in §"Forbidden patterns" already binds `list-plan-threads` through its
`list-*` glob — "No mutating CLI flags on `list-*` or `next` skills" — so
no edit is needed there; its non-normative parenthetical about `bd`
reads simply does not apply to this filesystem-only enumerator.)

**G. Spec-tree README skill inventory — `SPECIFICATION/README.md`
§"Required content".** The clause "one operator skill: drive; three
thin-transport skills: detect-impl-gaps, list-work-items, next — per
`contracts.md` §"The skill surface"" MUST become "one operator skill:
drive; four thin-transport skills: detect-impl-gaps, list-plan-threads,
list-work-items, next — per `contracts.md` §"The skill surface"".

**H. New behavior scenario — `SPECIFICATION/scenarios.md`.** A new
`## Scenario 42 — list-plan-threads enumerates unarchived plan threads`
MUST be appended (the current last scenario is `## Scenario 41`), ratifying
the unarchived-visible / archived-invisible split, the lexicographic
ordering, the read-only guarantee, and the degrade-on-missing behavior:

## Scenario 42 — list-plan-threads enumerates unarchived plan threads

```gherkin
Feature: list-plan-threads enumerates unarchived plan threads
  As a consumer of the read/awareness surface
  I want open planning threads enumerated as a thin-transport read
  So that an unarchived thread is never invisible to the awareness picture

Scenario: unarchived threads enumerate in lexicographic order; archived threads do not
  Given a governed repo whose plan/ thread store contains unarchived thread directories plan/beta-topic/ and plan/alpha-topic/
  And an archived thread directory plan/archive/old-topic/
  When list-plan-threads --json is run
  Then plan_threads is exactly ["alpha-topic", "beta-topic"]
  And no entry references old-topic or the plan/archive/ path
  And the invocation mutates nothing

Scenario: a repo with no plan directory yields zero plan threads
  Given a governed repo with no plan/ directory
  When list-plan-threads --json is run
  Then plan_threads is empty
  And the invocation exits 0
```

**I. Heading-coverage co-edit — `tests/heading-coverage.json`.** The
revision accepting this proposal MUST co-edit `tests/heading-coverage.json`
atomically (per the repo's heading-coverage discipline; `SPECIFICATION/
constraints.md` closed-but-unproven prohibition; `SPECIFICATION/
contracts.md` `closed_item_integrity`), appending one entry for the new
`## Scenario 42 — list-plan-threads enumerates unarchived plan threads`
heading: `spec_root: SPECIFICATION`, `spec_file: scenarios.md`,
`test: TODO` (until the declared impl follow-up binds a real
integration-tier test node id), with a `reason` naming this proposal.
This file MUST be included in the revise payload's `resulting_files[]` so
the co-edit lands in the same commit. No other heading-coverage entry
changes — items A/B/C/D/E/F/G touch only H3/H4 headings or body prose,
none of which the H2-only registry tracks.
