# Cross-host per-epic serialization through the public conditional close

Written 2026-10-12 by the relay session (Claude Code, session
`relay-delivery-and-progress-deadline`). This note supersedes the
recommendation in research note 004.

## The maintainer ruling that reopened the question

On 2026-10-12, after reading note 004, the maintainer ruled:

> The assumption that writes only occur from a single host is invalid. Beads
> is a server, and it's exposed as a DOLT server. There may be writes in the
> future from multiple hosts or multiple containers or cloud instances. There
> may not even be a shared state where places are writing to beads.

That ruling removes every design whose fence lives outside the Beads server:
a kernel lock, a lockfile, a host-scoped ownership root, or a sibling-service
singleton. Note 004's Option A is one of these, and so is the host-ownership
proposal the stall plan had drafted. Both are withdrawn. The stall session was
told this the same day and told to continue its unaffected work. The only
state every writer shares is the Beads Dolt server. So per-epic serialization
must be enforced by the server, through the public `bd` surface.

Note 004's measurements still stand. Concurrent distinct-key metadata writes
silently lose updates, and concurrent comment appends all survive. Only its
topology argument and its recommendation are withdrawn.

## Which public writes are conditional at v1.2.2

The storage layer of exact upstream `6c124203e771433a3550c348771a5b5e27fd3c21`
was searched for every conditional `UPDATE`, `INSERT IGNORE` and
`ON DUPLICATE KEY` statement. Two writes reachable from the command line are
genuine compare-and-swap operations on one row. A compare-and-swap writes only
if the row still holds the value the caller expects, and reports whether it
did.

| Public write | Server-side condition | Usable here? |
| --- | --- | --- |
| `bd update --claim` (`issueops/claim.go`) | `UPDATE … SET assignee, status='in_progress' WHERE id=? AND status='open' AND assignee is empty or the caller` | No. The installed guard `/usr/local/bin/bd` refuses `--claim` on every record. Every create is forced to `backlog`, so the native `open` status it requires never exists. Using it would change fleet guard and conformance policy. |
| `bd close <id> --reason <r>` (`issueops/close.go`) | `UPDATE … SET status='closed', closed_at, updated_at, close_reason=? WHERE id=? AND status!='closed'` | Yes. `closed` is a lifecycle status, and the guard passes `close`. The reason is written in the same statement as the status change, and a loser matches zero rows and so cannot overwrite it. |

Every other conditional statement found is an idempotent insert or upsert. An
idempotent write succeeds again when repeated, so it cannot exclude a second
writer. Labels, dependencies, child counters and comment de-duplication are
all of this kind. Creating a record with an existing explicit id is an
upsert, so explicit-id creation must never be used as an exclusion.

## Measurement: concurrent closers of one token

Method. Each trial created a fresh owned disposable record with
`--no-history`. The guard forced each one to `backlog`, and the commit
messages show that `--no-history` records are wisps. Four separate processes
were released at the same instant, each running
`bd close <token> --reason <unique op id> --json`. Each process then read the
record back with `bd show --json` and recorded whether `close_reason` was its
own. After all four finished, the parent read the final `close_reason`. Every
token was deleted afterwards, and `bd show` exits non-zero for all of them.
All calls went through the public guard, run from the tenant root under
`with-livespec-env.sh`. Probe SHA256: `bd577b1c…bb04` (driver) and
`64836601…ac26` (contender).

Result, over 20 trials of 4 contenders each:

- Every token ended `closed` with exactly one contender's reason.
- In **no trial did more than one contender read back its own reason**, and
  the contender that did always matched the final value. There were 0
  mismatches of either kind, counting both the reason read back and the
  reason the CLI reported.
- Losers took one of two paths. Sometimes the conditional `UPDATE` matched
  zero rows and the CLI returned 0 with the record already closed. Other
  times Dolt rejected the losing transaction at commit with
  `Error 1213 (40001): serialization failure: this transaction conflicts with
  a committed transaction from another client`, and the CLI exited 1. Of the
  80 closer exits, 22 were non-zero. The exit-code patterns per trial were
  `0,0,0,0` (4 trials), `0,0,0,1` (10) and `0,0,1,1` (6). **The exit code
  does NOT identify the winner, so the winner must always be established by
  reading `close_reason`.**

