# lifecycle-front-end-retrofit — handoff

Thread state: **BOTH GATES EXECUTED 2026-07-04 — nothing blocks the
re-archive.** Gate 1 (proposal ratification) and gate 2 (backlog
re-triage) are both executed and recorded below; the authorized rework
slice is merged, released (v0.9.0), and accepted `done`. The one
remaining act for this thread is the close-out itself: a docs-only PR
moving `plan/lifecycle-front-end-retrofit/` to
`plan/archive/lifecycle-front-end-retrofit/` (this handoff is the
final note recording both gate outcomes).

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

## Gate 1 — Workstream B: replacement-proposal ratification (EXECUTED 2026-07-04)

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
- THIRD AMENDMENT 2026-07-04 per verification pass #3 (one minor
  blocker + one advisory, both fixed): new I12 rewords the two
  surviving valve-vocabulary sentences in the `orchestrate` "Human
  valve actions" paragraph ("human-TRIGGERED valve commands" →
  "human-TRIGGERED operator commands"; "The valve-action behavior"
  → "The operator-action behavior"), and B4 now also rewords its
  adjacent gloss to "(the authoritative gate + valve contract is
  §…)".
- FOURTH AMENDMENT 2026-07-04 per verification pass #4 (one minor
  blocker, applied by the overseer inline): new I13 rewords the
  unparenthesized twin of B4's gloss — the §"Dispatcher grooming
  behavior" closing sentence "The authoritative valve contract is
  §…" becomes "The authoritative gate + valve contract is §…".
  Next action: fresh independent re-verification pass #5 (scoped);
  only after a no-blockers verdict does the maintainer-authorized
  ratification chain run.
- Post-ratification follow-up candidates recorded by pass #3
  (deliberately NOT folded into the proposal):
  1. Surface names retaining "valve" as NAMING — the contracts
     "Human valve actions" label, Scenario 31's H2/Feature line,
     and the "operator valve surface" phrase — eligible for a
     rename in a follow-up, deliberately not churned now.
  2. §"Consent boundary" machine-path list stays cross-referenced
     rather than extended.
  3. Scenario 10/23 heading-coverage `reason` texts still narrate
     hold-at-valve — accurate for the shipped tests until the
     rework slice lands; refreshed then.
- **GATE 1 FULLY EXECUTED 2026-07-04.** After five verification
  passes (the final one returning no blockers on the four-times-
  amended proposal), the maintainer RATIFIED the replacement. The
  accept revise cut `SPECIFICATION/history/v029/` and landed via
  PR #303 (merge `b55ecc1`): all 46 replace-edits applied
  (exactly-one-match asserted per target), the new "## Work-item
  state semantics" section with the intent-preservation clauses,
  the `admission_policy` invariant, the policy-edit operator
  actions, and the `tests/heading-coverage.json` co-edit (new
  entry with tier-acknowledging TODO reason; three retitled
  scenario headings + Scenario 10's `clauses[].scenario`;
  Scenario 31 / Dispatcher-admission reasons refreshed; Scenario
  10/23 test bindings kept for the rework slice). `just check`
  green (54 targets).
- **Rework slice EXECUTED.** `bd-ib-7cpgeh` ("Rework approve: to
  pending-approval→ready + implement set-admission:/set-acceptance:
  policy-edit actions") — filed via the consented capture seam on
  the ratification authorization, routed `ready` by the intake
  Definition-of-Ready checklist (admission `auto`), factory-
  dispatched (`orchestrate run --action impl:bd-ib-7cpgeh`), merged
  green via PR #305 (merge `9503866`, released as v0.9.0), AI
  acceptance pass run, parked at `acceptance`, and human-leg
  accepted to `done` via `orchestrate run --action
  accept:bd-ib-7cpgeh` (journaled) on the directive's "merge and
  closure" authorization. The pass-3 follow-up candidate (3) —
  Scenario 10/23 heading-coverage reasons — was resolved by the
  slice itself (it re-bound the scenario tests).
- Verifier advisory 6 (the `livespec_runtime` invariant gloss
  divergence) is RESOLVED as moot by the second amendment: the
  proposal now keeps the "(the structural grooming gate)" gloss
  byte-verbatim, matching both the design record and the runtime's
  ratified twin (repo `thewoolleyman/livespec-runtime`) — no
  runtime-side follow-up is needed for this gloss.

## Gate 2 — Workstream C: backlog re-triage (EXECUTED 2026-07-04)

The maintainer approved execute-as-drafted (including the two flagged
items: `bd-ib-cur` with the auto-normalize choice fixed in its journal
comment; `bd-ib-webwai` newly unblocked). Executed one item at a time,
re-reading each item's live state first — all 20 table premises held
(every item still `backlog`), so there were ZERO skips:

- 10 → `pending-approval`: `bd-ib-3m44nx`, `bd-ib-9ch`, `bd-ib-cur`,
  `bd-ib-h55`, `bd-ib-hkzcfb`, `bd-ib-ls32yb`, `bd-ib-mwz`,
  `bd-ib-umno37`, `bd-ib-v5n`, `bd-ib-webwai`.
- 3 → `blocked`: `bd-ib-ss7rkr` + `bd-ib-w4iaaf`
  (`blocked-reason:needs-human`), `livespec-impl-beads-zsl`
  (`blocked-reason:infra-external`).
- 7 stay `backlog` (no writes): `bd-ib-82a`, `bd-ib-k5p`,
  `bd-ib-un226z`, `bd-ib-z2ctra`, `livespec-impl-beads-29f`,
  `livespec-impl-beads-bqq`, `livespec-impl-beads-zbl`.

Every write is journaled as a comment on the item naming the actor
and the table's reason. Note: the draft's summary tally line said
"11 → pending-approval · 6 stay backlog", but its table rows
enumerate 10 → pending-approval and 7 stays — the per-row
dispositions are the approved record and were executed as drafted;
the tally line simply miscounted. See the execution record appended
to `research/backlog-retriage-draft.md`.

## Read-first chain

1. `plan/lifecycle-front-end-retrofit/research/track-reasoning.md` —
   why this shape; filing-time decisions; the (now obsolete) interim
   mechanism rationale.
2. `plan/lifecycle-front-end-retrofit/research/backlog-retriage-draft.md`
   — the gate-2 disposition table.
3. `SPECIFICATION/history/v029/proposed_changes/approval-is-the-pending-approval-to-ready-transition.md`
   — the gate-1 replacement proposal, RATIFIED at v029 with its accept
   revision file beside it (the original was rejected at
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
