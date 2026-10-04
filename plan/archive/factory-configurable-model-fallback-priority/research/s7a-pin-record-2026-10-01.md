# S7a pin record — the capability-bearing carrier build on hp and vps

Written 2026-10-01 by the session driving plan epic `bd-ib-jxvgq5`, executing
`bd-ib-q32gs5` (S7a) under the operator's standing authorization to finish the
plan autonomously. Every value below was measured; the ledger receipt comment
on `bd-ib-q32gs5` carries the same facts with the raw command output.

## What changed in the record before it ran

The S7a record filed on 2026-09-30 assumed two serving factory hosts. That was
stale: the vps `fabro-server` unit was stopped and disabled on 2026-09-11
02:21 local by `systemctl disable --now fabro-server.service`, by maintainer
direction recorded on `bd-ib-3ysb6k` ("must remain stopped", "do not query,
start, or restart either VPS Fabro backend"), and PR 2467 (`12ca3cd7`) removed
vps from `.livespec.jsonc` `factories`, leaving hp the sole active factory.
The fabro-currency plan's P6 (`bd-ib-iud52v`, pending-approval, deadline
2026-11-14) is where vps is expected to come back, on the new Fabro.

So the vps leg of S7a became: build the carrier tip on vps (a compile, which
the direction permits) and re-pin the on-disk `~/.fabro/bin/fabro`, which is
the Dispatcher's local CLIENT for `fabro run --server hp`, WITHOUT starting
the unit. The capability advertisement is therefore proved on hp only; the
vps binary is proved identical by checksum and by a content check for the two
capability strings.

## Build

| Fact | Value |
|---|---|
| source | `thewoolleyman/fabro` `origin/factory-integration` at `8869e88b2f7e383ec6fceb8d3f6f928dd0339b34` (carrier tip; contains S4 `20bf91e06` and fork PR 10) |
| where | vps, worktree `~/.worktrees/fabro/factory-integration`, detached gate `20261001T190939Z-3418100` |
| how | `bun install --frozen-lockfile`; `cargo clean --release -p fabro-spa`; `cargo dev build --release -p fabro-cli`; `CARGO_BUILD_JOBS=6`, `nice -n 10`, shared `CARGO_TARGET_DIR` (found cold, 422M, and lock-contended by the fabro-currency session's nextest gate) |
| duration | 19:09:39Z to 19:40:11Z, host load 20 to 25 on 18 cores throughout |
| output | `fabro 0.254.0 (8869e88 2026-10-01)`, 117,435,040 bytes, sha256 `4edcc4407fa624230608f533fb7533c3534e617c086bbdcfe9a15182b5c0afd1` |
| staged as | `~/.fabro/bin/fabro.8869e88-s7-candidate` on vps; copied over `tailscale ssh cwoolley@hp-xubuntu` to `/home/cwoolley/.fabro/bin/fabro.8869e88-s7-candidate`, identical sha256 on hp |
| content check | `strings -n 12` on the new binary finds `acp.fallback_chain.v1` (2) and `acp.candidate_config_options.v1` (1); the same probe on the outgoing vps binary `977cb67` finds neither (the control) |

A throwaway candidate server on `127.0.0.1:32286` (the README's comparison
harness recipe) could not serve the proof: an unconfigured Fabro home enters
install mode and answers 404 on `/api/v1/system/info`. That probe was stopped
and its home removed; the live proof is taken on hp after the swap.

## Deploy

| Fact | hp | vps |
|---|---|---|
| before | `fabro 0.254.0 (4b8cc85 2026-09-12)`, unit active as `cwoolley` | `fabro 0.254.0 (977cb67 2026-09-09)`, unit inactive and disabled since 2026-09-11 |
| drain window | `fabro ps --server hp` printed "No running processes found" at 22:49:36Z; the last foreign run (livespec-overseer) ended at 22:49Z and our own kc7vzk run had succeeded at 22:29Z | not applicable (unit stays stopped) |
| swap | 22:49:36Z to 22:50:07Z: `cp` candidate to `fabro.new`, `mv fabro fabro.4b8cc85-pre-s7.bak`, `mv fabro.new fabro`, `sudo systemctl restart fabro-server`; unit `active`, ExecStartPost readiness gate passed, ExecMainPID 2454011 | `cp` candidate to `fabro.new`, `mv fabro fabro.977cb67-pre-s7.bak`, `mv fabro.new fabro`; unit verified still inactive and disabled afterwards |
| after | `fabro 0.254.0 (8869e88 2026-10-01)` | `fabro 0.254.0 (8869e88 2026-10-01)`, sha256 `4edcc440…5c0afd1` |
| capability proof | `fabro system info --json --server https://hp-xubuntu.perch-rudd.ts.net:32276`: `git_sha 8869e88`, `build_date 2026-10-01`, `capabilities ["acp.fallback_chain.v1", "acp.candidate_config_options.v1"]` | checksum identity with the hp binary plus the content check above; no server to query |
| readiness | `fabro-server-verify-web` run from vps with hp's base URL and canonical host: passed | not applicable |
| store | `fabro ps -a` lists 1,226 historical runs and `inspect 01M3WDFM0BF9` reads `succeeded`, so the SlateDB store survived the restart | not applicable |

One instrument note for the next operator: the OLD `977cb67` client's `system info
--json` OMITS the `capabilities` key entirely when talking to the new server. A
capability probe must be made with a client that knows the field, or an absent
key reads as an absent capability. The first dispatch through the re-pinned vps
client was `bd-ib-tmgt7v` (gate `20261001T225504Z-2400183`).

The ledger receipt is the comment dated 2026-10-01T22:56:07Z on `bd-ib-q32gs5`.

## Rollback

On hp, as `cwoolley`: `mv /home/cwoolley/.fabro/bin/fabro.4b8cc85-pre-s7.bak
/home/cwoolley/.fabro/bin/fabro && sudo systemctl restart fabro-server`. On
vps: `mv ~/.fabro/bin/fabro.977cb67-pre-s7.bak ~/.fabro/bin/fabro` (no unit
restart; the unit stays stopped).
