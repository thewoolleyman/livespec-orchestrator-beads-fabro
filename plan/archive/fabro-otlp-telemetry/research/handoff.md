# Fabro OTLP telemetry — handoff

## Resume contract

The next-session prompt is:

```text
Open plan/fabro-otlp-telemetry/handoff.md and execute its Next action.
```

Read these committed artifacts in order:

1. `plan/fabro-otlp-telemetry/research/findings.md`
2. `plan/fabro-otlp-telemetry/research/quarry-otlp-logs-export-2026-08-02.md`
3. `plan/fabro-otlp-telemetry/pr-576-comment.md`

The findings document contains the source links, dated forge state, technical
review, and ledger reconciliation. The timestamped Quarry file preserves the
actual Markdown source because the temporary external document advertises an
expiry date. The comment file is the exact response that was posted and is
enclosed in a preformatted block that preserves its literal Markdown backticks.

## Purpose and decision boundary

This thread coordinates the proposed rewrite of
[fabro-sh/fabro PR #576](https://github.com/fabro-sh/fabro/pull/576) from its
current `tracing`-span transport into an initial canonical
`RunEvent`-to-OTLP-logs slice.

Bryan (`brynary`) proposed the new direction in
[comment 5079036739](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5079036739)
and linked the Quarry design captured by this thread. The maintainer agrees that
the direction is promising and offers to rewrite the PR, but the rewrite is
deliberately on hold until Bryan confirms that this is the direction he wants
for PR #576. Do not modify the upstream branch merely because the design is
detailed; confirmation is the coordination gate.

The maintainer posted the reviewed response on 2026-08-02 at 03:31:41 UTC as
[comment 5154982522](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5154982522).
The posted body matches the response preserved in `pr-576-comment.md`. The
complete PR conversation contained no later reply from Bryan as of the forge
read immediately after posting. Recheck the live conversation before repeating
that absence claim.

## Ledger relationships

The ledger is the source of lifecycle status. Refresh it rather than copying a
status from this handoff:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- bd show bd-ib-zjz3ie --json
/data/projects/1password-env-wrapper/with-livespec-env.sh -- bd show bd-ib-98c --json
/data/projects/1password-env-wrapper/with-livespec-env.sh -- bd show bd-ib-i4r --json
```

The three records have different responsibilities:

| Work item | Responsibility |
| --- | --- |
| `bd-ib-zjz3ie` | This plan thread's epic anchor and the durable coordination record for the proposed PR #576 direction change. |
| `bd-ib-98c` | The broader Codex-era factory-observability context that explains why Fabro telemetry is operationally important. |
| `bd-ib-i4r` | The direct upstream PR #576 record. Its description still reflects the older tracing-span transport and must not be mistaken for the proposed current design. |

The relationship is recorded in the new epic description and in these plan
artifacts. No formal `depends_on` edges were added: such edges express lifecycle
blocking, while these records currently supply coordination and historical
context. If Bryan confirms the logs direction, regroom or supersede
`bd-ib-i4r` so its durable implementation description matches the accepted
upstream scope. Do not rewrite it speculatively while upstream direction is
unconfirmed.

## Settled findings

The later Bryan comment supersedes the earlier traces-only framing as the
candidate upstream direction. The original PR remains useful prior art for the
stable background-thread exporter choice, but its developer-`tracing` surface is
not the intended telemetry contract in the Quarry proposal.

The proposed architecture is sound in its main shape:

- Treat eligible, non-streaming canonical `RunEvent` values as structured OTLP
  log records.
- Keep the first increment logs-only and defer trace and metric design.
- Add a dedicated `fabro-otel` foundation crate and compose an OTLP sink beside
  the existing event sinks.
- Keep export opt-in, bounded, redacted, batched, and unable to fail a run.
- Resolve configuration centrally and propagate resolved standard `OTEL_*`
  settings to workers.

Four corrections must survive into any rewrite:

1. The proposed dependency features do not support the stated batching path.
   OpenTelemetry Rust 0.32's stable `BatchLogProcessor` supports the blocking
   reqwest client on its dedicated background thread. Async reqwest requires
   the experimental async-runtime log processor and its separate feature. The
   proposed first slice should use the stable processor with
   `reqwest-blocking-client` unless upstream explicitly chooses the
   experimental processor.
2. The proposed strict logs-only dependency claim is not achievable with the
   listed OTLP HTTP encodings in version 0.32: both `http-proto` and
   `http-json` force-enable the SDK's trace and metrics features. The slice can
   still be logs-only behaviorally.
3. The scope is eligible, non-streaming events, not literally every event.
   `TextDelta` and `ToolCallOutputDelta` are explicitly excluded by the
   Quarry decisions.
4. Redaction parity should compare the semantic redacted property values.
   The proposed OTLP body is a structured `properties` map, whereas
   `redacted_event_json` serializes the entire event envelope; literal
   whole-record byte parity is not the correct assertion.

Two explicit policy decisions should remain visible:

- Propagating OTLP headers through worker environment variables is deliberate
  in the Quarry proposal. It increases descendant credential exposure and is
  justified there by current worker behavior. The reply does not reopen that
  settled design discussion, but implementation and operator documentation
  must not conceal it.
- Redaction removes recognized secrets; it does not make exported content
  metadata-only. Operator documentation must state plainly that redacted event
  properties can include prompts, responses, patches, commands, and similar run
  content.

## Next action

Wait for Bryan's confirmation or correction on
[the posted response](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5154982522).
Before acting, re-read the complete PR conversation. Do not repost the response
and do not rewrite the branch while the coordination gate remains unanswered.

If Bryan confirms the proposed direction, update the ledger description for the
direct upstream work, derive the implementation plan against current Fabro
`main`, and rewrite the outward-facing PR directly. This work is not
factory-safe because it changes an upstream repository and depends on maintainer
coordination.

If Bryan changes or declines the direction, capture his ruling in
`research/findings.md`, revise this handoff, and reconcile `bd-ib-i4r`
accordingly. Do not preserve a superseded recommendation merely because it is
already written here.
