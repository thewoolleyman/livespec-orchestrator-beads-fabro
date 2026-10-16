---
topic: idle-slot-audit
author: claude-opus-5-5-plan-bd-ib-opbzv3
created_at: 2026-10-16T19:25:39Z
---

## Proposal: A priority-epic idle-slot audit classifies every priority child across tenants against the factory board and surfaces dispatchable work beside an empty factory queue

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a read-only idle-slot audit to this plugin. Given a committed set of priority epics, which may live in several ledger tenants, and one configured factory, the audit lists every non-closed child of each epic. It puts each child into exactly one class against that factory's own run board, and it reports a finding when dispatchable priority work exists while the factory's own queue holds no waiting run, meaning nothing is waiting on the factory's queue, so a dispatch would be promoted immediately or, at worst, queue first in FIFO — the queueing §"Host concurrency belongs to the Fabro scheduler" sanctions. The audit is exposed as a read-only `dispatcher.py idle-slot-audit` subcommand and composes as a `hygiene:idle-slot:<factory>` needs-attention fact. It reads no concurrency ceiling and derives no available capacity, so §"Host concurrency belongs to the Fabro scheduler" holds unamended. The shipped `hygiene:idle-factory:<repo>` fact is unchanged.

### Motivation

Measured 2026-10-16 by the factory stability-freeze driver (session gitops-fleet-capacity-monitoring, epic livespec-dev-tooling-dfixhe). Nine hp slots sat idle for about five hours while four priority-set items were dispatchable. Three successive driver sessions repeated a handoff's claim that nothing could use the slots instead of measuring the queue. The driver hand-wrote a read-only measurement script, journaled at livespec-dev-tooling plan/gitops-fleet-capacity-monitoring/research/002-idle-slot-audit-2026-10-16.md. Its first run, at 15:56Z, reported 9 idle slots, 3 dispatchable children and 1 stale edge. The maintainer's instruction is to delegate that capability to this plugin rather than keep it in a driver's scratchpad, and the implementing work-item is bd-ib-irh4js, a child of plan epic bd-ib-opbzv3 (factory-idle-with-ready-work). The existing idle-factory fact cannot carry this: its clause scopes capacity to this repository's own accounting and eligibility to this repository's own ready set, so it sees neither a priority epic whose children live in another tenant nor the factory-wide board. The script has two measured false positives, and this clause settles both. First, bd-ib-35kfra was reported DISPATCHABLE NOW while a driver ruling held it, because the hold existed only in comment prose. This clause settles it by ruling that only ledger status or the shared admission-eligibility verdict can hold a child, so such a child stays DISPATCHABLE-NOW until its hold is recorded as a status. An `admission:manual` label does not hold an item that is already `ready`, because admission policy gates only the `pending-approval` to `ready` transition. Second, bd-ib-pe2dxk was reported STALE EDGE while its only open blocker, bd-ib-myvlbl, was `active` with a live implement run (01M52T69QT9Z, which later succeeded after 117 minutes). The script treated any `active` blocker as landed, so this clause treats a blocker with a live board run as unlanded. Design note on capacity (independent Fable review, round 1): the driver's script computed free slots from a hard-coded server ceiling of 10. §"Host concurrency belongs to the Fabro scheduler" forbids deriving available capacity from the scheduler's max_concurrent_runs on any surface. Rather than carve an exception to that ratified prohibition, the finding keys on the factory's own queue. Zero waiting (runnable) runs means the factory is not saturated by queued work; the audit cannot tell a free slot from an exactly-full scheduler without the ceiling it is forbidden to read, and does not claim to. Either way the ratified response is to submit, so the finding is correct in both cases. That condition held throughout the measured five-hour incident.

### Proposed Changes

1. In SPECIFICATION/contracts.md, section "Orchestrator-owned attention facts", immediately after the paragraph that ends "that the pre-dispatch acceptance wall would refuse." (the acceptance-filter paragraph following the idle-factory fact), insert the following new paragraphs:

