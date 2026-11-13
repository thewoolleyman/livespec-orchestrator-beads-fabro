---
topic: the-retained-payload-root-variable
author: claude-opus-5-5:address-honeycomb-alerts
created_at: 2026-11-13T02:28:19Z
---

## Proposal: Define LIVESPEC_RETAINED_PAYLOAD_ROOT and what it means for a process to name a holder, and make the unremovable-holder log a MUST

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The v363 paragraph on launcher payload holders spares and sweeps holders according to whether 'a running process names [it] in LIVESPEC_RETAINED_PAYLOAD_ROOT', but the specification never says that LIVESPEC_RETAINED_PAYLOAD_ROOT is an environment variable, who sets it, or what naming means, so the spare-and-sweep rule has no checkable meaning. Its logging requirement for an unremovable holder also carries no BCP14 keyword. This proposal adds one defining sentence and makes the log a MUST; the behaviour Scenario 363 already exercises is unchanged.

### Motivation

The post-step LLM doctor phase of the v363 revise (a-launcher-ended-by-a, work item bd-ib-immkx7), run on 2026-11-13 at legacy-coordinator-agent's direction, surfaced two findings on the new paragraph. (1) Undefined term: LIVESPEC_RETAINED_PAYLOAD_ROOT occurs in the specification only in this paragraph and in Scenario 363. The implementation defines it as PAYLOAD_ROOT_ENV in .claude-plugin/scripts/bin/_payload.py: the variable a launcher exports so the child processes of one dispatch (drive, the dispatcher.py it starts, and the helpers that starts) reuse the same payload tree instead of copying it again. The sweep can only test 'a running process names it' by reading running processes' environments, so the specification must say that is what naming is. (2) Weak BCP14: 'a holder that cannot be removed is logged' states load-bearing behaviour without a keyword, while Scenario 363 asserts the log.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch", in the paragraph "A launcher removes the private payload holder it made, and the next launcher reclaims what a killed one left" (ratified at v363), make two edits and change nothing else.

1. Directly after the paragraph's first sentence (the one ending "MUST remove that holder before it exits."), insert:

   > `LIVESPEC_RETAINED_PAYLOAD_ROOT` is the environment variable a launcher exports to the processes it starts so that every process of one dispatch reads the same payload holder instead of copying the payload again; a running process *names* a holder when its environment carries `LIVESPEC_RETAINED_PAYLOAD_ROOT` set to that holder's path.

2. Replace "This removal is best-effort: a holder that cannot be removed is logged, and it MUST NOT turn a dispatch into a refusal or a failure." with:

   > This removal is best-effort: a holder that cannot be removed MUST be logged, and its failed removal MUST NOT turn a dispatch into a refusal or a failure.

Every other sentence of the paragraph, including its use of "names in `LIVESPEC_RETAINED_PAYLOAD_ROOT`", stays as ratified; the new sentence gives that phrase its meaning. `scenarios.md` Scenario 363 already asserts both behaviours ("And no other running process names that holder in LIVESPEC_RETAINED_PAYLOAD_ROOT"; "Then the failed removal is logged") and needs no change. No H2 heading is added, renamed or removed, so `tests/heading-coverage.json` needs no co-edit.
