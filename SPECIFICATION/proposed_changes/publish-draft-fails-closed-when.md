---
topic: publish-draft-fails-closed-when
author: claude-opus-5-5
created_at: 2026-11-13T12:27:59Z
---

## Proposal: publish_draft adopts a pull request the forge created behind a failed create call, and only at the pushed head

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text covers a refused pull-request creation only when an earlier dispatch's pull request is already MERGED (Scenario 256). It says nothing about a creation command that fails while the forge did create the pull request, so `publish_draft` fails closed and a janitor-green run is lost. This proposal adds one paragraph to contracts.md §"Self-contained plugin dispatch", directly after the landed-publication paragraph. After a non-zero creation exit, `publish_draft` re-reads the forge by head branch, at most three times at 1, 2 and 4 seconds, and adopts an open pull request only when its head is exactly the pushed head. Otherwise it fails closed with LIVESPEC_PUBLISH_DRAFT_CREATE_FAILED naming the re-read count. It decides from exit statuses and re-read results, never from output text, and every other scripted pull-request-creating step follows the same rule. One scenario exercises it.

### Motivation

Filed as bd-ib-hzul2n on legacy-coordinator-agent's order (2026-11-10 about 20:00Z), measured by sandbox-commit-gate-ceiling, under plan publish-draft-green-work-loss (epic bd-ib-acrr56). Its FRESH dispatch on 2026-11-13 was refused at the dispatch stage as spec-change tier, verdict unstated, generalization target "## Scenario 256 — A publication that already landed is finished at publish_draft, not a failure", linked proposal topic publish-draft-fails-closed-when, spec v367. The judgement's rationale: "Scenario 256 only covers a refused pull-request creation where an earlier dispatch's pull request is already MERGED. The visible text does not state adopting an open pull request at the exact pushed head after a 5xx, the bounded re-reads at increasing intervals, the LIVESPEC_PUBLISH_DRAFT_CREATE_FAILED re-read count, or the fleet-wide adopt-on-re-read rule." A search of SPECIFICATION/*.md on origin/master confirms it: no clause mentions 5xx, adoption of an open pull request, or LIVESPEC_PUBLISH_DRAFT_CREATE_FAILED. Design choices, settled here rather than left open: (a) Adoption requires the exact pushed head, so a stale or foreign pull request on a reused branch name is never taken as this run's publication. (b) A pull request seen at another head counts as not found, rather than ending the re-reads, because the forge can lag a just-pushed head. (c) The pre-create reuse of an already-open pull request is deliberately left unchanged, for the same lag reason. (d) The limits are fixed at three re-reads and 1, 2 and 4 seconds, matching the old draft #4869 (6931627e1), whose diff the fresh run takes as reference. (e) The decision never parses output text, following the bd-ib-3d2c5y lesson. Placement: publish_draft is this orchestrator's workflow realization, so the paragraph belongs in this repository's contracts.md. Fleet scope, coordinator rule K: every factory-target repository, and every scripted step that creates a pull request and then reads the forge for it. In-flight survey: no open spec PR or pending proposal states this.

### Proposed Changes

Two edits, both in this repository's spec target.

1. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch": insert the following paragraph immediately after the paragraph that begins "**A publication that already landed is finished at publish_draft.**".

**A pull request the forge created behind a failed create call is adopted, never re-created or lost.** When `publish_draft`'s pull-request creation command exits non-zero, and the preceding paragraph's landed-publication check, which a refusal for a branch with no commits beyond the default branch takes first, has not finished the publication, `publish_draft` MUST NOT fail on that exit alone. It MUST re-read the forge for the open pull requests whose head branch is the run's publish branch, reading each one's number and current head commit. It MUST make at most three re-reads, waiting 1, 2 and 4 seconds before the first, second and third. When a re-read finds an open pull request whose head commit is exactly the head this visit pushed, `publish_draft` MUST stop re-reading, MUST adopt that pull request as the run's publication, recording its number exactly as it records a pull request it created, and MUST end exactly as a successful creation ends. `publish_draft` MUST NOT adopt an open pull request on the publish branch whose head commit is any other commit. A re-read that finds only such pull requests counts as finding none. When a re-read itself fails, `publish_draft` MUST fail closed at once with `LIVESPEC_PUBLISH_DRAFT_CREATE_FAILED`, naming which re-read of the three failed. When three re-reads complete without finding the pushed head, `publish_draft` MUST fail closed with `LIVESPEC_PUBLISH_DRAFT_CREATE_FAILED`, stating that it made three re-reads and found no open pull request at the pushed head, and naming, when a re-read saw one, an open pull request on the publish branch at a different head and that head. The decision to re-read, to adopt and to fail MUST be taken from the creation command's exit status and the re-reads' own results, never from text in the creation command's output such as an HTTP status code. This paragraph does not change how `publish_draft` treats an open pull request it finds before it creates one, nor any other stage. Every other scripted command step of the implement-work-item workflow that creates a pull request and then reads the forge for it MUST follow the same adopt-on-re-read rule. Measured 2026-11-10 on bd-ib-hmed6n run 01M72YPACEEH: `publish_draft@1`'s `gh pr create` received "HTTP 502 Bad Gateway" from the forge's GraphQL endpoint. The forge nevertheless created draft pull request #4847 at 16:08:47Z, on head 631949c13 with green CI. `publish_draft` failed closed with "no pull request is open for the publish branch and gh pr create failed"; `refresh_repair` found no brief, and a janitor-green run (96 of 96) ended at `needs_human`. Scenario <number assigned at revise> in `scenarios.md` exercises this paragraph.

2. `SPECIFICATION/scenarios.md`: append the following scenario after the last numbered scenario. The revise assigns its number and writes that number into both the heading and the closing sentence of the paragraph above.

## Scenario <number assigned at revise> — publish_draft adopts a pull request the forge created behind a failed create call, and only at the pushed head

```gherkin
Feature: publish_draft does not lose a publication the forge made behind a failed create call
  Scenario: A pull request created behind a server error is adopted
    Given a publish_draft that pushed head H to the run's publish branch
    And the pull-request creation command exits non-zero reporting an HTTP 5xx
    And the forge holds an open pull request P on the publish branch at head H
    When publish_draft handles the failed creation
    Then publish_draft adopts P as the run's publication and records its number
    And the run ends publish_draft exactly as a successful creation ends it

  Scenario: No pull request at the pushed head fails closed after the bounded re-reads
    Given a publish_draft that pushed head H to the run's publish branch
    And the pull-request creation command exits non-zero reporting an HTTP 5xx
    And no re-read finds an open pull request on the publish branch at head H
    When publish_draft handles the failed creation
    Then publish_draft re-reads the forge three times, waiting 1, 2 and 4 seconds before them
    And it fails closed with LIVESPEC_PUBLISH_DRAFT_CREATE_FAILED stating that it made three re-reads

  Scenario: A pull request at another head is never adopted
    Given a publish_draft that pushed head H to the run's publish branch
    And the pull-request creation command exits non-zero
    And the forge holds an open pull request on the publish branch at a head other than H
    When publish_draft handles the failed creation
    Then publish_draft does not adopt that pull request
    And it fails closed with LIVESPEC_PUBLISH_DRAFT_CREATE_FAILED naming that pull request and its head

  Scenario: The decision ignores status digits in the command's output
    Given a pull-request creation command that exits zero while its output contains the text 502
    When publish_draft handles the creation
    Then publish_draft treats the creation as successful and makes no re-read
```

No existing H2 heading is renamed or removed. The revise that accepts this proposal MUST add, in the same change, one `tests/heading-coverage.json` row for the new scenario heading with `"test": "TODO"`, `"work_item": "bd-ib-hzul2n"` and a `reason` that names the owed test's tier as "integration tier or above". It MUST then REGENERATE the debt register with `uv run python -m livespec_dev_tooling.heading_coverage_debt`, and never author its entry by hand.
