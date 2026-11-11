## The maintainer's statement of what done means

no ledger comment can make an item undispatchable in any tenant.

## Definition of Done assertions derived from that statement

- On the released plugin build, a dispatch of a ready work item in this repository's tenant whose ledger comments carry a goal-template opening delimiter passes stage goal-minijinja-preflight and lists a factory run.
- The goal rendered for that dispatch carries the comment whole and untruncated with each opening delimiter in bracket form, and the ledger comment itself is unchanged.
- On the released plugin build, a dispatch of a ready work item in a second fleet tenant, livespec-dev-tooling, whose ledger comments carry a goal-template opening delimiter passes stage goal-minijinja-preflight.
- A hand-picked dispatch refused because an item field carries a goal-template opening delimiter names the stage and the field in drive's summary, exits with code 5, and its fleet launcher does not re-take the ticket.
- A ledger comment that an orchestrator writer appends quoting specification clause text that carries a goal-template opening delimiter holds that quote in bracket form.

# 001 — Opening state of the goal-template opener group (2026-11-11)

Notation: work-item ids beginning `bd-ib-` are in this repository's ledger tenant; ids beginning
`livespec-dev-tooling-` are in the livespec-dev-tooling tenant. "Opener" means a goal-template
opening delimiter (an opening curly brace followed by a second opening curly brace, a percent sign
or a hash sign). This note never writes one literally, because ledger and goal text that carries
one is exactly the defect this plan removes.

## Why this plan exists

Opened on the ruling legacy-coordinator-agent (session 5bf269cf) recorded on epic
livespec-dev-tooling-6tgd2z at 2026-11-11T16:52:39Z, under the maintainer's 2026-11-09 orphan rule
("If it's not related to any existing open plan extremely closely, then make a new plan"). The
previous owner of these items, plan radar-and-deterministic-admission, is parked; nothing is routed
to it. Plan dispatch-payload-packaging declined the group because its assertions are packaging only.

Incident that triggered it: on 2026-11-11 livespec-dev-tooling-2zotza became undispatchable
because a coordinator grade comment quoted an opener (successor livespec-dev-tooling-tkglxi).
Ledger comments cannot be edited or deleted, so the only remedy today is a successor item.

## Measured state at opening (origin/master 9383485f6, spec v353)

- `commands/_dispatcher_loop.py` lines 205-215 still call `minijinja_openers_in_goal_sources`
  with the item, its comments and the lessons, and return a failed outcome at stage
  goal-minijinja-preflight on ANY finding. Spec v330 (Scenario 333) says a comment or lesson
  opener is rewritten to bracket form in the goal and the dispatch proceeds. The implementation
  is therefore behind the ratified spec, in every tenant, since every tenant's dispatch runs this
  code.
- `dispatcher.py` has no `host-only` subcommand, and `fleet-launch/dispatch-dual.sh` has no
  exit-code-5 handling. Scenarios 314 and 315 (spec v304) are ratified and unshipped.

## The items

| Item | What it does | Status at opening |
| --- | --- | --- |
| bd-ib-cfgtlo | Render-time neutralization of comment and lesson openers (Scenario 333); field opener is a mechanical filing finding that approve refuses (Scenario 334); field refusal exits 5 with one REFUSED line. The fleet-wide fix. | ready, blocked by bd-ib-v52w7a |
| bd-ib-v52w7a | Committed fleet launcher screens host-only items and never re-tickets an exit-5 refusal (Scenario 314). | pending-approval, blocked by bd-ib-t5aju3 |
| bd-ib-it2d | drive's summary names the stage and field of a field refusal (Scenario 321); `supersede-contaminated` (Scenario 322). Definition of Done re-cut 2026-11-11 by dispatch-payload-packaging on coordinator authority. | ready, no ticket |
| bd-ib-engf4h | Orchestrator comment writers that quote clause text write the bracket form (defence in depth). No ratified scenario states it yet; linked topic every-ledger-comment-that-quotes has no proposal. | pending-approval, spec-change tier |
| bd-ib-t5aju3 | Hand-picked dispatch refusals exit 5 with one REFUSED line; `dispatcher.py host-only` (Scenario 315). Fifth child by the coordinator's follow-up ruling; it is the blocker of bd-ib-v52w7a. | ready, no ticket since 2026-11-07 |

## Corrections to the opening brief

1. The brief's first action was to get bd-ib-v52w7a's linked proposal ratified. It already is:
   topic a-committed-fleet-launcher-screens merged as spec v304 (pull request #4463,
   2026-11-05T11:50:09Z). No revise slot is needed for it.
2. The real serial chain is bd-ib-t5aju3, then bd-ib-v52w7a, then bd-ib-cfgtlo: three factory
   runs before the fleet-wide fix.
3. bd-ib-cfgtlo depends on bd-ib-v52w7a only through its seventh assertion (the launcher does not
   re-take a ticket after exit 5). Scenario 314's second case states that generically and is owned
   by bd-ib-v52w7a. The coordinator decided at about 17:10Z (its clock): that assertion is dropped
   from bd-ib-cfgtlo, the blocks edge is removed, and bd-ib-cfgtlo is ticketed at once. Both were
   done at opening and are recorded on both items.
4. The coordinator also ruled that bd-ib-t5aju3 is adopted as a fifth child, because it heads the
   chain to bd-ib-v52w7a. It gets a fresh ticket in parallel, so its pre-dispatch judgement
   re-takes the stale spec-change tier record of 2026-11-05T14:04:06Z.
5. Priority: this plan is not on the maintainer's priorities record, so its tickets queue in
   first-in-first-out order behind priorities 1 to 5.

## Open work this plan will route

- bd-ib-engf4h needs a proposed change under "## Dispatcher policy settings" adding a scenario for
  quoting writers, then its References line names that scenario.
- The plan-level proof for the second-tenant assertion is a host-captured dispatch in
  livespec-dev-tooling on the released build that carries bd-ib-cfgtlo.
