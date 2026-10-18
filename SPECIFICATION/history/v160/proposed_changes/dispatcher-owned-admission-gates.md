---
topic: dispatcher-owned-admission-gates
author: claude-opus-5-5:run-lifecycle-false-verdicts
created_at: 2026-10-18T15:22:56Z
---

## Proposal: A caller does not gate a dispatch on the default branch's CI

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Say in one normative place that a caller of drive or of the Dispatcher does not pre-check the default branch's CI, name the three admission conditions the Dispatcher owns (the bounded master-CI preflight wait, the admission session-headroom assessment, and plugin build currency surfaced as a warning and refused only below a committed minimum_release floor), and name what a launch loop may add on its own (host capacity, slot availability, launch spacing).

### Motivation

On 2026-10-18 nine launching sessions each held launches behind a hand-rolled master ci-green pre-check: the latest default-branch run was pending, as it is for much of any day on a repository that releases often, while the ratified master-CI preflight ("A still-running master CI run is not a failure") would have waited it out. The stale guide .ai/master-ci-green-preflight.md (being rewritten by bd-ib-2jfzgr) and a coordinator gate list both told callers to pre-check; nothing in the spec says callers must not. The maintainer directed a spec and guidance change that calls the rule out (work-item bd-ib-zygea5; capacity coordinator rulings R178 and R183). The same shape is what produced the bounded wait on 2026-10-13 (epic bd-ib-jnpvh4).

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatch preflight and post-merge step discipline", insert the following paragraph and list directly after the paragraph that begins "**A still-running master CI run is not a failure.**" and before "**Janitor check-suite resolution.**". No heading is added.

**A caller does not gate a dispatch on the default branch's CI.** Rationale: this repository's default branch moves with every merge and releases often, so its latest CI run is pending for much of any working day. A caller that reads that run itself sees an empty conclusion and holds a launch the master-CI preflight above would have admitted after waiting. On 2026-10-18, nine launching sessions each held launches behind a hand-rolled "master ci-green" pre-check while the preflight would have waited out the pending run. The 2026-10-13 measurement that produced the bounded wait recorded the same shape: a pending run read as a refusal pushed a retry loop onto every caller, and those loops raced the newer runs (design record: ledger epic `bd-ib-jnpvh4`; the 2026-10-18 instance is recorded on work-item `bd-ib-zygea5`). A caller of `drive` or of the Dispatcher, whether an operator, a launch loop, a supervising session or a coordinator, MUST NOT gate a dispatch on the default branch's CI state itself: it MUST NOT read the default branch's latest CI run to decide whether to invoke a dispatch, and it MUST NOT hold, defer or skip a dispatch because that run is pending. A caller MUST NOT duplicate any of the following three admission conditions, which the Dispatcher owns:

1. The master-CI preflight of this section. It waits on a pending run for its bounded window and refuses only on a run that concludes red, an unprovable condition, or the expiry of that window (`master-ci-pending`).
2. The admission session-headroom assessment of §"Provider spend containment" → "Admission filters candidates by projected Claude session headroom". It skips a covered candidate whose remaining headroom is below the committed floor or whose projected exhaustion falls inside the committed horizon. When an admission-required node is left with no eligible candidate, the item stays `ready` without a claim until the scheduled reevaluation.
3. Plugin build currency per §"Self-contained plugin dispatch" → "The dispatch-admission path MUST NOT block on ambient release-staleness". A build that lags the latest release is surfaced as a non-blocking fact and never refused on that ground. The only blocking currency form is a committed `dispatcher.minimum_release` floor. Keeping a long-lived session bound to the registered build is the operator's duty, not an admission condition.

A caller MAY add gates of its own for conditions the Dispatcher does not own: capacity on the factory host (for example its measured idle CPU), the availability of a launch slot, and the spacing between launches. Such a gate decides only WHEN a caller invokes a dispatch, and it MUST NOT re-implement, pre-empt or stand in for any of the three conditions above.

