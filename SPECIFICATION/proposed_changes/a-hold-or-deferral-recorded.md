---
topic: a-hold-or-deferral-recorded
author: claude-opus-5-5
created_at: 2026-11-07T16:44:50Z
---

## Proposal: A hold recorded only in the dispatch journal reaches needs-attention, and a recovery-held item is never reported idle

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Register a closed list of journal-recorded hold and deferral stages as attention facts under a new hygiene:journal-hold:<subject> fact, state when a hold is current and how it retires, let a launcher participate by journaling a launcher-hold record, and exclude a recovery-held item from the idle-factory fact and idle-slot audit.

### Motivation

legacy-coordinator-agent ordered this on 2026-11-07 as the condition on its revise ruling for bd-ib-so6fef, widened by its fleet-scope order: every hold or defer stage that reaches no needs-attention lane must reach the dispatcher's pass and the coordinator's tick, because holds that live only in a journal are how stalls go silent.

Read-only survey of the Dispatcher's commands package on 2026-11-07 (a static read; nothing was run), checked against the code for the stages named here: recovery-held is written only to the host journal and reaches the drain report as status capacity-deferred; no _needs_attention module reads these stages; a held orphan run appears in no output at all, while keeping its factory slot; and the idle lanes read holds only from ledger status and the admission verdict, so a recovery-held item can be reported as idle with an impl:<id> handoff.

This uses the spec's own mechanism. "Wait completeness" is deliberately closed and says a contract leaving work parked must register its attention derivation, so the stages are enumerated rather than claimed universally.

Launcher holds stay inside "The ownership boundary": the snapshot may read this repository's own journal and may not read a launcher's files, so a launcher participates by journaling. Writing that record is the launcher owner's change, not this clause's implementer's.

Not added: claim refusals and whole-run pre-dispatch refusals, which already exit non-zero with stderr when they happen. Work item: bd-ib-5xogp4, plan factory-run-work-preservation (epic bd-ib-nckst7).

### Proposed Changes

1. contracts.md, §"Orchestrator-owned attention facts" → "Wait completeness": add to the closed enumeration "each hold or deferral named under 'Journal-recorded holds' below".

2. Same section, before "Parked-acceptance arity and distinguishability", add this paragraph:

   > **Journal-recorded holds (`hygiene:journal-hold:<subject>`).** Each hold or deferral stage this paragraph names records its state in this repository's dispatch journal, and the snapshot MUST compose it. The stages are closed: `recovery-held`, `publish-branch-reclaim-held`, `run-wall-budget-held`, `stall-cancel-release-held`, `provider-limit-release-held`, `stranded-claim-hold`, `orphan-run-reconcile-held`, `sandbox-container-held`, `rework-capacity-deferred`, `incident-proof-pointer-refused`, `acp-availability-observed-refused`, `admission-held` carrying the reason `unresolvable-assignee`, and `launcher-hold`. The `<subject>` is the work-item id the record names, otherwise its run id, otherwise its container name. For each subject whose hold is current, the snapshot MUST carry exactly one fact naming the subject, the stage and every reason the record carries, and its handoff MUST inspect the recorded stage in the dispatch journal. It MUST NOT advertise a valve the hold does not have. A hold is current when its record is the newest record of a named stage for that subject, it was appended within the last seven days, no later record of that subject in the same journal is a route, release, launch or terminal record, and, where the subject is a work-item, that item is not closed. A stage whose hold ends without any later record therefore retires at seven days, and it MUST NOT be reported as resolved. The facts MUST be composed from one reading of the journal per snapshot, and a journal that cannot be read MUST be reported as unobservable rather than as carrying no holds. The derivation reads only this repository's own journal, so a hold journaled on another host is out of its scope. A launcher that holds a queued launch outside the Dispatcher participates by appending one `launcher-hold` record to the dispatch journal of the repository it holds, naming the hold and the held work-item when one is known; the snapshot MUST NOT read a launcher's hold files, tickets or output ("The ownership boundary" below). An item whose current hold is `recovery-held` MUST NOT count as admission-eligible for the idle-factory fact or as dispatchable in the idle-slot audit, because routing does not offer that item to the admission valve. `publish-branch-reclaim-held` is not such a hold: it refuses no dispatch. Scenario 324 in `scenarios.md` exercises this paragraph.

3. Same section, the idle-factory qualifier: `admission-eligible` MUST exclude an item whose current hold is `recovery-held`.

4. scenarios.md: add `## Scenario 324 — A hold recorded only in the dispatch journal reaches needs-attention` with nine Gherkin cases: one fact naming every reason; a run subject; retirement on a later route record; seven-day retirement that does not read as resolved; a closed item; an unreadable journal; a launcher hold composed from the journal and never from its files; a recovery-held item not reported idle; a reclaim-held item still counted. The number MUST be re-checked at revise. The same pass MUST add `tests/heading-coverage.json` and `tests/heading-coverage-debt.json` entries owned by bd-ib-5xogp4.
