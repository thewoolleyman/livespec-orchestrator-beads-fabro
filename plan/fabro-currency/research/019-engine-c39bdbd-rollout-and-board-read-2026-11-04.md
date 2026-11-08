# 019 — Engine c39bdbd rolled out; the slow-board stop-the-line (2026-11-04)

Written by `claude:fabro-currency` (Claude Code session 5eb22cd1) on 2026-11-04. It continues
note 018. The ledger records are the plan epic `bd-ib-6tcjfx` handoff entries of 2026-11-04,
and the coordinator traffic is with `legacy-coordinator-agent` and `legacy-dispatcher-agent`.

## What was deployed

- Fork PR `thewoolleyman/fabro#23` (`bd-ib-xoh477` server half: a run-list entry carries a goal
  preview of at most 1 KiB) was gated and rebase-merged at `c39bdbded`. The branch was rebased
  onto the carrier tip `fcb4dc073` first, so the gate graded what merged.
  - Gate run `20261104T065451Z-1810591`: fmt and clippy (`nightly-2026-04-14`) clean. Its
    nextest legs ran ZERO tests: `fabro-server`'s `it` target declares
    `required-features = ["test-support"]`, and a filter over a target that was not built
    selects nothing. A 0-test nextest run exits 4 and is not a gate.
  - Gate run `20261104T071538Z-2176572` (`-p fabro-server --features test-support`): GREEN 1/1;
    RED 1/1 failed at `tests/it/api/runs.rs:346`, the byte-bound assertion, with
    `handler/runs.rs` reverted to `fcb4dc073`.
- The Petri `565ac47` bump the 018 handoff listed as a separate step was already on the
  carrier: fork PR #22 pinned Petri `d25a6c15`, whose history contains `565ac47`.
- Build `fabro 0.393.0-nightly.1 (c39bdbd 2026-11-04)`, sha256 `e93c96b7…6e96`, staged at
  `~/.local/state/fabro-web-prod/v0393-c39bdbded/`. Over `8764f1de8` it carries #20
  (`bd-ib-q3xszn`, test-only), #21 and #23 (`bd-ib-xoh477`) and #22 (`bd-ib-gmuxd4`).
- Pins: livespec-dev-tooling PR #3369 (`ebbba70a`) for all three gmktec instances. The factory
  client moved in this repository's PR #4363 (`828a53225`): `.livespec.jsonc`
  `dispatcher.factories.{petri,candidate}.bin` and `fleet-launch/config.sh`
  `FLEET_LAUNCH_FABRO`. The overseer, dev-tooling and driver-codex repositories still pin the
  0.382 `adeefec4c` client in their own `.livespec.jsonc`.

## The stop-the-line: slow board reads on `:32276`

`legacy-coordinator-agent` stopped the line at about 08:0xZ. `fabro ps -a` against main
took 26-38 s against a 30 s client timeout, launchers read the fleet as unknown, and dispatch
liveness reads failed (`bd-ib-ke5wkf`, `livespec-dev-tooling-7uq5ri`).

Measured from vps, before acting:

- `GET /api/v1/runs?include_archived=true`: first byte at 1.2-2.3 s, total 7.3-9.2 s, body
  1,911,454 bytes (554,426 gzipped). The same query on `:32277` returned 5,785 bytes in 1.3 s.
- The same 2.3 MB static SPA asset, which costs the server nothing, took 3.8-6.3 s
  (366-605 KB/s). The vps-gmktec link moves about 0.4-0.6 MB/s.
- So the server answered in 1-2 s, and the time was transfer: about 87% goal text, multiplied by
  N launchers polling at once. The 0.382 client also sends no `Accept-Encoding` and downloads
  every run even on plain `ps`.

The fix was the already-merged xoh477 pair. Measured on `:32276` after the restart, with the
c39bdbd client:

| Read | Before | After |
| --- | --- | --- |
| `-a` list body | 1,911,454 B (gzip 554,426) | 80,913 B (gzip 8,672) |
| raw `-a` GET | 7.3-9.2 s | 0.20-0.66 s |
| plain `fabro ps` | 16-26 s (0.382 client) | 0.24-0.45 s |
| `fabro ps -a` | 26-38 s | 0.96-1.27 s |

The "after" figures were taken at zero active runs.

## Rollout, measured

