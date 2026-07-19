# Handoff — otel-receiver-attr-verification

## ⇥ START HERE — this thread has ONE job

Confirm that the five O4 `run_turn` **span attributes** actually reach Honeycomb,
now that the receiver-side allowlist fix has landed on `master`. The fix is
already written, reviewed, tested, and merged — **nothing needs to be built.**
This thread is a *verification* thread, blocked only on an execution-context
condition described below.

**Definition of done:** one dispatch runs, and
`get_span_details(span_name="run_turn")` on the Honeycomb `fabro` dataset shows
`command`, `config_name`, `visit`, `stop_reason`, and `node_id` populated. Then
close `bd-ib-98c.2` and archive this thread.

## Context in one paragraph

The `codex-factory-telemetry` track (now archived at
`plan/archive/codex-factory-telemetry/`) restored factory observability for the
Codex era. Its last slice, **O4** (`bd-ib-98c.7`), added a `run_turn` span to
fabro at the ACP seam carrying which command an agent turn ran and how it ended.
The emitter half is **DONE and PROVEN**: the host binary is pinned to
`fabro 0.254.0 (b9b63a8)` and live dispatches put `run_turn` spans into
Honeycomb with the correct trace shape. But the spans arrived with **every O4
attribute silently dropped**, because our receiver's forwarded-attribute
allowlist is fail-closed. That allowlist was widened in **PR #777** (merged).
The widening has *not yet been observed working*, for the execution-context
reason below — that observation is all that remains.

## ▶ WHY IT IS NOT YET CONFIRMED (read before re-running anything)

The confirming dispatch (`bd-ib-98c.15`, green, PR #779 merged) STILL showed
`run_turn` spans with all five attributes missing. That is **not** a defect in
PR #777. Diagnosis, verified on 2026-07-19:

1. The OTLP receiver is a **single host-wide listener on `172.17.0.1:4318`**.
   Whichever dispatch starts first OWNS that listener, and it enriches/scrubs
   spans for **every concurrent dispatch**, not just its own.
2. At the time of the confirming dispatch, that listener was **pid 3916659**,
   owned by a *different*, concurrently-running factory loop:
   `python3 ~/.claude/plugins/cache/livespec-orchestrator-beads-fabro/.../b800fefde7ba/scripts/bin/dispatcher.py loop --repo /data/projects/livespec-orchestrator-beads-fabro --budget 1 --parallel 1 --item bd-ib-zaq3`
3. That process runs from the **INSTALLED PLUGIN CACHE**, not from the repo
   checkout. Verified at the time: `grep -c '"config_name"' _otel_scrub.py`
   returned `1` in repo `master` but **`0` in every plugin cache copy AND the
   marketplace copy**.

### The generalizable lesson (worth keeping)

A receiver-side change in this repo does **NOT** reach the running factory until
the installed plugin is refreshed to a commit containing it **AND** the process
that owns `:4318` restarts. Editing the repo alone is insufficient. This is the
same class of trap as the plugin-marketplace rule in `AGENTS.md` §"Agent
prerequisites for plugin work" — *establish execution context FIRST; trace where
the running code actually loads from before concluding a fix is broken.*

## ▶ NEXT ACTION — the exact procedure

**Preconditions (check BOTH before dispatching; otherwise you will re-run the
same false negative):**

```bash
# (a) Who owns the receiver right now, and from WHICH copy?
ss -ltnp | grep 4318                      # note the pid
tr '\0' ' ' < /proc/<pid>/cmdline; echo   # plugin cache path or repo path?

# (b) Does the code that pid loaded actually carry the fix?
grep -c '"config_name"' <that-path>/scripts/livespec_orchestrator_beads_fabro/commands/_otel_scrub.py
# 1 = has the fix, 0 = pre-fix (a dispatch now would be another false negative)
```

Also confirm the installed plugin has refreshed past PR #777:

```bash
grep -rc '"config_name"' ~/.claude/plugins/cache/livespec-orchestrator-beads-fabro/*/*/scripts/livespec_orchestrator_beads_fabro/commands/_otel_scrub.py | grep -v ':0$'
```

**Do NOT kill a running loop's receiver to force the issue** — that interrupts
someone else's in-flight dispatch. Wait for a window where either no loop owns
`:4318`, or the owning loop already runs post-fix code.

**Then:**

1. File a throwaway confirmation work-item (docs-only, mirroring `bd-ib-98c.15`;
   see `plan/archive/codex-factory-telemetry/handoff.md` for the established
   pattern) and promote it to `ready`:
   `bd update <id> -s ready`.
2. Dispatch it, from inside the env wrapper:
   ```bash
   /usr/local/bin/with-livespec-env.sh -- .claude-plugin/scripts/bin/dispatcher.py \
     dispatch --repo /data/projects/livespec-orchestrator-beads-fabro --item <id> < /dev/null
   ```
3. Verify in Honeycomb (`livespec` env, `fabro` dataset), via the Honeycomb MCP:
   `get_span_details(span_name="run_turn", time_range="30m")`.
   **PASS** = `command` / `config_name` / `visit` / `stop_reason` / `node_id` all
   populated. **FAIL** = they are absent again → re-check the preconditions
   above before suspecting the code.
4. On PASS: close `bd-ib-98c.2`, record the result on `bd-ib-98c.7`, and archive
   this thread.

## What "correct" looks like (the already-proven half)

The emitter is known-good; do not re-litigate it. Reference shape, verified live
in trace `4881b84df66381b29f67f7c482ee259b`:

```
<root>            run       ← SERVER run span
└─                run       ← WORKER run span (O2 traceparent join)
   ├─             run_turn  (304.2s)
   ├─             run_turn  (44.1s)
   └─             run_turn  (68.6s)
```

Three `run_turn` spans = the three agent turns, nested under the **worker `run`
span**. **NOT** under a `Stage` span — `Stage started/completed` are tracing
EVENTS (`meta.annotation_type=span_event`), not spans, and fabro-workflow had no
spans of its own before O4. An earlier draft of the O4 verification asserted a
Stage-span parent; that check can never pass. Span **events** also *bypass* the
allowlist entirely, which is exactly why the node-lifecycle attributes were
always visible while O4's span attributes were not.

## References

- **Ledger:** `bd-ib-98c.2` (receiver-side item; carries the full root-cause
  comment) and `bd-ib-98c.7` (O4; carries the emitter proof). Epic `bd-ib-98c`.
- **The merged fix:** PR #777 — `_otel_scrub.py` `ATTRIBUTE_ALLOWLIST` gains
  `command`, `config_name`, `visit`, `stop_reason`, `node_id` (Red→Green, with
  `TDD-*` trailers). The drop site is `_otel_enrich.py`
  (`if not is_allowed_attr(key=key): continue` — no error, no log line).
- **Proof dispatches:** `bd-ib-98c.14` → PR #774 (emitter proven, attributes
  dropped); `bd-ib-98c.15` → PR #779 (the false negative diagnosed above).