Positive control for the harness. Note 004's distinct-key probe used the same
release-and-read-back shape and did detect lost updates (3 of 12), so this
harness can see a double write when one happens.

Limit. All contenders ran on this host, because the tenant's server listens
on loopback today. The exclusion is enforced inside the server, by the
conditional statement and by Dolt's commit-time conflict check, and neither
depends on the client's host. A released proof from two genuinely separate
hosts or containers is still owed before anyone claims cross-host behavior
was observed.

## Design consequence: an epoch-token chain

Model each per-epic authority transition as the close of a single-use token:

1. The current epoch E is represented by one open token record. The epic's
   authority is whatever the closed token chain says. The epic metadata
   `next_action` and progress comment become projections (caches) of that
   chain.
2. A writer first reads the current token E, then validates its transition
   against the state E implies. That covers the budget, the original
   deadline, the causal-recovery rules and stale-epoch checks. It then
   creates its own candidate token for E+1, with a server-assigned id and
   never an explicit one. Finally it closes token E with
   `--reason <transition payload>`. The payload carries the operation id, the
   prior epoch, the new authority and the candidate token id for E+1.
3. The writer reads token E back. Its own operation id in `close_reason`
   means it won: the transition, its receipt and the identity of the next
   token were all committed in one server statement. Any other reason means
   it was a stale writer. It is refused before any authority changes, it
   closes its own candidate token as unused, and it reports the winner.
4. A retry with the same operation id reads token E. If E carries that
   operation id, the original event is returned and no deadline moves.
5. A crash before the close changes nothing. A crash after the close leaves
   the transition durable while the projections lag. The partial write is
   then visible as a closed token whose payload is not yet reflected in
   `next_action`. Any reader can reconcile it deterministically from the
   chain, and dispatch is withheld until it does. This is exactly the
   contract's "A partial write MUST be diagnosable and must not authorize a
   fresh dispatch until reconciled."
6. A lost update to a projection only makes it stale or behind. Readers
   verify the projection by walking forward from the cached token to the
   first open token.

What this satisfies, measured against the ratified text:
- "Writes MUST serialize per epic and detect a stale prior epoch before
  mutation" is enforced by the server, for any number of hosts.
- No plugin lockfile or advisory lock is introduced, so `constraints.md`
  §"Process boundaries" is kept as written.
- There is no direct plugin SQL, no daemon and no Beads change.
- The tenant database stays the only authoritative store.

The same primitive can give the stall plan's "serialized generation-fenced
ownership" of a recovery attempt. Closing a per-attempt token is the claim. A
crashed claimer is superseded only by a NEW attempt after the bounded
attempt deadline, never by stealing the old attempt. That plan's owner
decides whether to adopt this; this note does not assign them any work.

## Open questions before implementation

- **Token storage.** The probe's tokens were wisps. `bd purge` deletes closed
  ephemeral records, which would erase chain history. Permanent task records
  go from `backlog` to `closed`, which conforms to the lifecycle, but they
  would have to be kept out of `next`, `list-work-items` and plan-child
  enumeration. Choose one and measure it.
- **Payload size.** The capacity of `close_reason` for a transition payload
  is not yet measured. The payload could instead carry a digest plus a native
  comment.
- **Read cost.** Chain walks are bounded by the projection cache. This is not
  yet measured.
- **Specification.** The ratified clauses appear to be satisfied without
  amendment. Whether the token chain needs its own normative description is a
  question for the propose-change step, not a decision made here.
- **Released proof.** Cross-host contention needs released two-host proof,
  as described above.

## Effect on the backend question and on `bd-ib-zi5ygh`

Beads PR 1 should stay closed. Even under the multi-host requirement, the
installed public surface already supplies the server-enforced
compare-and-swap that PR 1 was adding. That is the evidence the maintainer's
closure asked for, and it points away from a Beads change.

The abstract-socket lock in the preserved `bd-ib-zi5ygh` artifact is a
host-scoped fence, so this ruling invalidates it outright, not merely as a
matter of policy. Its other recorded defects remain owed.
