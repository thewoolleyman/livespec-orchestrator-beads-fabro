# lifecycle-front-end-retrofit — handoff

Thread state: **LIVE — two open maintainer gates.** Workstream A is
complete and its epic is closed, but per maintainer direction
(2026-07-03) a thread with open gates stays under `plan/`; the earlier
archive was premature and has been reverted. Re-archive ONLY after BOTH
gates below are executed.

Resume command:
`/livespec-orchestrator-beads-fabro:plan lifecycle-front-end-retrofit`

A fresh session should read THIS file, then the read-first chain below,
and can then execute the next actions without consulting chat history.

## Workstream A — COMPLETE (record)

Epic **`bd-ib-ew7bdv`** closed `resolution:completed` 2026-07-03; all
three slices factory-landed and closed:

- A1 `bd-ib-r3vsnd` — PR #264 (`ac0b477`): the intake
  Definition-of-Ready checklist routes filed items into lifecycle
  STATES; label stamps retired; gap-capture hardcode fixed.
- A2 `bd-ib-h2tnil` — PR #266 (`bcc06f9`): groom targets
  `backlog`-STATUS items; `needs-regroom` label machinery deleted.
- A3 `bd-ib-q3x6va` — PR #270 (`4000048`): `orchestrate run` valve
  actions `approve:` / `accept:` / `reject:<id>:rework|regroom` live.
  The interim `bd update` status-flip mechanism this thread used is
  OBSOLETE now that these exist.

Status is DERIVED, never stored here — verify live:

```bash
cd /data/projects/livespec-orchestrator-beads-fabro
/data/projects/1password-env-wrapper/with-livespec-env.sh \
  bd show bd-ib-ew7bdv bd-ib-r3vsnd bd-ib-h2tnil bd-ib-q3x6va --json
```

## Open gate 1 — Workstream B: replacement-proposal ratification (maintainer)

Gate 1's first leg is EXECUTED (2026-07-04): the maintainer REJECTED
the original proposal
`pending-approval-to-ready-structural-gate-ownership` — it completed
the v020-Scenario-23/v023 drift toward valve-side approval, the
opposite of the locked cross-repo design of record (repo
`thewoolleyman/livespec`, `plan/archive/work-item-state-machine/`,
decisions 26/32: approval IS the `pending-approval → ready`
transition; the admission valve is mechanical). The rejection was
executed via `/livespec:revise` — revision
`SPECIFICATION/history/v027/` (a pure-reject snapshot, spec files
byte-identical to v026; the rejected proposal and its
rejection-revision file are archived there).

- NEW gate-1 artifact awaiting ratification:
  `SPECIFICATION/proposed_changes/approval-is-the-pending-approval-to-ready-transition.md`
  — approval IS the `pending-approval → ready` transition (manual: a
  human's explicit `approve`; auto: automatic at capture/groom time);
  the admission valve (`ready → active`) is purely mechanical;
  Scenarios 10/23/31/33 re-expressed; a new ratified `## Work-item
  state semantics` section carries the maintainer's verbatim
  rationale plus intent-preservation clauses; the dropped
  "`admission_policy` governs only the `approve` routing" invariant
  is ratified doctor-checkable. Per maintainer approval 2026-07-04
  the proposal ALSO carries the policy-edit operator actions
  `set-admission:<id>:auto|manual` and
  `set-acceptance:<id>:ai-only|human-only|ai-then-human` on the
  `orchestrate` human-valve surface, governed by the
  no-surprise-transitions rule (a policy edit never moves an item
  between states; a `manual → auto` flip on a `pending-approval`
  item still requires an explicit `approve:<id>`).
- AMENDED 2026-07-04 per the independent Fable verification (3
  blockers, all fixed in the proposal text): the missed risk-dial
  drift carrier ("admission + reversibility" → "the `approve` gate +
  reversibility"); Scenario 10's Feature stanza now fully specified;
  the maintainer quote made byte-exact to the transcript (capital
  "Piling", with a do-not-correct note). The verifier's advisories
  are folded into the same amendment: a drift-residue sweep (new
  proposal section I — enumeration counts, "two human valves"
  phrasing, machine-path verb lists, groom-output texts), the
  ratification payload now explicitly spans contracts.md,
  scenarios.md, spec.md, AND constraints.md plus the
  heading-coverage co-edit (Scenario 31's stale entry reason
  refreshed; Scenarios 10/23 test bindings kept or TODO'd, never
  renamed to not-yet-existing tests), and the implementation-impact
  paragraph now states the revise pass files nothing.
- SECOND AMENDMENT 2026-07-04 per re-verification #2 (which
  confirmed all 35 replace-targets, the byte-exact quote, and model
  fidelity; 2 minor blockers + 3 advisories remained, all fixed):
  Scenario 7's "into ready slices" / drain lines added to the I10
  groom-output sweep; D2 now also rewords "which valve was
  collapsed" to "which gate was collapsed"; section F reverted to
  keep the invariant gloss "(the structural grooming gate)"
  byte-verbatim per the design record and the livespec-runtime twin
  (the proposal holds itself to its own byte-fidelity standard);
  the heading-coverage co-edit now also covers Scenario 10's
  `clauses[].scenario` string; new I11 sharpens the Scenario 35/37
  "collapsed valve" / "human-delegable valves" narrative residue to
  gate-vocabulary.
- Next action: fresh independent Fable RE-VERIFICATION #3 (fleet
  standing rule: no-blockers verdict required before ratification).
  Only then the MAINTAINER runs `/livespec:revise` against
  `SPECIFICATION/` and accepts or rejects the replacement. Do not
  self-revise from a track session.
