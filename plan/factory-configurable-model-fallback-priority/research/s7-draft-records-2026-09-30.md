# S7 draft work-item records for maintainer consent

Written 2026-09-30 by the session driving plan epic `bd-ib-jxvgq5`, after the
fork half of the in-protocol selection (`bd-ib-afcn3d`) merged into the
carrier as `8869e88b2`. Nothing here is filed. As with S4, S5 and S6, the
point is to make consent a yes or a no on an exact record. Each record is
complete enough to file verbatim through `capture-work-item` as a child of
`bd-ib-jxvgq5`; the acceptance criteria are `- ` bullets, one assertion each,
ending in a period, kept inside the vocabulary of the diff that would satisfy
them, with no scenario reference in the criteria field.

## Why S7 splits in two

The post-ratification research described S7 as one slice: "publish and pin
the capability-bearing Fabro build, publish the first fallback-capable
orchestrator release, set `dispatcher.minimum_release`, reject new grammar
when either the local plugin floor or the resolved remote capability is
absent, run a controlled factory journey, bind Scenario 127". Two facts
measured today make that one record unfilable as written:

- Pinning the build is HOST work. It rebuilds the fork on vps, swaps the
  binary under the `fabro-server` unit, copies the vps-built binary to hp and
  restarts hp's unit, which kills every foreign run on hp. That is
  `factory_safety: mutates-host-machinery` and cannot run in a sandbox; the
  Dispatcher drain must never pick it up.
- The adoption gate and the journey proof are ordinary in-repository Python
  and are factory-dispatchable, but only once the factory can dispatch at all.
  Consumer dispatch is refused today at `run-config-overlay` until the
  llm-provider-manager thread ships the executable or reverts the consumer
  carrier (ruling on `overseer-tm2qtw`), and the structured chain the proof
  must exercise lands with `bd-ib-kc7vzk`, which is held on the same thing.

So: S7a is host-routed and can start on consent; S7b is factory-safe and is
blocked on S7a, `bd-ib-kc7vzk` and a working factory.

## Measured state the records depend on

| Fact | Value (2026-09-30) |
|---|---|
| carrier tip `origin/factory-integration` | `8869e88b2` (this slice) on `20bf91e06` (S4) on `4b8cc85e0` (fork PR 8) |
| vps engine | `fabro 0.254.0 (977cb67 2026-09-09)` |
| hp engine | `fabro 0.254.0 (4b8cc85 2026-09-12)` |
| capabilities the carrier advertises | `acp.fallback_chain.v1`, `acp.candidate_config_options.v1` (`fabro-types/src/capabilities.rs`) |
| Dispatcher remote capability gate | none exists: no module under `commands/` reads `GET /system/info` capabilities; `_dispatcher_minimum_release_floor.py` exists and reads `dispatcher.minimum_release` |
| S7 gap ids | `gap-j6kfvdht`, `gap-wdianxsa`, named by no ledger item |
| Scenario 127 | `tests/heading-coverage.json` entry carries `test: "TODO"` |

Neither host carries S4 or this slice, so the first real fallback chain
dispatched anywhere will be refused by S7b's gate until S7a lands, which is
the intended order.

## S7a — pin the capability-bearing Fabro build on both factory hosts

**Title:** Pin the capability-bearing factory-integration build on vps and hp

**Repository target:** livespec-orchestrator-beads-fabro (runbook and
receipt); the binaries live on the hosts. `factory_safety:
mutates-host-machinery`, host-routed, opened through `driver-dispatch`.

**Description.** Build `factory-integration` at `8869e88b2` (or the carrier
tip at the time, which must be a descendant) on vps per
`orchestrator-image/README.md` §"Start / restart" (`bun install
--frozen-lockfile`, `cargo clean --release -p fabro-spa`, `cargo dev build
--release -p fabro-cli`), retain the outgoing binary as
`fabro.977cb67-pre-s7.bak`, swap by atomic rename, restart `fabro-server`
through systemd and pass the web-readiness gate. Copy the vps-built binary to
hp per §"The hp factory host", retain `fabro.4b8cc85-pre-s7.bak`, swap as
`cwoolley`, and restart hp's unit inside a drain window (no foreign run
listed by `fabro ps --server https://hp-xubuntu.perch-rudd.ts.net:32276`).
Verify on each host that `fabro --version` names the pinned commit and that
`fabro system info --json --server <that host>` lists both capability
strings. Record the receipt (both versions before and after, the backup
filenames, the drain-window evidence, the capability output) as a ledger
comment and update the README carried-fix rows from "NOT deployed" to
deployed with the date, and the `AGENTS.md` host lines. Rollback is the
documented `mv` of the `.bak` back into place plus a unit restart.

