# Factory monitor — standing operating charter

Created 2026-09-10 as a deliberately long-running operations thread. This is not a finite delivery plan and must not be archived merely because the factory is currently healthy or because one incident is resolved. It remains live until the maintainer explicitly retires the monitoring function and names its successor.

## Mission

Continuously watch the Fabro factory and the work flowing through it, detect regressions and outages quickly, declare incidents immediately, triage from evidence, restore the normal path autonomously, and retain a durable timeline on the plan epic. Primary evidence comes from correctly targeted Fabro state, dispatcher and host logs, GitHub state where applicable, and Honeycomb observability. The session minimizes model spend by making mechanical probes programmatic and delegating bounded review to cheap background agents; expensive reasoning is reserved for a changed or anomalous signal.

## Coverage

- Both declared factories, always queried explicitly: `hp` at `https://hp-xubuntu.perch-rudd.ts.net:32276` and `vps` at `https://vps.perch-rudd.ts.net:32276`. A bare local `fabro ps` is never evidence about either factory.
- Live, blocked, and terminal Fabro runs; run creation failures; unexpected cancellation or removal; stalls; repeated node visits; failed pins or invalid workflow graphs; provider, token, credential, GitHub App, model, storage, and sandbox failures.
- Dispatcher dispatch/reconcile journals, system and user timers, service health, factory-host disk and container pressure when indicated, current releases/plugin-cache currency, and master/PR checks when they are causal.
- Honeycomb triggers and SLOs first, then narrow recent-window span discovery and targeted queries. Reuse query results, start with the smallest useful time window, validate span and column identity before aggregation, and never burn tokens on repeated broad scans.
- Active work and known remediations across the family, correlated to current sessions through Teamux before attribution. Potential problems that have not yet become incidents are surfaced to the human.

## Low-cost monitoring loop

1. Run mechanical probes in background processes or cheap agents. Prefer small JSON snapshots and state-change detection over streaming full logs into model context.
2. Poll factory endpoints explicitly and compare current run state with the previous snapshot. Read only new journal/log lines since the last cursor. Check Honeycomb alert state and recent error/failure signals on a slower cadence, and query deeper only when a signal changes.
3. Keep the quiet healthy loop terse. Do not author repeated handoffs or research notes for unchanged state; the epic timeline records meaningful baselines, incidents, mitigations, root causes, and changed next actions.
4. While an incident is active, publish a status report at least hourly with impact, start time, evidence, owner/session if known, mitigation status, root-cause confidence, next action, and the next report deadline.

## Incident protocol

1. Declare the incident immediately in the active session when a verified breakage is seen. Record UTC time, impact/blast radius, affected factory/run/item, and the signal that fired. A suspected but unverified problem is raised to the human as a potential problem rather than silently normalized.
2. Stop the line for shared factory/tooling breakages. Do not reroute, pin around, blind a gate, or invoke a private fixed build to keep unrelated work moving. Recovery must return through the normal release, install, reload, dispatch, and verification path.
3. Triage with independent evidence: correctly targeted Fabro state plus logs/journal, Honeycomb where available, forge/ledger state, and host measurements when the named path proves the failure is remote. Validate that every negative instrument has a positive control and is pointed at the right population.
4. If a live session caused the regression, identify it by Teamux session name, notify that session immediately with the evidence and an instruction to fix or revert, and watch until the correction is merged, released/reloaded as required, and mitigation is verified on the normal path.
5. If no active session owns it or root cause remains unattributed, scan the complete ledger including closed work and read overlapping items/comments. Reuse an existing bug when one exists. Otherwise file one through `capture-work-item`, then start the appropriate remediation autonomously. Factory-safe fixes use the factory unless the factory itself or master health is the failure being restored.
6. Dead runs may be reaped only after the mandated full export is written to the owning item and verified through `bd comments ... --json` using the `text` key. Live-run removal remains human-gated unless another explicit rule authorizes it.
7. Mitigation is not closure. Continue watching through rollout and a post-fix proving interval; record root cause and prevention follow-up separately when needed.

## Existing related work — re-verify before relying on status

The 2026-09-10 opening survey found these live anchors: `bd-ib-qfv9` (factory/run correlation in Honeycomb), `bd-ib-cewr` (silent-failure surfaces), `bd-ib-2nq` (Fabro token-TTL fixes/rollout), `bd-ib-uy4lp7` (valid released workflow graph and plugin install), `bd-ib-jxvgq5` (per-node model fallback), `bd-ib-btr5do` (mechanically enforced factory usage), `bd-ib-wcuauj` (runaway containment), and `bd-ib-plhtmx` (credential-freshness redesign). Relevant standalone survivors include `bd-ib-i66q`, `bd-ib-3f79`, `bd-ib-m0t0`, `bd-ib-2vda`, `bd-ib-m1av`, `bd-ib-ebd0`, and `bd-ib-i7ag`. These are routing hints, not current truth; status, comments, forge state, and shipped build evidence must be re-read at incident time.

## Lifecycle and handoff

This epic is the incident and handoff anchor. Research files hold durable analysis only; no status queue or `handoff.md` is created. The plan has no ordinary archive-completion condition. An explicit maintainer retirement must transfer every active incident and monitoring obligation to named successor work before archive gates are even considered.
