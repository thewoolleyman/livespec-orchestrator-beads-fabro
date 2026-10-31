# Host Fabro server (self-hosted dark factory)

Moved word for word from `AGENTS.md` §"Host Fabro server (self-hosted dark factory)" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## Host Fabro server (self-hosted dark factory)

The Dispatcher's host-direct path (`dispatcher.py loop` run on the host, NOT in
the orchestrator container) connects to a long-lived Fabro server on
**`127.0.0.1:32276`**. Installing the plugin does NOT start it; the maintainer
runs it directly from `~/.fabro/bin/fabro`. Measured 2026-10-01: `hp` runs
`fabro 0.254.0 (8869e88 2026-10-01)`, the carrier tip, which carries the S4
ACP fallback chain (`bd-ib-mujvyn`, fork PR 9) and the in-protocol model and
effort selection (`bd-ib-afcn3d`, fork PR 10); S7a of plan `bd-ib-jxvgq5`
(`bd-ib-q32gs5`) deployed it with `fabro.4b8cc85-pre-s7.bak` retained. `vps`
is a RETIRED factory in the sense that it is absent from `.livespec.jsonc`
`factories` (`bd-ib-3ysb6k`, 2026-09-11), so no dispatch is routed to it.
**Its units are NOT stopped**, although this paragraph said so until
2026-10-23: measured that day, `fabro-server` and `fabro-server-mi-homelab`
were both enabled and active since 2026-10-19 13:04 CEST, and both start
`~/.fabro/bin/fabro`. Since 2026-10-23 that file is declared in
livespec-dev-tooling's `ansible/inventory/host_vars/vps.yml` as the 0.254.0
8869e88 web-prod build (sha256 `199407ce…`, byte-identical to hp's legacy
engine), staged by the `fabro-hosts.yml` play without a restart. So a change
to that file changes two live servers' engine at their next restart, and the
host PATH client must not share it (`bd-ib-zb2hso` step 2). The `dispatcher.minimum_release`
floor and the end-to-end fallback proof are S7b (`bd-ib-jamtsf`). Both builds come from
**`factory-integration`** — the ONE standing branch in our fork
(`thewoolleyman/fabro`) that carries every fabro fix the factory needs but
upstream has not released (today: PR #568 credential refresh,
the env-configurable daemon-readiness timeout, PR #552 configurable checkpoint
git timeout, PR #576 OTLP export transport, the fork-local O1 worker-OTLP env
re-injection + O2 W3C-traceparent join that light that transport up for the Codex
era, the fork-local P2 that decouples OTLP export from `FABRO_LOG` so quieting
logs cannot silently zero telemetry, the fork-local O4 `run_turn` ACP turn
span that makes per-turn command/stop-reason queryable, and the `bd-ib-cewr.4`
fix that makes the pre-run push precondition ASK origin via `ls-remote` instead
of pushing — fast-forwarded onto `factory-integration` and deployed to both
hosts on 2026-09-09).
Never pin a fabro build from any other branch. The base-version ceiling is
CONDITIONAL, not permanent: `SPECIFICATION/constraints.md` §"Fabro runtime
constraints" (ratified in `v035`) says the base "MAY move forward" and that the
`< 0.256` prohibition "lifts ONLY when the `workflow.fabro` migration lands"
(fabro #474 de-templates `acp.command`, so on any unmigrated graph every
dispatch dies `exit 127`). **The maintainer's standing direction (2026-09-30) is
to STAY CURRENT on Fabro and to build what the factory needs on top of it —
preferably by contributing it upstream — never to freeze on the fork.** The
2026-09-06 backlog sweep (`bd-ib-j81s`) closed `bd-ib-6qu` and `bd-ib-2nq.4`
with a "fork-only posture is ratified" reading that the ratified text does not
contain; that was the sweep's misreading, not a maintainer ruling, and both
records are poisoned by ledger text so neither can carry the correction. The
live successor is plan `fabro-currency` (epic `bd-ib-6tcjfx`;
`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`), which
also records that upstream re-platformed onto the Petri engine on
2026-09-17..21, so "staying current" is a migration, not a pin bump. The
build/pin/rollback commands are in `orchestrator-image/README.md`.

**THIS REPO'S DISPATCHES DO NOT GO TO `127.0.0.1` — check the configured factory
before concluding a run is missing.** The local server described in this section is
real and is what `sudo systemctl restart fabro-server` manages, but
`.livespec.jsonc` sets `dispatcher.default_factory` to **`hp`**, and its
`dispatcher.factories` block defines only two targets, neither of them loopback:
`hp` = `https://hp-xubuntu.perch-rudd.ts.net:32276` and `vps` =
`https://vps.perch-rudd.ts.net:32276`. The Dispatcher passes the resolved factory's
URL to `fabro run --server`, and an item can override the choice through its own
`dispatch_factory` metadata key.