**Priority-epic idle-slot audit (`hygiene:idle-slot:<factory>`).** The audit is configured by a committed-only `dispatcher.idle_slot_audit` object. That object is NOT declared API-configurable and is therefore committed-only under "The declared-API-configurable class". It carries `factory`, which names one entry of `dispatcher.factories`, and `priority`, a non-empty array whose entries each name `repo`, a path to a local checkout of a tenant's repository resolved relative to this repository's root, and EITHER `epic`, a work-item id in that tenant, OR `items`, a non-empty array of work-item ids in that tenant. The `items` form exists for a priority epic whose children live in a different tenant from the epic. The object carries NO concurrency or slot value: the audit reads no ceiling and derives no available capacity, per §"Host concurrency belongs to the Fabro scheduler". When the object is absent, the audit MUST report that it is not configured, and no idle-slot fact composes. When the object is present but malformed, the audit MUST refuse with a configuration finding naming the offending key, and no idle-slot fact composes.

The audit MUST read each named tenant's ledger through that tenant's own checkout and committed configuration, and it MUST read the configured factory's run board through a side-effect-free run listing of that factory, and MAY read the factory-native availability evidence the shared admission-eligibility verdict already reads, from every declared factory, without issuing any probe or confirmation turn. It MUST NOT write to any ledger, dispatch journal, or factory, MUST NOT execute credential probes or availability confirmation turns, and MUST NOT read comment prose. For an `epic` entry, the children are every non-closed record linked to the epic by a `parent-child` or `tracks` dependency edge or by the dotted-id hierarchy at any depth. These are the two child-linkage arms of the plan child-enumeration union; that union's third arm, records that block the epic, is excluded. For an `items` entry, the children are the named non-closed records, and an id absent from its tenant MUST be reported as missing and MUST NOT be omitted. A board row is LIVE when its status is non-terminal (`blocked`, `paused`, `runnable`, `running`, or `starting`), and QUEUED when its status is `runnable`. A `submitted` or `pending` row is neither live nor queued: the Dispatcher starts every run it submits and creates no approval-gated child run, so such a row is not its dispatch. A live row is ATTRIBUTED to the work-item whose id the Dispatcher stamps into the run's goal. The audit MUST report the counts of live rows and queued rows on the factory, attributed to the Fabro server's own board. It MUST NOT present either count as an Orchestrator bound or as available capacity.

