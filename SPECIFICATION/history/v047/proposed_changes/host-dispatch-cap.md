---
topic: host-dispatch-cap
author: claude-fable-5
created_at: 2026-07-24T07:45:00Z
---

## Proposal: `dispatcher.host_dispatch_cap` — the host-level dispatch concurrency cap (default 2)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- SPECIFICATION/spec.md
- tests/heading-coverage.json

### Summary

Add a new committed dispatcher setting, `dispatcher.host_dispatch_cap`
(positive integer, default **2**, no per-item override), that caps the
number of factory dispatches concurrently in flight on the shared host.
The Dispatcher refuses the dispatch that would exceed the cap BEFORE the
admission valve mutates the Ledger or any sandbox work starts, with a
refusal that names the guard, the cap, the observed count, and a remedy
the blocked party can perform. A parked (`human_input_required`) run
never counts toward the cap; a crashed dispatch's capacity claim
self-heals. This is the specified DEMOTION of the interim binary
admission mutex (`bd-ib-sd8o` deliverable (c)) into a counting cap —
the durable successor that retires one-at-a-time dispatch.

### Motivation

The interim admission mutex (landed as `bd-ib-uwshxy`, PR #902)
mechanically enforces one dispatch at a time host-wide. Its premise —
a contended host resource under concurrent dispatch — was DISPROVEN by
the `bd-ib-tyxzhv` diagnosis (2026-07-24): the "bwrap namespace denial"
is a host sysctl constant unrelated to concurrency, the "`--network
host`" doctrine is false at the running engine's own commit (`allow_all`
maps to the Docker bridge default, so sandboxes already have per-run
network namespaces), and two real concurrent runs succeeded with
verified overlap at the engine, sandbox, AND live-ACP-agent layers.
The maintainer's directive (2026-07-24, relayed via the track
supervisor's brief-027): parallel throughput is the priority; demote
the mutex from binary to a config-keyed counting cap, default 2 (the
live-verified level), with raising further being config-only. The
binary mutex is an implementation-level interim guard that never had
spec coverage; its counting successor introduces a committed
consumer-visible `dispatcher.*` key and durable refusal semantics, so
it belongs in the spec (settings are spec-governed per §"Dispatcher
policy settings" and the §"API-configurable completeness" discipline).
Evidence record: `bd-ib-tyxzhv` (closed 2026-07-24, notes carry the
full matrix); design record: `bd-ib-sd8o` notes.

### Proposed Changes

**(a) `contracts.md` — new H3 after §"Per-repo WIP cap".**

INSERT, after the ENTIRE §"Per-repo WIP cap" subsection (whatever
paragraphs it then contains) and before "### Post-merge acceptance
(`acceptance → done`)", a new H3 section (against the current tree the
subsection is the single paragraph ending "...the `active` state at
once."):

```
### Host-level dispatch concurrency cap (`host_dispatch_cap`)

The Dispatcher additionally enforces a **host-level** concurrency
ceiling on factory dispatches: `dispatcher.host_dispatch_cap` (positive
integer, default **2**), a sibling `.livespec.jsonc` key of `wip_cap`.
Where `wip_cap` bounds this repo's `active` work-items at the Ledger
level, `host_dispatch_cap` bounds the number of factory dispatches
concurrently IN FLIGHT on the shared host — across every repo
dispatching to that host's Fabro server. Each repo's Dispatcher
enforces its own committed cap against the host-wide in-flight count;
the two caps are independent and both must hold. Each repo's committed
cap is that repo's SELF-limit against the shared host-wide count, not
a mutually-enforced global: the host is bounded at 2 only while every
dispatching repo commits (or defaults to) 2.

The guard runs BEFORE the admission valve mutates the Ledger and before
any sandbox work starts. The in-flight count is measured by two
INDEPENDENT host-global gauges, each capped separately — admission is
refused when either has reached the cap (never by summing them):
(i) live capacity claims — one held per admitted dispatch from guard
time (so a dispatch counts before its run is externally observable)
until that dispatch reaches a terminal or parked outcome; and (ii)
Fabro runs observed
host-wide in a non-terminal, non-parked state — the leg that counts a
run no claim accounts for, such as a hand-launched run. When admitting
would drive the in-flight count past the cap, the Dispatcher MUST
refuse the dispatch, and the refusal MUST name the guard, the cap
value, the observed in-flight count, and a remedy the blocked party
can perform (wait for an in-flight run to reach terminal state, or
raise the committed cap — raising the cap MUST be config-only, never a
code change; that clause is a design constraint on implementations,
not a runtime behavior, so it carries no scenario). A PARKED
(`human_input_required`) run MUST NOT count toward the in-flight total
— gauge (ii) excludes it by status, and it holds no live claim once
its dispatcher has surfaced the parked outcome — parked runs never
block work. A capacity claim left behind by a
crashed dispatch process MUST self-heal: a claim whose recorded holder
pid no longer maps to a live process MUST be reclaimed at the next
attempt rather than counted, never stranding host capacity behind a
provably-stale artifact. (A recycled pid that maps to a live unrelated
process is not provably stale by this test; that bounded residual is
tracked as its own hardening item, `bd-ib-j4clfi`, and tightens beyond
this floor when it lands.)

The default of **2** is the empirically verified safe level: 2x
concurrent dispatch was proven collision-free at the engine, sandbox,
and live-agent layers on 2026-07-24 (evidence `bd-ib-tyxzhv`; design
record `bd-ib-sd8o`). This cap is the demotion of the interim binary
admission mutex (`bd-ib-sd8o` deliverable (c)): the counting successor
keeps the proven claim/release/crash-reclaim semantics while retiring
one-at-a-time dispatch.
```

**(a2) `contracts.md` §"Per-repo WIP cap" — retire the falsified
"later knob" sentence (adversarial-review finding #1).**

REPLACE (verbatim, within the section's single paragraph):

```
Total fleet concurrency is the
sum of the per-repo caps; a separate fleet ceiling is a later knob if
ever wanted.
```

WITH:

```
Total LEDGER-level fleet concurrency is the
sum of the per-repo caps; the host-level ceiling on concurrently
in-flight dispatches is the separate `host_dispatch_cap` (§"Host-level
dispatch concurrency cap (`host_dispatch_cap`)").
```

Without this, the new H3 directly contradicts the sentence above it
(the "later knob" has landed). NOTE for the reviser of the PENDING
`wip-cap-zero-dispatch-off.md` proposal: that proposal's edit (a)
REPLACES this same paragraph using the pre-edit text as its verbatim
anchor; once this change lands, that anchor no longer matches and the
reviser must re-derive it against the amended paragraph (the two edits
compose — theirs appends a value-domain paragraph, ours rewrites one
sentence).

**(a3) `contracts.md` §"Dispatcher policy settings" intro — the
design-record enumeration gains the second ceiling (adversarial-review
finding #3).**

REPLACE (verbatim — the intro paragraph's final clause):

```
records the maintainer's ruling that every setting is per-item overridable
EXCEPT `wip_cap`.
```

WITH:

```
records the maintainer's ruling that every setting is per-item overridable
EXCEPT `wip_cap`. The later `host_dispatch_cap` (2026-07-24, §"Host-level
dispatch concurrency cap (`host_dispatch_cap`)") joins `wip_cap` under that
ruling's rationale: a concurrency ceiling is not a per-item property.
```

**(b) `contracts.md` §"`wip_cap` — the one setting with no per-item
override" — the cap pair now shares that property.**

REPLACE (verbatim — the H3 heading and the section's first two
sentences):

```
### `wip_cap` — the one setting with no per-item override

`dispatcher.wip_cap` (existing, default `5`, §"Per-repo WIP cap") is likewise
an API-settable setting, surfaced under the console Settings surface. It is
the ONE setting with **no per-item override**: it is a per-repo concurrency
ceiling, so a per-item value is structurally meaningless.
```

WITH:

```
### `wip_cap` and `host_dispatch_cap` — the settings with no per-item override

`dispatcher.wip_cap` (existing, default `5`, §"Per-repo WIP cap") is likewise
an API-settable setting, surfaced under the console Settings surface, and so
is `dispatcher.host_dispatch_cap` (default `2`, §"Host-level dispatch
concurrency cap (`host_dispatch_cap`)"). These are the TWO settings with
**no per-item override**: each is a concurrency ceiling (per-repo /
host-level), so a per-item value is structurally meaningless.
```

The rest of the section (the "Its value semantics are unchanged."
sentence and the design-record citation) is untouched; the cited
ruling's rationale ("a concurrency ceiling is not a per-item property")
is exactly what `host_dispatch_cap` inherits.

**(c) `scenarios.md` — new Gherkin scenario (behavior ⇒ scenario
discipline).**

ADD a new `## Scenario 49` after Scenario 48, modeled on Scenario 48's
multi-scenario house style. (Cross-proposal interactions, for the
reviser of the PENDING `wip-cap-zero-dispatch-off.md`: (i) both
proposals anticipate "49" as the next free scenario number; whichever
ratifies second takes 50 — the rule in both is "the next free scenario
number", and the heading-coverage `heading` string must move in
lockstep with any renumbering. (ii) This proposal's edit (b) RENAMES
the H3 that wip-cap-zero's edit (d) cites by its old name
(§"`wip_cap` — the one setting with no per-item override"); after this
change lands, that citation must be read against the renamed
§"`wip_cap` and `host_dispatch_cap` — the settings with no per-item
override". (iii) If wip-cap-zero ratifies FIRST, its value-domain
paragraph joins the §"Per-repo WIP cap" subsection — edit (a)'s insert
still goes after the ENTIRE subsection, before §"Post-merge
acceptance".)

````
## Scenario 49 — The host dispatch cap admits up to the cap and refuses the next with a performable remedy

```gherkin
Feature: A host-level dispatch concurrency cap governs how many factory
  dispatches may run concurrently on the shared host

  Scenario: The dispatch that would exceed the cap is refused before any work
    Given a committed `dispatcher.host_dispatch_cap` of 2
    And two of this host's factory dispatches already in flight
    When a third dispatch is attempted
    Then it is refused BEFORE the admission valve mutates the Ledger
    And no Fabro sandbox run is launched for it
    And the refusal names the guard, the cap value, the observed in-flight
      count, and a remedy the blocked party can perform
    And the refused items stay `ready`

  Scenario: A dispatch below the cap is admitted alongside a live run
    Given a committed `dispatcher.host_dispatch_cap` of 2
    And one of this host's factory dispatches already in flight
    When a second dispatch is attempted
    Then the host-capacity guard does not refuse it
    And both dispatches proceed concurrently

  Scenario: A parked run never counts toward the cap
    Given a committed `dispatcher.host_dispatch_cap` of 2
    And one PARKED (human_input_required) Fabro run
    And one of this host's factory dispatches in flight
    When a second dispatch is attempted
    Then the parked run does not count toward the in-flight total
    And the host-capacity guard does not refuse the dispatch

  Scenario: A crashed dispatch's capacity claim self-heals
    Given a capacity claim left behind by a dispatch process that died
      without releasing it
    And no live process bears the claim's recorded pid
    When the next dispatch is attempted
    Then the dead holder's claim is reclaimed rather than counted
    And the dispatch proceeds
```
````

**(c2) `spec.md` §"Dispatcher policy settings" — the sole-exception
enumeration gains the second ceiling (adversarial-review finding #2).**

REPLACE (verbatim):

```
Each setting is a GLOBAL
DEFAULT for the repo, and (except for the per-repo `wip_cap` concurrency
ceiling) each is OVERRIDABLE PER WORK-ITEM by a ledger label:
```

WITH:

```
Each setting is a GLOBAL
DEFAULT for the repo, and (except for the two concurrency ceilings — the
per-repo `wip_cap` and the host-level `host_dispatch_cap`) each is
OVERRIDABLE PER WORK-ITEM by a ledger label:
```

**(d) `tests/heading-coverage.json` co-edit (REQUIRED by the new H2).**
The new `## Scenario 49` is a new H2 heading, so the same revise payload
MUST add a matching entry (`test` MAY be the literal `"TODO"` with a
non-empty `reason`) to `tests/heading-coverage.json`, per the revise
co-edit discipline. The (b) edit changes only an H3 and (a) adds only an
H3, so no other heading-coverage change is needed.

**(e) Deliberately NOT touched.** The `contracts.md` §"Dispatcher
policy settings" intro paragraph's general "a per-item ledger label
overrides the global default" framing already tolerates `wip_cap`'s
exception via the dedicated H3 this proposal amends (the (a3) edit
touches only the design-record clause); no broader intro rewrite. The
`contracts.md` `--parallel` passage ("MUST NOT raise the per-repo WIP
cap") stays true — `host_dispatch_cap` is an additional independent
bound, and that passage never claimed `wip_cap` was the sole one. The
tail of the (b) section ("Its value semantics are unchanged." + the
`wip_cap`-specific design-record citation) stays true of `wip_cap`
itself. The interim mutex's
implementation mechanics (lock-file naming, slot layout) stay OUT of the
spec — the spec commits the behavior (cap, refusal contents, parked
exemption, crash self-heal), not the artifact format. The impl-side
`api-configurable-keys.json` manifest entry for the new key rides the
implementation change under §"API-configurable completeness", not this
proposal.
