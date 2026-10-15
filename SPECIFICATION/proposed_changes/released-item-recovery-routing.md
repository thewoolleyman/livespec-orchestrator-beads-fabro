---
topic: released-item-recovery-routing
author: claude-opus-5-5
created_at: 2026-10-15T19:45:16Z
---

## Proposal: Decide a released item's recovery route before admission, and execute it per item after admission

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text says WHAT the Dispatcher decides for an item it released automatically, but not WHERE in the dispatch sequence it decides. Today each of the three releases ("A first stall cancel is released and recovered", "Provider-limit release and re-dispatch" and the adapter launch release) hands the item to the ordinary admission valve. The shared clause "Recovery from the failed run's preserved work" then says the decision happens "Before stale publish-branch reclaim". The reclaim now sits after admission (bd-ib-huoyk7), and a resume refuses any item that is not `ready`. Read together, the clauses cannot be implemented as written.

This proposal adds one named step, **recovery routing**. It is a read-only, per-item measurement that runs after the pre-dispatch wall and BEFORE the admission valve. It assigns each released candidate exactly one route: `fresh`, `resume`, `seeded` or `held`. Admission then claims as it does today. Each launch path executes the claimed item's route on that item's own argument clone, so the stale publish-branch reclaim runs only for `fresh` and `seeded` items and never for a `resume` item.

### Motivation

Run 01M509HNX5KGKSRV04VQEYVWH6 of bd-ib-3snvbf (dispatch a7395318d0c945589105940e7936139f, 2026-10-15) delivered that item's four resume-anchor assertions. It then stopped on the two assertions that bd-ib-qgcpoc now carries, with three measured findings. The first two are confirmed against the code and the spec; the third is confirmed with a narrower blast radius than reported.

1. **Ordering.**
   - The recovery clause puts the decision "Before stale publish-branch reclaim" (contracts.md 7447-7451). The watchdog's release paragraph says the same: "Before any stale publish-branch reclaim, it evaluates the resume preconditions" (contracts.md 1597-1601).
   - The reclaim runs past admission. Both launch paths call `post_admission_publish_branch_reclaim` after `admit_and_select` has written `ready -> active` (`_dispatcher_loop_wave.py:144`, `_dispatcher_run_commands.py:209-225`). The module docstring of `_dispatcher_pre_dispatch_wall.py:21-29` records why: bd-ib-huoyk7, a capacity-deferred item lost its branch and pull request.
   - A resume refuses "before the admission valve" when "the item is not `ready`" (contracts.md 4247-4255). So at the reclaim's position the decision would refuse every released item on the not-ready bullet. The run tried exactly this wiring and rejected it.
2. **Wave hand-over.**
   - The drain admits a whole wave (`_admit_and_dispatch_loop_wave`, `_dispatcher_loop_wave.py:110-176`) and launches it in one thread pool.
   - The resume command is a separate single-item sequence (`run_resume_command`, `_dispatcher_resume_command.py:171-241`), with its own preamble, gather, ladder, wall and admission.
   - "This item resumes instead" therefore cannot be an exit code the wall returns. It has to be a per-item route inside the wave.
3. **Per-item seed.**
   - The resume head reaches the sandbox through `resume_checkout_for`, which reads `RESUME_HEAD_ARG` off the namespace each dispatch receives (`_dispatcher_resume_entry.py:149-169`, reached from the overlay at `_dispatcher_loop.py:244`).
   - Setting that attribute on the wave's SHARED namespace would leak one item's head to the whole wave, as the run reported.
   - Correction: the wave already clones the namespace per item before `dispatch_one`. See `_dispatcher_loop_wave.py:147-160`, which calls `args_with_dispatch_factory_target` and `args_with_dispatch_workflow_name`; each builds `argparse.Namespace(**vars(args))` (`_dispatcher_factory_ledger.py:138-162`, `_dispatcher_workflow_ledger.py:103-116`). The resume command's `_resumed_args` already sets the head on such a clone (`_dispatcher_resume_command.py:287-299`). A per-item route needs no new plumbing to the overlay, only a third per-item clone step applied in the same place.

Change 3 below also repairs drift between the ratified reclaim text and the implementation. contracts.md 4050-4052 still says the reclaim is "a pre-dispatch act of both `dispatch` and `loop` for every selected item", while since bd-ib-huoyk7 the implementation runs it only past admission, for the items selected to launch.

The run also recorded that no recovery-source or seed mechanism exists under `commands/`. A grep of the package for `recovery_source` and `seed_record` on master 0b4e508d returns nothing.

