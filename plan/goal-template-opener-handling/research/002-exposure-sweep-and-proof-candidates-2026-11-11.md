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

- This first pass read two tenants: livespec-orchestrator-beads-fabro (5,176 exported records)
  and livespec-dev-tooling (3,723). The rest of the fleet was read about an hour later; see
  "Fleet-wide pass" below.
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

## Fleet-wide pass

At about 22:30Z the same export and search were run over every other tenant with a `.beads`
configuration under `/data/projects` on this host, at the fleet coordinator's request.

Scope: 19 tenants exist there; 18 were read. NOT read: hetzner-xubuntu-info, which answered
"Access denied" under the family wrapper. On the coordinator's instruction no credential was
sought for it, so its state is unknown. homelab, openbrain and resume were read through their
own project wrappers.

No open item carries an opener in: agent-flywheel, agentic_coding_flywheel_setup, dolt-server,
gdk-in-a-box-agent-flywheel-wrapper, homelab, livespec-tdd-proof, openbrain, resume and
tab-groups-windows-list.

Comment-poisoned, beyond the two tenants above: only livespec-console-beads-fabro, with
livespec-console-beads-fabro-mxppfq (a blocked bug, comment of 2026-09-12) and
livespec-console-beads-fabro-4jb3kl (a plan epic, harmless).

So the dispatchable work items stranded by a comment, across the 18 tenants read, are four:
livespec-dev-tooling-k9mr, livespec-dev-tooling-uwkmew, livespec-dev-tooling-pztogk and
livespec-console-beads-fabro-mxppfq.

Field-only, beyond the two tenants above:

- livespec: livespec-cpqi (`ready`, notes field, offset 8738), livespec-qj3ef3 (active,
  description), livespec-5qu1 (backlog, description) and livespec-h22nve (a plan epic).
- One family with one cause: sibling items about uploading flake-retry records carry the same
  GitHub Actions condition expression in their description in eight tenants: bd-ib-j3rrad,
  bd-gj-inpdgb, livespec-driver-claude-jk6ka4, livespec-driver-codex-lkw5kl,
  livespec-driver-pi-baowvv (active), livespec-qj3ef3 (active), overseer-6fvwoq and
  livespec-runtime-2rqkj4.

Dispositions the coordinator recorded on 2026-11-11: it repaired livespec-dev-tooling-2ocz4v
itself and will repair livespec-cpqi and livespec-5qu1 before they launch; the eight-tenant
family goes to plan fleet-flaky-tests to fix in one pass; the remaining field-only items are
edited when they come up for approve. This plan edited none of them. Comments are not
hand-edited by anyone: the comment-poisoned items wait for bd-ib-cfgtlo.

What the fleet pass adds to the picture: field openers come overwhelmingly from quoting
GitHub Actions or Ansible expressions into an item, and one fan-out filing reproduced a single
opener into eight tenants. That is the population the filing-time finding of Scenario 334
(bd-ib-cfgtlo) stops at the source.

## Sequencing decided inside the plan

bd-ib-engf4h and bd-ib-it2d each carry a blocks edge from bd-ib-cfgtlo since 2026-11-11.
bd-ib-engf4h's writers must call the one shared rewrite function that bd-ib-cfgtlo adds to the
goal render, and bd-ib-it2d's summary assertions sit on the refusal path bd-ib-cfgtlo builds.
The dispatcher holds both tickets in place until bd-ib-cfgtlo closes. bd-ib-v52w7a's reference
line now names Scenario 314 and its second assertion is restated in that scenario's generic
exit-code-5 terms.

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
