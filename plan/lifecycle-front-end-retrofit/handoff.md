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

- A1 `bd-ib-r3vsnd` — PR #264 (`ac0b477`): intake-DoR routes filed
  items into lifecycle STATES; label stamps retired; gap-capture
  hardcode fixed.
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

## Open gate 1 — Workstream B: proposal ratification (maintainer)

- Artifact:
  `SPECIFICATION/proposed_changes/pending-approval-to-ready-structural-gate-ownership.md`
  — `pending-approval → ready` is the structural grooming gate only;
  all human permission at the admission valve (Scenarios 23/31
  unchanged).
- Next action: the MAINTAINER runs `/livespec:revise` against
  `SPECIFICATION/` and accepts or rejects the proposal. Do not
  self-revise from a track session.
- If accepted: verify whether the capture routing needs a follow-up
  (an effective-`manual` DoR-passing item would then also proceed to
  `ready` instead of resting at `pending-approval`); file any follow-up
  via `capture-work-item`.

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
3. `SPECIFICATION/proposed_changes/pending-approval-to-ready-structural-gate-ownership.md`
   — the gate-1 proposal.

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
