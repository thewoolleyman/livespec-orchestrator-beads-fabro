# lifecycle-front-end-retrofit — handoff

Single resumable execution-coordination point for this thread. A fresh
session should read THIS file, then the read-first chain below, and can
then execute the next action without consulting chat history.

## Thread anchor

- Ledger epic: **`bd-ib-ew7bdv`** (bd-ib tenant). Children (via
  `parent-child` edges): `bd-ib-r3vsnd` (A1), `bd-ib-h2tnil` (A2,
  `blocks`-edge on A1), `bd-ib-q3x6va` (A3).
- Status is DERIVED, never stored here. Compose it read-only:

  ```bash
  cd /data/projects/livespec-orchestrator-beads-fabro
  /data/projects/1password-env-wrapper/with-livespec-env.sh \
    bd show bd-ib-ew7bdv bd-ib-r3vsnd bd-ib-h2tnil bd-ib-q3x6va --json
  ```

  plus `/livespec-orchestrator-beads-fabro:next` for the ranked view.

## Read-first chain

1. `plan/lifecycle-front-end-retrofit/research/track-reasoning.md` —
   why this shape: the verified front-end/label-triage drift, the
   approved A1/A2/A3 cut, filing-time decisions (parent-child edges,
   policies, the sanctioned interim status mechanism).
2. `plan/lifecycle-front-end-retrofit/research/backlog-retriage-draft.md`
   — Workstream C DRAFT disposition table. NO status writes until the
   maintainer approves it.
3. `SPECIFICATION/proposed_changes/pending-approval-to-ready-structural-gate-ownership.md`
   — Workstream B filed proposal (pending-approval → ready is the
   structural grooming gate; admission is the sole approval act).
   Ratification via `/livespec:revise` is a MAINTAINER gate — do not
   self-revise.

## Next action

Dispatch the slices through the factory SEQUENTIALLY — never hand-code
them inline in a planning session:

1. Flip the slice being dispatched to `ready` status (the sanctioned
   INTERIM mechanism — today's `next`/dispatch ranks `ready`-STATUS
   items and the valve surfaces don't exist until A3 lands; record each
   flip in the work-item's notes/journal):

   ```bash
   /data/projects/1password-env-wrapper/with-livespec-env.sh \
     bd update bd-ib-r3vsnd --status ready
   ```

2. `/livespec-orchestrator-beads-fabro:orchestrate` →
   `run --action impl:bd-ib-r3vsnd` (A1 first).
3. After A1 merges + closes: same for A2 (`bd-ib-h2tnil`). A3
   (`bd-ib-q3x6va`) is independent and may dispatch in any free slot.
4. After each merged PR: pull the primary checkout, remove the
   dispatch worktree if one was created locally, verify clean master.
5. When A1–A3 are all `done`: close the epic through the ledger and
   archive this thread (`git mv plan/lifecycle-front-end-retrofit/
   plan/archive/lifecycle-front-end-retrofit/`).

Maintainer gates outstanding (surface, do not self-approve):

- Workstream C disposition table approval (then execute dispositions
  one at a time, re-reading live state first).
- Workstream B proposal ratification (`/livespec:revise`).

## Binding constraints

- Repo mutations: worktree → PR → rebase-merge; worktrees only under
  `~/.worktrees/livespec-orchestrator-beads-fabro/<branch>`; always
  `mise exec -- git …`; never `--no-verify`.
- Product `.py` changes follow the red-green-replay commit protocol
  (factory-side for these slices).
- Beads only via the wrapper
  `/data/projects/1password-env-wrapper/with-livespec-env.sh`; secrets
  probe-only.
- Operate only in worktrees/branches this track creates; never touch
  another session's branch. Carry this fence into every dispatched
  brief.
- The shipped groom/capture skills still implement the OLD label
  workflow (what this track fixes) — do not rely on their
  needs-regroom machinery while managing this epic.
