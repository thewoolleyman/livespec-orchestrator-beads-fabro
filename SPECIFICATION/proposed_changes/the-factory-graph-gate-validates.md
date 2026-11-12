---
topic: the-factory-graph-gate-validates
author: claude:fabro-currency session e3e56105
created_at: 2026-11-12T17:40:05Z
---

## Proposal: The factory-graph gate validates only with a client whose release triple is at or after 0.396.0 and reports the client version per graph

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Extend the "CI graph-gate binary" bullet of constraints.md §"Fabro runtime constraints" so the factory-graph gate (`check-fabro-graph-validity`) is bound to the rules of the engine the factory moves onto. The pinned upstream release's release triple MUST be at or after `0.396.0`, the first upstream release that refuses `run.prepare`; the factory's `0.393.0` carrier client is below that floor. Wherever the gate runs, in CI or on a developer host, it MUST read the resolved client's version before validating anything. A client reporting no parseable version, or one older than `0.396.0`, MUST fail the gate with a control finding naming the version and the floor (or, when none is parseable, saying so), and no graph is validated with it. Every graph the gate validates is reported together with the client version that validated it. A new scenario, numbered at revise, states these behaviours, including the regression they exist to catch: a committed graph whose exit node is unreachable fails the gate under a client at or above the floor.

### Motivation

Measured 2026-11-11 on the dispatching host vmi3006760 (work-item bd-ib-3lxeqf). `check-fabro-graph-validity` passed on master (rc 0) while the committed `groom-work-item` graph FAILED `fabro validate` under both Petri-era clients the factory uses (0.393.0-nightly.1 bbe6938 and 0.408.0-nightly.0): `attractor.exit_unreachable` plus five unreachable nodes. The gate validated with the binary its resolver returned, `/home/ubuntu/.fabro/bin/fabro` = 0.254.0 (8869e88) on that host, and CI pins upstream `v0.254.0` in `dev-tooling/install-ci-fabro.sh`. The 0.254 engine was retired from the factory on 2026-10-24, and its validator accepts the groom graph, so the gate guards an engine no factory runs.

The current bullet fixes only HOW the installer fetches the pinned release (architecture-matched static asset, published sha256, refusal by name on other architectures). It says nothing about WHICH engine family the pin or a developer host's client must belong to, and nothing about reporting which client validated a graph. So both the 0.254 pin and a silent fall-through to a legacy local client are conforming today. The launch pre-screen therefore held bd-ib-3lxeqf at spec-change tier (partial) under topic the-factory-graph-gate-validates, and the fleet coordinator (legacy-coordinator-agent, ~17:4xZ 2026-11-12) ruled it a genuine gap and ordered this proposal. It is time-bound: the one non-renewable Petri transition (same section) ends at 2026-11-14T00:00:00Z, and after that no 0.254 engine is admissible anywhere in the factory chain.

FLEET SCOPE (searched 2026-11-12 ~17:35Z at HEAD of every git clone under /data/projects): livespec-orchestrator-beads-fabro is the ONLY repository whose CI runs `dev-tooling/install-ci-fabro.sh` (`.github/workflows/ci.yml` installs it through `just install-ci-fabro`, then runs `just check-fabro-graph-validity`). homelab, livespec-console-beads-fabro and openbrain mention `check-fabro-graph-validity` only in a comment inside their committed implement-work-item workflow graph, and their CI neither installs nor runs it. livespec-dev-tooling's `homelab-worker/prove-ci-installer.sh` takes an installer path as an argument to prove it on a homelab worker; it is an operator proof tool, not a CI caller. No other clone references the installer or the gate.

A Red and an implementation for this behaviour are already preserved at `needs-human/f45193625cd243e5b39d7921ef8d295e` (0bf33fa60). It pins `v0.408.0-nightly.0` with per-architecture sha256 and asset ids, adds a client-version control with the 0.396.0 floor, and emits one `validated with fabro <version>` record per graph. The clause below is worded to match that implementation, so the seeded relaunch satisfies it as preserved.

### Proposed Changes

### 1. `SPECIFICATION/constraints.md` §"Fabro runtime constraints": replace the "CI graph-gate binary" bullet

Replace the bullet in full with:

