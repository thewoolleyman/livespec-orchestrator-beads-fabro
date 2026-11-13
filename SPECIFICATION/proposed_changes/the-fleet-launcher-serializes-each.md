---
topic: the-fleet-launcher-serializes-each
author: claude-opus-5-5
created_at: 2026-11-13T04:58:52Z
---

## Proposal: Queued fleet launchers finish their pre-dispatch checks before the queue head, so only the mutex-held binding count is serialized

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" already lets an impl launcher run its launch-time Definition-of-Done preflight while it waits behind older tickets on a factory's FIFO. It says nothing about the launcher's other pre-dispatch work: the ready-set check, the host-only screen, the origin-tip refresh before the preflight, a size screen, the usable-credential probe (`dispatcher.py claude-cred-status`) and the ACP override assembly. It also never says when a launcher stops holding the queue head. A launcher therefore does that work at the head, and the next ticket waits behind all of it. Measured after the 2026-11-13 03:59:33Z hold lift, consecutive LAUNCH lines were about 90 s apart, so filling 18 slots takes about 26 minutes after every lift. This proposal makes five changes:

- **Pre-dispatch checks run while queued.** Every launcher that holds a per-factory FIFO ticket, impl or resume, MUST run every pre-dispatch check that applies to its launch kind while it is queued, not after it reaches the head. Together the checks make one *pre-dispatch pass*, reusable for `FLEET_LAUNCH_PREFLIGHT_REUSE_S`, the window the preflight pass already uses. The rule covers every lane that takes a FIFO ticket: the default gmktec instance, the candidate instance and the mi-homelab instance.
- **Only the launch point is serialized.** The *launch point* is a closed, ordered list of steps:
  1. take the factory launch mutex;
  2. make the binding count, which writes the in-flight marker;
  3. under the mutex, re-read the holds, the shared fleet cap and the target factory's capacity;
  4. drop the FIFO ticket;
  5. release the mutex;
  6. refresh the checkout to the origin tip;
  7. invoke `drive` or `resume`.

  No pre-dispatch check may run under the mutex. After the release, a check the pass already covers is not run again. A launcher MUST drop its ticket before it releases the mutex. The next ticket then becomes the head at that release, not at the earlier launcher's LAUNCH line.
- **The two launch-point rules stay at the launch point.** The hold re-read under the mutex and the origin-tip refresh immediately before `drive` or `resume` do not move. Their bullets are reworded to place them in the list above.
- **ACP override assembly is a pre-dispatch check.** A launcher assembles its `--acp-node` arguments while queued and reuses them within its pre-dispatch pass.
- **Sequence-log timing.** Each launcher logs when each pre-dispatch check passes, when it reaches the FIFO head, when it takes and releases the mutex, and when it launches. The host-captured proof can then read the gap between consecutive launches from the logs.

The FIFO bind order, every hold, cap and gate rule, and every admission condition the Dispatcher owns are unchanged.

### Motivation

Work item bd-ib-kzmihk, filed by legacy-dispatcher-agent under legacy-coordinator-agent's child-filing ruling of about 04:1xZ on 2026-11-13. Its spec-change-tier comment names §"Provisional fleet launch scripts" as the heading to generalize, and Scenario 297 as the scenario that governs it today.

**The measurement.** legacy-dispatcher-agent read these consecutive main-lane LAUNCH lines after the 03:59:33Z hold lift on 2026-11-13:

| Work item | LAUNCH line |
|---|---|
| iykdts | 04:03:27 |
| z7ckf4 | 04:04:55 |
| djk6ig | 04:06:40 |
| comnk4 | 04:08:04 |
| vy75ws | 04:09:58 |

That is about 90 s per launch. Filling 18 slots takes 17 × 90 s, about 26 min, at every lift.

**Where each launch spent its time:**

1. The head ticket took 26–64 s from the previous LAUNCH line to its "gmktec green" line.
2. It then held the gmktec launch mutex for about 23 s for the binding count. The log line for this step is "R277: mutex released after the count".
3. After releasing the mutex, it spent another 26–35 s before its LAUNCH line. That time went on the fast-forward preflight at the origin tip, a credential probe and the ACP override assembly.

The next ticket became the queue head only at that LAUNCH line. The Dispatcher's own pre-launch work (39 phases, about 404 s wall and 147 CPU-s for iykdts) already runs in parallel across launches, so it is not what serializes them.

