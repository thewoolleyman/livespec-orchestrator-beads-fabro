---
topic: definition-and-proof-of-done-repair
author: claude-fable-5-1
created_at: 2026-10-04T05:28:46Z
---

## Proposal: Plan-level Definition of Done and Proof of Done, and a third archive leg

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A plan epic carries a Definition of Done recording the maintainer's stated done criterion, every plan assertion is mapped to carriers at the scoping event, and a plan MUST NOT archive without a verified plan-level Proof of Done record.

### Motivation

Plan definition-and-proof-of-done (epic bd-ib-7sjdzv) was reopened on 2026-10-04 by maintainer ruling. plan/definition-and-proof-of-done/research/004-reopen-failure-analysis-and-repair-scope-2026-10-04.md records the measured evidence: of the five factory runs that have entered the proof stages, two merged with captured and verified records, two died at the proof-to-fix handoff, and one is held; finding F1 and F8: done is defined per work item while the maintainer's intent arrives per plan. The herdr plan (overseer-uzvcbn) recorded the maintainer's done criterion only in a research note; this plan itself was archived on closed children plus a coverage review with nothing exercised. The archive gate certifies coverage, not function.

### Proposed Changes

In contracts.md §"Planning Lane realization", add a subsection `### Plan Definition of Done and Proof of Done` after §"The `plan/<slug>/` plan store":

**The plan Definition of Done.** A plan epic's `description` MUST carry, as its first heading, a Definition of Done section parsed by the ONE primitive of §"Effective acceptance criteria" ("The Definition of Done section"). Its assertions MUST state the outcome the maintainer asked for, and the `plan` front-end MUST record the maintainer's own statement of done VERBATIM in the plan's initial research note beside the assertions derived from it. For an epic the `References:` line is OPTIONAL, because a plan MAY precede the specification it will ratify; when present it is validated exactly as for a work item. A plan assertion's proof mode is `host_captured` unless it appears under `### Human-attested`; `factory_captured` MUST NOT be declared on an epic, since no factory run executes against one, and MUST be reported as a Definition-of-Done finding.

**When the section is authored.** The `plan` front-end MUST author the section at plan creation. An attended creation MUST confirm the assertions with the maintainer; an unattended creation MUST record them as session-derived in the first handoff entry. A plan epic lacking the section (one created before this clause was ratified) MUST be reported by every plan resume as `plan-definition-of-done: missing`, and the resuming session MUST author it before recording any further scoping event. There is NO exemption list: a plan MUST NOT archive without the section, whenever its epic was created.

**The carrier map.** Every scoping event MUST name, for each plan assertion, either the child work-item assertions that carry it or the literal `plan-level proof`. A plan assertion with neither is a scoping finding, and `record_scope_event` MUST refuse a scoping event that leaves one unmapped. A child whose Definition of Done silently narrows a plan assertion it is named as carrying (for example, replacing an observed behaviour with the existence of tests) does NOT discharge it; the plan-level proof is what discharges a plan assertion.

**The plan Proof of Done record.** A plan-level proof MUST be published as an append-only comment on the plan epic whose first line is `Plan Proof of Done — <captured|verified|not_reproduced|human_attested> — <session or human identity> — <UTC timestamp>`. Its body MUST contain, per plan assertion in Definition of Done order: the assertion text, its proof mode, the numbered reproduction steps (credentials by environment-variable name only), the proof (a fenced code block for each text capture and a proof-asset reference per §"Proof of Done record" for each image, named `<epic-id>__<session-identity>__<capture|verify>__<NN>__<slug>.<ext>`), and the BUILD IDENTITY exercised — the release tag and the installed build identifier of every artifact the steps ran. Where a release applies to the plan's work, a `captured` record taken against an unreleased tree MUST NOT be accepted; the steps MUST run against the released artifact installed through its normal installation path. A `verified` record MUST be published by a party with no role in the plan's implementation, replaying the captured steps verbatim; a record whose verifying identity equals its capturing identity is not evidence.

