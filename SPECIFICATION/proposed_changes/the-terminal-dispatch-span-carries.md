---
topic: the-terminal-dispatch-span-carries
author: claude-opus-5-5
created_at: 2026-11-14T00:21:08Z
---

## Proposal: The terminal dispatch span names the repository the dispatch ran for

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The livespec.dispatch.terminal span carries livespec.repository, naming the repository the dispatch ran for. It is the same value the dispatch's fabro run already carries as the run label livespec.repository. The receiver allowlist admits the key. When the repository cannot be established the span omits the key and names it in livespec.dispatch.unavailable_fields. Together with the run class, execution target and sandbox CPU-seconds the terminal span is gaining, this lets a Honeycomb query attribute factory CPU by repository.

### Motivation

Work item bd-ib-yq7ugj (plan factory-run-yield, epic bd-ib-ft26pi, assertion 3: report lever 7, factory CPU attribution by repository). The throughput track's one metric is per repository (PRs per repository per hour merged to main and green), so the CPU levers have to be ranked per repository. Measured on master 86e1b558a: `livespec.repository` is written only as a fabro run label (`_dispatcher_run_labels.REPOSITORY_LABEL_KEY`). The terminal-span paragraph of §"Bounded session waits and observable inventory" names no repository key, and `_otel_scrub.ATTRIBUTE_ALLOWLIST` does not admit it. The correlation triple's work.item.id prefix names the TENANT, which differs from the repository for a cross-tenant item, so it is not a substitute. bd-ib-faprof (proposal dispatch-terminal-span-scheduler-inputs, v299) adds run class, execution target and sandbox cost to the same span. Under ruling R301 that span is extended and never paralleled. This proposal extends it the same way. In-flight alignment: default-align. No open spec pull request touches the terminal-span paragraph (surveyed 2026-11-14). Effect on the track metric: none directly. It is the measurement that ranks the per-repository CPU levers.

### Proposed Changes

**1. Repository on the terminal span (`contracts.md` §"Bounded session waits and observable inventory").** In the terminal-span paragraph, after the sentence "Its parent MUST be the dispatch span, and it MUST carry the correlation triple.", insert:

> It MUST also carry `livespec.repository`, naming the repository the dispatch ran for, with the same value the Dispatcher passes to that dispatch's `fabro run` as the run label `livespec.repository`. When the Dispatcher cannot establish that value, the span MUST omit the key and name it in `livespec.dispatch.unavailable_fields`. The receiver allowlist MUST admit `livespec.repository`.

**2. New scenario (`scenarios.md`, appended at the next free Scenario number when revised):**

```gherkin
## Scenario NNN — The terminal dispatch span names the repository the dispatch ran for

Feature: Factory cost is attributable by repository
  As an operator ranking factory CPU levers per repository
  I want every terminal dispatch span to name its repository
  So that a Honeycomb query attributes factory CPU by repository

Scenario: A terminated dispatch's terminal span carries its repository
  Given a dispatch whose fabro run carries the run label livespec.repository
  When the dispatch reaches a terminal state
  Then its livespec.dispatch.terminal span carries livespec.repository with the same value
  And the attribute reaches dataset livespec-dispatcher through the receiver allowlist

Scenario: An unknown repository is named as unavailable, never fabricated
  Given a dispatch whose repository the Dispatcher cannot establish
  When the dispatch reaches a terminal state
  Then its terminal span omits livespec.repository
  And livespec.dispatch.unavailable_fields names livespec.repository
```

**3. Heading coverage.** The revise pass that adds the scenario MUST add its `## Scenario NNN` heading to `tests/heading-coverage.json` in the same change.
