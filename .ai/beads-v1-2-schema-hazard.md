# Beads v1.2.0 / v1.2.1 schema hazard and upgrade traps

Moved word for word from `AGENTS.md` §"Beads runtime prerequisites" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

**NEVER install beads v1.2.0 or v1.2.1 — a single invocation strands every
tenant on the shared server.** Upstream published both **by accident on
2026-08-11 without release testing**. Running the v1.2.1 binary **even once**
migrates the database schema from **v53 to v65**, after which every v1.1.2 /
v1.2.2 binary refuses with `schema version mismatch: database is at v65, binary
knows up to v53`. Upstream's recovery guidance assumes a local single-clone
database; **we run a shared multi-tenant Dolt server**, so one invocation
against a shared tenant strands that tenant for every client in the family —
currently **14 live tenants**. v1.2.1 is marked prerelease rather than
withdrawn, so it is **still downloadable**: this is a live hazard, not history.
The current stable is **v1.2.2**, which is a recovery release re-issuing the
tested 1.1 line. **This host's `/usr/local/bin/bd-real` was cut over to v1.2.2
on 2026-08-31 and every family tenant is at schema v53** (receipt:
`plan/archive/beads-v1-1-2-upgrade/research/cutover-receipt-2026-08-31.md`). Two facts
from that cutover that bite any future upgrade: `bd migrate --dry-run` is NOT a
preview — a v1.2.x binary migrates an older store ON OPEN, before printing
"Version matches" — so probe an un-migrated tenant only through mysql, never
through any `bd` verb; and a fleet pause must stop the ROOT system timer
`reconcile-runs.timer` (`systemctl list-timers --all`, system AND user manager),
which reads this repo's ledger every ten minutes and auto-migrated this tenant
mid-cutover. That attribution came from the SUDO JOURNAL, which is the
instrument for "which process touched a tenant": every `with-*-env.sh` wrapper
call re-execs through `sudo`, so `journalctl --since <t1> --until <t2>
-o short-iso _COMM=sudo | grep 'PWD=/data/projects/<repo>'` lists each call
with its full command, and `-o verbose` adds the owning `_SYSTEMD_UNIT`; the
Dolt server's own journal logs nothing per connection. If a database has already been migrated to v65, do NOT
improvise: roll the schema cursor back per upstream's `docs/RECOVERY-1.2.1.md`
(at tag v1.2.2), use `BD_IGNORE_SCHEMA_SKEW=1` only as a stopgap, and upgrade
**every** clone before recovering — a leftover v1.2.1 binary silently
re-migrates. Measured 2026-08-20: nothing in this repo or the eleven sibling
repos resolves a beads version dynamically, so the exposure is human, not
mechanical. Full evidence:
`plan/archive/beads-v1-1-2-upgrade/research/release-target-restatement-2026-08-20.md`;
ledger item `bd-ib-3kolea.4`.