In §"Archive on completion", replace `Archive requires BOTH legs.` with `Archive requires ALL THREE legs.` and add after the completeness leg: Third, the proof leg: the plan epic MUST carry a Definition of Done section, and the latest plan Proof of Done record on the epic MUST be `verified`, MUST cover every plan assertion that is not `human_attested`, and MUST postdate the last scoping event; each `human_attested` plan assertion MUST have a `human_attested` record. `archive_thread` MUST refuse while the proof leg is unmet, naming each unproved assertion, and the independent completeness reviewer MAY be the verifying party. The transfer exception is unchanged in form but narrowed in effect: remaining WORK may be transferred to named carriers, but a plan assertion MUST NOT be transferred out of the plan to obtain an archive — an unproved plan assertion keeps the plan live.

The `plan_close_evidence` conformance check (§"Plan-record conformance checks") MUST additionally report a closed epic whose timeline carries no `verified` plan Proof of Done record.

In scenarios.md add `## Scenario 135 — A plan cannot archive until its own Definition of Done is proved against the released build`:

```gherkin
Feature: A plan is done when its stated outcome was observed, not when its children closed

  Scenario: Plan creation records the maintainer's statement and derives assertions
    Given a maintainer describes a new plan and states what done means
    When the plan front-end creates the plan
    Then the epic description's first heading is a Definition of Done section
    And the initial research note carries the maintainer's statement verbatim

  Scenario: A scoping event that leaves a plan assertion unmapped is refused
    Given a plan epic with two Definition of Done assertions
    When a scoping event names carriers for only one of them
    Then the scoping event is refused naming the unmapped assertion

  Scenario: Closed children and a coverage review do not archive an unproved plan
    Given a plan whose children are all closed and whose timeline carries valid completeness-review evidence
    And the epic carries no verified plan Proof of Done record
    When the plan operation attempts the archive
    Then the archive is refused naming each unproved plan assertion
    And the plan directory and the epic are unchanged

  Scenario: A record captured against an unreleased tree is not evidence
    Given a plan whose work ships through a release
    And a captured plan Proof of Done record whose build identity names an unreleased tree
    When the archive gate evaluates the proof leg
    Then the record is rejected naming the missing release identity

  Scenario: A self-verified record is not evidence
    Given a verified plan Proof of Done record published by the identity that captured it
    When the archive gate evaluates the proof leg
    Then the record is rejected as not independent

  Scenario: A legacy plan gains the section when next resumed
    Given a plan epic created before this clause with no Definition of Done section
    When the plan is resumed
    Then the resume reports plan-definition-of-done missing
    And no further scoping event is recorded until the section exists
```

The revise pass MUST co-edit tests/heading-coverage.json and tests/heading-coverage-debt.json for the new Scenario 135 heading as an owned TODO naming the implementing child.

## Proposal: A third proof mode, host_captured, for proof that needs the released build or a host surface

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The per-assertion proof-mode enumeration gains `host_captured`: an agent session captures the proof on an operator host in the same record format, an independent party replays it, and the item rests in acceptance until the verified host record exists.

### Motivation

Plan definition-and-proof-of-done (epic bd-ib-7sjdzv) was reopened on 2026-10-04 by maintainer ruling. plan/definition-and-proof-of-done/research/004-reopen-failure-analysis-and-repair-scope-2026-10-04.md records the measured evidence: of the five factory runs that have entered the proof stages, two merged with captured and verified records, two died at the proof-to-fix handoff, and one is held; finding F5: the closed enumeration `factory_captured | human_attested` has no honest value for a proof an agent can perform but only against the released, normally installed build on a host. The herdr plan's real acceptance (run the released overseer in a live herdr session) was written as prose, 'coordinator owns that final acceptance', outside the proof system.

### Proposed Changes

In contracts.md §"Effective acceptance criteria" → "Per-assertion proof mode", change the closed enumeration to `factory_captured` | `host_captured` | `human_attested` and add:

`host_captured` means the assertion's proof requires the released, normally installed artifact or a surface of an operator host that no sandbox image can carry, and that an agent session can nonetheless exercise without a human. An assertion's mode is `host_captured` when it appears under a `### Host-captured` sub-heading inside the Definition of Done section. That sub-heading MUST carry, before its first bullet, a line `Reason: <text>` naming the host surface or the released-build requirement; a `### Host-captured` sub-heading with no non-empty `Reason:` line MUST be reported as a Definition-of-Done finding by the host-side wall exactly as for `### Human-attested`. An implementer MUST NOT change an assertion's mode.

