---
topic: provisional-fleet-launch-scripts
author: claude-opus-5-5
created_at: 2026-10-24T21:40:37Z
---

## Proposal: Provisional fleet launch scripts and their check

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Ratify the provisional fleet-launch/ directory as a caller-side launch loop: what it may and may not do, where its host values live, the check-fleet-launch obligation that keeps a broken launcher from reaching master, and the condition under which it is retired.

### Motivation

Plan provisional-fleet-launch (epic bd-ib-klkbxp) committed the factory seats' launch scripts under a top-level fleet-launch/ directory (PR #3595), at the maintainer's direction that they be committed as provisional and experimental under the repository's full standards. Its child bd-ib-nz4av6 adds a check-fleet-launch target with shellcheck and a hermetic harness, but its Definition of Done cannot pass the launch-time judgement: no ratified heading states the check obligation, and the host-concurrency rule that keeps these gates caller-side is an H3 the judgement will not cite. Two launcher defects reached production on 2026-10-24 (the retired-board stall and a statement swallowed by a trailing comment, which bash -n passed), which is why the obligation is a behavioural harness and not only a syntax check.

### Proposed Changes

Append a new section to SPECIFICATION/contracts.md:

## Provisional fleet launch scripts

The top-level `fleet-launch/` directory is a PROVISIONAL and EXPERIMENTAL caller-side launch loop: it decides only WHEN a caller invokes `drive --action impl:<item>`, as §"Dispatcher admission, WIP cap, and post-merge acceptance" permits a caller to do ("A caller MAY add gates of its own for conditions the Dispatcher does not own"). Its shared fleet cap, per-factory FIFO tickets and mutex, hold file, board and in-flight readers are caller-side gates; per §"Host concurrency belongs to the Fabro scheduler" the Dispatcher MUST NOT read, enforce or depend on any of them, and `fleet-launch/` MUST NOT re-implement, pre-empt or stand in for any admission condition the Dispatcher owns.

Every script under `fleet-launch/` MUST open with a banner marking it PROVISIONAL and EXPERIMENTAL that names the livespec console application and the committed launch-loop tool (work-item bd-ib-jr6w7v) as its first-class replacement. Every host-specific value a `fleet-launch/` script reads MUST be assigned in `fleet-launch/config.sh` or in one constants block at the head of a Python script, and each such value MUST be overridable from the environment, so the scripts can be exercised against stubs.

`just check` MUST run a `check-fleet-launch` target, declared in the justfile's `check:` targets array, that runs shellcheck over every shell script under `fleet-launch/` and runs a hermetic harness. The harness MUST exercise the launcher against stub factory boards and throwaway queue, lock, in-flight and state directories, and its cases MUST cover at least: reading a factory board; refusing a launch when the shared fleet cap is reached; launching two queued tickets in FIFO order; holding a launch while the hold file exists; and counting a retired factory's board as zero rather than as unknown. A change to a `fleet-launch/` launcher that breaks any of those cases MUST make `just check` exit non-zero. A syntax check alone MUST NOT be treated as satisfying this obligation.

The directory MUST be deleted once every factory launch on the operator host is made by the livespec console application or by the committed launch-loop tool, and no seat runs a `fleet-launch/` script.

Append to SPECIFICATION/scenarios.md:

## Scenario 242 — The provisional fleet launch check fails the build on a broken launcher

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: a broken provisional launcher cannot reach master
  Scenario: the harness exercises every launch gate against stubs
    Given fleet-launch/config.sh values overridden to stub factory boards and throwaway directories
    When just check runs check-fleet-launch
    Then shellcheck runs over every shell script under fleet-launch/
    And the harness reads a stub board, refuses a launch at the shared fleet cap, launches two queued tickets in FIFO order, holds a launch while the hold file exists, and counts a retired factory's board as zero

  Scenario: a defect in a launcher turns the check red
    Given a change that makes the launcher count a retired factory's board as unknown
    When just check runs check-fleet-launch
    Then check-fleet-launch exits non-zero
    And just check exits non-zero
```

The revise that accepts this MUST add `tests/heading-coverage.json` entries for both new H2 headings (a `test` of `"TODO"` with a reason naming bd-ib-nz4av6 is acceptable until that item binds them).
