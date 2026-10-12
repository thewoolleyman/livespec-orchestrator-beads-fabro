# Ledger writers are multi-host — never fence ledger writes on the host

This note records a maintainer ruling and the measurements behind it. It
exists because the host this repository runs on makes a single-host
assumption look measured rather than assumed: the tenant's Dolt server
listens on `127.0.0.1:3307` only, and `.beads/config.yaml` pins
`dolt.server-host: 127.0.0.1`. Both of those are configuration TODAY, not
design constraints.

## The ruling (maintainer-declared 2026-10-12)

> The assumption that writes only occur from a single host is invalid. Beads
> is a server, and it's exposed as a DOLT server. There may be writes in the
> future from multiple hosts or multiple containers or cloud instances. There
> may not even be a shared state where places are writing to beads.

So any coordination between ledger writers must be enforced INSIDE the Beads
server, through the public `bd` surface. None of the following can fence
ledger writes: a kernel lock, a lockfile, an abstract socket, a host-root
ownership directory, a per-host singleton service, or anything else that
lives on one machine.

*Cost of missing this, 2026-10-12:* two plan sessions converged on a
host-scoped fence in the same morning. One was the relay plan's research
note 004, Option A. The other was the stall plan's draft amendment to
`SPECIFICATION/constraints.md` §"Process boundaries". Both rested on the
loopback listener as "the measured topology". Both were withdrawn the same
day, and the preserved `bd-ib-zi5ygh` artifact's abstract-socket lock is
invalid for the same reason.

## What the installed `bd` (v1.2.2) actually guarantees under concurrency

Each of these was measured with owned disposable records and separate
processes released at the same instant. Full methods and sources are in
`plan/relay-delivery-and-progress-deadline/research/004-serialization-under-installed-beads-2026-10-12.md`
and `005-cross-host-serialization-by-conditional-close-2026-10-12.md`.

- **`bd update --metadata` is a client-side read-modify-write.** Two
  concurrent writers of DIFFERENT top-level keys lost one key in 3 of 12
  trials, and both exited 0. Distinct keys do not make metadata writes safe.
- **`bd comments add` is an insert.** 30 of 30 concurrent appends survived.
  But read order is `created_at` at one-second resolution, not commit order.
- **`bd close <id> --reason <r>` is a server-enforced compare-and-swap**
  (`UPDATE … WHERE status != 'closed'`, with `close_reason` written in the
  same statement). In 20 trials of 4 concurrent closers, exactly one reason
  won every time. **The exit code does NOT name the winner.** A loser exits 0
  when its update matched no row, or exits 1 with Dolt `Error 1213`. Read
  `close_reason` back to learn who won.
- **`bd update --claim` is also a server compare-and-swap, but it is
  unusable here.** The lifecycle guard at `/usr/local/bin/bd` refuses it on
  every record, and it needs the native `open` status, which the conformant
  store never holds.
- **Creating a record with an explicit id is an upsert, not an exclusion, and
  it REOPENS closed records.** A second `bd create --id X` on a closed X exits 0
  and resets it to `backlog`, erasing `close_reason` and replacing the title.
  Concurrent duplicate creates all exit 0. Never use `bd create --id <fixed>` as
  a "first creator wins" step, and never re-create a record whose close carries
  meaning (research note 007 of the relay plan).

## How to apply

Before proposing any design that serializes or fences ledger writers, state
in one sentence which SERVER-SIDE operation enforces the exclusion. If the
answer names a file, a socket, a process, a host or a directory, the design
is wrong for this fleet, however well it tests on one host.