PRIOR ART that this proposal must reconcile: bd-ib-ogymgj ("Resume a provider-limit-released item from its published pull request before any publish-branch reclaim") and bd-ib-kn7ktk ("Seed a provider-limit re-dispatch from the failed run's preserved tree when resume is inapplicable"). Both are children of plan epic bd-ib-jxvgq5, filed against v127, and sit at `pending-approval`. They are the provider-limit twins of bd-ib-qgcpoc's two assertions, so all three items need the same unimplemented mechanism and hit the same ordering conflict. This proposal therefore specifies routing ONCE, for every automatically released item, so that one implementation discharges all three.

Work-item: bd-ib-qgcpoc (plan stall-watchdog-false-kills, epic bd-ib-laf735). Line numbers are against master 0b4e508d. Reviewed by the gitops-fleet-capacity-monitoring coordinator's Fable review (verdict BLOCK on text fixes, all applied; filed without a second review per its ruling).

### Proposed Changes

#### Recommended placement and rejected alternatives

**Recommended: recovery routing, after the pre-dispatch wall and before admission; route executed per item after admission.**

- The decision is a READ: the resume gather and ladder (`gather_resume`, `resume_refusals`, `_dispatcher_resume_command.py:195-204`) plus the preserved-work lookup. At that position the item is still `ready`, so the ladder's not-ready bullet keeps its full force. A resume still "never steps around the ledger's human decision", and no internal caller gets an exemption.
- Nothing is mutated before the claim. A capacity-deferred item keeps its branch and pull request, which is the huoyk7 guarantee. The route is simply discarded and re-measured on the next pass.
- It is not a wall row. The wall's stated invariant is that every row is a refusal and none mutates (`_dispatcher_pre_dispatch_wall.py:21-29`, 170-173), and a route is not a refusal.
- Remote measurement stays off the critical path of ordinary dispatch. Routing asks the forge and the factory only for an item whose latest journaled dispatch ended in one of the three releases, which mirrors the reclaim's "Only a re-dispatch asks" rule (contracts.md 4058-4068).
- The double remote probe is intentional. Routing asks origin and the factory before the claim, and the reclaim asks again after the claim. The first answer decides the route while nothing has been mutated. The second is the reclaim's own measurement at the moment it would delete a ref, so a destructive act never runs on an answer taken before admission.

Rejected:
- **Invoke resume from the reclaim's post-admission position.** It refuses on not-ready. Relaxing that bullet for an internal caller weakens the one refusal that protects a human decision, and the implementing run tried and rejected this route.
- **Add routing as a row of the pre-dispatch wall.** It breaks the wall's refusal-only invariant, and a "resume instead" outcome is not a refusal the wall can return.
- **Exit the wave and run the resume command separately.** The item would leave the wave's WIP accounting and admission audit (the `loop-pick` record, `_dispatcher_loop_wave.py:127-135`), and a second admission path would exist for the same item in the same pass.
- **Move the reclaim back before admission.** That directly reverses bd-ib-huoyk7.
- **Set the head on the shared namespace.** It leaks to the whole wave, as the third finding showed.

**1. contracts.md, §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" (7447-7472).** Replace the first paragraph ("Before stale publish-branch reclaim, the Dispatcher MUST evaluate ... MUST NOT reclaim the branch.") with:

"An item is *released for recovery* when its latest journaled dispatch ended in a first-stall release (§"Dispatcher progress watchdog"), a `provider-limit-release` record, or an `adapter-launch-release` record. Both `dispatch` and `loop` MUST perform *recovery routing* for every released candidate. Routing comes after the pre-dispatch wall and BEFORE the admission valve, while the item is still `ready`, and assigns the item exactly one route. Routes are graded in the order listed; the first that holds is the route, and an unobservable or unreadable measurement at any step routes `held`. A refusal of §"Resume from a published pull request (`resume --item`)" is *fallback-permitting* when its named remedy is a plain dispatch: the publish branch carries no open pull request, which includes a missing pull request and one closed without merging; no proof record names a head and no cancel record anchors one; the pull request's head moved; the Definition of Done changed; or the pull request already anchored two resumes. Every other refusal is *non-fallback*: the earlier run is live, the item's dispatch-scoped ownership lock is held by a live process, or the pull request is merged (its remedy stays `reconcile-merged --item`). The not-ready refusal cannot apply, because routing grades a `ready` item. A non-fallback refusal takes precedence over every fallback-permitting one, so a merged pull request is never treated as a missing anchor.

- `resume`, when every published-PR resume precondition of §"Resume from a published pull request (`resume --item`)" passes;
- `seeded`, when every applicable resume refusal is fallback-permitting and preserved work is verified;
- `fresh`, when every applicable resume refusal is fallback-permitting and preserved work is confirmed absent;
- `held`, when any non-fallback refusal applies, or any measurement routing needs cannot be taken.