In "The deliverable policy", add: an assertion the sandbox could exercise through a declared sandbox capability (§"Definition-of-Done and Proof-of-Done stages" → "Sandbox capabilities") MUST NOT be declared `host_captured`, and an assertion an agent session could exercise on a host MUST NOT be declared `human_attested`; the gate MUST refuse either declaration naming the assertion and the capability or host surface that makes the stronger mode available. The modes are ordered `factory_captured`, then `host_captured`, then `human_attested`, and an assertion MUST carry the first mode in that order that can prove it.

In "Derived routing, never stored", add: when any gradeable assertion is `host_captured`, the item MUST rest in `acceptance` after merge until a `host_verified` record exists for it, under EVERY effective `acceptance_policy`; an `ai-only` policy is NOT refused for such an item, because the host leg is agent-performable, and the item closes under `ai-only` once the `host_verified` record exists and the factory leg passed.

In §"Proof of Done record", extend the first-line grammar to `<captured|verified|not_reproduced|host_captured|host_verified|host_not_reproduced|human_attested>` and add: **The host leg.** For an item with `host_captured` assertions, an agent session on an operator host MUST publish a `host_captured` record on the item's pull request after the change is merged and, where a release applies, released and installed through its normal installation path; the record MUST name the build identity exercised (release tag and installed build identifier) and otherwise follows the record structure. A DIFFERENT session identity MUST replay those steps verbatim and publish `host_verified` or `host_not_reproduced`. A `captured` or `verified` record on such an item MUST list the host-captured assertions under a heading stating they are pending the host leg. The implementation MUST provide one posting primitive that renders these records so that no session hand-formats one. The pointer ("The pointer") MUST additionally carry the comment link of the latest `host_verified` record once it exists.

In §"Post-merge acceptance (`acceptance → done`)", add: **The host-captured leg.** The acceptance pass MUST judge a `host_captured` assertion passing only from a `host_verified` record that lists it as reproduced and names a build identity containing the merged change; `host_not_reproduced` is a FAIL for that assertion and is rework input; with no host record the assertion is PENDING, the pass lists it as pending the host leg, and the item rests in `acceptance` without consuming the acceptance rework cap. `needs-attention` MUST surface a pending host leg as an attention fact naming the item, the pull request and the assertions.

In scenarios.md add `## Scenario 136 — A host-captured assertion holds the item in acceptance until an independent host replay verifies it against the released build`:

```gherkin
Feature: Proof that needs the released build is captured by an agent on a host, not waved through

  Scenario: A Host-captured sub-heading without a Reason line blocks ready
    Given an item whose Definition of Done carries a Host-captured sub-heading with no Reason line
    When the approve valve is driven
    Then the item rests at pending-approval with the missing Reason as the finding

  Scenario: The item parks after merge with the host leg pending
    Given a merged item whose factory-captured assertions are verified and which carries one host-captured assertion
    When the post-merge acceptance pass runs
    Then the pass lists the host-captured assertion as pending the host leg
    And the item rests in acceptance under an ai-only policy
    And needs-attention surfaces the pending host leg with the pull request link

  Scenario: An independent host replay closes the item
    Given a host_captured record naming the released build and a host_verified record from a different session identity
    When the acceptance pass runs
    Then the host-captured assertion is judged passing from the host_verified record
    And the item closes and its pointer carries the host_verified record link

  Scenario: A self-replayed host record is not evidence
    Given a host_verified record published by the session identity that published the host_captured record
    When the acceptance pass runs
    Then the host-captured assertion stays pending and the record is reported as not independent

  Scenario: The gate refuses a weaker mode than the assertion needs
    Given an assertion declared human_attested that an agent session could exercise on a host
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion and the host surface
```

The revise pass MUST co-edit tests/heading-coverage.json and tests/heading-coverage-debt.json for the new Scenario 136 heading as an owned TODO naming the implementing child.

## Proposal: An assertion states behaviour, and a test run is not proof of behaviour

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A Definition of Done assertion MUST name an observable behaviour of the delivered artifact; an assertion about the existence or passing of tests is a finding on a behavioural item, and the capture stage MUST exercise the behaviour through its real surface rather than publish suite output.

