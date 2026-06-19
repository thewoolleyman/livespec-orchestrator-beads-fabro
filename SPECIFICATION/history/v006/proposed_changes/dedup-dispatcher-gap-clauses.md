---
topic: dedup-dispatcher-gap-clauses
author: claude-opus-4-8
created_at: 2026-06-19T18:00:35Z
---

## Proposal: Deduplicate Dispatcher gap-detectable behavior clauses

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The v004 §"Grooming and slice-size calibration" → "### Gap-detectable behavior clauses" H3 restated all eight realization behaviors as normative MUST clause lines, but behaviors 4 (Dispatcher refuses human-gated), 5 (non-convergence bounce to needs-regroom), and 6 (emit calibration telemetry) ALSO already exist as normative MUST clause lines in the sibling "### Dispatcher grooming behavior" subsection. Because the mechanical gap-detector keys gap-ids on hash(spec_file + heading_path + clause_text), these three behaviors yield two gap-ids each under two different heading paths, producing duplicate gap-tied work-items that conflict with the existing OPEN items livespec-impl-beads-cjey2z (behavior 4), n5kina (behavior 5), and yfsv4j (behavior 6), which are tied to the §"Dispatcher grooming behavior" gap-ids. This proposal removes the three duplicate clause lines from the H3 (keeping them ONLY in their authoritative §"Dispatcher grooming behavior" location, byte-unchanged so cjey2z/n5kina/yfsv4j stay valid), keeps the five genuinely-new H3 clauses (behaviors 1 intake Definition-of-Ready, 2 groom front-end, 3 needs-regroom state+transitions, 7 calibration analysis pass, 8 single Fabro DOT tweak), and adds a one-line cross-reference in the H3 intro pointing to §"Dispatcher grooming behavior" for the Dispatcher behaviors' normative clauses.

### Motivation

Eliminate a one-to-many gap-id duplication introduced at v004 so the mechanical gap-detector no longer emits two gap-ids per Dispatcher behavior. The duplicate H3 gap-ids (gap-vihl76nl, gap-6sjw3ezu, gap-mt7eycbr) have zero work-items tied to them, while the authoritative §"Dispatcher grooming behavior" gap-ids (gap-dpk6g22t, gap-rs4tkntz, gap-ajq7ynr4) carry the three OPEN gap-tied work-items. Removing the H3 duplicates is the lowest-churn fix: it keeps the existing gap-ids stable, files no orphan work-items, and prevents duplicate gap-tied filings. No new behavior is introduced, so all Gherkin Scenarios 1-15, the Open realization choices, and the compose-next already-satisfied note are preserved verbatim, and no H2 heading is added/changed/removed (the edit is entirely inside the existing H3).

### Proposed Changes

In SPECIFICATION/contracts.md, inside §"Grooming and slice-size calibration" → "### Gap-detectable behavior clauses":

1. Update the H3 intro paragraph: scope it to the NON-Dispatcher behaviors and add a one-line cross-reference stating that the Dispatcher behaviors' authoritative normative clauses live in §"Dispatcher grooming behavior" (refuse human-gated; bounce on non-convergence; emit calibration telemetry), and noting they are NOT restated here to avoid a duplicate gap-detectable line.

2. Remove the THREE duplicate clause lines from the H3:
   - "The Dispatcher MUST refuse to auto-dispatch a `human-gated` (spec-change) item — it surfaces it for the maintainer instead." (behavior 4)
   - "On factory NON-CONVERGENCE (a dispatched slice that will not converge through the janitor gate) the Dispatcher MUST mark the item `needs-regroom` and SURFACE it (escalate-don't-drop), never infinite-retry." (behavior 5)
   - "The Dispatcher MUST emit calibration telemetry: an outcome signal plus mechanical size proxies recorded on the EXISTING Dispatcher journal (the journal → Honeycomb leg already designed in the operability preconditions), with NO new always-on service." (behavior 6)

3. Keep the FIVE remaining H3 clause lines unchanged (behaviors 1, 2, 3, 7, 8).

4. Leave the "### Dispatcher grooming behavior" subsection BYTE-UNCHANGED (its clauses are the authoritative location for behaviors 4/5/6 and keep gap-ids gap-dpk6g22t / gap-rs4tkntz / gap-ajq7ynr4 stable).

5. Preserve everything else verbatim: all Gherkin Scenarios 1-15, "### Open realization choices", and the compose-next already-satisfied note at the end of the H3.

No H2 heading is added, removed, or renamed (the edit is entirely within the existing H3), so tests/heading-coverage.json needs no change.