**What the section allows today.** The section already requires the launch-time Definition-of-Done preflight to run while the launcher is queued (Scenario 297). It also requires tickets to bind in FIFO order, and the mutex to be held only from the binding count to a release that comes before `drive` starts. Three things are missing:

- It does not say the other pre-dispatch checks may run, or must run, before the head.
- It does not say when a launcher stops holding the head.
- It does not require the resume launcher, the candidate lane or the mi-homelab lane to do any of their work while queued.

A launcher that does its credential probe and override assembly after the head therefore conforms, and the next ticket waits behind it.

**The work item's Definition of Done** asserts:

1. A queued impl launcher logs its pre-dispatch checks as passed before its sequence log shows it reaching the head.
2. The next queued launcher whose checks have passed takes the mutex when the head releases it after its binding count, without waiting for the earlier launcher's LAUNCH line.
3. Queued launchers still bind in FIFO order.
4. Holds, the fleet cap and the factory's capacity are still re-read under the mutex at the launch point. A hold set after the checks passed still holds the launch.
5. The checkout is still brought to the fetched origin default-branch tip immediately before `drive` or `resume`.
6. The resume launcher completes its pre-launch checks while queued.
7. The candidate lane completes its pre-dispatch checks while queued.
8. The mi-homelab lane completes its pre-dispatch checks while queued.

A host-captured assertion requires consecutive LAUNCH lines after the next lift to be separated by at most the mutex-held binding count plus a small bound.

**Design choices, stated for the grade:**

- **The pre-dispatch checks are one closed list.** The list names each check this section or the committed launchers already make:
  - the ready-set check;
  - the host-only screen;
  - the origin-tip refresh that precedes the preflight;
  - the launch-time Definition-of-Done preflight;
  - any size screen;
  - the usable-credential probe;
  - the ACP override assembly.

  Everything else in the launcher is either a gate this section already runs on every poll, such as the WIP gate, the holds, the fleet cap, factory-class pressure and the per-factory caps, or it is part of the launch point. A launcher that adds a check later adds it to this list or to the launch point, never between them.
- **One pass, one reuse window.** The checks pass together as one *pre-dispatch pass*. That pass reuses the existing `FLEET_LAUNCH_PREFLIGHT_REUSE_S` window and the existing stale-pass re-run at the head. No second reuse value is added, so a stale preflight and a stale credential probe expire on the same clock.
- **Only the launch point is serialized.** The launch point is a closed, ordered list. The binding count, with its in-flight marker, and the re-reads run under the mutex. The ticket is dropped before the mutex is released. After the release, the launcher runs the launch-point origin-tip refresh and does not re-run any check its pass already covers. That refresh is serialized per checkout, not per queue, so it never holds another ticket's head. The committed impl launcher today runs its credential probe and a ready-set re-check after the release, and this change moves both into the pass. Its seat-gated release path (`RELEASE_BLOCKED`) is different: its ready-set check cannot pass until the release valve runs at the launch. That check MAY still run after the release, because by then the launcher holds no ticket and no mutex.
- **Holds and caps are re-read under the mutex at the launch point, unchanged in substance.** Today "Holds re-read at the launch point" asks for the re-read "immediately before it invokes drive or resume" while the mutex is held. The section also requires the mutex to be released before `drive` starts, so with the launch-point origin-tip refresh in between, "immediately" has always meant the last step under the mutex. The rewording states that. A hold set during the post-release refresh is still caught for an impl launch by "Holds re-read until admission". The shared fleet cap and the target factory's capacity were already re-read under the mutex by the binding count. The paragraph now names them so a reused pass can never stand in for them.
- **FIFO order is untouched.** A launcher that reaches the head before its own checks pass finishes them there, then binds. The rule never lets a later ticket whose checks passed overtake an earlier one. This keeps Definition of Done assertion 3 and Scenario 297's ordering, and it is why the host-captured bound holds only for queued tickets whose checks passed while they waited.
- **Failure outcomes are unchanged.** A check that fails while queued ends or yields the launcher exactly as the same failure would at the head. No check gains a new outcome rule, and a launcher never takes the mutex after a failed check.
- **A yielding launcher is not required to run checks.** The repository WIP gate's existing bar on running the preflight while the gate holds stands, and it extends to every pre-dispatch check. Every other yield rule likewise does not require checks while the launcher yields. A pass already taken stays reusable within its window.
- **No numeric gap bound in the clause.** The coordinator's required behaviour is a structural rule: only the mutex-held binding count is serialized. That rule fixes the gap between consecutive launches at the launch point's own steps. A fixed number of seconds would be a host tuning value, not a contract. The section instead requires the timing lines the host-captured proof reads.