Out of scope: the orchestrator release, the `minimum_release` floor, the
Dispatcher gate and the journey proof (S7b).

**Acceptance criteria (draft):**

- `orchestrator-image/README.md` records the pinned build commit for vps and hp with the deployment date and the retained backup filenames.
- `AGENTS.md` names the same pinned build commit for both hosts and no longer says that neither host carries the S4 chain or the in-protocol selection.
- The ledger receipt comment carries the before and after `fabro --version` output for both hosts and the `fabro system info --json --server` capability list showing `acp.fallback_chain.v1` and `acp.candidate_config_options.v1` on each.
- The hp restart happened inside a recorded drain window with no foreign run listed before the swap.

## S7b — adoption gate, release floor and the end-to-end fallback proof

**Title:** Gate new ACP chain grammar on the resolved factory capability and the plugin floor, and prove one fallback journey

**Repository target:** livespec-orchestrator-beads-fabro. Factory-safe.
Blocked by S7a (both hosts pinned), `bd-ib-kc7vzk` (the structured chain the
proof renders), and a dispatchable factory (the llm-provider-manager fix or
revert).

**Description.** Before claim, the Dispatcher reads `GET /system/info` on the
dispatch's resolved factory server (never a local binary, per the same rule
`_acp_projection_run.py` already states for events) and refuses a node whose
rendered chain carries new grammar (a non-empty `fallbacks`, identity,
signature or pricing field) when `acp.fallback_chain.v1` is absent, or
carries `config_options` when `acp.candidate_config_options.v1` is absent,
with a refusal naming the factory, the missing string and the node. The
capability read is cached per dispatch and an unreachable server is a
refusal, not a pass. Publish the first fallback-capable orchestrator
release, set `dispatcher.minimum_release` in `.livespec.jsonc` to it, and
refuse new grammar when the executing build is below that floor through the
existing `_dispatcher_minimum_release_floor.py` verdict. Then run one
controlled factory journey on hp: a two-candidate structured chain whose
primary is a model the provider refuses with the measured exact diagnostic
and whose fallback succeeds in the same node visit; assert from the run's
own events and the Dispatcher journal one `agent.acp.failover`, one
projected hold, one warning fact, the S6 cost attribution, unchanged run and
sandbox identity, no predecessor replay, and the started event's confirmed
`model`. Bind Scenario 127 in `tests/heading-coverage.json` to that
consumer-tier test and replace its `TODO`.

Carries `gap-j6kfvdht` and `gap-wdianxsa`.

**Acceptance criteria (draft):**

- A Dispatcher module reads the resolved factory's `GET /system/info` capabilities before claim and refuses a chain carrying new grammar when `acp.fallback_chain.v1` is absent, naming the factory and the missing string.
- The same module refuses a chain carrying `config_options` when `acp.candidate_config_options.v1` is absent, and an unreachable factory server is refused rather than passed.
- `.livespec.jsonc` sets `dispatcher.minimum_release` to the first fallback-capable release and the minimum-release verdict refuses new grammar below it.
- A consumer-tier test dispatches a two-candidate structured chain to a pinned factory and asserts one `agent.acp.failover` event, one projected hold, one warning fact, the attributed cost, unchanged run and sandbox identity, and the started event's confirmed model.
- `tests/heading-coverage.json` binds the ordered-fallback scenario heading to that test with no `TODO`.

## Plain-language summary for the consent question

S7a: put the new engine on both factory machines, keeping the old one to
switch back to, and prove each machine now advertises the two new abilities.
It restarts hp, so it waits for a moment when nothing is running there.

S7b: teach the Dispatcher to check a factory's advertised abilities before
sending it the new configuration, refuse if they are missing or if the plugin
is too old, then run one real job where the first model is refused and the
second one finishes it, and prove from the records that exactly what the
specification promised happened. It cannot start until the factory can
dispatch again and the structured chain has landed.

## Next ledger action

Present both records for consent. On consent, file S7a first through
`capture-work-item` with `factory_safety: mutates-host-machinery` set through
the valve, then S7b with `blocks` edges from S7a and `bd-ib-kc7vzk`. Neither
should be dispatched by the drain: S7a is host work, S7b waits on its edges.