Routing MUST NOT mutate the ledger, origin, or any factory. An item not released for recovery is routed `fresh` without any remote measurement. A route is valid only for the pass that measured it: an item the valve defers for capacity carries no route into the next pass, which measures it afresh. A `held` item MUST NOT be offered to the admission valve in that pass. It stays `ready`, the journal carries one `recovery-held` record naming the item and the measurement that could not be taken, every applicable non-fallback refusal with its existing remedy in the order the resume's refusals are listed, or both, and the next pass retries automatically. Under `loop` the hold is reported as a deferred outcome on the same terms as a capacity deferral. Under `dispatch --item` it is a precondition error (exit `3`, §"Dispatcher exit codes") naming the item and the measurement or the non-fallback refusals with their remedies, before any run exists, as `resume --item` refuses today."

Keep the second paragraph ("When resume is inapplicable ... seeded from preserved work ..."), the third ("The seed record MUST name ...") and the fourth ("A confirmed absence of preserved work ...", 7470-7472) unchanged, then add after the fourth:

"After admission, each launch path MUST execute every admitted item's route on that item's own copy of the dispatch arguments, in the same per-item step that applies the item's factory and workflow pins. Route-specific state MUST NOT be written to arguments shared by the wave. A `resume` route executes the resume's post-admission sequence: it journals the `resume` record before the run exists, enters at the anchored node on the anchored head, and runs the workflow the earlier dispatch record names. The status grading of the not-ready refusal is satisfied by routing and is not repeated after the claim. A `seeded` route checks out the recorded SHA as the preceding paragraph requires. The stale publish-branch reclaim runs for `fresh` and `seeded` items only. For a `seeded` item it runs after the seed's preservation is verified, and it MUST NOT run for a `resume` item. An automatically routed resume is subject to the WIP-cap posture of the entry point that admitted it."

**1b. contracts.md, §"Factory-configurable ACP fallback priority", the two release steps that name a recovery source.** The phrase below occurs exactly twice in contracts.md: once in the provider-limit release's step (1), wrapped across 7405-7406, and once in the adapter launch release's step (1) on 7445. Each occurrence is one minus-line:

"and the recovery source chosen under "Recovery from the failed run's preserved work" below or its confirmed absence;"

Replace it in both places with:

"and the preserved-work reference the release observed (the published head or preservation ref) or its confirmed absence; the recovery route itself is decided by recovery routing at the item's next dispatch;" (ending in ';' because each site continues an inline numbered list)

**2. contracts.md, §"Dispatcher progress watchdog" → "A first stall cancel is released and recovered" (bold label at 1584; the replaced sentence is 1597-1601, verbatim).** Replace "Before any stale publish-branch reclaim, it evaluates the resume preconditions, which the cancel record can now anchor (§"Resume from a published pull request (`resume --item`)"). It invokes resume under its own invoker identity when they pass, and otherwise makes a dispatch seeded from preserved work." with: "Recovery routing evaluates that next dispatch before admission, under §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work". The cancel record can anchor the resume route (§"Resume from a published pull request (`resume --item`)"). A `resume` route runs under the Dispatcher's own invoker identity."

**3. contracts.md, §"Stale publish-branch reclaim before a re-dispatch" (4043-4056).** After "...as a pre-dispatch act of both `dispatch` and `loop` for every selected item.", insert: "It runs after the admission valve, for the items admission selected to launch, and only for those whose recovery route is `fresh` or `seeded` (§"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work"). A deferred item keeps its branch and any pull request on it."

**3a. contracts.md, §"Stale publish-branch reclaim before a re-dispatch", the "Acceptance attribution survives the reclaim" bullet (4120-4124).** Replace "For an item released under §"Factory-configurable ACP fallback priority" → "Provider-limit release and re-dispatch", the Dispatcher makes that choice itself" with "For an item released under §"Factory-configurable ACP fallback priority" → "Provider-limit release and re-dispatch", released by that section's adapter launch release, or released after a first stall cancel under §"Dispatcher progress watchdog", the Dispatcher makes that choice itself".

**4a. contracts.md, §"Resume from a published pull request (`resume --item`)", the exception list (4141-4147).** Replace "and an item released after a first stall cancel under §"Dispatcher progress watchdog": for each" with ", an item released by that section's adapter launch release, and an item released after a first stall cancel under §"Dispatcher progress watchdog": for each".

**4. contracts.md, §"Resume from a published pull request (`resume --item`)", the not-ready refusal (4252).** Append: "For a resume the Dispatcher routes itself, this bullet is graded at recovery routing, before admission, and not again after the claim."

No new `##` heading is added to contracts.md.

**5. scenarios.md: add a new scenario after Scenario 184.**