### Motivation

Plan definition-and-proof-of-done (epic bd-ib-7sjdzv) was reopened on 2026-10-04 by maintainer ruling. plan/definition-and-proof-of-done/research/004-reopen-failure-analysis-and-repair-scope-2026-10-04.md records the measured evidence: of the five factory runs that have entered the proof stages, two merged with captured and verified records, two died at the proof-to-fix handoff, and one is held; finding F3: two overseer items' entire Definition of Done read 'tests prove X; the full just check aggregate passes' and their proof assets were pytest output; the herdr slice's gate accepted assertions as 'exercisable via a local Unix-socket test server and adapter regression tests'. Where an assertion named real behaviour (PR 2538) the proof was strong. The problem this plan was opened for, that nothing in the loop exercises the delivered behaviour, persists whenever the assertion is written about tests.

### Proposed Changes

In contracts.md §"Effective acceptance criteria", add after "The Definition of Done section":

**Behavioural assertions.** A gradeable assertion MUST name an observable behaviour or state of the delivered artifact on a surface a user or operator of that artifact reaches: a command and what it prints or changes, an API call and its response, an interface and what it shows, a process and what it does to a real peer. An assertion whose subject is the existence, coverage or passing of tests or checks — `tests prove ...`, `regression tests cover ...`, `the aggregate passes` — is a TEST-EXISTENCE ASSERTION. A test-existence assertion is legitimate ONLY when the item's deliverable is itself a test, a check or a gate; on any other item it MUST be reported as a Definition-of-Done finding by the gate, naming the assertion and the remedy (restate it as the behaviour the tests were meant to establish). The janitor gate already guarantees the aggregate, so an assertion restating it carries no information and MUST NOT be counted as discharging a behavioural requirement. The host-side wall MAY report the mechanically recognisable forms; the judgement is the gate's.

In §"Definition-of-Done and Proof-of-Done stages" → `dod_gate`, add to the node's duties: it MUST report every test-existence assertion on an item whose deliverable is not a test, check or gate.

In `proof_capture`, add: for a behavioural assertion the node MUST exercise the behaviour through the surface the assertion names, using the delivered artifact as a user or operator would, and the output of the repository's own test suite MUST NOT be the proof of a behavioural assertion, alone or as its only step; it MAY appear as supporting evidence beside a real exercise. When the surface the assertion names cannot be reached with the sandbox's declared capabilities, the node MUST NOT substitute a test run, a fixture or a double: it MUST end through the structured needs-human ending naming the assertion and the missing capability. `proof_verify` MUST report `not_reproduced` for a behavioural assertion whose captured proof is suite output alone, since there is no exercise to replay.

In scenarios.md add `## Scenario 137 — A behavioural assertion is proved by exercising the behaviour, and a sandbox that cannot exercise it says so`:

```gherkin
Feature: Proof exercises the delivered behaviour through its real surface

  Scenario: A test-existence assertion on a behavioural item is a gate finding
    Given an item delivering a command-line behaviour whose only assertion says tests prove the behaviour
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion
    And the finding's remedy is to restate the assertion as the behaviour

  Scenario: A test-existence assertion is legitimate when the deliverable is a check
    Given an item whose deliverable is a new enforcement check and whose assertion says the check fails on a seeded violation
    When the dod_gate node evaluates the rendered goal
    Then the item proceeds to implement

  Scenario: Capture exercises the behaviour rather than the suite
    Given a behavioural assertion naming a command and its output
    When the proof_capture node runs
    Then the published steps invoke that command on the delivered artifact
    And the record's proof for that assertion is not test-suite output alone

  Scenario: A missing capability ends the run instead of substituting a double
    Given a factory-captured assertion about a terminal multiplexer the sandbox image does not carry
    When the proof_capture node reaches that assertion
    Then the run ends through the structured needs-human ending naming the assertion and the missing capability
    And no record claims the assertion from a fixture or a test double

  Scenario: Suite-only proof does not replay
    Given a captured record whose proof of a behavioural assertion is test-suite output alone
    When the proof_verify node replays the record
    Then its verdict is not_reproduced naming that assertion
```

The revise pass MUST co-edit tests/heading-coverage.json and tests/heading-coverage-debt.json for the new Scenario 137 heading as an owned TODO naming the implementing child.

