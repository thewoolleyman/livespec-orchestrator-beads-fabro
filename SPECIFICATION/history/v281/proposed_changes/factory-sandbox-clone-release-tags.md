---
topic: factory-sandbox-clone-release-tags
author: claude-opus-5-5
created_at: 2026-11-02T18:14:33Z
---

## Proposal: A factory sandbox clone's prepare chain refreshes the remote's release tags

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a new contracts.md H2, §"Factory sandbox clone release tags", directly after §"Self-contained plugin dispatch", stating that the prepare steps the Dispatcher renders into every run MUST refresh the clone's tag namespace from the remote (forced, after the unshallow and no later than the dispatch-base fetch), so that after preparation the clone's newest release tag equals the remote's, every remote tag reachable from the fetched default branch is present and agrees with the remote, and a tag-reading check reads the remote's tags; a failed refresh fails preparation. Add Scenario 298 exercising it, and the matching tests/heading-coverage.json entries at revise.

### Motivation

Work-item bd-ib-ia6zbf ("Factory sandbox clones carry the remote's current release tags, so a tag-reading check does not read a tag set about 50 releases stale") was refused by the dispatcher's Definition-of-Done gate: its reference line cited §"Fabro factory host provisioning constraints", which never governs clone tag preparation. The gate's governing-heading verdict was `kind: unstated`, with generalization target §"Self-contained plugin dispatch", and its remedy was to file the behaviour through the spec-change tier. A search of every H2 in SPECIFICATION/*.md and of the body text for clone, tag, unshallow, single-branch, launch-overlay and default-branch-fetch terms found no clause stating how a factory sandbox clone's tag set is prepared: the dispatch-base fetch is described only in code (`_dispatcher_default_branch_fetch.py`, bd-ib-xlblgr) and passes no tag refspec. Measured cause, from factory run 01M6E7FFPF99 (livespec-dev-tooling-t4rx4t): the Dispatcher's launch overlay unshallows the single-branch sandbox clone and fetches only the default-branch refspec, so the remote's tag namespace is never refreshed. The clone's release tags stopped at v1.99.0 while the remote was at v1.153.2, and livespec-dev-tooling's tests/spec/test_versioning_lockstep.py failed in the refresh merge's suite-green leg. A dedicated H2 is proposed rather than a paragraph inside §"Self-contained plugin dispatch" because the gate requires an H2 whose whole section governs the item's assertions; that section spans well over a thousand lines of unrelated dispatch rules, and placing the new H2 directly after it keeps it adjacent to the overlay and prepare-step rules it extends. In-flight spec work surveyed 2026-11-02 (14 remote spec/* branches, open PR 4193 revise v277) touches nothing about clone tags; this proposal aligns with all of it and only takes the next scenario number after PR 4193's Scenario 297.

### Proposed Changes

### contracts.md

Add a new H2 to `SPECIFICATION/contracts.md`, placed immediately after §"Self-contained plugin dispatch" and before §"Work-item state semantics", with exactly this heading and body:

~~~~markdown
## Factory sandbox clone release tags

A factory run's sandbox clone MUST carry the release tags its repository's
remote holds at dispatch time, so a check that reads tags inside the run
reads the same tag set a fresh clone of the remote would read. This section
governs every run the Dispatcher launches: the reserved `implement-work-item`
workflow, every registered variant, a target-local workflow resolved under
"Target-local workflow" in §"Self-contained plugin dispatch", and a run the
Dispatcher resumes.

**The prepare chain refreshes the remote's tags.** The prepare steps the
Dispatcher renders into a run MUST include a fetch from `origin` that updates
the clone's tag namespace from the remote's, with existing local tags
overwritten where the remote's tag of the same name points at a different
object. That fetch MUST run after the committed prepare chain's opening
unshallow step and no later than the Dispatcher-materialized dispatch-base
fetch of the default branch, so every later prepare step and every graph node
observes the refreshed tags. It MAY be the dispatch-base fetch itself, for
example `git fetch --quiet --tags --force origin
+refs/heads/<default_branch>:refs/remotes/origin/<default_branch>`, provided
the remote-tracking ref that fetch exists to create is still written. Tag
auto-following on the unshallow fetch, or on any fetch of a branch refspec
alone, MUST NOT be relied on to satisfy this section: it brings in only tags
that point into newly fetched history and leaves tags already present, or a
tag set seeded from elsewhere, unrefreshed.

**What the clone holds after preparation.** After the run's prepare steps
complete, all of the following MUST hold in the sandbox clone:

- every tag the remote holds whose target is reachable from the fetched
  default branch is present locally and points at the same object as the
  remote's tag of that name;
- the newest release tag the clone reports, ordered by version, equals the
  newest release tag the remote holds at dispatch time; and
- `git describe --tags` on the fetched default branch's tip names the same tag
  it names in a fresh full clone of the remote.

The fetch MAY bring in every tag the remote holds, including tags that point
outside the fetched default-branch history.

**A failed refresh fails preparation.** When the tag refresh exits non-zero,
the prepare chain MUST fail, as a failure of the dispatch-base fetch does. It
MUST NOT continue on the tag set the clone already had, because a tag-reading
check would then grade the change under test against a stale tag set and
report its own staleness as the change's defect.

**Tag-reading checks are not made to tolerate stale tags.** A repository's
check that reads release tags MUST NOT be weakened to tolerate a clone whose
tags lag the remote; the remedy for a stale tag set is this section's
refresh. Measured 2026-11-02 on factory run 01M6E7FFPF99
(livespec-dev-tooling-t4rx4t): the sandbox clone of livespec-dev-tooling
carried release tags ending at v1.99.0 while the remote's default branch was
at v1.153.2, and the repository's versioning lockstep test failed in the
refresh merge's suite-green leg on that stale tag set. The Dispatcher's launch
overlay unshallowed the single-branch clone and fetched only the
default-branch refspec, so the clone's tag namespace was never refreshed.
Scenario 298 in `scenarios.md` exercises this section.
~~~~

### scenarios.md

Add a new scenario to `SPECIFICATION/scenarios.md`, after the highest-numbered scenario present at revise time. It is numbered 298 here because Scenario 297 is claimed by the in-flight revise v277 (PR 4193); revise MUST renumber it to the next free number if that has changed, and MUST update the "Scenario 298" cross-reference in the new contracts.md section to match:

~~~~markdown
## Scenario 298 — A factory sandbox clone carries the remote's release tags after its prepare steps

Governing clause: `contracts.md` §"Factory sandbox clone release tags".

```gherkin
Feature: A factory run reads the remote's release tags, not a stale tag set

  Scenario: A clone whose tags lag the remote is refreshed during preparation
    Given a governed repository whose remote holds release tags through v1.153.2 on its default branch
    And a sandbox clone of that repository whose local release tags stop at v1.99.0
    When the Dispatcher launches a run against that repository and the run's prepare steps complete
    Then the newest release tag the clone lists by version order is v1.153.2
    And every remote release tag whose target is reachable from the fetched default branch is present locally and points at the same object as on the remote
    And git describe --tags on the fetched default branch's tip names the same tag as in a fresh full clone of the remote

  Scenario: A local tag that disagrees with the remote is overwritten
    Given a sandbox clone holding a release tag whose name the remote holds pointing at a different commit
    When the run's prepare steps complete
    Then that tag in the clone points at the remote's commit

  Scenario: A tag-reading check in the run reads the refreshed tags
    Given a governed repository whose check suite includes a check that reads its release tags
    And a sandbox clone whose local release tags lag the remote's
    When that check runs in a factory run after the prepare steps
    Then it reads the remote's newest release tag and passes or fails on the change under test

  Scenario: A failed tag refresh fails preparation
    Given a run whose tag refresh fetch exits non-zero
    When the run's prepare steps execute
    Then the prepare chain fails
    And no later prepare step or graph node runs on the clone's previous tag set
```
~~~~

The outer `~~~~` fence delimits the text revise inserts; the inner `gherkin` fence is part of that text, as in every existing scenario.

### tests/heading-coverage.json (co-edit at revise)

Co-edit `tests/heading-coverage.json` at revise, in the same change that lands the two headings, per the repository's revise co-edit discipline. Revise MUST add one entry for each new H2:

- `{"heading": "## Factory sandbox clone release tags", "spec_root": "SPECIFICATION", "spec_file": "contracts.md", "test": "TODO", "reason": "An integration-tier test is owed for this heading: the owning work-item bd-ib-ia6zbf makes the Dispatcher's rendered prepare steps refresh the remote's tags, together with the test that binds this entry.", "work_item": "bd-ib-ia6zbf"}`
- `{"heading": "## Scenario 298 — A factory sandbox clone carries the remote's release tags after its prepare steps", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "reason": "An integration-tier test is owed for this heading: the owning work-item bd-ib-ia6zbf adds the prepare-step tag refresh and the test exercising a clone whose tags lag the remote.", "work_item": "bd-ib-ia6zbf"}`

The scenario entry's heading MUST match the number revise assigns. This proposal does not edit `tests/heading-coverage.json` itself, because the headings it would name do not exist in the ratified spec until revise lands them.

