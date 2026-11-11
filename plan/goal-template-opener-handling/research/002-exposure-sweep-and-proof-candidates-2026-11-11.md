# 002 — Exposure sweep, proof candidates, and the escaper item (2026-11-11)

Notation as in note 001. "Opener" means a goal-template opening delimiter; this note never
writes one literally. "Comment-poisoned" means an opener sits in an append-only ledger comment
of the item. "Field-only" means an opener sits only in an editable field (title, description,
acceptance criteria, notes or design).

## What was measured, and its scope

At about 21:40Z on 2026-11-11 the two tenants this plan's proof touches were each exported
once with `bd export` (which carries every item's comments), from the tenant's own repository
root, and every record whose status is not `closed` was searched for the three opener forms in
its fields and in each comment.

Scope limits, stated so the counts are not over-read:

- Only two tenants were read: livespec-orchestrator-beads-fabro (5,176 exported records) and
  livespec-dev-tooling (3,723). The other fleet tenants were not read. The 2026-08-22 sweep
  recorded on bd-ib-ai9a read twelve.
- Closed items were excluded on purpose: a closed item is not dispatched.
- A plan epic is never dispatched, so an opener in an epic's comments strands nothing. Epics
  are listed separately below for that reason. Each item's type and plan slug were read from
  the export, not inferred from its title.

## Result

| Tenant | Open items with an opener | Comment-poisoned | Field-only |
| --- | --- | --- | --- |
| livespec-orchestrator-beads-fabro | 11 | 7 | 4 |
| livespec-dev-tooling | 11 | 8 | 3 |

Comment-poisoned, livespec-orchestrator-beads-fabro:

- All seven are plan epics (type `epic`, each with a plan slug): bd-ib-2nq
  (fabro-token-refresh), bd-ib-nckst7 (factory-run-work-preservation), bd-ib-ynnykl
  (legacy-dispatcher-agent), bd-ib-qy5wol (sandbox-commit-gate-ceiling), bd-ib-acrr56
  (publish-draft-green-work-loss), bd-ib-6tcjfx (fabro-currency) and bd-ib-jxvgq5
  (factory-configurable-model-fallback-priority). The newest poisoned comment is of
  2026-11-11, on bd-ib-6tcjfx. No dispatchable work item in this tenant is comment-poisoned
  today.

Comment-poisoned, livespec-dev-tooling:

- Three work items: livespec-dev-tooling-pztogk (a task at `acceptance`; one comment of
  2026-11-11, and its description carries an opener too), livespec-dev-tooling-k9mr (a bug,
  backlog, priority 3; one comment of 2026-09-10) and livespec-dev-tooling-uwkmew (a bug,
  blocked; one comment of 2026-10-30).
- Five plan epics: livespec-dev-tooling-ko26ez, -ib3oe3, -me5aqz, -6tgd2z and -kcoslm. The
  coordinator's own epic, -6tgd2z, has two poisoned comments.

Field-only (recoverable by editing the field):

- livespec-dev-tooling-2ocz4v is `ready` since 2026-11-03 with an Ansible variable reference
  at three offsets of its description (232, 308, 2167). On the code on master it is refused at
  stage goal-minijinja-preflight the moment it is dispatched. Reported to the coordinator.
- bd-ib-j3rrad, bd-ib-43abuz, livespec-dev-tooling-m3zid4 and livespec-dev-tooling-4mhpf4 are
  `pending-approval`; bd-ib-ebd0 is backlog; livespec-impl-beads-zsl is blocked. Once
  bd-ib-cfgtlo ships, `approve` refuses each until its field is edited.

What this says about the goal: comment poisoning is still being produced (three items gained a
poisoned comment in the last four days, one of them today), and most of it lands on plan
epics, where it is harmless. The work items it has stranded in these two tenants are
livespec-dev-tooling-k9mr, livespec-dev-tooling-uwkmew and livespec-dev-tooling-pztogk; the
last is already past dispatch. The incident item livespec-dev-tooling-2zotza is closed and so
is outside this count.

## Proof candidates for the plan's own Definition of Done

The plan assertions 1 to 3 need a dispatch of a comment-poisoned item that passes the
preflight on the released build. Naturally poisoned items are better evidence than a
constructed one, because they are the population the goal is about:

- Assertions 1 and 2 (this tenant): no naturally poisoned work item exists here today, so
  the proof needs a small real item filed for the purpose, with one instruction comment longer
  than 1,000 characters carrying an opener, which is Scenario 333's own Given. If a work item
  in this tenant is poisoned by then, use that instead.
- Assertion 3 (livespec-dev-tooling): livespec-dev-tooling-k9mr or livespec-dev-tooling-uwkmew.

Each proof records the released plugin version, the item id, the comment id, the preflight
stage outcome and the listed run id, and for assertion 2 the goal file the Dispatcher wrote,
showing the comment whole with each opener in bracket form.

## The escaper item, bd-ib-ai9a

bd-ib-ai9a (backlog, priority 1, parentless) measured in August that the escaper's output is
itself rejected by the engine. Reading master at 622eca9d8:

- `escape_minijinja_literal` is still applied to the goal body in `commands/_dispatcher_goal.py`.
  Because the preflight refuses any opener in the goal sources first, that call never sees an
  opener at run time today. After bd-ib-cfgtlo it still will not: comment and lesson openers
  are rewritten to bracket form before it, and field openers are refused.
- `comment_safe_external_text` applies the escaper and then replaces every opening brace pair
  with brackets, so its output carries no opener either.
- The escaper is also applied in `commands/_dispatcher_setup_nodes.py` to values written into
  graph attributes that are not ledger text. That path is where bd-ib-ai9a's defect can still
  be reached, and it is outside this plan's goal.

So this plan does not need bd-ib-ai9a, and its deferral in the scope event stands. The
completeness review should decide whether bd-ib-ai9a is closed as unreachable for goal text
and re-filed narrowly for the setup-node path.

## Spec v355

The writer-side rule that bd-ib-engf4h implements was ratified on 2026-11-11 as spec v355
(proposal pull request 4969, revise pull request 4973). Two points were ruled by the fleet
coordinator before the cut: a writer the specification elsewhere requires to use
`comment_safe_external_text` is unchanged, and a reader never derives a clause digest from a
recorded quote. The post-step doctor phases of that revise were not run.