## Proposal: Declared sandbox capabilities, checked in both directions

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The sandbox image publishes the capabilities it can exercise, and the gate reports a factory_captured assertion that needs an absent capability, with remedies, exactly as it already reports a human_attested assertion the sandbox could capture.

### Motivation

Plan definition-and-proof-of-done (epic bd-ib-7sjdzv) was reopened on 2026-10-04 by maintainer ruling. plan/definition-and-proof-of-done/research/004-reopen-failure-analysis-and-repair-scope-2026-10-04.md records the measured evidence: of the five factory runs that have entered the proof stages, two merged with captured and verified records, two died at the proof-to-fix handoff, and one is held; finding F4: the gate's deliverable-policy check runs in one direction only. All four herdr slices were filed entirely factory_captured although the sandbox image carries tmux and a headless browser and no herdr, and the gate, with nothing declaring what the sandbox can exercise, reasoned about capability from the item's own prose and passed them.

### Proposed Changes

In contracts.md §"Definition-of-Done and Proof-of-Done stages", add after the vocabulary paragraph:

**Sandbox capabilities.** A *sandbox capability* is a named surface the sandbox can exercise for proof: the baseline `terminal` (a shell and the governed repository's own toolchain) plus each additional surface the image carries, such as `headless_browser`, `tmux` or `herdr`. The sandbox image the Dispatcher selects MUST publish its capabilities as the file `/etc/livespec/sandbox-capabilities`, one lowercase snake_case name per line; an image without the file has exactly the capability `terminal`. A governed repository MAY mirror the list as the committed `dispatcher.sandbox_capabilities` array so that the capture, groom and approve displays can show it without a sandbox; the published file is the authority, and the gate MUST report a mirrored name the image does not publish as a Definition-of-Done finding against the configuration rather than against the item.

In `dod_gate`, extend the proof-mode duty: for every `factory_captured` assertion the node MUST identify the surface its proof needs and MUST report, as a Definition-of-Done finding, an assertion whose surface no published capability provides, naming the assertion, the missing capability, and the remedies in order — add the capability to the sandbox image; declare the assertion `host_captured` with a Reason when its proof needs the released build or a host surface; declare it `human_attested` only when no agent session can exercise it. The existing refusal of a `human_attested` assertion the sandbox could exercise MUST name the published capability it relies on. The node MUST read the published file, never infer capability from the item's own prose.

In §"Effective acceptance criteria" → "The deliverable policy", replace `whose subject the factory sandbox could exercise` with `whose subject a published sandbox capability can exercise`.

In scenarios.md add to Scenario 137's feature (the same heading) the scenarios:

```gherkin
  Scenario: A factory-captured assertion needing an unpublished capability is a gate finding
    Given a sandbox image publishing terminal, tmux and headless_browser
    And an item whose factory-captured assertion is about behaviour inside herdr
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion and the capability herdr
    And the finding lists the remedies in order

  Scenario: Publishing the capability clears the finding
    Given the same item and a sandbox image that now publishes herdr
    When the dod_gate node evaluates the rendered goal
    Then the item proceeds to implement

  Scenario: An image without the capability file has only the terminal
    Given a sandbox image that publishes no capability file
    When the dod_gate node evaluates an assertion needing a browser
    Then the finding names headless_browser as missing
```

## Proposal: The referenced scenario governs the proof

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Where the spec tree carries a scenario stating the behaviour an assertion names, the item MUST reference that scenario, and the proof record MUST name the scenario each assertion exercises.

### Motivation

Plan definition-and-proof-of-done (epic bd-ib-7sjdzv) was reopened on 2026-10-04 by maintainer ruling. plan/definition-and-proof-of-done/research/004-reopen-failure-analysis-and-repair-scope-2026-10-04.md records the measured evidence: of the five factory runs that have entered the proof stages, two merged with captured and verified records, two died at the proof-to-fix handoff, and one is held; finding F6: any resolvable H2 satisfies the reference line. The herdr slices reference the generic 'Runtime requirements' heading although the same revision ratified herdr scenarios, and the first merged proof item references 'Inherited from livespec'. The proof steps are therefore not tied to any scenario's own Given, When and Then.

### Proposed Changes

In contracts.md §"Effective acceptance criteria" → "The Definition of Done section", add: where `scenarios.md` carries a `## Scenario NN — <title>` heading whose scenarios state the behaviour an assertion names, the reference line MUST include that heading; a reference line naming only a non-scenario H2 while such a scenario exists MUST be reported as a Definition-of-Done finding by the gate, naming the scenario heading that governs the assertion. A non-scenario H2 remains a valid reference for an assertion no scenario states.

In §"Definition-of-Done and Proof-of-Done stages" → `proof_capture`, add: where an assertion is governed by a referenced scenario heading, the reproduction steps SHOULD follow one of that heading's scenarios step for step, and the record MUST name, per assertion, the referenced heading and the scenario title the steps exercise, or state that no scenario governs it.

In §"Proof of Done record" → "The record", add `the governing scenario (referenced heading and scenario title) or the statement that none governs it` to the per-assertion body list. Scenario 137 exercises this clause through its capture scenario.

## Proposal: Definition-of-Done authoring rules live in the filing front-ends

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The capture, gap-capture, groom and plan front-ends MUST carry the Definition-of-Done authoring rules and MUST display every mechanically detectable finding, each assertion's proof mode and the sandbox capabilities at filing time.

### Motivation

Plan definition-and-proof-of-done (epic bd-ib-7sjdzv) was reopened on 2026-10-04 by maintainer ruling. plan/definition-and-proof-of-done/research/004-reopen-failure-analysis-and-repair-scope-2026-10-04.md records the measured evidence: of the five factory runs that have entered the proof stages, two merged with captured and verified records, two died at the proof-to-fix handoff, and one is held; finding F2: prose/capture-work-item.md, prose/capture-impl-gaps.md, prose/groom.md, prose/plan.md and prose/implement.md contain zero occurrences of 'definition of done', 'proof' or 'attested' (measured on master 6513226b). Enforcement exists only at dispatch, so a filer learns the rules from refusals, and nothing prompts a filer to choose a proof mode against what the sandbox can exercise.

### Proposed Changes

In contracts.md §"Effective acceptance criteria", add after "Who must carry the section":

**Authoring at filing time.** Every front-end that files or reshapes an implement-kind work item — `capture-work-item`, `capture-impl-gaps`, `groom`, and the `plan` front-end when it routes a child — MUST author the item's Definition of Done section under the rules of this section, and its harness-neutral prose MUST state those rules: one behavioural assertion per bullet ("Behavioural assertions"); the proof mode of each assertion chosen in the order `factory_captured`, `host_captured`, `human_attested` against the published sandbox capabilities; the scenario reference where a scenario governs the assertion; and, for a child of a plan, which plan assertions it carries. Each such front-end MUST display, before the filing is confirmed, the effective-criteria parse, each assertion with its proof mode, the sandbox capabilities it resolved (`dispatcher.sandbox_capabilities`, or `terminal` when unset), and every Definition-of-Done finding the host-side wall can detect. Filing stays consent-gated and a front-end MUST NOT refuse on a finding, but an item filed with an outstanding finding MUST NOT be routed to `ready` by intake and MUST carry the finding as a ledger comment so it is repaired where it was made. The implement prompt MUST state the kept-current rule: an implementer that finds the Definition of Done wrong, or a proof mode unachievable, ends through the structured needs-human ending with the proposed amendment.

In scenarios.md add to Scenario 131's feature (the same heading) the scenario:

```gherkin
  Scenario: Filing displays the findings and withholds ready
    Given a filer captures an implement-kind item whose only assertion is a test-existence assertion
    When the capture front-end displays the filing
    Then the display shows the assertion, its proof mode, the sandbox capabilities and the finding
    And on confirmation the item is filed, not routed to ready, and carries the finding as a ledger comment
```

## Proposal: Proof findings reach the fix stage, and a parked acceptance verdict is recorded honestly

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A code-change finding from either proof stage MUST arrive at the fix stage as its work order; an acceptance verdict that parks an item MUST be recorded on the item with its reason; the pointer MUST be written whenever a verified record exists; and a dispatch MUST NOT report green at done for an item resting in acceptance.

### Motivation

Plan definition-and-proof-of-done (epic bd-ib-7sjdzv) was reopened on 2026-10-04 by maintainer ruling. plan/definition-and-proof-of-done/research/004-reopen-failure-analysis-and-repair-scope-2026-10-04.md records the measured evidence: of the five factory runs that have entered the proof stages, two merged with captured and verified records, two died at the proof-to-fix handoff, and one is held; finding F7: on overseer-6ltxut (run 01M3WDN74ESC) proof_capture found a real defect and routed to fix, whose prompt knows only a red janitor; the fix stage changed nothing and reported success (bd-ib-yastku). On bd-ib-mxqrr4 (PR 2538, captured and verified) the acceptance pass returned NEEDS_ATTENTION, recorded no reason on the item, wrote no Proof of Done pointer, and the dispatch still reported status green at stage done; the item has rested in acceptance since 2026-10-01 with nothing saying why.

### Proposed Changes

In contracts.md §"Definition-of-Done and Proof-of-Done stages", add: **Proof findings are the fix stage's work order.** When `proof_capture` ends with `preferred_label=fix`, or `proof_verify` publishes `not_reproduced`, the finding — the assertion, what was observed, and what the proof needs — MUST be delivered to the `fix` node as its work order through the run's stage context, and the `fix` prompt MUST treat a proof finding as a first-class reason for entry beside a red janitor. A `fix` visit entered from a proof stage MUST end either with a tree change addressing the finding or through the structured needs-human ending stating why the finding is wrong; it MUST NOT end succeeded with an unchanged tree. A proof stage's finding MUST also be published on the pull request as part of that stage's record, so it survives the run.

In §"Post-merge acceptance (`acceptance → done`)", add: **A parking verdict is recorded.** Whenever the acceptance pass leaves an item in `acceptance` — NEEDS_ATTENTION, a pending host or human leg, or a PASS under `ai-then-human` — the Dispatcher MUST record on the item, as a ledger comment, the verdict, each evidence leg with what was observed or what could not be observed, and the action that would move the item. The dispatch result for such an item MUST report the stage `acceptance` and the verdict, and MUST NOT report status `green` at stage `done`; `done` is reported only for an item the pass closed.

In §"Proof of Done record" → "The pointer", add: the pointer MUST be written whenever a `verified` record exists for the merging run, independently of the acceptance verdict; an item in `acceptance` whose merging run has a `verified` record and whose description has no pointer MUST be surfaced by `needs-attention` as a hygiene fact, and `reconcile-merged` MUST write the missing pointer.

In scenarios.md add `## Scenario 138 — A proof finding reaches the fix stage, and a parked acceptance verdict is recorded with its reason and its pointer`:

```gherkin
Feature: The proof chain does not lose what it found

  Scenario: A capture finding is the fix stage's work order
    Given a green janitor and a proof_capture node that ends with preferred_label fix naming an assertion
    When the fix node starts
    Then its context carries the assertion and what the proof observed
    And the pull request carries the finding in the capture stage's record

  Scenario: A fix visit from a proof stage cannot succeed on an unchanged tree
    Given a fix node entered from proof_verify with a not_reproduced finding
    When the fix node ends without changing the tree
    Then it ends through the structured needs-human ending stating why the finding is wrong

  Scenario: A red janitor still reaches the fix stage as before
    Given a red janitor outcome
    When the fix node starts
    Then its context carries the janitor failure output

  Scenario: A parking verdict is recorded and reported honestly
    Given a merged item whose merging run has a verified record
    And an acceptance pass that returns NEEDS_ATTENTION
    When the dispatch completes
    Then the item carries a ledger comment naming the verdict, the unobserved leg and the action that would move it
    And the item's description carries the Proof of Done pointer
    And the dispatch result reports stage acceptance, not green at done

  Scenario: A missing pointer on a verified item is surfaced and repaired
    Given an item in acceptance whose merging run has a verified record and whose description has no pointer
    When needs-attention runs and reconcile-merged is driven for the item
    Then needs-attention reports the missing pointer as a hygiene fact
    And reconcile-merged writes the pointer
```

The revise pass MUST co-edit tests/heading-coverage.json and tests/heading-coverage-debt.json for the new Scenario 138 heading as an owned TODO naming the implementing child.