A `blocks` dependency is OPEN when its blocker is not `closed`; a blocker absent from its tenant is open and MUST be shown as unresolved. Each child MUST receive exactly one class, assigned by the first rule below that matches:
- `RUNNING` when a live row is attributed to the child.
- `POST-RUN` when its status is `active` or beads-native `in_progress`.
- `NEEDS-CAPTURE-OR-ACCEPT` when its status is `acceptance`.
- `NEEDS-APPROVAL` when its status is `pending-approval`.
- `UNADMITTED` when its status is `backlog` or beads-native `open`.
- `PARKED` when its status is `blocked` or beads-native `deferred`.
- For a child whose status is `ready`:
  - `HOST-ONLY` when the shared factory-safety routing predicate routes it to the host.
  - `BLOCKED` when it has an open `blocks` dependency whose blocker is unresolved, is neither `active` nor `acceptance`, or is `active` with an attributed live row.
  - `STALE-EDGE` when it has open `blocks` dependencies and every one of them is on a blocker that is `acceptance`, or that is `active` with no attributed live row.
  - `HELD` when the shared admission-eligibility verdict for its tenant, evaluated with capacity excepted (the drain's own non-capacity eligibility that the idle-factory fact also consumes), does not admit it. The audit MUST show the verdict's reason beside the child where the verdict exposes one, and otherwise the eligibility stage that refused it (the acceptance wall or readiness). A tenant's recorded provider-exhaustion wait or admission-required ACP chain wait holds every ready child of that tenant, with the wait named as the reason.
  - `DISPATCHABLE-NOW` otherwise.
- `UNCLASSIFIED-STATUS`, naming the status verbatim, for any other non-closed status. It never contributes to the finding line.

The audit MUST show each child's open `blocks` blockers with their statuses, and MUST NOT read any other dependency type as a blocker. An operator hold MUST be expressed through ledger status or the admission verdict, because the audit reads no other hold. A tenant whose ledger cannot be read MUST be reported as unreadable and MUST NOT be omitted. A board that cannot be read MUST be reported as unobservable, its live and queued counts MUST be reported as unknown and MUST NOT be computed as zero, and no idle-slot finding composes. The audit's output MUST end with a finding line when the board is observable, its queued count is zero, and at least one child is `DISPATCHABLE-NOW` or `STALE-EDGE`. That line MUST name the factory, its live-row count attributed to the Fabro server, and those child ids in configuration order. An empty queue is evidence that nothing waits, not that a slot is free; the finding asserts only the former. A run rests briefly at `runnable` after every start even when the scheduler has room, so the finding MAY clear for one scheduler tick after a dispatch.

The audit is invoked as `dispatcher.py idle-slot-audit --repo <path> [--json]`, a read-only subcommand that prints the per-epic classification and the finding line, or emits them as JSON under `--json`. When the finding line would print, the needs-attention snapshot MUST carry exactly one `hygiene:idle-slot:<factory>` fact at `high` urgency. Its `summary` MUST be a deterministic one-line statement naming the factory, the count classified `DISPATCHABLE-NOW` and, separately, the count classified `STALE-EDGE`, and the first such id. Its single `handoff` MUST be an inspection handoff that runs the audit subcommand. It MUST NOT advertise `impl:<id>`, because the first child may live in another tenant. The fact rides the existing `hygiene` kind and introduces NO new wire kind, grammar form, or field. Identical ledgers, board, configuration, and evaluation time MUST produce a byte-identical row. The fact clears the instant the finding line would not print. This fact and the `hygiene:idle-factory:<repo>` fact are independent: neither suppresses, replaces, or re-derives the other.

2. In SPECIFICATION/scenarios.md, append a new heading after the highest-numbered scenario on master at filing time (Scenario 185). Scenario 186 is reserved by the pending proposal exhaustion-record-per-credential-identity, so this one is numbered 187 unless that number is also reserved by then, in which case it takes the next free number:

## Scenario 187 — A priority-epic idle-slot audit surfaces dispatchable priority work while the factory queue is empty, and a blocker with a live run is not a stale edge

```gherkin
Feature: The idle-slot audit measures the priority queue against the factory board
  As a factory driver whose slots sat idle for hours while priority work was dispatchable
  I want every priority-epic child classified against the live board across tenants
  So that idle capacity beside dispatchable work is surfaced instead of assumed away

Scenario: An empty factory queue beside a dispatchable priority child produces the finding and the attention fact
  Given a committed dispatcher.idle_slot_audit naming a factory and a priority epic in another tenant's checkout
  And the factory board shows 1 live row and no runnable row
  And one child of that epic is ready with no open blocks dependency and is admitted by its tenant's admission-eligibility verdict with capacity excepted
  When the idle-slot audit runs
  Then that child is classified DISPATCHABLE-NOW
  And the output ends with a finding line naming the factory, 1 live row attributed to the Fabro server, and that child's id
  And the needs-attention snapshot carries exactly one hygiene:idle-slot fact whose handoff runs the idle-slot audit
  And no ledger, dispatch journal, or factory was written

Scenario: A ready child whose only blocker is active with a live run is BLOCKED, not STALE-EDGE
  Given a ready priority child whose only open blocks dependency is on an active item
  And a live board row is attributed to that active blocker
  When the idle-slot audit runs
  Then the child is classified BLOCKED
  And when instead no live row is attributed to that active blocker the child is classified STALE-EDGE

Scenario: A hold the admission verdict refuses is HELD, and prose cannot hold a ready child
  Given a ready priority child with no open blocks dependency that its tenant's admission-eligibility verdict does not admit
  When the idle-slot audit runs
  Then the child is classified HELD with the verdict's reason beside it
  And a ready child whose only hold is written in a comment is classified DISPATCHABLE-NOW

Scenario: A queued run or an unobservable board yields no finding
  Given a configured audit with a DISPATCHABLE-NOW priority child
  When the factory board shows one runnable row
  Then no finding line is printed and no hygiene:idle-slot fact composes
  And when instead the board cannot be read it is reported unobservable with unknown live and queued counts, and no finding line is printed
```

3. tests/heading-coverage.json MUST gain an entry for the new Scenario 187 heading with `"test": "TODO"`, `"work_item": "bd-ib-irh4js"`, and a non-empty reason stating that the audit and its attention fact are not yet implemented.
