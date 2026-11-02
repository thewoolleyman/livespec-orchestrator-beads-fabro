---
topic: fabro-fork-rust-gates-and
author: claude-opus-5-5:dev-host-test-gate-load
created_at: 2026-11-02T19:10:14Z
---

## Proposal: Fork gate and build venue

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add a 'Fork gate and build venue' bullet to constraints.md §'Fabro runtime constraints' (after 'Rebuild and re-pin'): fork Rust gates on carrier branches and the pinned carrier build run on the fleet's ARC k3s runner capacity, a dev-host build is a throttled, recorded fallback only; plus Scenario 300.

### Motivation

Plan dev-host-test-gate-load (livespec-dev-tooling epic 6vuiwe) owns dev-host (VPS) load; fork Rust builds are its largest remaining gate load. Today the fork's rust.yml runs only for main, so every carrier-branch gate and every carrier build runs on the shared dev host (orchestrator .ai/fabro-fork-hand-build.md, 'The merge gate is local'), throttled only by the coordinator's nice-19 ruling of 2026-11-02. Implementation item bd-ib-dqxcsh is held at the spec-change tier (unstated under this heading, linked topic fabro-fork-rust-gates-and). Routed by legacy-coordinator-agent under R301 (~19:0xZ, 2026-11-02).

### Proposed Changes

In SPECIFICATION/constraints.md §'Fabro runtime constraints', insert after the '**Rebuild and re-pin.**' bullet:

- **Fork gate and build venue.** A push to, or a pull request against, a
  carrier branch of the fork (any branch a pinned factory build is cut
  from) MUST run the fork's Rust format, clippy and test gates on the
  fleet's self-hosted ARC k3s runner capacity, so the pull request's
  status rollup carries their verdicts; a carrier-branch pull request
  with no such checks MUST NOT be read as green. The release binary a
  factory build pins MUST be built on that capacity, by a GitHub
  workflow or a k3s Job, from a named carrier ref, and published with a
  `BUILD_INFO` naming the source ref and commit; producing it MUST NOT
  require a build on the dev host. A fork gate or build on the dev host
  is permitted only as an explicit fallback while the cluster venue is
  unavailable, at `nice -n 19` with `CARGO_BUILD_JOBS=4`, and the work
  item that used it MUST record the fallback. The hand-build guidance
  (`.ai/fabro-fork-hand-build.md`) names the cluster venue, under the
  runbook-lockstep rule below.

In SPECIFICATION/scenarios.md, append:

## Scenario 300 — Fabro-fork gates and carrier builds run on the cluster, not the dev host

Governing clause: `constraints.md` §"Fabro runtime constraints".

```gherkin
Feature: fork Rust gates and pinned carrier builds run on ARC k3s runner capacity
  Scenario: a fork pull request against a carrier branch carries cluster-run gate verdicts
    Given a pull request in thewoolleyman/fabro targeting a carrier branch a pinned factory build is cut from
    When its checks run
    Then the format, clippy and test gates run on an ARC k3s runner pod
    And the pull request's status rollup carries their verdicts
    And no cargo or rustc process for that pull request runs on the dev host

  Scenario: a pinned carrier build is produced off the dev host
    Given a named carrier ref
    When the carrier build runs
    Then the release binary is built on the ARC k3s runner capacity or in a k3s Job
    And it is published with a BUILD_INFO naming the source ref and commit

  Scenario: a dev-host fallback is throttled and recorded
    Given the cluster venue is unavailable
    When a fork gate runs on the dev host
    Then it runs at nice 19 with CARGO_BUILD_JOBS=4
    And the work item that used it records the fallback
```

