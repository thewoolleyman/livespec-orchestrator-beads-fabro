# Live TDD calibration provisioning receipt

Work item: `bd-ib-i56nut`. Environment: `livespec`, team `thewoolleyweb`,
dataset `livespec-dispatcher`. Provisioning measurements were taken on
2026-10-07 UTC. The appended 2026-10-08 measurement records the subsequently
observed seven-field terminal event; the earlier negative observation remains
historical evidence. Formal host capture and independent replay are separate
from this receipt.

## Executed artifact and historical invocation

The provisioner and its three definition files were byte-identical to release
`v0.173.7`, commit `7eea7be2dbb633eed6f73577eb82dfca1394a40d`.
They ran from the ordinary primary checkout at
`c09b37d6b3d313f81bce9fc2e3bd040802480019`; no plugin cache was pinned or
substituted. The following content check returned zero before execution:

```bash
git diff --exit-code v0.173.7 -- \
  orchestrator-image/provision-honeycomb-tdd-calibration.sh \
  orchestrator-image/honeycomb
```

The following historical command ran from the repository root using its normal
credential wrapper. It used an existing recipient identifier, not a new
notification destination. Read the credential-transport limitation below before
considering a replay:

```bash
mise exec -- just gate-start -- \
  /data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  env HONEYCOMB_OPERATOR_ALERT_RECIPIENT=jKw2EyfLJ3W \
      HONEYCOMB_TDD_TRIGGER_WINDOW_SECONDS=28800 \
  bash orchestrator-image/provision-honeycomb-tdd-calibration.sh
```

The wrapper supplies the configuration key. The operator invocation contains no
literal key, but the released script expands it into curl's `--header` argument.
It is therefore NOT protected against process-argument inspection, contrary to
the script's own comments. Independent review identified this inherited defect;
separate backlog item `bd-ib-lckfxl` owns private header transport and a sentinel
credential regression. This receipt neither proves argv secrecy nor repairs it.
Do not print credentials, inspect live secret-bearing argv, or copy host keys
into a sandbox. The public resource identifiers below are not credentials.

## Live API refusal and supported configuration

The first invocation, at 23:38 UTC, created both derived columns, all seven
queries and annotations, and the board. The trigger rejected the default
86,400-second window:

```text
resource: trigger
request: POST https://api.honeycomb.io/1/triggers/livespec-dispatcher
http status: 422
response: {"error":"query: time_range: must be no greater than 28800.."}
```

The committed trigger definition explicitly prescribes 28,800 / 7,200 seconds
as its already-known fallback. Applying that configuration succeeded. This was
an operator-configurable API limit, not a change to the implementation or a
suppressed check.

The live trigger is enabled, evaluates every 7,200 seconds over 28,800 seconds,
and alerts on `AVG(tdd_post_hoc_red_flag) >= 0.25`, with `exceeded_limit=1` and
`alert_type=on_change`. It excludes `tdd_post_hoc_red = unknown` and uses the
existing recipient `jKw2EyfLJ3W`. Its tags are `owner:livespec` and
`workitem:bd-ib-3h5vfq`. The classifier's timing threshold is 120 seconds;
the actual expression uses `LT`, so equality alone does not classify a run
as post-hoc. These are starting monitoring parameters, not a newly ratified
admission threshold.

## Resource identities and repeat application

[Open the live board](https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/gfiN4nKP8o3).

| Resource | Identifier |
| --- | --- |
| `tdd_post_hoc_red` derived column | `44RAwgsXUoh` |
| `tdd_post_hoc_red_flag` derived column | `EkWwa8x47JG` |
| TDD calibration board | `gfiN4nKP8o3` |
| Post-hoc Red share trigger | `EQMwDT61A6s` |

| Panel, in committed order | Query | Annotation |
| --- | --- | --- |
| Post-hoc share by repository | `9qZMyMGY8Gd` | `J3fFWRBF4kv` |
| Post-hoc share by adapter | `hEsdUSxxASj` | `6ADv1FtbKAB` |
| Red-to-Green gap | `6Fuhr4vQyXP` | `txVkX3G6CH` |
| Order refusals | `niejqSiwqK` | `u8rFC61Y1bP` |
| Cycles against assertions | `GSLAjHyLc1H` | `xveDqHkx3zf` |
| Suite-green with first-write-before-Red | `GVc9yKum3o2` | `gitnmpWThte` |
| Classification coverage | `fzHKXjnbMf3` | `h2VPf7VSNnK` |

The successful complete applications were gate runs
`20261007T233843Z-3512802` and `20261007T233901Z-3516407`.
The latter finished at 23:39:12 UTC with exit zero. It reported `updated` for
both derived columns, all annotations, the board and trigger, and `reused query`
for all seven query identifiers. No second set of resources was created.
Independent API reads confirmed the seven panels, positions, derived expressions,
trigger window, threshold, frequency, and recipient.

## Historical telemetry boundary: provisioning alone was not proof

The live query at 23:36 UTC required `name = dispatcher.calibration` and
`exists` for each of these fields on the SAME event:

