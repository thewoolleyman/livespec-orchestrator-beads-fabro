## Why this charter amendment exists

On 2026-11-03 livespec-dev-tooling-xllgai, the Hetzner track's only factory blocker, sat READY and unticketed for about two hours. Its owning seat is Codex, which cannot SendMessage, so its pickup requests went into ledger comments nobody read, and nothing detected a ready item with no ticket. The maintainer's words (recorded on epic livespec-dev-tooling-6tgd2z): "Ensure there is a permanent fix for this: the dispatcher couldn't see them either. It wasn't skipping Hetzner work; the item never reached it."

## Charter additions (this seat)

1. **Unticketed-ready sweep, every pass.** Sweep the READY items of every plan on the coordinator's latest priorities-record, across every fleet tenant, using the list-work-items projection per tenant and the union of the plans' children. For each READY item with no ticket in the gmktec launch queue, no launcher or resume waiter, and no seq log, either ticket it at its plan's priority or record the exact refusal on the item and message legacy-coordinator-agent at once. The seat's mechanical form is `tmp/petri-canary/sweep-ready.sh`, which prints `UNTICKETED-READY <tenant> <id> <status> | <title>` lines.
2. **Request channel any seat can use, Codex included: the ledger label `dispatch:requested`.** Scan for it every pass (the same script prints `REQUESTED` lines). Ticket the item, or write the refusal as a comment on the item, then remove the label.
3. **Readable tenants.** The sweep reads the orchestrator, dev-tooling, overseer, driver-codex and driver-claude ledgers. The hetzner-xubuntu-info tenant needs scoped AWS credentials this seat does not hold, so its ready items reach the seat only through the coordinator, and the sweep reports it UNREADABLE rather than silently omitting it.
4. **The coordinator's own flag.** legacy-coordinator-agent adds a deterministic UNTICKETED-READY flag to scripts/coordinator/fleet-utilization.sh, so the check does not depend on either seat remembering.

## Loop prompt added to this seat

`legacy-dispatcher-agent pass: re-arm throughput-watch Monitor if not running (TaskList); order queued tickets by the latest priorities-record on livespec-dev-tooling-6tgd2z; read live vs fleet-cap/gmk-cap and queue depth; report endings to owners; on a stall, name the serializer and message legacy-coordinator-agent; run tmp/petri-canary/sweep-ready.sh: ticket or record the refusal for every UNTICKETED-READY item of a plan on the latest priorities-record, and handle every REQUESTED (dispatch:requested) item, then remove the label`

## First measurement

The first sweep (2026-11-03 16:38Z) found 104 READY items with no ticket: 53 orchestrator, 27 overseer, 12 dev-tooling, 8 driver-claude, 4 driver-codex. Most are backlog outside the plans on the priorities record. The sweep does not yet join plan membership, so a pass triages by title and by the priorities record. One of them, livespec-dev-tooling-4rcuxp (disk retention), was a plan item a seat was waiting on; it was ticketed at once.