1. Apply with restarts off: failed=0, `fabro.incoming` staged plus a restart-pending marker on
   all three instances.
2. Candidate and mi-homelab were restarted at 0 runs and report Git SHA `c39bdbd`.
3. Main: `legacy-dispatcher-agent` set `hold-gmktec` at 09:54:01Z. Thirteen runs were cancelled
   at 09:56:18-35Z. The restart play then converged EVERY gmktec role before the fabro_server
   handler, and about 12 minutes later it refused on one active run, `bd-ib-ke5wkf`. That
   launcher had run LAUNCH at 09:46:45Z, before the hold, and listed only at 10:08:50Z. The
   dispatcher's in-flight scan had skipped launchers whose last line was a board-read retry.
   That run was cancelled, and a retry scoped `--tags untagged` reached the restart in 169 s.
   Main has reported `c39bdbd` since about 10:12Z.
4. One orphan sandbox was reaped: run `01M6HTWZ8FFY` (`livespec-dev-tooling-t5rjdr`) had
   SUCCEEDED at 00:34Z, but its pod was still Running. Every cancelled run's sandbox was already
   `no-pod`.
5. Fourteen items were re-dispatched by `legacy-dispatcher-agent` at 10:11:55Z.

## Lessons

- **Read each run's stage before a cancel-to-idle restart.** `bd-ib-uq2ocd` run
  `01M6JSNVH32S8` was mid-push in `publish_draft` when cancelled, and its green commit is lost:
  the run record shows a 0-file diff and its pod was gone. A run in `publish_draft` or
  `pr_refresh` must either finish, or have its commit preserved to a `needs-human/` ref, before
  the cancel. The ruling is `legacy-coordinator-agent`'s, and it is being added to
  livespec-dev-tooling `.ai/factory-restart-cancels-runs.md`.
- **Narrow the restart play.** The full `fabro-hosts.yml` play kept the factory cancelled but
  not restarted for about 12 minutes; `--tags untagged` took under 3.

## Side findings from the same window

- **gmktec otel-receiver: a false deferred restart.** Its restart-pending marker had been
  written at first install (2026-10-18 02:42:53 PDT, two seconds before the service's first
  start) and never cleared. It was cleared by an allowed restart at 10:18:15Z on the
  coordinator's ruling. Spans resumed: the receiver's io grew once runs landed, and Honeycomb
  `fabro` held 1,247 spans from 10:18 to 10:25Z. The role defect is livespec-dev-tooling-y53v27.
- **Overseer dispatches failing with "the exact local Git commit could not be made
  available".** These are `overseer-a3gzyv` and `overseer-o6gmkk`. The failure is client-side:
  fabro-manifest makes one `git push` of the dispatch's `livespec/source/<uuid>` branch,
  discards the stderr, and maps any failure to Unpublished. An exact reproduction (same user,
  wrapper, no TTY, stderr kept) failed 2 of 3 times on GitHub's side: "remote: Internal Server
  Error" and "remote: fatal error in commit_refs". The pre-push hook passed every time, during
  the githubstatus incident "Pull Requests, Git Operations and Issues" (declared 09:49:55Z).
  The fix is filed as `bd-ib-uctbct` under this plan: a bounded retry with backoff on a
  transient remote rejection, and the push stderr kept in the error.

## Items

- Closed: `bd-ib-xoh477` (#21 `ad393441b`, #23 `c39bdbded`).
- Closed: `bd-ib-gmuxd4` (#22 `fcb4dc073`). Its fourth assertion, at least ten consecutive
  solo runs of the stall test binary at a load above 30, was taken on `c39bdbded` and recorded
  on the fork PR (comment 6629117836). Gate `20261104T103133Z-1125465` ran 10 runs, but only
  runs 1-3 started at a 1-minute load above 30; runs 4-10 passed at 25-29 and are not counted.
  The load-gated top-up `20261104T110347Z-1837828` added 7 runs, each started above 30. That
  gives 10 qualifying runs at a 1-minute load of 35.7-51.5, each 13/13. Across all 17
  consecutive runs, 0 failed, including the two real-clock tests tracked as `bd-ib-oeckki`.
  Counting only runs whose own start was above the threshold was this session's reading;
  the first gate's 10/10 alone would have been a mis-graded claim.
- `bd-ib-ljw2xg` (#19): the live-server proof is still owed, now on `c39bdbd`.
