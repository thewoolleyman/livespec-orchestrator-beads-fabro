---
topic: factory-cycle-progress-bounce
author: codex
created_at: 2026-10-08T23:53:27Z
---

## Proposal: Observe completed test-first cycles and explain the existing non-convergence bounce

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Make the authorized S6 runtime progress signal precise: record completed Red-Green cycles, changed product logical lines and elapsed seconds; explain insufficient completed-cycle progress at the existing fix-loop cap; and permit per-cycle size or time enforcement only through separately adopted committed settings. No numeric threshold is adopted.

### Motivation

Plan bd-ib-q622ls opening research D3 and existing child bd-ib-z2y4ca require deterministic per-cycle observations rather than a predictive hand-chosen size limit. The current calibration and non-convergence contracts cover aggregate outcome/proxies and the fix-loop cap, but do not define these additional measurements or their failure semantics. The maintainer has approved autonomous completion of the plan, including ratified non-convergence behavior with numeric calibration deferred.

### Proposed Changes

Add a subordinate runtime-cycle-progress contract beneath the existing calibration/non-convergence contract, with the following requirements and a new real-surface Gherkin scenario.

The Dispatcher MUST derive progress for the current dispatch from its actual preserved commit/provenance series, including failed and unmerged runs; it MUST NOT depend on a successful merge to observe the run which needs to bounce. A completed cycle MUST be one distinct verified Red-Green pair in the sanctioned test-first provenance, including a Green-amended commit that retains its Red evidence. The same pair MUST count once across duplicate observations or retries; an open Red, a suite-green-only commit and an unrelated historical commit MUST NOT count as a completed cycle. The effective assertion count MUST come from the sanctioned parser for the work-item criteria used by that dispatch.

For every observable completed cycle, calibration MUST record its one-based ordinal, source commit/pair identity, product logical lines changed and elapsed cycle seconds, alongside the dispatch's effective assertion count. Changed product logical lines MUST mean added plus removed logical lines between that pair's test-only Red state and Green state, not net file growth; the measurement MUST use the repository's canonical logical-line counting and product-path classification, excluding tests, documentation, comments, blank lines and formatting-only changes. Elapsed seconds MUST be the nonnegative interval from the pair's preserved Red capture time to its verified Green time, not the interval between later merge commits. The source identities and measurement method MUST be retained so an operator can replay the observation. Unavailable source trees, unsupported counting, incomplete provenance or invalid/reversed timestamps MUST be exposed as unobserved with a reason for the affected measurement, never substituted with a healthy-looking zero or fabricated duration. An unavailable individual size/time measurement MUST NOT erase an otherwise independently established completed-pair count.

At the existing configured fix-loop cap, a run with an observed completed-cycle count smaller than its effective assertion count MUST take the sanctioned non-convergence return to backlog and surface both counts and the cap in its bounce reason. The comparison MUST NOT create an earlier count-only bounce before the cap, change the cap, or treat count sufficiency as proof that acceptance passed. Existing non-convergence and ordinary admission/acceptance gates MUST remain effective independently. When the series or assertion count cannot be established, the progress comparison MUST be reported unobserved, not falsely classified as a zero-count deficit; existing cap-based non-convergence still applies.

The committed-only settings dispatcher.adopted_cycle_product_lloc_ceiling and dispatcher.adopted_cycle_duration_seconds_ceiling MUST be absent by default and MUST remain outside the API-configurable policy set. A present value MUST be a positive integer excluding booleans; invalid policy MUST refuse before claim or lifecycle mutation. Each ceiling MUST remain inactive until a maintainer separately adopts its numeric value through a reviewed committed change. An observed completed cycle strictly exceeding an adopted corresponding ceiling MUST contribute to the same sanctioned non-convergence/backlog disposition before merge, naming the setting, adopted value, observed value and cycle identity. Equality MUST NOT be a breach. Absence of adoption or an unobserved measurement MUST NOT manufacture a breach. Neither the calibration analysis nor this revision may adopt a value. The existing intake size_justification exception MUST NOT waive these independent runtime gates.

The terminal calibration journal and span MUST expose the per-cycle observations or explicit absence diagnostics, effective assertion count, completed-cycle count and whether a progress deficit or adopted cycle ceiling contributed to the bounce. Journal and span projections MUST agree; absent numeric observations MUST remain null in the journal and omitted numeric attributes on the span, with an accompanying reason. No new always-on service or Fabro platform modification is permitted.

Add a Gherkin scenario covering: a converging multi-cycle run with replayable measurements; failed/unmerged source recovery; duplicate/open-Red/suite-green exclusions; an observed deficit at the cap versus the same progress before the cap; sufficient count not bypassing a failing ordinary gate; an absent ceiling; equality and strict breach under each adopted ceiling; invalid configuration; and unavailable evidence without fabricated zeros. Co-edit the heading coverage mapping during ratification with an explicit real integration-tier test debt owned by bd-ib-z2y4ca, preserving existing first-seen dates. Scenario numbers MUST be allocated against the then-current live tree, not reused from concurrent revisions. This proposal aligns with the independent bounded-wait/session-recovery work and changes neither its deadlines nor recovery ownership.