The practical consequence, measured 2026-08-21: a bare `fabro ps` defaults to the
LOCAL server and reports `No running processes found` while this repo's dispatch is
perfectly healthy on `hp`. That is a clean, plausible, wrong answer with no error —
an instrument aimed at the wrong host, per the fourth trap in the beads-trap
catalogue above. Pass the factory explicitly:

```bash
~/.fabro/bin/fabro ps --server https://hp-xubuntu.perch-rudd.ts.net:32276
```

The same applies to `inspect`, `dump` and `attach`, all of which accept `--server`
and all of which reach a remote run's state when given it — verified on run
`01M0H73GQ8Y0`, where `dump --server` exported 61 files and `attach --server`
reached a run holding a live human gate and answered it. Concluding that a remote
run is unreachable because a bare invocation found nothing is the same trap one
level on.

**To ROUTE a dispatch to a chosen factory, name it — and note that `drive.py`
cannot.** The paragraph above is about pointing a QUERY at the right host; this
one is about pointing a DISPATCH, and it has a different mechanism and a worse
failure mode. `dispatcher.py dispatch` takes `--factory <name>`, and the
environment variable `LIVESPEC_FABRO_FACTORY=<name>` does the same job through
any entry point. `_pinned_factory` in
`commands/_dispatcher_factory_ledger.py` applies the ratified order — the flag,
read by `explicit_dispatch_factory`, then the variable, then the item's recorded
factory — so either routing input wins over that recorded pin and over
`dispatcher.default_factory`, at the ADMISSION claim stamp as well as at the
dispatch resolution. **`drive.py` has
NO `--factory` flag**, so through `drive --action impl:<id>` the environment
variable is the only route.

This matters whenever a dispatch is EVIDENCE ABOUT A BUILD rather than merely
work to be done, because the two factories CAN carry different fabro binaries
and nothing in a run's own output announces which engine it ran on. Measured
2026-09-07, and recorded here as the worked example rather than as current
state: vps had been re-pinned to `7b4e3f3` while hp still ran `8de6611`,
so an unrouted control dispatch would have exercised the NEW workflow on the
OLD engine and returned a completely normal green run. That is the
wrong-population trap from the catalogue above, arriving through the default
rather than through a typo — there is no error, no warning, and the result
looks exactly like success.

**That divergence closed on 2026-09-09 (both hosts at `977cb67`), RE-OPENED
on 2026-09-12 (hp `4b8cc85`, vps `977cb67`), and closed again on 2026-10-01
when S7a put `8869e88` on both (vps as a staged client only; its unit is
retired), as measured at the top of this section.** Do NOT read any day's parity as a standing guarantee — a re-pin lands on one host at
a time, so the two hosts diverge for as long as the second rollout takes, and
the paragraph above describes what that window looks like from a dispatch. When
a dispatch is EVIDENCE ABOUT A BUILD, establish the engine per dispatch instead
of quoting this line: read `fabro --version` ON the factory host itself (the
per-host invocations are in `orchestrator-image/README.md`), because
`~/.fabro/bin/fabro --version` run locally reports the LOCAL client, not the
engine the dispatch will land on.

So: when a dispatch is a control, route it explicitly and record which factory
it ran on. When it is ordinary work, the default is fine.

**A Fabro run being `blocked` does not mean the work is incomplete.** This gets its
own Fabro-section entry because the discriminator is operational: use
`fabro inspect --server <factory> <run>` before attaching or reaping. Measured
2026-08-22, run `01M0MC8FFXEH` sat `blocked` for 65 minutes while `inspect` showed
implement complete and review succeeded with `preferred_label=approve`; only the
`pr` stage was blocked, on a non-fast-forward rejection against the branch the same
run had already pushed before rebasing (`bd-ib-e3xm`). A human gate had no useful
answer to give, and Retry could only meet the same rejection.

The invisible end state is reviewed work published on a branch with no open PR. It
is not unpublished, so an unpublished-work reap watcher does not fire; it is not a
PR, so forge queries keyed on pull requests miss it; and it disappears from
ordinary `fabro ps` once the run exits. A blocked run does eventually reach a
terminal status, and `fabro rm` refusing one without `--force` proves only that it
has not reached that point yet. The discriminator between a run that ended on its
own and one a human removed is `fabro ps -a`: the former remains listed with a
terminal status, while `fabro rm --force` deletes it from `ps -a`.

**But do NOT read that terminal duration as the moment the run was reaped or its
scheduler slot came back. CORRECTED 2026-08-22 — this paragraph originally said
the opposite, and the retraction is the point.** It cited run `01M0KXYZRWXN`
"self-terminating exactly at `240m00s`" as proof a configured ceiling had fired,
treating the ROUNDNESS as evidence the mechanism acted. That inference is
inverted. **An exact round number is the signature of a CONSTANT, not of a
measurement:** it tells you what was configured and never that the configured
thing did anything.