```gherkin
## Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch
Feature: Recovery routing for an automatically released item
  Scenario: A first-stall-released item in a drain wave resumes while its wave-mates dispatch plainly
    Given a ready item released after a first stall cancel whose cancel record anchors a resume
    And a second ready item in the same drain wave with no earlier dispatch
    When the drain routes, admits and launches the wave
    Then the released item's resume preconditions are graded while it is ready, before admission
    And the released item's run enters at the anchored node on the anchored head under the Dispatcher's own invoker identity
    And the journal carries a resume record and neither a publish-branch-reclaim nor a publish-branch-reclaim-held record for it
    And the second item's run starts at start on the default branch with no resume head
  Scenario: An unanchorable released item is seeded from verified preserved work
    Given a ready released item whose resume is inapplicable and whose failed run has a verified preserved commit
    When the Dispatcher routes and launches it
    Then its run checks out the recorded commit SHA
    And its seed record names the source run, remote, immutable commit SHA and preservation reference
    And the publish branch is reclaimed only after that preservation is verified
  Scenario: A capacity-deferred released item is untouched
    Given a ready released item that recovery routing assigned the resume route
    When the admission valve defers it for capacity
    Then its publish branch and pull request are unchanged and no resume record is journaled
    And no recovery-held record is journaled for it
  Scenario: An unobservable measurement holds the item without reclaim
    Given a ready released item whose forge or factory measurement cannot be taken
    When the Dispatcher routes it
    Then the item stays ready and is not admitted in that pass
    And the journal carries a recovery-held record naming the measurement
    And no publish-branch reclaim runs for it
  Scenario: A live ownership lock holds a released item that has preserved work
    Given a ready released item whose resume is inapplicable and whose failed run has a verified preserved commit
    And the item's dispatch-scoped ownership lock exists and its process is alive
    When the Dispatcher routes it
    Then the route is held, not seeded
    And the journal carries a recovery-held record naming the live ownership lock, its age and the wait-or-confirm-liveness remedy
    And the item is not admitted in that pass and no publish-branch reclaim runs for it
    And under dispatch --item the dispatch exits with code 3 naming the live ownership lock before any run exists
  Scenario: A merged pull request holds a released item and keeps the reconcile-merged remedy
    Given a ready released item whose publish branch carries a merged pull request
    And its failed run has a verified preserved commit
    When the Dispatcher routes it
    Then the route is held, neither seeded nor fresh
    And the journal carries a recovery-held record naming the merged state and the remedy reconcile-merged --item
    And no publish-branch reclaim runs for it
```

Scenario 172's existing scenarios ("A first stall cancel after publishing is released and resumed", "A first stall cancel before publishing is released and recovered from preserved work") stay unchanged; Scenario 185 states their placement. Scenario 144 is unchanged.

#### Heading-coverage implications (tests/heading-coverage.json)

- Add an entry for the new `## Scenario 185 — ...` heading: `spec_file` `scenarios.md`, `test` `"TODO"`, `work_item` `bd-ib-qgcpoc`, with a reason naming this revision and the shared provider-limit carriers bd-ib-ogymgj and bd-ib-kn7ktk.
- Re-point the existing Scenario 172 entry (line 1744), whose `work_item` is `bd-ib-3snvbf` and whose reason says "bd-ib-3snvbf owns the binding". After the 2026-10-15 re-cut, bd-ib-3snvbf no longer carries Scenario 172's recovery scenarios. Recommend moving `work_item` to `bd-ib-qgcpoc`, the last carrier to land, and updating the reason. Otherwise 3snvbf's closing criteria would cover a binding it can no longer complete (the circular shape AGENTS.md records for bd-ib-99a1).
- No contracts.md H2 changes, so no other entry changes.

#### Recorded rulings (gitops-fleet-capacity-monitoring coordinator, after Fable review, 2026-10-15)

- (a) Under `dispatch --item`, `held` is a precondition error, exit `3`, naming the measurement, and the Dispatcher journals `recovery-held`. This matches the resume's own refusal posture (contracts.md 4247-4250), because a hand-picked dispatch is a sanctioned operator override (contracts.md 4570-4573).
- (b) The WIP-cap posture follows the admitting entry point. A routed resume in a `loop` wave is a counted claim, and under `dispatch --item` it bypasses the cap like any hand-picked dispatch. Grounds: the resume's own admission clause (contracts.md 4187-4193), the hand-picked bypass (contracts.md 946), and the sanctioned override (contracts.md 4570-4573). Change 1's sentence "An automatically routed resume is subject to the WIP-cap posture of the entry point that admitted it." stands as written.
- (c) Scope is all three release kinds, as drafted: the first-stall release (contracts.md 1595-1597), the provider-limit release (contracts.md 7405-7406) and the adapter launch release (contracts.md 7445).