- **Archived parent track:** `plan/archive/codex-factory-telemetry/` —
  `handoff.md` (full arc), `o4-acp-turn-plan.md` (O4 build plan + corrected
  verification step), `emitter-replan.md` (the O1–O5 decomposition).
- **Runbook:** `orchestrator-image/README.md` §"Host Fabro server" — the pinned
  binary, the carried-fix table (incl. O4), and the corrected re-pin procedure
  (stage + atomic `mv`; a plain `cp` over the running binary fails `ETXTBSY`,
  and a silently-failed `cp` then a restart brings the server back up on the OLD
  binary).

## Do NOT

- Do NOT rebuild or re-pin fabro. The emitter is done and pinned
  (`fabro 0.254.0 (b9b63a8)`, `origin/factory-integration` = `b9b63a8a6`).
- Do NOT "fix" the allowlist again. It is already correct on `master`; a missing
  attribute means stale execution context, not a bad patch.
- Do NOT kill a running loop's receiver on `:4318` to force a clean run.

## Known limitations carried over (not this thread's job)

- **Parallel-branch spans orphan.** `fabro-workflow/src/handler/parallel.rs`
  runs branches via bare `tokio::spawn` with no span propagation, so a
  `run_turn` inside a PARALLEL branch exports as an orphan root rather than
  joining the dispatch trace. Pre-existing; sequential factory workflows are
  unaffected. O4 is simply the first place it became visible.
- **`acp.command` is now load-bearing off-host.** It egresses to Honeycomb, so
  it must stay argv-only and secret-free (ACP credentials are env-injected,
  never argv). The credential-URL scrub + `ATTR_MAX_LEN` truncation are
  defense-in-depth, not the primary guarantee.
- **O5 token/cost** (`bd-ib-98c.8`) remains deferred, and the O2 capture-site
  test guard (`bd-ib-98c.11`) remains open. Neither belongs to this thread.
