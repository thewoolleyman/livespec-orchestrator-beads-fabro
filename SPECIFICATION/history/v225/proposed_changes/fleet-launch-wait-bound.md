---
topic: fleet-launch-wait-bound
author: claude-opus-5-5
created_at: 2026-10-26T14:32:57Z
---

## Proposal: The provisional launcher's slot-wait bound defaults to 24 hours and a give-up names its item and ticket

### Target specification files

- SPECIFICATION/contracts.md

### Summary

In §"Provisional fleet launch scripts", the launcher's bound on waiting for a factory slot defaults to 86400 seconds (24 hours) and stays an overridable host value, and a launcher that gives up waiting logs the work item and the queue ticket it held.

### Motivation

Work-item bd-ib-byxi53 (the launcher gives up after 6 h waiting for a slot and silently drops its queue ticket) asserts a 24 h default for FLEET_LAUNCH_MAX_WAIT_S and a give-up line naming the item and ticket. Its governing-heading screen split (R316) at 13:29Z on 2026-10-26: Codex found that neither assertion is governed, because the section requires host values to be overridable but states no default wait bound and no give-up logging. Measured 2026-10-26 on the gmktec queue: six launchers holding tickets gave up at the 21600 s default between 04:55Z and 05:40Z, each logging only "no slot within 21600s: give up", which names neither item nor ticket; they were found by hand about 2 h later and re-ticketed with a 86400 s bound. Slots on that factory are held by runs that can each take the 6 h whole-run wall budget, so a queue deeper than one wave routinely waits longer than 6 h. Coordinator gitops-fleet-capacity-monitoring routed this change spec-first.

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Provisional fleet launch scripts", append one sentence to the end of the second paragraph (the one ending "so the scripts can be exercised against stubs."):

```
The launcher's bound on how long it waits for a factory slot, `FLEET_LAUNCH_MAX_WAIT_S`, MUST default to 86400 seconds (24 hours) and remains an overridable host value like any other, and a launcher that gives up waiting at that bound MUST log the work-item id it was launching and the queue ticket it held.
```

No `## ` heading changes, so `tests/heading-coverage.json` is unchanged.
