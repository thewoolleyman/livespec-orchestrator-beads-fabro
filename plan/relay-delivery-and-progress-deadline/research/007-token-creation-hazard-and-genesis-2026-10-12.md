# Token creation hazard and chain genesis

Written 2026-10-12 by the relay session (Claude Code, session
`relay-delivery-and-progress-deadline`). The maintainer accepted the
epoch-token direction of research notes 005 and 006 on 2026-10-12 ("I have
no objections to this direction. Continue autonomously."). This note settles
the two design facts that still had to be decided before the work could be
filed.

## Measurement: a duplicate explicit-id create resets a closed record

Method. The probe used owned disposable records through the public guarded
`bd`, run under `with-livespec-env.sh`. All of them were deleted afterwards.
Probe SHA256 prefix `07c8fe97e3cf08ab`. For both a `--no-history` record and
a regular record, it ran four steps:
1. `bd create --id X` (title "first");
2. `bd close X --reason WINNER`;
3. `bd create --id X` again (title "second");
4. three concurrent `bd create --id Y` calls for a fresh id Y.

Result, the same for both kinds:

| Step | Exit | Record afterwards |
| --- | --- | --- |
| first create, then close | 0, 0 | `closed`, `close_reason` "WINNER", title "first" |
| duplicate create of the closed X | **0** | **`backlog`, `close_reason` null, title "second"** |
| three concurrent creates of Y | 0, 0, 0 | one row, `backlog`, title of whichever create landed last |

A duplicate explicit-id create is an upsert that **reopens a closed record
and erases its close reason**. It exits 0 and prints no warning, and
concurrent duplicate creates all report success. In a token chain, a late
create of an already-closed token's id would therefore reopen it and allow a
second winner, destroying the committed transition.

Two rules follow:

1. **Tokens are created ONLY with server-assigned ids** (`bd create` with no
   `--id`), and are never re-created. The 60-transition prototype in note 006
   already created tokens this way.
2. **No step may derive a token's id from an epic id, an operation id or any
   other value.** Nothing about explicit-id creation is exclusive.

## Genesis: who creates an epic's first token

Each transition is made safe by closing the CURRENT token. The very first
token, the genesis, has no predecessor to close, and the measurement above
rules out a deterministic-id "create if absent". So genesis must happen at a
point where only one writer can exist:

- **New plan epics.** `create_thread` creates the genesis token, with a
  server-assigned id, and the epic in the same call. The epic's id is fresh
  and unknown to any other party until that call returns, so the genesis is
  single-writer by construction. The epic's metadata records the genesis
  token id.
- **Existing live plan epics.** A sanctioned migration operation
  (`migrate_plan_records` already exists as the plan-record migration verb)
  creates the genesis token and records it. The migration is a deliberate
  operator act, run once per epic, so it is the "next sanctioned write that
  supplies the required fields" for a legacy pointer.
- **Every other sanctioned writer** (`append_handoff`,
  `append_supervisor_handoff`, `set_next_action`, the relay primitives) NEVER
  creates a genesis token. On a live epic with no chain, the writer keeps
  today's legacy behaviour: the pointer stays readable, a missing-tracking
  finding is reported, and the finding names the migration as the remedy.

The residual risk is two operators migrating the same epic at the same
moment, which would produce two genesis candidates. The migration narrows
this by refusing any epic whose metadata already names a genesis token and
by reading its own write back. Readers also check every payload's
prior-token link, so a fork in the chain is reported, and dispatch is
withheld until it is resolved. A fork is never silently followed.

## Consequences for the filed work

- The `BeadsClient` seam gains three verbs: a no-history create that returns
  the server-assigned id, a delete, and a close that reports nothing about
  the winner (the caller must read `close_reason` back).
- The in-memory fake must model the server faithfully. Its close must be
  conditional (a closed record keeps its first close reason), and its
  duplicate explicit-id create must reopen the record as the real server
  does, so tests can exercise the hazard rather than hide it.
- Sanctioned writers never call an explicit-id create for any token.
