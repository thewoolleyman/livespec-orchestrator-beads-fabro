# 020 — Main `:32276` moves to engine 85af354 and sandbox driver v0.8.1 (2026-11-05)

Written by `claude:fabro-currency` (Claude Code session 96987a1e) on 2026-11-05. It continues
note 019. The ledger records are the plan epic `bd-ib-6tcjfx` scope events at 12:49:51Z and
12:52:08Z, and the handoffs at 14:34:14Z and 16:42:25Z. Coordinator traffic was with
`legacy-coordinator-agent`, `legacy-dispatcher-agent` and `kubernetes-sandbox-backend`. All
times are UTC.

## Why one window carried two changes

Main still served `c39bdbded` after the candidate (`:32278`) and mi-homelab (`:32277`) had
moved to `85af3547e`. Its restart had first been gated on `bd-ib-adcaa6` closing green. The
maintainer then ruled, in the scope event at 12:46:55Z on `livespec-dev-tooling-6tgd2z`, "Just
open the restart windows and notify the people waiting on it, don't wait on me". So the
coordinator folded the gmktec sandbox-driver change, v0.8.1 at its own versioned path
(`bd-ib-zl3qcz` CPU request 3 under limit 6, `bd-ib-mdern6` exec-stream resume), into the same
apply. It set three conditions:

1. A one-apply revert is written down before applying.
2. Engine and driver are verified, then the `bd-ib-adcaa6` canary clears its first node
   before any refill.
3. A canary failure stops the refill and reverts both.

## What ran

| Time | Step |
| --- | --- |
| 16:11:07Z | livespec-dev-tooling #3474 (driver v0.8.1 re-pin) merged as `7d2dd488`, after a flaky-test root fix (#3500) and a rebase |
| 16:13-16:21Z | Revert branch `revert/fabro-server-85af354-driver-v0.8.1` committed as `f34a7a07` and pushed, NOT merged; it applies every `# REVERT:` line of the fleet instance |
| 16:14:20Z | The successor dispatcher session set fleet cap 0 (it had been 16) and sent its 15-run board |
| about 16:20Z | `kubernetes-sandbox-backend` sent a preserve list of all 15 runs, each `git ls-remote` verified; this session re-verified every ref and sha |
| 16:19:44-57Z | All 15 runs cancelled by full id through `POST /api/v1/runs/{id}/cancel`, each returning 202; the board read 0 at 16:20:20Z |
| 16:13-16:29Z | Drift gate `20261105T161350Z-508051`: changed=4 failed=0 |
| 16:29-16:40Z | Apply gate `20261105T162931Z-692385`, full role, restart allowed: changed=11 failed=0 |
| 16:41Z | Verified: PID 1395385 reports `85af354`, sha `d6fcfafa…5e1711`; restart-pending empty; both providers on `sandbox-driver-kubernetes-v0.8.1` (`ad74f14d…`) with `CPU_REQUEST_CORES=3`; shared v0.5.0 path untouched |
| 16:51:40Z | Canary `bd-ib-adcaa6` run `01M6P9Z39GA2` launched alone at cap 1, seeded from its preserve ref |
| about 16:53Z | Pod `Burstable`, requests.cpu 3 and limits.cpu 6, with node cgroup `cpu.max 600000 100000`, checked by `kubernetes-sandbox-backend` |
| about 16:54Z | Canary cleared run_prepare 1-52, `dod_gate` and `dod_gate_mutation_guard`; "first node green, refill" sent; the dispatcher refilled to cap 20 at 16:54:38Z |

`bd-ib-a7zpxy` run `01M6P565FD4M` ended between the 16:12Z and 16:14Z boards. Its pod was
already gone, so there was no tree to preserve.

## Proofs taken on main after the restart

- **`bd-ib-m7lxgn`** (fork #26). Two `fabro sandbox cp` calls of `/etc/hostname` from the live
  canary returned rc 0 in 14.28 s and 1.10 s, and both copied the pod's hostname. The journal
  shows ONE plugin generation launch for both calls and two `sandbox/file` 200s. Since the
  restart there are 0 `plugin transport failed` lines. Closed.
- **`bd-ib-dmjsmd`** (fork #25), measured on cancelled run `01M6NKNEY7RM`, whose stream holds
  24,644 items:
  - `fabro events --json -n 30` took 3.53 s for 30 items and 46,725 bytes, seq 24615..24644.
    The c39bdbd stack needed 61 s.
  - An unbounded read killed at 15 s had already printed 4,500 items. The c39bdbd stack
    printed 0 bytes.
  - No node-subject item carried `meta.script`. The only `script` keys were in the run-spec
    platform item at seq 1.

  Closed.
- **`bd-ib-uctbct`** (fork #24) is a CLIENT fix, in the dispatch push that `fabro run` makes.
  It takes effect only once the Dispatcher's pinned client is `85af3547e`, which is this
  change's `.livespec.jsonc` edit.

## Lessons

- The repo's background guard refuses a foreground `git commit` whose hooks run gates. In
  another repository's worktree, too, commit and push through `just gate-start -- …` and
  `just gate-wait`.
- `fleet_host_guard` refuses a compound ssh command it cannot parse, even a read-only one.
  Keep each ssh to one plain read, such as `journalctl … > local-file`, and do the filtering
  locally.
- Run the drift before the cancels. Here it took 15 minutes, so it went first and the cancels
  overlapped its tail, while the apply itself waited for zero runs.
