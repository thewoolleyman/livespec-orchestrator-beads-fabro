---
topic: a-spec-change-tier-hold
author: claude-opus-5-5
created_at: 2026-11-12T18:05:00Z
---

## Proposal: A held item's derived proposal topic is unique, so one item never inherits another's ratification

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The autonomy-tier bullet says a held item's linked topic "is first recorded as the stem the Dispatcher derives for the item". Nothing makes that stem unique, or keeps it off a topic that already names a proposed change or a revision record. Today the stem comes from the first five words of the title, so two items whose titles begin alike share one topic. The later item then reads the earlier item's ratification as its own and waits for a re-judgement that cannot release it. This proposal requires the derived stem to be unique across the tenant's recorded topics and the governed spec tree, extended deterministically when the title-derived stem collides.

### Motivation

Work item bd-ib-flvxx3, adopted into plan bd-ib-ax3rds on legacy-coordinator-agent's routing (session 959b2f8b, 2026-11-12), ranked above zyu2ug and 7itf42. It is held at spec-change tier for this linked stem: verdict unstated, generalization target Scenario 206. The topic is the item's linked stem, so the hold links without a relink.

Measured on 2026-11-09 on livespec-dev-tooling:
- livespec-dev-tooling-khlrw3 ("A CI job that fails at \"Initialize containers\" …") was recorded at filing with linked topic `a-ci-job-that-fails`.
- That topic was ratified at v124 for livespec-dev-tooling-cetyrq ("A CI job that fails at Set up job on a codeload 429 …"), a different behaviour.
- The hold therefore read `awaiting-rejudgement`. A re-judge still said spec-change, but the recorded topic was kept, so the hold never cleared.

legacy-dispatcher-agent has measured the same topic-name reuse on jkwzwv and akljpy; the details are on the item. The cause is `proposal_topic_for` (`commands/_spec_change_tier.py`), which uses only the first `_TOPIC_WORD_CAP = 5` title words.

Design choices, stated for the grade:
- **Unique against both sources.** The stem must not equal another item's recorded linked topic, because two holds would then share one ratification. It must not name an existing proposal or revision record either, because the hold would read a decision about different behaviour.
- **Deterministic extension.** A collided stem is extended by a suffix derived from the item's own id, so re-deriving for the same item yields the same topic and a retried filing records no second one.
- **Existing collisions keep the relink route.** An item already carrying a colliding topic is repaired through `relink-spec-tier`. This proposal changes derivation, not records already written.

In-flight alignment, all `align`: #5058 reads the hold this topic feeds and does not derive it; #5068 adds fields to the tier record without changing the topic. Fleet scope: every repository that runs the spec-change-tier classifier inherits this, because the derivation lives in the plugin.

### Proposed Changes

**1. A unique derived stem (`contracts.md` §"Grooming and slice-size calibration", the "An autonomy tier is assigned" bullet).** After the sentence "The linked topic is first recorded as the stem the Dispatcher derives for the item.", add:

> That derived stem MUST be unique when it is first recorded. It MUST differ from the linked topic recorded on every other work item of the tenant. It MUST NOT name a proposed change under `<spec-root>/proposed_changes/`, or a revision record under `<spec-root>/history/vNNN/proposed_changes/`, that exists when the stem is derived. When the title-derived stem collides with any of these, the Dispatcher MUST extend it with a suffix derived deterministically from the item's id, so deriving again for the same item yields the same topic. A topic already recorded on an item is never re-derived; a recorded topic that collides is repaired only through the `relink-spec-tier` route.

**2. Scenario (`scenarios.md`).** Append the scenario below, numbered at revise time.

## Scenario <number assigned at revise> — A held item's derived proposal topic is unique against other items and the spec tree

```gherkin
Feature: one held item never inherits another's ratification through a shared topic
  Scenario: two items whose titles begin alike get different topics
    Given two held feature items whose titles share their first five words
    When each is filed
    Then their recorded linked proposed-change topics differ

  Scenario: a stem that already names a proposal or revision is extended
    Given a held item whose title-derived stem already names a proposed change or a revision record under the governed spec tree
    When the item is filed
    Then its recorded linked topic names neither
    And deriving the topic again for the same item yields the same topic
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-flvxx3"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. The row and entry MUST carry the heading as numbered at revise.