Measured first-hand on 2026-08-22. That run's `conclusion.timing.wall_time_ms` is
`14400071`, which reproduces this repo's own `implement` node `timeout="14400s"`
(`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`) to 71
milliseconds — the duration IS the timeout constant. Every per-node
`wall_time_ms` on the same record is `0`, so the record carries no independent
timing to check it against. The control settles it: `01M0M9AHRXEX` in
`livespec-overseer` is terminal at exactly `360m00s` — the SAME
`ImplementWorkItem` workflow, a different repo's configured timeout. If 240 were
a fleet-wide ceiling, 360 could not exist. (A peer session reports the run's
container had been dead roughly 52 minutes before that value was written; that
part is cited here, not verified here.)

WHAT IS NOW OPEN, and it is worth more than the retracted claim: if the recorded
duration is a constant stamped at finalisation, then **a run's own record cannot
tell an operator when its capacity actually returned** — slot accounting keyed on
that number reports a figure nobody can act on. That question belongs to
`bd-ib-rnlks6` (a blocked run holding its scheduler concurrency slot), NOT to the
storage-reclamation epic whose child originally recorded this paragraph: that
epic governs disk headroom, and a scheduler slot is not disk.

**Factory ENOSPC is a FACTORY-HOST failure, not an item failure.** The signature
measured on 2026-08-22 is: `drive.py` exits 1, the dispatcher exits 1, the failed
stage is `fabro-run`, no Fabro run is created, a phantom claim is left behind, and
the error detail names `ENOSPC` on a storage path that the dispatching machine
cannot see. The discriminator is the path: `/home/cwoolley/...` named the factory
host user while the dispatching machine was `ubuntu`, so local `df` and local
process views were clean but irrelevant. The failure happens before
item-specific processing, so no property of the work item can cause or avoid it.
Check disk on the selected factory host itself:

```bash
ssh <factory-host> df -h /
```

The blast radius is every repo routed to that factory, not the one item that
reported first; on 2026-08-22 two different repos failed with this signature
within 44 seconds. Factory ENOSPC is a transient breakage of a shared host: do
NOT re-route the dispatch to the second declared factory to keep your own work
moving — §"Stop the line for breakages" above treats an intermittent ENOSPC as
a transient that is WAITED OUT and retried on the NORMAL path. Notify the
factory owner (or clear the space yourself) so the full factory cleanup
proceeds, WAIT for the host to recover, and re-dispatch on the normal path once
`ssh <factory-host> df -h /` shows headroom. livespec-overseer carries the
phantom-claim list where this signature is
a sibling-repo update; route that update to livespec-overseer instead of editing
that repo from this one.

- **Start / restart** (OAuth-only — no wrapper, no `ANTHROPIC_API_KEY`):

  ```bash
  sudo systemctl restart fabro-server
  ```

  The canonical unit and installer live in the fleet repo
  `thewoolleyman/fabro-hosts`, at `services/fabro-server/` (moved out of
  `vps-info` on 2026-08-20, because `fabro-server` runs on both `vps` and
  `hp-xubuntu` and a per-host copy is what let the two diverge silently). One
  unit template plus a six-line `hosts/<host>.env` covers both factories, and
  `install.sh` refuses to apply one host's values on another. The unit runs Fabro in the
  foreground under systemd, passes the affirmative `--web` option, restarts it
  after failures and reboots, and refuses readiness unless `/runs` exists and
  the unauthenticated `/login` shell plus its JavaScript bundle load. Build the
  pinned fork with
  `cargo clean --release -p fabro-spa` followed by
  `cargo dev build --release -p fabro-cli`; the targeted clean prevents Cargo
  from reusing an assetless release embedding crate, and a plain `cargo build`
  does not refresh the embedded SPA. Never run `fabro server start` / `restart`
  directly on this host, because that bypasses supervision and the web-console
  readiness gate.
- **OAuth-only posture — do NOT put `ANTHROPIC_API_KEY` in the SERVER env.** It
  bills API cost and can leak into the sandbox. The agent's model auth is
  `CLAUDE_CODE_OAUTH_TOKEN`, injected into the *sandbox* by the Dispatcher per
  dispatch. In `fabro doctor`, `[✗] LLM Providers (none configured)` is therefore
  CORRECT.
- **Credentials live in `~/.fabro/`** (the GitHub App integration from the vault;
  `auth.json`; the SlateDB `storage/`). `fabro doctor` should show GitHub App
  **configured**; if it is not, the server's vault did not load — do NOT "fix" it
  by adding `ANTHROPIC_API_KEY`.
