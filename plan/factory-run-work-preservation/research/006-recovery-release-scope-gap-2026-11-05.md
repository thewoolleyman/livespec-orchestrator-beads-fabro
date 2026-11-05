# 006 — Which run endings a re-dispatch actually seeds from: a scope gap in plan assertion 2 (2026-11-05)

Session: factory-run-work-preservation plan seat, 2026-11-05, about 17:40Z. legacy-coordinator-agent asked whether the accepted
design (note 005) covers two things for a run that a factory restart cancelled before its `janitor` stage succeeded:
(a) that run's settled work reaching origin, and (b) the next dispatch starting from it. The question came from a measurement
the coordinator made earlier that day. After the 16:14Z restart of the petri server (:32276), cancelled runs relaunched FRESH.

This note answers both parts and drafts a decision for the maintainer. It is a draft, not a decision. No `propose-change` has been
filed. Note 005 still governs everything it covers.

## Answer

**(a) Restart-cancelled work reaches origin: YES.** Plan assertion 1 names "restart cancels" in its list of endings. Its carriers
are bd-ib-ofvsr3 and bd-ib-xdhe5z.
- bd-ib-ofvsr3 pushes the run branch's tip to `refs/livespec/wip/<item>/<run>/<n>` at the end of each of the three commit-settle
  steps. That happens while the run is still running, before any cancel, so how the run later ends cannot skip it.
- bd-ib-xdhe5z writes the `livespec-preserved-tree` receipt when any non-merge ending is recorded.
- This does not conflict with the spec's rule that "a run that is not janitor-green MUST be cancelled without a publication"
  (`contracts.md` §"A janitor-green run that a factory restart or an outside cancel ends is published to a preservation ref").
  That rule governs what the cancel itself publishes. The work-in-progress capture happens earlier, at the commit step.
- What is lost is the node visit in progress at the cancel, which the maintainer's ruling of 2026-11-05 accepts.

**(b) The next dispatch starts from that work: NO, as specified and as built.** Plan assertion 2 promises it: "A re-dispatch of an
item whose earlier run ended without merging starts from that run's preserved tree". Its carrier bd-ib-v6br5b does not deliver it
for this ending.
- **The child is gated.** Every bd-ib-v6br5b assertion, and every case in Scenario 319, applies only to an item that is
  *released for recovery*.
- **The spec's list.** `contracts.md` §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved
  work" (about line 9353) says an item is released for recovery only when its latest dispatch ended in one of these:
  - a first-stall release;
  - a `provider-limit-release`;
  - an `adapter-launch-release`;
  - a `stale-assignee-clear`;
  - a stale assignee whose run stamp names a run;
  - the workflow's `needs_human` or `non_converged` terminal, once the item is back at `ready`.
- **What every other item gets.** The same clause says "An item not released for recovery is routed `fresh` without any remote
  measurement."
- **The code matches the spec.** `released_for_recovery` in
  `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_recovery_release.py` sets the answer only for
  `stall-cancel-release`, `provider-limit-release`, `adapter-launch-release`, and a terminal carrying a `needs_human_kind` or the
  non-convergence marker.
- **Consequence.** A restart-cancelled run is none of these, so its re-dispatch goes fresh, exactly as the coordinator measured.
  With bd-ib-ofvsr3 shipped, the work-in-progress ref would sit on origin unused.

## How each ending in plan assertion 1 fares at re-dispatch

Scope: read from the `contracts.md` recovery clause, from `_dispatcher_recovery_release.py`, and from
`_dispatcher_run_wall_budget_disposition.py`. I did not exercise any of these against a live run.

| Ending (plan assertion 1) | Released for recovery? | Basis |
|---|---|---|
| needs-human terminal (publish_draft failure included) | yes, once the item is back at `ready` | `needs_human` terminal clause |
| first stall-watchdog cancel | yes | `stall-cancel-release` |
| Dispatcher run-wall-budget cancel | **no** | rests `blocked`/`needs-human` through its own stage; it is not the workflow's `needs_human` terminal, so the terminal clause does not name it |
| factory restart cancel | **no** | not in the list. `cancel-for-restart` itself has no implementation under `.claude-plugin/scripts` (grep, 2026-11-05) |
| cancel made outside the Dispatcher | **no**, unless a stale-assignee clear happens to apply | not in the list; the stale-assignee run states are `failed`, `succeeded` and `absent` |
| Fabro server crash, `fabro rm -f` | yes, when the item comes back as a stale assignee with run state `absent` | `stale-assignee-clear` |

So the gap is wider than restart cancels. Three of the seven endings that plan assertion 1 lists save their work to origin, but a
re-dispatch never uses it.

## Options for the maintainer

1. **Release for recovery on every non-merge ending that has a preserved capture (RECOMMENDED).**
   - **Rule.** An item is also released for recovery when its latest dispatch ended without merging and its latest run holds a
     work-in-progress ref, as recorded by bd-ib-xdhe5z's `livespec-preserved-tree` comment.
   - **Safety.** Recovery routing's existing measurements decide resume / seeded / fresh / held, and its existing preference order
     still applies. The release consumes no rework budget, as every other release already does not.
   - **What it adds.** One clause to the release list, one Scenario 319 case (a restart-cancelled run is seeded from its latest
     capture), and one bd-ib-v6br5b assertion.
   - **Why it fits.** It ties the release to the receipt the plan already builds, so a future ending needs no new list entry. It is
     the smallest change that makes plan assertion 2 true as worded.
   - **Interaction with the run-wall-budget rest.** That cancel still rests the item `blocked` for a person, because its "no release
     arm" reasoning is about not re-dispatching unattended. Under this option, it would only change the route once a person returns
     the item to `ready`: seeded instead of fresh.
2. **Add only the restart cancel to the release list.**
   - Narrower, and it closes the case the coordinator measured.
   - Outside cancels and the wall-budget return still go fresh, so plan assertion 2 stays false for them. It would need re-wording
     to name the endings it covers.
3. **Change nothing; re-word plan assertion 2 to the endings that already release.**
   - Costs nothing to build.
   - Contradicts the maintainer's "every way a factory run ends" in note 001. A restart, the most common fleet-wide ending, would
     keep redoing settled work.

**Recommendation: option 1.** It keeps the maintainer's stated aim and adds one rule rather than a list. It also reuses machinery
the plan already carries: the receipt (bd-ib-xdhe5z) and the routing (bd-ib-v6br5b).

## If the maintainer chooses option 1 or 2

- **Spec.** File `/livespec:propose-change` amending "Recovery from the failed run's preserved work" and adding the Scenario 319
  case, then revise it.
- **bd-ib-v6br5b.** Add the matching Definition-of-Done assertion. Its release currently waits for bd-ib-ofvsr3 to ship.
- **Plan.** Record the choice as a scope event. The carrier map does not change: assertion 2 stays carried by bd-ib-v6br5b.

Related, as legacy-coordinator-agent states it (not re-verified here): publish-draft-green-work-loss (bd-ib-vraou4,
bd-ib-adcaa6, and ruled seeds in bd-ib-ltlg4i assertion 5) covers janitor-green cancels. It does not cover automatic seeding of a
non-green cancelled run, so this plan does not overlap with it.
