## The maintainer's statement of what done means

Authored by the owning session under the coordinator's ruling (legacy-coordinator-agent, session 56abab83, ruling R301, 2026-11-12; coordinator-duties section 4: the owning session writes the successor's Definition of Done and the coordinator grades it). Not maintainer words. The source rule is the maintainer's 2026-11-09 orphan rule on epic livespec-dev-tooling-6tgd2z: "If it's not related to any existing open plan extremely closely, then make a new plan." Done means: on the released orchestrator build, a factory run pays for the full check aggregate once, every sandbox commit leg reaches a verdict inside its bounds, a missing verdict never misroutes the run, an armed pull request overtaken only in record files resumes without a human, and the review_fix visit-bound class measured on 2026-11-12 stops recurring with uninformed briefs after the v0.323.0 roll.

## Definition of Done assertions derived from that statement

- On the petri factory, a run of the released orchestrator build runs the full check aggregate once on its tree before publication, and each commit made inside its implement, fix or review_fix turns runs the affected-tests gate instead, unless that commit's change cannot be scoped.
- On the petri factory, a run of the released orchestrator build whose refresh made a merge commit publishes that head without the merge commit's hook running the full pytest suite, and the publishing pre-push replay check accepts it.
- On the petri factory, a Green amend made through the sandbox commit runner whose repository hook runs the full aggregate reaches the hook's passed or failed verdict within the commit-run settle bound, not no-verdict.
- A dispatch of the released orchestrator build renders each commit-settle node with the timeout its workflow declares unless configuration names that node.
- On the released orchestrator build, a janitor visit ended by its node timeout with no check-suite verdict never routes the run into the fix node.
- On the released orchestrator build, an armed pull request overtaken by a default-branch advance whose conflicted paths are all declared record files is resumed by the Dispatcher in the same invocation, with a journal row naming every conflicted path, instead of resting at needs-human.
- Over the first 24 hours of fleet factory dispatches on orchestrator v0.323.0 or later, every re-entered review_fix visit after a hook-refused Green amend carries that refusal's failed targets in its brief.

# Successor to sandbox-commit-gate-ceiling (2026-11-12T15:19:15Z)

## Why this plan exists

Plan `sandbox-commit-gate-ceiling` (epic bd-ib-qy5wol) has a VERIFIED plan Proof of Done
(record 2026-11-12T14:59:18Z, session 6ee8c13a, build v0.317.0). Its archive is blocked
only by open children. Thirteen of them carry no plan assertion. legacy-coordinator-agent
ruled (R301, 2026-11-12) that each should move to an existing open, not-parked plan only
if that plan is extremely closely related, and that the rest, plus the owed post-v0.323.0
re-measure, go to one successor plan whose Definition of Done the owning session writes.

## Disposition survey (2026-11-12)

Checked against every live `plan/` epic. None is extremely close to these children: each
is a follow-up of qy5wol's own commit-gate theme (commit hook cost, settle bounds,
no-verdict routing, record-file resume). `checkpoint-commit-hook-failures` is close to
bd-ib-rhv4lo, but that child cannot move yet (see below).

Movable now, re-parented here: bd-ib-22ckko, bd-ib-fde4ie, bd-ib-2eyiwy, bd-ib-72hvx5,
bd-ib-kclvlo, bd-ib-mfl2qa, bd-ib-qv7ba2.

Refused by the disposition primitive, so they stay under qy5wol for now:
- held spec-change tier (move after the proposal ratifies): bd-ib-ebwpxw, bd-ib-mx2h62,
  bd-ib-rhv4lo, bd-ib-vamn3n;
- no recorded tier classification (move once intake or the pre-dispatch wall records
  one, or let them close): bd-ib-b3qjzq, bd-ib-prualo.

## Owed measurement carried here

The 2026-11-12 classification of LIVESPEC_REVIEW_FIX_OPEN_RED_VISIT_BOUND_EXHAUSTED
(18 runs, 2,665 run-minutes over 72 h; table in the MEASUREMENT comment on bd-ib-wotls4).
Cause A (14 runs) is carried by bd-ib-wotls4, released in v0.323.0. Re-measure over the
first 24 h after the v0.323.0 roll. A visit-bound ending whose brief names the refusal
and still loops is a new class. Cause B (2 runs) and the `git reset --soft` adherence
finding are deferred to that re-measure.
