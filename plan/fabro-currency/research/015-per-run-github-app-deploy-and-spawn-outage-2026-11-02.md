# 015 — Per-run GitHub App build deployed to gmktec, and the worker-spawn outage it exposed (2026-11-02)

Work-item: `bd-ib-voozdp` (per-run GitHub App selection on shared main Petri), the
Fabro fork half. Its Dispatcher binding sibling is `bd-ib-iphzb7`.

## What shipped

- Engine change: `thewoolleyman/fabro#13`, merged as `613add19c` on
  `carrier-candidate-registered-20261023` (the serving base, not `factory-integration`).
  It is `9f6c38fab` plus `[run.integrations.github.app]`. Its Petri lock is unchanged
  at `e92b191`.
- Release build: `fabro 0.393.0-nightly.1 (613add1 2026-11-02)`, sha256
  `def1dc89890c0481f8e733016ab78481dd2f26d8cab9248eb6b4b1fec5f6a344`, staged on vps at
  `~/.local/state/fabro-web-prod/v0393-613add19c/` with `BUILD_INFO` and `SHA256SUMS`.
  It took 63 minutes at nice 19 and 4 jobs.
- Pin: livespec-dev-tooling PR #3141, merged as `9657a61e`. Only `fabro-server` `:32276`
  moves. `fabro-server-candidate` and `fabro-server-mi-homelab` stay on `9f6c38fab`, by
  coordinator ruling. No vault entries were written: the maintainer adds homelab's App
  4688510 key personally.
- Serving: since 2026-11-02T15:04:02Z, PID 201185. `/api/v1/system/info` reports
  `git_sha 613add1`.

## The outage

| Time (UTC) | Event |
| --- | --- |
| ~14:25 | Last successful worker spawn |
| 14:27:07 | The restart-deferred apply (`fabro_server_restart_allowed` false) renames the new build over `/home/cwoolley/.fabro/bin/fabro` |
| 14:42:47 | `Failed to spawn worker: spawning run worker process: No such file or directory (os error 2)` for run `01M6EBCYNJ1S` (livespec-rjvz4r) |
| 14:48:33 | Dispatcher sets hold-gmktec |
| ~15:00 | Coordinator R301 stability override: the 9 live runs are cancelled (all 202) and their set is handed to the dispatcher |
| 15:04:02 | Re-apply with `fabro_server_restart_allowed=true` restarts the instance onto 613add1; 4 orphaned Kubernetes sandboxes are reaped |

Cause: the server builds each worker's launch from `std::env::current_exe()`
(`lib/apps/fabro-server/src/server.rs` `worker_launch_spec`). After a rename over the
running binary, Linux reports that executable as `<path> (deleted)`, so `spawn` fails
with ENOENT. The role's HOST_VARS.md claim that replacing a binary "never interrupts a
live factory" holds only for runs whose worker already exists.

The fix is `livespec-dev-tooling-udma` (P1, ready). Interim rule (coordinator): any
apply that stages a Fabro binary restarts that instance in the same step.

## Still owed for `bd-ib-voozdp`

The proof is a homelab run on `:32276` publishing as App 4688510. It waits only on that
App's private key being in main Petri's vault, which the maintainer owns. After the
proof, close `bd-ib-voozdp` with PR #13 and merge SHA `613add19c`, then tell
legacy-dispatcher-agent "released and provisioned" so it releases `hl-l7msl6`,
`hl-jfgwsi` and `hl-h2254o`.
