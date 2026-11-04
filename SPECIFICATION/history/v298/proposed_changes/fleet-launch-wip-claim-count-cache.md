---
topic: fleet-launch-wip-claim-count-cache
author: claude:gmktec-factory-placement
created_at: 2026-11-04T18:52:47Z
---

## Proposal: fleet-launch-wip-claim-count-cache

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State, as a MUST rule for the committed fleet-launch launchers, the shared per-repository WIP claim-count cache: the repository WIP gate's capacity-projection read is taken once per repository per cache time-to-live under a per-repository serialization and reused by every other launcher, a stale read is recomputed, the per-caller in-flight addition excludes the launcher's own marker, and the cached count equals the uncached one. Add harness coverage and Scenario 308.

### Motivation

Work item bd-ib-zwtfbq (requested by legacy-coordinator-agent, 2026-11-04; plan parent bd-ib-k7ymgx). On 2026-11-04 the waiting gmktec launchers ran tmp/petri-canary/wip-claimed-count.py once per launcher per poll: about 29 concurrent copies at 30-40% CPU each, on a VPS at CPU PSI 71-82. A shared cache in that gitignored scratch file (25 s TTL, flock, statuses cached and the in-flight addition recomputed per caller) cut the process count to 1-10 and PSI to about 62 (measured 00:47-00:49Z). The committed launcher that replaces the scratch scripts at the bd-ib-x7bwug cutover must carry the same cache, or the cutover silently brings back the 29-process load. The 15:44Z dispatch screen of bd-ib-zwtfbq refused its References line because no ratified heading states this launcher-side behaviour; v296 (bd-ib-3ufx6l) added the repository WIP gate this cache serves, so the rule now has a place to sit. The in-flight addition is stated because the interim launcher counts it and the v296 gate text does not: without it, launches already past the FIFO but not yet claimed are invisible to the gate.

### Proposed Changes

In SPECIFICATION/contracts.md §"Provisional fleet launch scripts", insert the following bullet into the list of committed-launcher gates immediately after the bullet that begins "**Breakage exception.**" and before the bullet that begins "**Early-exit re-ticket.**":

> - **Shared WIP claim-count cache.** The count the repository WIP gate holds on is the target repository's counted-claims count, read through the capacity projection, plus that repository's launches already past the FIFO, each marked by a live in-flight marker, whose work item is not yet at status `active`; a launcher MUST NOT count its own in-flight marker. The projection read MUST be shared across launchers through a per-repository claim-count cache file, in the directory a host value in `fleet-launch/config.sh` names, holding the projection's count, each counted work item's status, and the time the read was taken. A launcher MUST read that cache file before it spawns any process to compute the count. A cached read younger than the cache time-to-live, a host value assigned in `fleet-launch/config.sh` and overridable like any other, MUST be reused rather than recomputed. A cached read that is older than the time-to-live, absent or unparseable MUST be recomputed through the capacity projection, and that recomputation MUST be serialized per repository, so that when many launchers poll within one time-to-live window the projection read runs once and every other launcher reuses its result. The in-flight addition MUST be recomputed on every gate pass from the cached statuses, never cached. For the same ledger state and the same in-flight markers, the gate MUST report the same count with the cache as an uncached computation does; a time-to-live of 0 MUST disable the cache.

In the same section, insert the following paragraph immediately after the paragraph that begins "The `check-fleet-launch` harness cases MUST also cover each of the gates above":

> The `check-fleet-launch` harness cases MUST also cover the shared WIP claim-count cache: many launchers for one repository polling within one time-to-live window run the projection read once; a cached read older than the time-to-live is recomputed; a launcher's own in-flight marker is excluded from the count it takes; and the cached count equals the uncached count for the same ledger state and in-flight markers.

In SPECIFICATION/scenarios.md, append after Scenario 307:

## Scenario 308 — Fleet-launch launchers share one WIP claim-count read per repository per time-to-live

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: The committed fleet-launch launchers share the repository WIP claim-count read
  Background:
    Given fleet-launch/config.sh values overridden to a throwaway claim-count cache directory, a throwaway in-flight directory and a stub capacity projection that records each read

  Scenario: Launchers polling within one time-to-live run the projection read once
    Given five impl launchers for repository A at the WIP gate
    And no claim-count cache file for repository A
    When all five pass the WIP gate within one cache time-to-live
    Then the stub capacity projection records exactly one read for repository A
    And every launcher takes its count from that read

  Scenario: A stale cached read is recomputed
    Given a claim-count cache file for repository A older than the cache time-to-live
    When an impl launcher for repository A passes the WIP gate
    Then the stub capacity projection records a new read for repository A

  Scenario: A launcher does not count its own in-flight marker
    Given repository A's projection reports 2 counted claims
    And live in-flight markers for not-yet-active work items bd-x and bd-y in repository A
    When the impl launcher for bd-x passes the WIP gate
    Then the count it holds on is 3

  Scenario: The cached count equals the uncached count
    Given one ledger state and one set of in-flight markers for repository A
    When the WIP gate count is taken once with the cache and once with a cache time-to-live of 0
    Then both counts are equal
```

No existing sentence is changed or removed. The repository WIP gate bullet already requires the counted-claims count through the capacity projection; this bullet states how that read is shared, and adds the in-flight launches the interim launcher already counts, so the gate does not overshoot the cap between a launch and its claim.