**Fleet scope.** The rule covers the impl launcher `fleet-launch/dispatch-dual.sh`, the resume launcher `fleet-launch/resume-capped.sh`, the candidate lane (a gmktec launch the gmktec target setting sends to the candidate instance) and the mi-homelab lane. This is committed launcher code under `fleet-launch/`. The seat's `tmp/` scripts converge on it through bd-ib-4xqmqh, and the seat rule already covers that.

**Prior art.** bd-ib-x7bwug (in acceptance) moved the launch-time preflight off the FIFO head, which is Scenario 297. This proposal generalizes that change to every other pre-dispatch check and to every lane.

**In-flight survey, 2026-11-13 ~05:00Z.** Scope:

- the in-tree proposals on origin/master at 3271c2f85 under `SPECIFICATION/proposed_changes/`;
- the 28 remote `spec/*` branches;
- the open PRs touching `SPECIFICATION/` or `fleet-launch/`.

These touch §"Provisional fleet launch scripts":

- **a-committed-single-item-operator** (bd-ib-fc6da3, PR #5120). It adds `fleet-launch/override-item.sh`, which takes no FIFO ticket and applies the impl launcher's preflight, origin-tip, credential-wrapper and ACP-override rules. The override never holds a queue head. Its pre-dispatch checks simply run before it takes the mutex, and its launch point follows the same closed list, skipping the ticket-drop step. Relation: `align`, in either revise order.
- **each-gmktec-fabro-server-s-2** (bd-ib-rtzhfc, #5101, in-tree). It adds per-server limits from `max_concurrent_runs` and a runtime fleet cap bounded by the committed `fleet-launch-cap`. This proposal re-reads "the shared fleet cap and the target factory's capacity, by the rules this section then gives for them" under the mutex, so whichever cap rules are ratified are the ones re-read. Relation: `align`.
- **each-gmktec-fabro-server-s** (bd-ib-rtzhfc, in-tree, the WIP-cap half). The WIP count is read at the repository WIP gate, which stays a per-poll gate, not a pre-dispatch check. Relation: `align`.
- **a-fleet-launcher-holds-its** (bd-ib-4vwaty, #5088, in-tree). It adds a master-CI wait marker and a re-bind under the mutex at the pass line. That re-bind happens after `drive` starts, so it is not part of the pre-dispatch work. Relation: `align`.
- **a-fleet-launcher-honours-a** (bd-ib-aibd3u, in-tree). It adds `exempt:` lines to a repository hold file. The launch-point hold re-read applies whatever exemptions the hold rules then give. Relation: `align`.
- **the-launcher-holds-one-wip-number** (bd-ib-5k2yq2, in-tree). It orders a breakage-listed ticket ahead on the FIFO, and adds a capacity-deferred return that re-runs the preflight only when the pass is stale. This proposal says tickets bind in "the order this section's FIFO rules fix", so a ratified breakage ordering is that order. Its stale-pass rule is the same reuse window. Relation: `align`.
- **concurrent-git-fetches-into-one** (bd-ib-zyu2ug, PR #5072). It puts one fetch lock on each checkout. Both origin-tip refreshes, the queued one and the launch-point one, take that lock. The lock is per checkout, not per queue. Relation: `align`.
- **fleet-launchers-log-and-retry** (bd-ib-7itf42, PR #5073). It adds non-run exit rules. A pre-dispatch check that fails while queued exits under the same non-run exit rules. Relation: `align`.
- **Implementation drafts PR #4822 (bd-ib-3ufx6l), #4218 (bd-ib-nmuyjc.6) and #3788 (bd-ib-nz4av6).** These carry launcher code and harness cases only, with no specification text. Relation: `align`.

No in-flight item is superseded or in conflict.

### Proposed Changes

Every edit below is in `contracts.md` §"Provisional fleet launch scripts", plus one new scenario appended to `scenarios.md`. The proposal does not edit Scenario 297's text. It adds, renames and removes no H2 heading in `contracts.md`.

**1. Pre-dispatch checks ahead of the queue head (`contracts.md`).** Immediately after the paragraph that begins "A `fleet-launch/` impl launcher that holds a per-factory FIFO ticket MUST run its launch-time Definition-of-Done preflight while it is queued", add the paragraphs below:

> **Pre-dispatch checks ahead of the queue head.** A launcher's *pre-dispatch checks* are exactly the checks below, each where this section requires it for the launcher's launch kind:
>
> - the ready-set check, with its bounded retry;
> - the host-only screen;
> - the checkout at the origin tip that precedes the launch-time Definition-of-Done preflight;
> - that preflight;
> - any screen of the work item's size the launcher makes;
> - the usable-credential probe (`dispatcher.py claude-cred-status`), where the launcher makes one;
> - the assembly of the `--acp-node` arguments from the ACP overrides file.
>
> A launcher that holds a per-factory FIFO ticket, impl or resume, MUST run every pre-dispatch check that applies to its launch while it is queued behind older tickets. It MUST NOT wait to reach the head of the FIFO before any of them starts. This rule applies to every lane whose launches take a per-factory FIFO ticket:
>
> - a launch onto the default gmktec factory instance;
> - a launch the gmktec target setting sends to the candidate instance;
> - a launch onto the mi-homelab instance, the factory instance `fleet-launch/config.sh` names as `FLEET_LAUNCH_HL_SERVER`.
>
> Checks that pass together make one *pre-dispatch pass*, taken at the time the last of them passed. A pre-dispatch pass is reusable for `FLEET_LAUNCH_PREFLIGHT_REUSE_S` seconds, by the rules the paragraph above gives for a preflight pass. A launcher that reaches the head of the FIFO holding a reusable pre-dispatch pass MUST proceed to the factory's mutex without running any pre-dispatch check again. A launcher that reaches the head with no pass, or with only a pass older than the reuse window, MUST run every pre-dispatch check again before it takes the mutex.
>
> A pre-dispatch check that fails, while queued or at the head, MUST end or yield the launcher exactly as this section requires for that failure at the head. The launcher MUST NOT take the factory's mutex after a failed pre-dispatch check. A launcher that yields the FIFO head under any rule of this section is not required to run pre-dispatch checks while it yields. The repository WIP gate's bar on running the preflight while that gate holds is unchanged.
>
> Running pre-dispatch checks while queued MUST NOT change the order in which queued launchers bind. Tickets still bind in the order this section's FIFO rules fix. A launcher whose checks passed MUST NOT bind ahead of an older live ticket that those rules do not skip, even when that older launcher's checks have not yet passed.
>
> **Launch point.** A launcher holds the head of its FIFO only from the moment its ticket becomes the head until it releases the factory launch mutex after a binding count that lets it launch. Its *launch point* is these steps, in this order:
>
> 1. take the factory launch mutex;
> 2. make the binding count, writing its fleet in-flight marker as this section requires;
> 3. under that mutex, re-read every hold that applies to its launch, the shared fleet cap and the target factory's capacity, by the rules this section then gives for each. The target factory's capacity is its per-factory or candidate cap, plus factory-class pressure where the launcher gates on it;
> 4. drop its FIFO ticket (a launcher that holds no ticket skips this step);
> 5. release the mutex;
> 6. bring its checkout to the origin tip, as "Checkout at the origin tip" requires at the launch point;
> 7. invoke `drive --action impl:<item>` or `resume --item <item>`.
>
> A launcher MUST drop its FIFO ticket before it releases the mutex, so the next live ticket becomes the head at that release. It MUST NOT keep its ticket, or hold the head, through the launch-point refresh or the invocation. While it holds the mutex, it MUST NOT run any pre-dispatch check. Between releasing the mutex and invoking `drive` or `resume`, it MUST NOT run again any pre-dispatch check that its pre-dispatch pass already passed. A check that cannot pass until a step at the launch, such as a seat-gated release of a blocked item, MAY run after that step, because by then the launcher holds no ticket and no mutex. A step that another rule of this section requires at the launch, such as consuming a freeze-allowlist line, is part of the launch point and is not a pre-dispatch check.
>
> When a launch-point re-read finds an applicable hold set, or finds the shared fleet cap or the target factory's capacity reached, the launcher MUST:
>
> - release the mutex and its marker;
> - keep its FIFO ticket;
> - launch nothing.
>
> "Holds re-read at the launch point" and the binding count already require this. A reusable pre-dispatch pass MUST NOT stand in for any of those re-reads.
>
> **Sequence-log timing.** A launcher MUST write each of these lines to its sequence log, each with a UTC timestamp:
>
> - one line when each pre-dispatch check passes, naming the check;
> - one line when its ticket becomes the live head of its FIFO;
> - one line when it takes the factory launch mutex, and one when it releases it;
> - one *launch line* when it invokes `drive` or `resume`, naming the work item and its target factory instance.
>
> When the launcher reuses a pre-dispatch pass at the head, it MUST log that reuse, naming the time the pass was taken.

**2. Holds re-read at the launch point (`contracts.md`).** In the bullet that begins "**Holds re-read at the launch point.**", replace "while it holds the factory launch mutex, immediately before it invokes `drive` or `resume`." with:

> while it holds the factory launch mutex at its launch point, after its binding count and before it drops its FIFO ticket and releases that mutex. Only the remaining launch-point steps then separate the re-read from its invocation of `drive` or `resume`.

In the same bullet, replace "does NOT satisfy this rule." with:

> does NOT satisfy this rule, and neither does a reusable pre-dispatch pass.

**3. Checkout at the origin tip (`contracts.md`).** In the bullet that begins "**Checkout at the origin tip.**", replace "and again immediately before any launcher invokes `drive --action impl:<item>` or `resume --item <item>`," with:

> and again at the launch point of any launcher, after it releases the factory launch mutex and immediately before it invokes `drive --action impl:<item>` or `resume --item <item>`,

At the end of the same bullet, after "it is not an admission decision.", add:

> The refresh before the preflight is a pre-dispatch check, run while the launcher is queued. The refresh at the launch point is part of the launch point, and a launcher MUST NOT skip it on the strength of a reusable pre-dispatch pass.

**4. Resume launcher (`contracts.md`).** In the paragraph that begins "A resume launcher MUST NOT run the launch-time Definition-of-Done preflight", after its last sentence, add:

> A resume launcher MUST run every other pre-dispatch check that applies to a resume while it is queued, under "Pre-dispatch checks ahead of the queue head". Its launch point is the same ordered list of steps, so it holds the head of its FIFO only until it releases the mutex after its binding count.

**5. Configured ACP overrides (`contracts.md`).** In the bullet that begins "**Configured ACP overrides and judge-model environment.**", after the sentence that ends "and the launcher MUST log how many override arguments it passed.", add:

> Reading the overrides file and assembling those arguments is a pre-dispatch check. The launcher MUST do it while queued. It MAY pass the arguments assembled for a reusable pre-dispatch pass without reading the file again, and it MUST read the file again whenever it runs its pre-dispatch checks again. An edit to the file therefore reaches every launch whose pre-dispatch pass was taken after the edit.

**6. Harness cases (`contracts.md`).** Immediately after the paragraph that begins "The `check-fleet-launch` harness cases MUST also cover holds re-read until admission:", add:

> The `check-fleet-launch` harness cases MUST also cover pre-dispatch checks ahead of the queue head. They run against stub checks that each record their start and pass times, a stub launch-point refresh that records its start time and runs for a set interval, stub factory boards, and throwaway queue, lock, in-flight and state directories. The cases are:
>
> - three impl launchers queued on one factory FIFO. Each younger launcher's sequence log shows these checks passed before it shows that launcher's ticket at the head: the origin-tip refresh before its preflight, its preflight, its size screen, its credential probe, its ACP override assembly and its ready-set check.
> - the head launcher releasing the mutex after its binding count. The next launcher takes the mutex and makes its binding count while the head's stub launch-point refresh is still running, before the head's launch line.
> - the youngest launcher's checks passing first. The three launchers still bind in FIFO ticket order.
> - a launcher whose pre-dispatch pass is reusable. It starts no pre-dispatch check between taking the mutex and its launch line.
> - a launcher reaching the head with a pass older than `FLEET_LAUNCH_PREFLIGHT_REUSE_S`. It runs every pre-dispatch check again before it takes the mutex.
> - a queued launcher whose stub credential probe fails. It never creates the factory's mutex and exits as the same failure at the head would.
> - a hold file created after a queued launcher's pass was taken. At its launch point the launcher re-reads the hold under the mutex, releases the mutex and its marker, keeps its ticket and launches nothing. A shared fleet count read at the cap under the mutex holds it in the same way.
> - a stub origin advanced after a launcher's pass was taken. Its checkout is at the new tip when the stub drive starts.
> - an overrides file edited after a queued launcher's pass was taken. A launcher reusing that pass hands the stub drive the old arguments. A launcher whose pass was taken after the edit hands it the new ones.
> - a resume launcher queued behind an impl launcher on the same factory. It logs its pre-dispatch checks as passed before its ticket reaches the head, and takes the mutex as soon as the impl launcher releases it.
> - a gmktec launch the gmktec target setting sends to the candidate instance, and a launch onto the mi-homelab instance, each queued behind an older ticket. Each logs its pre-dispatch checks as passed before its ticket reaches the head.
>
> The scenario "Queued fleet launchers finish their pre-dispatch checks before the head, so only the binding count is serialized" in `scenarios.md` exercises these cases.

**7. Scenario (`scenarios.md`).** Append the scenario below. It carries no number; the revise pass assigns one.

## Scenario: Queued fleet launchers finish their pre-dispatch checks before the head, so only the binding count is serialized

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: A fleet launcher holds its FIFO head only for the mutex-held binding count
  Background:
    Given fleet-launch/config.sh values overridden to stub factory boards, stub pre-dispatch checks that each record their start and pass times, a stub launch-point refresh that records its start time and runs for a set interval, and throwaway queue, lock, in-flight and state directories
    And no hold file exists unless a step creates it
    And the shared fleet count is below the shared fleet cap unless a step says otherwise

  Scenario: Queued impl launchers finish every pre-dispatch check before they reach the head
    Given impl launchers A, B and C hold FIFO tickets on one gmktec factory instance, A oldest and C youngest
    When all three poll while A holds the head
    Then B's and C's sequence logs show the origin-tip refresh, the preflight, the size screen, the credential probe, the ACP override assembly and the ready-set check passed
    And each of those lines comes before that launcher's line showing its ticket at the head

  Scenario: The next queued launcher binds as soon as the head releases the mutex
    Given impl launchers A and B queued on one factory, A at the head, and B holding a reusable pre-dispatch pass
    When A releases the factory launch mutex after its binding count
    Then A's ticket is gone from the queue directory
    And B takes the mutex and makes its binding count while A's stub launch-point refresh is still running
    And B's binding count comes before A's launch line
    And B starts no pre-dispatch check between taking the mutex and its own launch line

  Scenario: Queued launchers still bind in FIFO ticket order
    Given impl launchers A, B and C queued on one factory, A oldest
    And C's pre-dispatch checks pass before A's and B's
    When the three launchers bind
    Then A binds before B and B binds before C

  Scenario: A hold set after the pass is still read under the mutex at the launch point
    Given a queued impl launcher whose reusable pre-dispatch pass was taken before the repository hold file for its repository was created
    When the launcher reaches the head and takes the factory launch mutex
    Then it re-reads the hold under the mutex after its binding count
    And it releases the mutex and its fleet in-flight marker
    And it keeps its FIFO ticket and launches nothing
    When the hold file is instead absent and the shared fleet count read under the mutex is at the shared fleet cap
    Then the launcher releases the mutex and launches nothing

  Scenario: The checkout is brought to the origin tip at the launch point
    Given a queued impl launcher whose pre-dispatch pass was taken at origin tip T1
    And the stub origin's default branch advances to T2 after that pass
    When the launcher reaches its launch point
    Then its checkout is at T2 when drive --action impl starts

  Scenario: The resume launcher, the candidate lane and the mi-homelab lane finish their checks while queued
    Given a resume launcher queued behind an impl launcher on one factory
    And a launch the gmktec target setting sends to the candidate instance, queued behind an older ticket
    And a launch onto the mi-homelab instance, queued behind an older ticket
    When each polls while an older ticket holds the head
    Then each logs every pre-dispatch check that applies to it as passed before its ticket reaches the head
    And each takes the factory launch mutex as soon as the launcher ahead of it releases it after its binding count
```

**8. Unchanged.** These stay as they are:

- Scenario 297's text and its gherkin block. The preflight remains one of the pre-dispatch checks, and that scenario's cases remain true.
- The repository WIP gate and its bar on the preflight.
- Every hold, cap, pressure and FIFO-skip rule.
- "Holds re-read until admission".
- Every admission condition the Dispatcher owns.

This proposal adds no host value. The pre-dispatch pass reuses `FLEET_LAUNCH_PREFLIGHT_REUSE_S`.

**9. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. It carries the row through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edits the file directly in that commit. The row MUST carry:

- `test: "TODO"`;
- `work_item: "bd-ib-kzmihk"`;
- a non-empty `reason` naming the tier the owed test runs at: integration, as `check-fleet-launch` harness cases over stub checks, stub boards and throwaway queue and lock directories.

The same commit MUST add one matching `tests/heading-coverage-debt.json` entry. It carries `spec_root`, `spec_file`, `heading`, `work_item: "bd-ib-kzmihk"` and `first_seen`, set to the revise date. No `contracts.md` H2 heading changes, so no other row is owed.