- **Fleet-shared + Tailscale-served.** `tailscaled` holds a standing
  `tailscale serve` proxy `https://vps.perch-rudd.ts.net:32276 → 127.0.0.1:32276`;
  it persists across restarts and simply returns refused while the loopback
  backend is down. The console URL is
  `https://vps.perch-rudd.ts.net:32276/runs`. A `:32276` listener owned by
  `tailscaled` (not `fabro`) means the proxy is up but the server is not.
- **Never `pkill -f 'fabro server'`** — it self-matches the killing shell and can
  reap unrelated shells. Match real daemons via `/proc/<pid>/exe` and kill by PID.
- **A merged factory slice stays `active` until you run `reconcile-merged
  --item <id>`; the `reconcile-runs.timer` does NOT close it.** The root
  timer runs `dispatcher.py reconcile-runs`, which reconciles only
  stranded/held runs and returns `reconciled: []` for cleanly-merged work.
  The active→closed valve on merge is a DIFFERENT subcommand driven PER
  ITEM: `dispatcher.py reconcile-merged --repo <repo> --item <id> --invoker
  <role:name>`. It runs the per-item post-merge janitor (fresh checkout +
  baseline checks — expect it to exceed a 600s foreground timeout; launch it
  through `just gate-start` per the bullet below, NOT as a harness background
  task) and closes the item, printing e.g. `bd-ib-cwhos6  green at done PR#2146
  merged, post-merge janitor green`. Consequence: after a slice's PR merges,
  any downstream item blocked on it stays blocked until you run
  `reconcile-merged` for the merged item. Measured 2026-09-04 on
  `console-control-plane-primitives`: two merged slices sat `active` across
  four timer cycles (40+ min) until `reconcile-merged --item` closed each,
  which was what cleared their dependent's blockers. (Prior plan handoffs
  wrongly asserted the timer auto-closes a merged item.) Related: `next`
  never lists a `pending-approval` item, so an `admission:auto` item is
  invisible to `next` but selectable by the dispatcher drain, and `drive
  --action impl:<id>` admits and dispatches such an item in one step.
- **A `drive` or `dispatcher.py` invocation launched as an AGENT-HARNESS
  BACKGROUND TASK can be killed mid post-merge, stranding merged work
  `active` — and the task's death is NOT the dispatch's verdict.** One
  `drive --action impl:<id>` spans the Fabro run, the PR, the merge, the
  post-merge janitor and acceptance, so it outlives any agent turn. Measured
  2026-09-10: two dispatches launched from one Claude Code session as
  `run_in_background` Bash tasks died **37 ms apart** after 34m55s and
  34m52s — the 3.3 s launch gap did not survive, so ONE event ended both,
  and a per-task lifetime cap is therefore excluded. Each task's only output
  was the harness line `exited with code 144`, and each `drive --json` log
  was 0 bytes because `drive` prints its result only on exit. There was no
  OOM (~57 GB free, no kernel OOM kill). **Both Fabro runs had SUCCEEDED and
  both PRs had MERGED** (PR 2458 as `52783f67`; PR 2459 as `51d99744`, 18 s
  before the kill); the kill landed in the post-merge janitor and acceptance
  stage, leaving both items `active`, assignee `fabro`, with no merge audit.
  So a dead background task tells you NOTHING about the dispatch — read the
  forge and the ledger before concluding anything failed. **The remedy is the
  detached gate runner**, which runs the command in its own session that
  survives the tool call and reports a durable `PASSED` / `FAILED` /
  `RUNNING` / `DIED_WITHOUT_VERDICT`:

  ```bash
  run_id=$(mise exec -- just gate-start -- <the drive or dispatcher invocation, env wrapper and all>)
  mise exec -- just gate-wait "$run_id"
  ```

  `gate-start` runs the argv it is given, unchanged, so the gate command is
  whatever you would otherwise have typed — including the
  `with-<project>-env.sh` credential wrapper this repo's beads prerequisites
  require. Launching through the runner does NOT license routing around a
  stale plugin build by explicit path; §"Stop the line for breakages" still
  governs WHICH build you invoke. The `gate-*` recipes come from the
  livespec-dev-tooling worktree-discipline pack through the OPTIONAL
  `import? 'dev-tooling/worktree.just'`, which is gitignored and therefore
  ABSENT until `just install-worktree-pack` (run from `just bootstrap`)
  materializes it — so `Justfile does not contain recipe gate-start` means
  the pack is not installed, NOT that the runner is the wrong route. Install
  the pack; never fall back to a harness background task.

  `gate-wait` exits with the gate's own exit code (75 for
  `DIED_WITHOUT_VERDICT`, which is neither a pass nor a fail); killing the
  waiter does not touch the gate, so it is the safe thing to background and
  it can simply be re-issued. **The recovery for a merged item left `active`
  is `dispatcher.py reconcile-merged --repo <repo> --item <id> --invoker
  <role:name>`, per item** — the bullet above; launch that through
  `just gate-start` too, for exactly the same reason.