- `tdd.red_commit_count`
- `tdd.green_commit_count`
- `tdd.red_green_gap_seconds_median`
- `tdd.suite_green_count`
- `tdd.assertion_count`
- `tdd.first_product_write_before_red`
- `tdd.order_refusals`

[The 24-hour query returned zero matching events](https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/livespec-dispatcher/result/6183sxWC9fP).
Span discovery was a positive control: terminal calibration events did exist,
and each of the seven columns was populated somewhere in the selected dataset,
but not all seven together. Aggregate zero is not proof of field presence;
`MAX` and `SUM` can render zero for an absent value. Likewise, repeated
calibration spans must not be reported as distinct runs without checking run
identity. That observation did not establish completion.

The shipped seven-panel queries were accepted against live data. Their
classification coverage showed unknown events, which remain visible rather
than being silently counted as healthy. Provisioning did not emit synthetic
factory telemetry or manufacture a run identity.

## Terminal seven-field observation — 2026-10-08 UTC

[The live raw-row query](https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/livespec-dispatcher/result/xSYnaiExsdx)
returned four rows at the SAME timestamp, `2026-10-08T01:24:05.580675626Z`,
for `work.item.id = bd-ib-juvega`. These are repeated exports of one terminal
event, not four independent runs. Every row contained all seven fields:

| Field | Observed value |
| --- | --- |
| `tdd.red_commit_count` | `3` |
| `tdd.green_commit_count` | `3` |
| `tdd.red_green_gap_seconds_median` | `360` |
| `tdd.suite_green_count` | `0` |
| `tdd.assertion_count` | `3` |
| `tdd.first_product_write_before_red` | `true` |
| `tdd.order_refusals` | `19` |

The dispatcher journal associates this item with dispatch
`b9e1b5a76c384339b0f65fb77ac1ee72` and HP run
`01M4CBAD9QMGTJGX807QMVDTDM` on
`https://hp-xubuntu.perch-rudd.ts.net:32276`. The real run succeeded;
[PR #2652](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2652)
merged as `f95ad6fd45e6058ad521eabfd8e6b6c7043bf9fe`.
The detached dispatcher gate `20261007T233025Z-3357009` completed with exit
zero at `2026-10-08T01:24:22Z`. Its collector/exporter started on released
`v0.173.7`; installing `v0.173.8` during the run does not retroactively change
that provenance. The exported OTLP span has trace ID
`6a8091f1e6728e646c1b3686c00a098f` and span ID `462e34da22cdf8ff`.

This proves field delivery, NOT healthy test-first ordering. In particular,
`first_product_write_before_red = true` and nineteen order refusals are real
adverse measurements. Zero suite-green count is a present numeric field, not
an aggregate substitute for missing data. The terminal outcome was `green`
with `converged = true`; neither label cancels these ordering observations.

### Reproduction

Use Honeycomb's `run_query` with the following request (raw rows, no aggregate
calculations). It reproduces the original absolute time window and field-presence
test rather than relying on today's default time range:

```json
{
  "environment_slug": "livespec",
  "dataset_slug": "livespec-dispatcher",
  "query_spec": {
    "from": "2026-10-08T01:23:00Z",
    "to": "2026-10-08T01:26:41Z",
    "filters": [
      {"column": "name", "op": "=", "value": "dispatcher.calibration"},
      {"column": "tdd.red_commit_count", "op": "exists"},
      {"column": "tdd.green_commit_count", "op": "exists"},
      {"column": "tdd.red_green_gap_seconds_median", "op": "exists"},
      {"column": "tdd.suite_green_count", "op": "exists"},
      {"column": "tdd.assertion_count", "op": "exists"},
      {"column": "tdd.first_product_write_before_red", "op": "exists"},
      {"column": "tdd.order_refusals", "op": "exists"}
    ]
  },
  "raw_row_columns": [
    "work.item.id", "tdd.red_commit_count", "tdd.green_commit_count",
    "tdd.red_green_gap_seconds_median", "tdd.suite_green_count",
    "tdd.assertion_count", "tdd.first_product_write_before_red",
    "tdd.order_refusals"
  ],
  "results_limit": 10
}
```

Cross-check the exported span and real remote run from the ordinary primary
checkout, preserving the configured credential route and explicitly aiming at HP:

```bash
jq -c '.resourceSpans[].scopeSpans[].spans[] |
  select(any(.attributes[];
    .key == "work.item.id" and .value.stringValue == "bd-ib-juvega")) |
  {name, traceId, spanId, startTimeUnixNano, attributes}' \
  tmp/fabro-dispatch-journal-calibration-spans.jsonl

/usr/local/bin/with-livespec-env.sh -- env PATH="$PATH" \
  fabro inspect 01M4CBAD9QMGTJGX807QMVDTDM \
  --server https://hp-xubuntu.perch-rudd.ts.net:32276 --json |
  jq '.[] | {run_id, status,
    conclusion: (.conclusion | {status, timestamp, final_git_commit_sha})}'
```

The local journal is a cross-check, not a substitute for the live Honeycomb
result. The resource identifiers, repeat-application receipts and monitoring
threshold above still apply. No synthetic telemetry was emitted to satisfy
this observation, and no additional provisioning was needed.