- At ratification: the `tests/heading-coverage.json` co-edit MUST
  land via the revise `resulting_files[]` mechanism (one added
  contracts.md H2; three retitled scenarios.md H2s; the refreshed
  entry reasons above), and the maintainer authorizes filing the
  implementation rework slice with the expanded scope: (a) the A3
  `approve:` valve action re-targets to `pending-approval → ready`
  (the Dispatcher's manual-admission surface point moves to
  `pending-approval`); (b) the `set-admission:` / `set-acceptance:`
  policy-edit actions are implemented (a store-seam policy updater
  mirroring `update_work_item_status`) — see the proposal's
  "Implementation impact" paragraph. The revise pass itself files
  nothing; the rework slice is a separate post-ratification act.
- Verifier advisory 6 (the `livespec_runtime` invariant gloss
  divergence) is RESOLVED as moot by the second amendment: the
  proposal now keeps the "(the structural grooming gate)" gloss
  byte-verbatim, matching both the design record and the runtime's
  ratified twin (repo `thewoolleyman/livespec-runtime`) — no
  runtime-side follow-up is needed for this gloss.

## Open gate 2 — Workstream C: backlog re-triage execution (maintainer)

- Artifact: `research/backlog-retriage-draft.md` in this thread — the
  DRAFT per-item disposition table (drawn 2026-07-03: 11 →
  pending-approval / 6 stay backlog / 3 → blocked). NO status writes
  have been made.
- Next action: the MAINTAINER approves (or edits) the table. Only
  then execute the approved dispositions ONE item at a time,
  re-reading each item's live state first (a console session
  consolidates items on this tenant; the draft's reasoning holds, the
  ledger holds the truth). Use the store seam / `bd update`, and set
  `blocked_reason` on items routed to `blocked`. Where a disposition
  is an admission decision, prefer the A3 valve actions.

## Read-first chain

1. `plan/lifecycle-front-end-retrofit/research/track-reasoning.md` —
   why this shape; filing-time decisions; the (now obsolete) interim
   mechanism rationale.
2. `plan/lifecycle-front-end-retrofit/research/backlog-retriage-draft.md`
   — the gate-2 disposition table.
3. `SPECIFICATION/proposed_changes/approval-is-the-pending-approval-to-ready-transition.md`
   — the gate-1 replacement proposal (the original was rejected at
   `SPECIFICATION/history/v027/`).

## Close-out condition

When BOTH gates are executed (proposal ratified-or-rejected via
`/livespec:revise` AND the approved dispositions applied), close this
thread: the epic is already closed, so simply re-archive via a
docs-only PR (`git mv plan/lifecycle-front-end-retrofit/
plan/archive/lifecycle-front-end-retrofit/`) with a final handoff
note recording both gate outcomes.

## Binding constraints

- Repo mutations: worktree → PR → rebase-merge; worktrees only under
  `~/.worktrees/livespec-orchestrator-beads-fabro/<branch>`; always
  `mise exec -- git …`; never `--no-verify`.
- Beads only via the wrapper
  `/data/projects/1password-env-wrapper/with-livespec-env.sh`; secrets
  probe-only.
- Operate only in worktrees/branches this track creates; never touch
  another session's branch.
- Known infra gotcha (filed as `bd-ib-qz7b54`, `pending-approval`):
  host-side dispatch under the wrapper loses `~/.local/bin` from PATH
  (sudo sanitization) — `fabro` unresolvable, and the crash strands an
  admitted item at `active`. Workaround: prepend `$HOME/.local/bin` to
  PATH inside the wrapper invocation.
