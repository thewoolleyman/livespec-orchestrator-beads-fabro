# Dossier 002 — root-cause pass on a second live specimen

Root-cause evidence for plan thread `acp-implement-zero-output-hang`
(ledger epic `bd-ib-b5dg`). Compiled 2026-08-30 from a fresh reproduction
relayed by the console-repo foreman (session `livespec-console-beads-fabro-foreman`)
plus a read-only `fabro dump --server hp` of two runs. Claims are labelled
**measured**, **inferred**, or **hypothesis**; do not strengthen a label when
quoting. Supersedes nothing in dossier 001 — it extends it and CORRECTS one of
its hypotheses (see §"Item dimension").

## Specimens

Both captured read-only (`fabro dump ... --server https://hp-xubuntu…:32276`)
before reap; artifacts held under the session scratchpad, not committed.

- **Fresh:** run `01M17P0QHRH7ZYXJ6DVTRSFAV4`, factory `hp`, dispatched
  2026-08-29 21:15:08Z for `livespec-console-beads-fabro-txtzn5.14`
  (re-dispatch under the post-ensure-plugins dispatcher). Terminal
  `failed`/`workflow_error`.
- **Morning (dossier 001's):** run `01M16KMWY5Y2DY0X90S1BDXCQX`, same item
  `.14`, dispatched 11:14:31Z. Terminal `failed`/`workflow_error`.

## The mechanism, measured on the fresh run

Event trace and `run.log` agree line-for-line:

1. Sandbox ready (image `python-rust-agent-v1.36.0`); **24 setup commands
   completed in 18.9s**. The environment/setup is healthy — **measured**.
2. `implement` node, attempt 1: `agent.acp.started` + `agent.session.activated`
   at 21:15:34.124Z. **Then the event stream is SILENT for the full 30
   minutes** — no intervening events at all — until `agent.acp.timed_out` at
   21:45:34.879Z (`dur≈1800030ms`). `output.log` is **0 bytes**; the stage
   `script_timing.json` records `stdout:"" stderr:"" duration_ms:1800030`;
   `active_time_ms=0`. **measured**.
3. Attempt 2 (in-run retry): re-activated 21:45:38.302Z, identical 30-min
   silent timeout at 22:15:38.977Z, `will_retry=false`. **measured**.
4. Edge → `escalate` (human gate) at 22:15:41Z; `run.blocked`
   `HumanInputRequired`. **Nobody answered it** — at 01:15:32Z `run.unblocked`
   is immediately followed by **fabro's own `escalate`-node stall watchdog**
   (`idle_seconds=7200`) failing the run `category=deterministic`,
   `wall_time_ms=14400002`, `active_time_ms=0`. So the specimen aged out on
   fabro's watchdog; it was not dispositioned by the console worker. **measured**.

So: the agent activates its ACP session and **never begins inference** — zero
tokens, `active_time_ms=0`. The block is at the ACP session/launch layer,
BEFORE the prompt is processed.

## What this refutes and what it leaves open

- **Item CONTENT is refuted as the mechanism.** The rendered `prompt.md` is a
  clean 22,128-byte coverage-closing task with ZERO template-opener occurrences
  (`{{`, `{%`, `{#` all count 0 — no poisoning per the CLAUDE.md ledger-text
  trap). And since inference never starts, no property of the prompt text can be
  what hangs the agent. **measured + inferred.**
- **Item CORRELATION remains open, and dossier 001's launch-env hypothesis
  needs the item dimension the foreman added.** `.14` hung on BOTH its dispatches
  today (11:14 and 21:15, ~10h apart); `ag0` completed 2/2 on the same factory
  the same day. A pure wall-clock token-expiry story does not fit: an `ag0`
  dispatched 11:20:33Z (PR #876) succeeded while a `.14` dispatched 11:14:31Z —
  six minutes EARLIER — hung. So time-of-day token expiry is **refuted** as the
  sole cause. What is item-adjacent about `.14` that survives a 10h gap and acts
  BEFORE inference is **unexplained** — candidates (all **hypothesis**): a
  per-dispatch credential lottery that `.14` keeps losing; a remote branch-state
  interaction (`feat/…-txtzn5.14` persists from the prior hung run); or
  coincidence at n=2. Do NOT assert an item-specific cause without a larger n.
- **The `github_token_refresh_limited` run.notice is NOT evidence of an expired
  token here.** It is emitted at the start of EVERY ACP agent stage as a standing
  caveat ("stages receive workflow env at process launch"), on both attempts, on
  healthy and hung runs alike. **measured** (present verbatim in `run.log`).

## The orchestrator-side gap (aim 2's target)

**measured:** the orchestrator's coarse stall watchdog did NOT pre-empt either
30-min dead turn. `_dispatcher_watchdog.py` has `DEFAULT_STALL_SECONDS=1500`
(25 min) and reads the max `fabro events` timestamp; with the event stream frozen
at 21:15:34Z, an engaged `WatchedFabroLauncher` (polling every 30s) should have
confirmed a stall at ~21:40 and killed via `fabro rm -f` — five minutes before
fabro's own 30-min turn timeout. It did not. Fabro's native turn timeout caught
each turn instead.

Load-bearing OPEN sub-question, requires console-tenant dispatcher evidence
(coordinate via console epic `livespec-console-beads-fabro-4jb3kl`): **was the
`WatchedFabroLauncher` engaged on this console dispatch path at all?** The two
live outcomes are:
- If NOT engaged → aim 2 is partly a wiring/config gap: the coarse watchdog
  already exists and would have fired; ensure the console dispatch path uses it.
- If engaged and it still didn't fire → aim 2 needs the watchdog logic itself
  fixed (floor, or the "unchanged across span" confirmation in `decide_stall`),
  and a zero-output-turn-specific fast path below fabro's 30-min turn ceiling.

Either way the remedy is orchestrator-side (per dossier 001's assessment); this
pass sharpens WHICH orchestrator change.

## Bearing on the three aims (grooming/cut still deferred)

- **Aim 1 (root-cause):** substantially advanced but not closed. Confirmed:
  reproducible for `.14`, pre-inference ACP block, coarse watchdog did not fire.
  Open: WHY zero output (credential vs ACP-adapter-startup vs item-adjacent), and
  whether the watchdog was engaged. The remaining evidence lives (a) inside the
  sandbox agent process (its own logs — the dump's `output.log` is empty because
  the ACP adapter wrote nothing) and (b) in the console dispatcher journal/config.
- **Aim 2 (fail-fast):** target confirmed = make the orchestrator kill a
  zero-output/silence turn below fabro's 30-min ceiling and retry-with-fresh-env
  or fail typed. Cross-ref `bd-ib-oj71` (distinct Codex-exhaustion trigger, same
  fail-fast shape).
- **Aim 3 (telemetry):** the orchestrator can surface its OWN kill/typed-failure
  outcome; the per-turn zero-output SOURCE datum stays fabro-side/deferred
  (`_dispatcher_heartbeat_probe.py`, work-item `29f.6`).
