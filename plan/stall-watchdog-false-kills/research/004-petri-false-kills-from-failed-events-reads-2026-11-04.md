# Petri false kills from failed events reads (2026-11-04)

This note was measured 2026-11-04 between 16:29Z and 16:50Z by session stall-watchdog-false-kills. The plan was resumed at
priority 2, on legacy-coordinator-agent's relay of the maintainer's priorities record (16:26:32Z on livespec-dev-tooling-6tgd2z).
The plan's recorded next action was to wait for the first petri `watchdog-stall-cancel` at or after v0.281.0. Four such cancels
already existed, so this note takes them.

## The four cancels

Every launch used build 5504f15bf67d (v0.283.0), which contains bd-ib-7eimxr (the Petri stream readers) and bd-ib-u6dglg (cancel
through the server route). Every row has `factory: petri`, `stall_layer: default`, `stall_seconds: 7200`, and null
`executing_stage`, `published_head` and `pull_request`.

Each run was exported before petri could prune it, with
`carrier-petri-v0.382-adeefec4c/fabro dump <run> --server https://gmktec-xubuntu.perch-rudd.ts.net:32276`. The exports are in
`tmp/stall-watchdog-exports/<run>/` in the primary checkout. They are gitignored, so this note is the durable account.

The "last event" and "gap" columns are read from each export's `events.jsonl` (`recorded_at`, in epoch ms):

| Item | Run | Cancel (Z) | Row quiet_seconds | Last event before cancel | Gap | Stage at cancel |
|---|---|---|---|---|---|---|
| bd-ib-ebdvbn | 01M6K1ZE1RWC2AFFTPGGYPB4HD | 13:12:51 | 7289 | 13:12:36 `step.progress.recorded` | 14 s | fix, started 12:58:22 |
| bd-ib-a7zpxy | 01M6K1WBF6KW6K5DPW4BVG5KKC | 15:12:16 | 7262 | 15:03:59 `step.progress.recorded` | 496 s | publish_draft@2, started 14:59:32 |
| livespec-dev-tooling-n6vnhp | 01M6K2K3MMZS340ZN18BGP3RY0 | 15:34:55 | 7319 | 15:34:54 | 1 s | publish_draft, started 15:31:11 |
| livespec-dev-tooling-dnokt2 | 01M6K30WSVGBKBY8V4ERW74GTG | 16:01:29 | 7223 | 15:46:16 `step.progress.recorded` | 912 s | publish_draft, started 15:46:13 |

All four are false kills. Plan assertion 4 is violated by every one of them.

None of these runs had a command node past its timeout. Their publish_draft stages ran for 12m44s, 3m44s and 15m16s before the
cancel. The coordinator's push-hang reading of n6vnhp ("4h50m silent at the publish_draft@2 push") came from the run's whole
length: n6vnhp launched at 10:45Z.

## Cause

- **Probe reads time out.** At 16:35Z, `fabro events <run> --json` on 01M6K2K3MMZS and 01M6K30WSVGB returned 0 bytes in 300 s
  (exit 124). The same read on 01M6K1WBF6KW at 16:43Z returned after 248 s, with 69,823,433 bytes and 12,881 records. A separate
  read, `-n 3` on 01M6K1ZE1RWC, exceeded 120 s (bd-ib-2dlh7m comment, 16:10Z). `fabro inspect` on the same runs answered
  promptly.
- **A failed read keeps the old instant.** The probe reads with `FABRO_PROBE_TIMEOUT_SECONDS` (60 s). On a failed read,
  `_dispatcher_io_liveness_probe.py:96-100` keeps `newest_event_epoch` at its last value and still returns a sample. The quiet
  window therefore grows across polls that observed nothing.
- **When the reads started failing.** Each row's `quiet_seconds` puts the last successful read about 7200 s before its cancel. For
  ebdvbn that is about 11:11Z, roughly 37 minutes after launch. The runs' streams were then several MB and growing.
- **Why the stage is null.** The same failed read, made by `watchdog_run_reading` (`_dispatcher_watchdog_run_probe.py:61`) just
  before the cancel, passes the empty string to the stage and publication readers. That is why the stage is null even with
  bd-ib-7eimxr's parser present.

Scenario 173 already says a failed per-run read makes the poll unobservable. A ratified clause under `## Grooming and slice-size
calibration` says "A failed events read MUST be treated as an unobservable sample, never as the run having disappeared or having
made no progress." The current code contradicts both.

## Dispositions (2026-11-04)

- **bd-ib-snq7o6 (filed, P2, ready).** A failed or timed-out events read does not count as quiet time. The stage is read from the
  run's by-id status or stage record. The release comment stops saying `fabro rm -f`. legacy-dispatcher-agent was asked to ticket
  it at the head of P2.
- **Interim lever.** On legacy-coordinator-agent's R493 ruling, `dispatcher.stall_timeout_seconds: 21600` was set in the committed
  `.livespec.jsonc` of this repository, livespec-dev-tooling and livespec-overseer. Those three are the highest-volume petri
  dispatch targets since 2026-11-01. A silent run is then left to the whole-run wall budget (21600 s), which exports before it
  cancels. Revert those keys once bd-ib-snq7o6 is released. Running loops keep their frozen 7200 s window.
- **bd-ib-lkta5g.** Now carries fabro-currency's request_stop hypothesis as an unmeasured candidate cause, and keeps that class
  owned by this plan. No sandbox-driver child was filed without a measured instance.
- **bd-ib-u6dglg host leg captured.** A `host_recorded` record is posted: all four records survive with `failed/cancelled`, and
  `fabro events` returns the stream (in 248 s). A separate session must post `host_verified`.
- **publish-draft-green-work-loss** was told (comment on bd-ib-acrr56) that its push-hang premise for n6vnhp and a7zpxy is refuted.
  Neither class should be filed there.

## Effect on the plan Proof of Done

Assertion 4's earlier reading (research note 003: 0 cancels in 360 dispatches, 2026-10-18 to 2026-10-25) predates the Petri
cutover and is superseded. "The fixes" now include bd-ib-snq7o6, so assertion 4 is taken over the seven days after its release.
Assertion 2 also waits for it, since every petri cancel today records a null stage.
