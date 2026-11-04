# Capture attempt: assertion 4 taken, assertions 1-3 blocked by Petri readers (2026-11-03)

This note was measured 2026-11-03 by session stall-watchdog-false-kills (Claude session cab279a1). The seat had been parked after the
master-red fix (PR #4157). The overseer then directed it to continue the plan. The plan's next step was the Proof of Done capture,
whose date gate passed at 2026-10-25T04:48:24Z.

## Assertion 4: the seven-day window, taken

The method is the 2026-10-18 06:00Z handoff's, unchanged. I read `tmp/fabro-dispatch-journal.jsonl` in every primary checkout
under `/data/projects` and in every worktree under `~/.worktrees/*/*`. That is 16 files, and none had an unparseable line.

| Reading | Value |
|---|---|
| Window | 2026-10-18T04:48:24Z (v0.211.5 published) to 2026-10-25T04:48:24Z |
| `watchdog-stall-cancel` rows in the window | **0** |
| Denominator: distinct `dispatch_id` values in the window | 360 (360 `dispatch-id` rows, 349 `fabro-run` rows, 812 distinct run ids) |
| Runs reaching janitor in the window | 232 `janitor-checkout-add` rows, 228 `janitor-post-merge` rows |
| Positive control: cancels across all time | 17, so the query can return a hit. The 06:00Z count was 15; adding the 3 below would give 18, and this note does not establish which earlier row is no longer present (a removed worktree journal is the likely cause). |

The denominator is not negligible: 360 dispatches. That retires the 06:00Z caveat that the window might be vacuously empty.

Three cancels fall **after** the window, all on `petri` at the default 7200 s window:

| At | Run | Item | quiet_seconds | executing_stage | published_head |
|---|---|---|---|---|---|
| 2026-10-31T07:37:06Z | 01M686BDQ9HTAQXRQEX98WRTQE | bd-ib-crtnzx | 7282 | null | null |
| 2026-10-31T20:28:21Z | 01M69H1QHVQ902M6B0D6QMH0TM | bd-ib-dwzkjg | 7243 | null | null |
| 2026-11-02T20:53:35Z | 01M6ENNY7EFP82HV5K02T3W38G | bd-ib-yuwftp | 7246 | null | null |

They do not bear on assertion 4's window, but the null fields are what the next section explains.

## Assertions 1-3: the readers do not parse the Petri stream

Since the cutover, `petri` is the default factory (the gmktec-xubuntu :32276 Petri-era server). hp was retired on 2026-10-24, and
the retired `hp` name falls back to `petri`. Assertion 1 names hp, so its proof can only be taken on petri.

The stall watchdog's three event readers match the pinned-build shape: `stage.started`, `stage.completed` and `stage.failed`,
keyed by `node_id`. The readers are `open_command_node` in `_dispatcher_open_command_node.py`, and `executing_stage` and
`last_publish_draft_publication` in `_dispatcher_stall_run_reading.py`. The Petri stream instead puts the event name at
`item.record.body.event`: `step.started`, `step.finished`, `step.progress.recorded` and `routing.resolved`. It puts the node at
`item.subject.node`, with `name` and `kind` (for example `attractor/command`).

Reproduction: live petri run 01M6FCWTFW32X2AN9JS6DAP5MN, read while inside `publish_draft`. Its last records were
`admission.decided`, then `step.started publish_draft attractor/command`, then `step.progress.recorded`; there was no
`step.finished`. I read the stream with the configured Petri client, `carrier-petri-v0.382-adeefec4c/fabro events <run> --json`,
which returned 9.1 MB and 4,822 records. The record counts were `step.progress.recorded` 4143, `step.started` 61 and
`step.finished` 60.

- `open_command_node(...)` returned `None`, although a command node was open.
- `executing_stage(...)` returned `None`.
- `parse_last_event_epoch(...)` returned 2026-11-03T01:16:03Z, which equals the last record. Event-time liveness works on Petri.

What this means for each assertion:

- **Assertion 1.** The open-command-node bound never applies on petri. A janitor or publish_draft node is protected only for as
  long as it keeps emitting `step.progress.recorded`. A silent command node gets the plain stall window. For yuwftp, the owner's
  hang triage shows `janitor@1` running when its run was cancelled.
- **Assertion 2.** Every petri cancel records a null stage. The release comment then misreports the null as "this dispatch
  journalled no cancel row for the item", although the row exists. This is the shared `UNREAD_CANCEL_ROW` text in
  `_dispatcher_stall_cancel_comments.py`.
- **Assertion 3.** The resume cancel anchor gates on `executing_stage` (`_dispatcher_resume_cancel_anchor.py`), and
  `published_head` is null. A stall-cancelled-after-publishing run on petri therefore cannot anchor a resume.

A side observation, outside this plan: one `fabro events --json` read of a 217-minute petri run did not finish within 120 s. The
watchdog's first, unbounded read uses a 60 s probe timeout (`FABRO_PROBE_TIMEOUT_SECONDS`). bd-ib-2dlh7m (unbounded `fabro events`
reads) and bd-ib-u6llci (whole-history re-reads) already track this.

## Disposition

- I filed **bd-ib-7eimxr** as a child of this epic (status `ready`). Its four-assertion Definition of Done covers the open command
  node, the executing stage, the publication fields, and the misleading release-comment wording, all on the Petri stream.
- The scope event of 2026-11-03 records the new carrier map: 1 → qsk4o5 and 7eimxr; 2 → nfbyot and 7eimxr; 3 → 3snvbf, qgcpoc
  and 7eimxr; 4 → plan-level proof. It also defers the capture until bd-ib-7eimxr is in a release.
- The capture is then retaken against that release. Assertion 4's reading above stands, and does not need to be re-taken over a
  new window.
