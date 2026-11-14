---
topic: factory-canary-record-one-line
author: claude-opus-5-5
created_at: 2026-11-14T03:50:00Z
---

## Proposal: A factory canary's sanctioned deliverable is one line recorded in the committed canary marker file

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The repository keeps a committed canary marker file, `orchestrator-image/canary-marker.md`. A factory canary filed from the committed canary fixture by `just canary-dispatch <factory>` has exactly one deliverable: one line appended under that file's `## Recorded canary dispatches` heading, naming the canary's work-item, its factory and its run. The canary changes no other file. The behaviour is stated so that a canary fixture is a ratified deliverable. Its spec-change tier then reads `none`, and a canary of a factory engine, catalog image or sandbox driver can be launched again.

### Motivation

Work item bd-ib-rsqzew, the canary fixture filed 2026-11-03. It is now adopted by plan gmktec-factory-placement (epic livespec-dev-tooling-me5aqz) on legacy-coordinator-agent's ruling of 2026-11-14.

The fixture class has been the fleet's canary vehicle since 2026-10-16. The marker file records eight canaries on factories hp, hp-candidate, petri and candidate, the last on 2026-11-10. bd-ib-rsqzew's own text read tier `none` at spec v278 and v280. At v373, on 2026-11-14T03:35:35Z, the same text read tier `spec-change`, verdict `unstated`. The rationale: the marker file "is a deliverable artifact, not a behaviour any ratified clause states", and Scenario 131, which the fixture references, "says nothing about a marker file or a recorded line". The dispatch refused the item with exit 5 and created no run.

Every future `just canary-dispatch` fixture now fails the same way. Meanwhile two candidate canaries are waiting for a vehicle on the gmktec candidate factory (:32278): livespec-dev-tooling-nfnvvb's python-agent-v1.207.0 catalog image canary, and kubernetes-sandbox-backend's sandbox-driver v0.8.5 canary. legacy-dispatcher-agent's scan at 03:38Z found no ticketed item in any candidate-capable repository with a current tier-`none` record. A ratified fixture is the vehicle that does not depend on the queue happening to hold one.

Track metric: PRs per repository per hour merged to main and green. A canary gates every engine, catalog and driver roll, and a roll that waits for a vehicle delays every factory PR it would speed up.

In-flight alignment: default-align. No open spec pull request touches the canary marker or the canary fixture (surveyed 2026-11-14). §"Self-contained plugin dispatch" → "Canary coverage" defines a release canary's samples and coverage record, and this proposal does not change it.

When this ratifies, the fixture text, `orchestrator-image/canary-fixture.md`, gains the new scenario heading on its `References:` line beside Scenario 131, and bd-ib-rsqzew's Definition of Done is rewritten to match. That is an implementation follow-up, recorded on bd-ib-rsqzew.

### Proposed Changes

**1. Canary fixture (`contracts.md` §"Self-contained plugin dispatch", a new paragraph after the "Canary coverage" paragraphs):**

> **Canary fixture.** The repository MUST keep a committed canary marker file, `orchestrator-image/canary-marker.md`, carrying a `## Recorded canary dispatches` heading, and a committed canary fixture, `orchestrator-image/canary-fixture.md`. `just canary-dispatch <factory>` files the fixture's text as a work item targeting the named factory. Such a canary work item has exactly one deliverable: it appends one line under the marker file's `## Recorded canary dispatches` heading naming its work-item id, its factory and its run id. It MUST NOT change any other file. The marker file carries no product behaviour, and no code reads it. A canary that records its line is evidence that the Definition-of-Done gate admitted its brief and that its implement node ran on that factory (Scenario 131). A canary of a factory engine, a factory catalog image or a sandbox driver MAY use a canary fixture as its sample.

**2. New scenario (`scenarios.md`, appended at the next free Scenario number when revised):**

```gherkin
## Scenario NNN — A factory canary records one line in the committed canary marker file and changes nothing else

Feature: A canary fixture is a ratified, minimal factory deliverable
  As an operator canarying a factory engine, catalog image or sandbox driver
  I want a canary work item whose only deliverable is one recorded line
  So that the canary measures the factory, not a change

Scenario: A canary fixture records its dispatch
  Given a canary work item filed from orchestrator-image/canary-fixture.md by just canary-dispatch for a factory
  When its factory run completes its implement node and opens its pull request
  Then the pull request appends one line under "## Recorded canary dispatches" in orchestrator-image/canary-marker.md
  And the line names the canary's work-item id, its factory and its run id
  And the pull request changes no other file
```

**3. Heading coverage.** The revise pass that adds the scenario MUST add its `## Scenario NNN` heading to `tests/heading-coverage.json` in the same change.
