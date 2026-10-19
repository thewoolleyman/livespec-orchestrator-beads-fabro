# `work-supply` host timer

Committed unit TEXT for the clock-fired supply of ready work to the factory,
one timer instance per tenant repository. Installing it on a host is a separate
operator action; nothing in this repository installs it.

Governing contract: `SPECIFICATION/contracts.md` §"Dispatcher loop invocation
surface" → "Clock-fired work supply". Governing scenario:
`SPECIFICATION/scenarios.md` §"Scenario 201".

## Why a timer

The drain is an engine somebody has to run, and until this timer existed that
somebody was whichever interactive session happened to be open. Measured
2026-10-13 on hp: the fleet Fabro server (cap 10) received no new
`ImplementWorkItem` run between about 18:27Z and 22:56Z. For roughly four and a
half hours there were zero runs in flight, the Claude credential probe reported
`usable`, and dispatch-ready work existed. No dispatcher or drain engine process
was running on the dev host, and dispatch resumed only when some session started
an engine again.

Each firing starts ONE ordinary unattended drain pass — `loop --repo <tenant>
--budget <n>`, with no `--item`. It is governed by the ranked queue, `wip_cap`,
every admission condition and the fail-closed unattended cost gate exactly as
any other unattended drain. The timer adds nothing to those and relaxes none of
them; all it changes is who starts the engine.

## Install

One invocation per tenant:

```bash
sudo ./install.sh --repo /data/projects/livespec-orchestrator-beads-fabro --interval 30min
```

`--interval` defaults to **30min** and is REFUSED below the documented minimum
of **10min**; `--budget` defaults to `3`; `--instance` defaults to the basename
of `--repo`. A span is `<positive integer><unit>` with unit one of
`s`/`sec`/`m`/`min`/`h`/`hr`/`hour` — a deliberately narrow subset of systemd's
time-span grammar, so a span this installer cannot measure is refused rather
than guessed.

The installer REFUSES (exit 78) in three cases, each naming the instance:

- the project env wrapper is not an executable file on the host — without it
  every pass runs `bd` with no `BEADS_DOLT_PASSWORD` and fails as `Access
  denied` / `no beads database found`, which reads as an absent tenant rather
  than an absent credential, on the interval, for ever;
- the interval is below the minimum, naming the interval given and the minimum;
- the interval is outside the grammar above.

Set `LIVESPEC_ENV_WRAPPER` when a host keeps the wrapper somewhere other than
`/usr/local/bin/with-livespec-env.sh`. `UNIT_DIR`, `INSTANCE_ENV_DIR` and
`DRY_RUN=1` exist for rehearsal and for this repository's own tests.

### Why the interval minimum, rather than a lock

Two concurrency defects live under this timer: `wip_cap` is not exclusive
across engines admitting in the same instant (`bd-ib-2vda`), and a sibling
engine's reconcile can cancel a just-launched re-dispatch (`bd-ib-m1av`), whose
stamp window is roughly forty seconds. The ratified contract deliberately adds
no exclusion between concurrent passes and licenses no host-scoped admission
lock — a host-scoped fence is invalid here, because ledger writers are
multi-host (`.ai/ledger-writers-are-multi-host.md`). Keeping firings far apart
is therefore the remedy available at this layer; a real exclusion belongs in
the ledger, under §"Per-repo WIP cap".

## What gets installed

| path | per | what it is |
| --- | --- | --- |
| `<unit-dir>/work-supply@.service` | host | the rendered service template |
| `<unit-dir>/work-supply@.timer` | host | the timer template, carrying **no** interval |
| `<unit-dir>/work-supply@<instance>.timer.d/interval.conf` | instance | the operator's interval |
| `<instance-env-dir>/<instance>.env` | instance | tenant checkout, budget, wrapper |

The timer template carries no interval on purpose. A systemd timer template
cannot vary a timer setting per instance, and leaving the setting out makes a
missing drop-in LOUD: systemd refuses a `[Timer]` with no value setting, so an
instance whose drop-in never landed fails at `daemon-reload` in front of the
operator. Had the template carried a default `OnBootSec`, that instance would
have loaded, fired once after boot, and never fired again — a silent
single-shot that reads exactly like a working timer.

## The build each firing executes

The service names **no** plugin build. `work-supply-pass.sh` resolves the
tenant's registered project-scoped install from the Claude Code plugin registry
(`~/.claude/plugins/installed_plugins.json`, the entry whose project path is the
tenant) at the moment it fires, and executes that build's
`scripts/bin/dispatcher.py`. So the next firing after a release runs the
released build with nothing reinstalled.

When the tenant has no registered install — or the registry cannot be read, or
the registered build carries no dispatcher entry point — the firing REFUSES
(exit 78), names the tenant, and starts nothing. It never falls back to a build
pinned at install time or to a guessed path: that fallback is how a host
silently keeps running a retired build, which is the stale-build trap
`AGENTS.md` records against long-lived sessions.

## Why a pass does not block the next firing

`dispatcher.py loop` blocks until its wave's post-verdict stages finish, which
is hours for one wave, and systemd never starts a `Type=oneshot` service that is
still active. The service's `ExecStart` is therefore the launcher, not the
drain: the launcher hands each pass to its own `systemd-run --collect` transient
unit — named per firing, with no `--wait` — and returns in under a second. The
timer's `OnUnitActiveSec` is measured from that activation, so capacity that
frees during a long pass is offered to ready work within one interval. An
overlapping pass is an ordinary concurrent unattended drain, bounded by
`wip_cap` as any other is.

No wall-clock ceiling is imposed on a pass. The pass is bounded by its
`--budget` and by its own terminal disposition; a timing bound that killed it
mid-flight could interrupt protected work — an active commit or an open
Red-Green pair — which `SPECIFICATION/constraints.md` §"Process boundaries"
forbids a timing bound from doing. A pass that dies anyway leaves its claims to
the ratified stranded-claim release.

## Verify

```bash
systemctl list-timers 'work-supply@*' --no-pager
journalctl -u 'work-supply@<instance>.service' -n 50 --no-pager
systemctl list-units 'work-supply-pass-*' --no-pager
journalctl -u 'work-supply-pass-<instance>-*' -n 200 --no-pager
```

The first two show the firings; the second two show the passes those firings
started. Each firing's own journal line names the tenant, the resolved build,
the budget and the transient unit it started, so a firing that resolved a stale
build is distinguishable from one that never ran.
