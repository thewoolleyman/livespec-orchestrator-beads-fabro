---
topic: a-released-item-s-recovery
author: claude:factory-run-work-preservation plan seat session d387b8
created_at: 2026-11-13T09:36:25Z
---

## Proposal: A recovery route's factory liveness read appends one journal record naming its factory, credential source and verdict

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add one paragraph to contracts.md §"Dispatcher policy settings", directly after "Factory reads take the Dispatcher's own factory credential.", requiring recovery routing's earlier-run liveness read to append exactly one `factory-liveness-read` record to the dispatch journal. The record names the work item, the factory and the server address it reached, the earlier run id, a verdict of `live`, `absent` or `unreadable`, and the credential source (`family-wrapper` or `process-environment`, with the per-name dev-token variable and never its value). An unreadable read also names its failure and exit code. The record is observation only and changes no route. Add two scenarios to Scenario 185 that exercise it. No heading changes, so the heading-coverage files stay untouched.

### Motivation

bd-ib-g2t2pg (plan factory-run-work-preservation, epic bd-ib-nckst7) is at pending-approval, at spec-change tier. Its filing-time tier record (2026-11-13T09:26:31Z, spec version 366) reads verdict partial, generalization target ## Scenario 185, linked topic a-released-item-s-recovery: Scenario 185 states only that an unobservable measurement journals a recovery-held record, not a per-read record naming the factory, server, earlier run, verdict, failure detail or credential source. legacy-coordinator-agent (session e7605d67, 2026-11-13) ordered this seat to cut the proposal under that topic.

THE GAP, measured on the orchestrator v0.326.0 canary (2026-11-13). bd-ib-comnk4 (#5129, d8df6c159, shipped in v0.326.0 = f4c05ab80) moved the recovery-routing liveness read, factory_reading() in _dispatcher_resume_factory_reading.py, called by gather_resume at _dispatcher_resume_observation.py:201, into the host default wrapper that owns the factory credential. That read writes no journal row. To show the read ran for livespec-dev-tooling-5wybjq (run 01M7A2P35VZH), the canary had to infer it from the pre-launch-cpu phase=recovery-routing row (09:08:49Z), the recovery-route route=seeded row (09:09:02Z) and the code path. No row named the read, the factory it reached, its credential source or its outcome. Rule CANARY-COVERS-CHANGED-PATHS needs a journal row for each changed path, and so does any later diagnosis of a credential fault in this read. That fault class is exactly what comnk4 fixed: a sealed tenant wrapper made an ended run's liveness unobservable (hxi-wv762e, run 01M778HJT951, 2026-11-12).

WHAT THE SPEC SAYS TODAY. contracts.md §"Dispatcher policy settings" → "Factory reads take the Dispatcher's own factory credential." governs which credential and environment the read uses, and when it may be reported unobservable. Scenario 185's "An unobservable measurement holds the item without reclaim" governs the held route. Neither requires the read itself to be journaled.

VERDICTS MAP TO THE SHIPPED READ. factory_reading() returns observed=False when the listing exits non-zero (unreadable); otherwise it reports the live runs attributed to the item (live when any is non-terminal, absent when none is) and whether the earlier run is listed.

RELATIONSHIP TO IN-FLIGHT WORK (survey 2026-11-13, 22 open spec PRs). None touches the factory-read paragraph or the liveness read; ALIGN with all of them. The nearest are recovery-routing-reads-a-rework (#5083, the rework-rejection read of recovery routing) and a-ruled-seed-s-recovery (#5067, a ruled seed's source run). Both add other inputs to the same routing pass, and neither adds or changes a journal record that this paragraph orders against.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Dispatcher policy settings": add one paragraph

Insert this paragraph directly AFTER the paragraph whose opening sentence is **Factory reads take the Dispatcher's own factory credential.**, and before the paragraph that begins "The registry refusal applies to resolving a DECLARED, registry-backed entry", separated by one blank line on each side. No existing paragraph changes:

```markdown
**A recovery route's factory liveness read is journaled.** Each time recovery routing takes the earlier-run liveness read of §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" for a released item, the Dispatcher MUST append exactly one `factory-liveness-read` record to the dispatch journal for that read, before it journals that item's `recovery-route` or `recovery-held` record in the same pass. The record MUST name: the work item; the factory name and the server address the read reached, as the factory resolution above resolved them; the earlier run id the read looked for, or `none` when the item has no journaled earlier run; the read's verdict; and the read's credential source. The verdict MUST be exactly one of `live`, when the factory answered and listed a run attributed to the item in a non-terminal state; `absent`, when the factory answered and listed no such run; or `unreadable`, when the factory could not be resolved or did not answer under the Dispatcher's own credential. A `live` or `absent` record MUST also name the status the factory listed for the earlier run, or `not-listed` when the listing did not carry it. An `unreadable` record MUST also name the failure, whether an unresolvable factory, an authentication refusal, an unreachable server, a timeout or a non-zero exit of the factory listing, and that listing's exit code, or `none` when no listing process ran. The credential source MUST be `family-wrapper`, naming the default family wrapper's pathname, when the read ran in an environment that wrapper established for it, or `process-environment` when the Dispatcher took the read from its own process environment as the preceding paragraph permits; in both cases the record MUST name the per-name dev-token variable the read used (`FABRO_DEV_TOKEN__<factory>`). It MUST NOT name a target's `credential_wrapper` as the source, and MUST NOT carry the value of any token or of any `FABRO_`-prefixed variable other than the server address. The record is an observation only: it MUST NOT change the route the read leads to. An `unreadable` read leads to the existing unobservable-measurement hold, and `live` and `absent` lead where the ratified routing rules already send them. This paragraph governs recovery routing's liveness read only; the liveness read of `resume --item` and the other factory-read surfaces above are unchanged. Scenario 185 in `scenarios.md` exercises this paragraph.
```

### 2. `SPECIFICATION/scenarios.md` §"Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch": add two scenarios

Insert these two scenarios inside that heading's `gherkin` block, directly AFTER the scenario "An unobservable measurement holds the item without reclaim" (whose last step is "And no publish-branch reclaim runs for it"), separated by one blank line on each side. No existing scenario changes:

```gherkin
  Scenario: A recovery route's factory liveness read is journaled with its factory, credential source and verdict
    Given a ready released item whose journal names an earlier run R on a declared factory F
    And the Dispatcher runs inside a sealed tenant wrapper's child and takes F's reads under the default family wrapper
    When the Dispatcher routes the item
    Then the journal carries one factory-liveness-read record for the item naming F, F's resolved server address, R, the verdict and the credential source family-wrapper with the wrapper's pathname and FABRO_DEV_TOKEN__F
    And that record precedes the item's recovery-route or recovery-held record in the journal
    And no record carries the dev token's value

  Scenario: A failed factory liveness read is journaled with its failure, and the item is held as unobservable
    Given a ready released item whose journal names an earlier run R on a declared factory F
    And F's run listing exits non-zero under the Dispatcher's own credential
    When the Dispatcher routes the item
    Then the journal carries one factory-liveness-read record naming F, R, the verdict unreadable, the failure and the listing's exit code
    And the item stays ready and is not admitted in that pass
    And the journal carries a recovery-held record naming the measurement
```

### 3. Heading coverage

This proposal MUST NOT add, rename or remove any `## ` heading: change 1 adds a paragraph inside an existing section and change 2 adds scenarios inside an existing scenario heading. `tests/heading-coverage.json` and `tests/heading-coverage-debt.json` therefore MUST NOT change in the revise that ratifies it.