```markdown
- **CI graph-gate binary.** CI's factory-graph gate is the
  `check-fabro-graph-validity` check, which validates the repository's
  committed Fabro workflow graphs during CI. It validates with the pinned
  upstream `fabro-sh/fabro` release, not with the factory's carrier build,
  and that binary is outside "the factory" as this section scopes it. The
  pinned release's release triple MUST be at or after `0.396.0`, the first
  upstream release that refuses `run.prepare`, so the gate judges graphs by
  the rules of the engine the factory moves onto. An earlier release,
  including `v0.254.0` and the factory's own `0.393.0` carrier client, MUST
  NOT be the gate's client, because its validator accepts graphs that
  engine rejects. The gate's installer MUST install the pinned release's static
  Linux asset whose architecture matches the CI runner's own (`x86_64` or
  `aarch64`). It MUST verify the downloaded asset against the sha256 that
  release publishes for that asset, pinned beside the version, before
  installing it. On any other runner architecture it MUST exit non-zero
  with a message naming that architecture and MUST NOT install a binary.
  Wherever the gate runs, in CI or on a developer host, it MUST read the
  version the resolved `fabro` client reports before it validates any
  graph. When that client reports no parseable version, or a version whose
  release triple is older than `0.396.0`, the gate MUST fail with a control
  finding naming the reported version and the `0.396.0` floor, or, when
  no version is parseable, saying so, and MUST NOT validate any graph with
  that client. It MUST NOT fall
  back to another client. For every graph it validates, the gate MUST
  report the graph's location together with the client version that
  validated it.
```

The bullet's first and installer sentences are unchanged. The added sentences fix the release-triple floor of the pin, the version control that applies on every host, and the per-graph version report.

### 2. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

The heading is numberless here; the revise pass assigns the next free scenario number and updates the references in changes 3 and 4 to match.

~~~markdown
## Scenario: the factory-graph gate validates only with a client whose release triple is at or after 0.396.0 and names the client version for each graph

```gherkin
Feature: The factory-graph gate validates with the engine the factory moves onto
  As a maintainer merging a change to a committed Fabro workflow graph
  I want the graph gate to judge it with a validator whose release triple is at or after 0.396.0
  So that a graph the factory's engine rejects cannot merge green

  Scenario: CI's pinned release is at or above the floor
    Given CI's factory-graph gate installer pins one upstream fabro release
    When the installer runs on a supported runner
    Then the installed binary reports a version whose release triple is at or after 0.396.0

  Scenario: A client below the floor fails the gate before any graph is validated
    Given the factory-graph gate resolves a fabro client that reports version 0.254.0 or 0.393.0-nightly.1
    When the gate runs in CI or on a developer host
    Then the gate fails with a control finding naming that version and the 0.396.0 floor
    And no graph is validated with that client

  Scenario: A client with no parseable version fails the gate
    Given the factory-graph gate resolves a fabro client whose --version output names no version
    When the gate runs
    Then the gate fails with a control finding saying the client reported no parseable version
    And no graph is validated with that client

  Scenario: Each validated graph is reported with its client version
    Given the factory-graph gate resolves a fabro client whose release triple is at or after 0.396.0
    When the gate validates the repository's committed workflow graphs
    Then it reports each validated graph's location together with that client's version

  Scenario: A graph the engine the factory moves onto rejects fails the gate
    Given a committed workflow graph whose exit node is unreachable
    When the factory-graph gate validates it with a fabro client whose release triple is at or after 0.396.0
    Then the gate fails naming that graph and attractor.exit_unreachable
```
~~~

### 3. `tests/heading-coverage.json`: add the new heading in the same revise

Add one entry to `tests/heading-coverage.json`, using the heading as numbered at revise:

```json
{"heading": "## Scenario: the factory-graph gate validates only with a client whose release triple is at or after 0.396.0 and names the client version for each graph", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "reason": "A real test at the integration tier or above is owed for this heading: the factory-graph gate's own suite (tests/dev-tooling/checks/test_fabro_graph_validity.py) gains cases in which a client reporting a release triple below 0.396.0 or no parseable version fails the gate with a control finding and validates no graph, and a client at or above the floor validates each committed graph and reports it with that version; the preserved implementation is at needs-human/f45193625cd243e5b39d7921ef8d295e. bd-ib-3lxeqf owns it.", "work_item": "bd-ib-3lxeqf"}
```

Add the matching row to `tests/heading-coverage-debt.json`. The register has no generator: the row is authored, and `check-heading-coverage-debt-register` admits it under its v067 spec-first admission, because this same change introduces the heading:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: the factory-graph gate validates only with a client whose release triple is at or after 0.396.0 and names the client version for each graph", "work_item": "bd-ib-3lxeqf", "first_seen": "<revise date>"}
```

The revise that ratifies this MUST co-edit both files, per AGENTS.md §"Revise co-edit discipline". No existing heading changes.

### 4. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-3lxeqf's Definition of Done `References:` line names the new scenario heading, as numbered at revise, beside `## Fabro runtime constraints` and `## Scenario 340 — ...`. Its tier is then re-classified (`dispatcher.py classify-tier`), and the Dispatcher relaunches it SEEDED from the preserved ref.

The host-captured regression proof needs a client at or above the floor on the host. On the dispatching host vmi3006760 the gate's resolver returns `~/.fabro/bin/fabro`, which is 0.254.0, and the gate runs inside `just check` (justfile:472). Until `LIVESPEC_FABRO_BIN` names a 0.408 client there (`~/.local/state/fabro-web-prod/v0408-d22808f8e/fabro` or `v0408-85071c828/fabro`), the gate fails on the version control, not on `attractor.exit_unreachable`. The capture MUST set it and record the client it used.
