# Dossier 003 — root cause of the 2×30-min burn: watchdog discovery is blind on the remote factory

Closes the remedy-relevant half of aim 1 for plan thread
`acp-implement-zero-output-hang` (epic `bd-ib-b5dg`). Compiled 2026-08-30 from a
code read of the shared orchestrator plugin, a live `fabro ps -a --json
--server hp` measurement, and the console foreman's durable answer on console
epic `livespec-console-beads-fabro-4jb3kl`. Labels **measured** / **inferred** /
**hypothesis** as before.

## The question this answers

Dossier 002 established: the agent emits zero output before inference, and **the
orchestrator's coarse 25-min watchdog did not pre-empt the two 30-min dead
turns**. This note answers WHY the watchdog did not fire — the half of aim 1 the
fail-fast remedy (aim 2) actually depends on. It does NOT answer why the agent
emits zero output (aim 1's trigger half — see §"Still open").

## Root cause (measured, code + journal + live ps)

The watchdog IS wired on the path that ran these dispatches — `_dispatch_one_locked`
(`_dispatcher_loop.py:214-225`) calls `run_dispatch_with_watchdog(...,
fabro_launcher_type=WatchedFabroLauncher)`, shared by both the single-item
`dispatch` and the `loop` drain. **So this is NOT a wiring gap** (confirmed
independently by the console foreman: `WatchedFabroLauncher` was the production
launcher in both builds that ran all five hung console dispatches). **measured.**

The watchdog never fires on the `hp` remote factory because of its **discovery
step**, not its stall logic. In `WatchedFabroLauncher._watch`
(`_dispatcher_io_fabro_launcher.py:146`):

1. Each 30s poll calls `_discover_run` → `port.ps(...)` =
   `fabro ps -a --json --server <hp>` (`_fabro_port.py:129-131`).
2. `_discover_run` returns a run ONLY if a ps row matches
   `run.work_item_id == plan.work_item_id` AND
   `status_kind in {"runnable","running"}`.
3. If no row matches, `_watch` hits `if known_run_id is None or run is None or
   run.status_kind != "running": continue` — a **silent `continue`**.
   `decide_stall` is consulted ONLY on a poll where discovery succeeded.

So whenever discovery fails, the watchdog is a no-op with **zero per-poll
observability**. The console journal's entire history carries **zero**
`watchdog-stall-cancel` and **zero** `stalled-no-progress` records; the only
watchdog-family record ever is one `stale-run-reap` from 2026-08-17, before the
`hp` remote-factory cutover (console foreman, on 4jb3kl). **measured.**

## Which sub-condition fails — narrowed

The statically-checkable sub-conditions all WORK, so they are ruled out:

- **Server + `-a`:** `port.ps` passes both `-a` and `--server <hp>`
  (`_fabro_port.py:131`). Not a bare-`fabro ps`-defaults-to-local bug. **measured.**
- **Goal-text id extraction:** `_WORK_ITEM_RE = re.compile(r"^Work-item:\s*(\S+)",
  re.MULTILINE)` (`_fabro_port_records.py:24`). Measured live: the hp ps row's
  `goal` field for both `.14` runs **starts with** `Work-item:
  livespec-console-beads-fabro-txtzn5.14\n` at line 0, so the anchored regex
  matches and extracts the id. (Note the ps `goal` is ~8KB and DIFFERS from the
  22KB `prompt.md`, whose first line is `Goal: Work-item: …` — the anchored regex
  would MISS that, but the ps goal is the one discovery reads, and it matches.)
  **measured.** Caveat (**hypothesis**): ps goal truncation on some rows could
  still break the regex (foreman's note); not observed on these two.
- **status_kind mapping:** `fabro_status_kind_from_payload` reads `status.kind`
  from the ps row (`_fabro_port_records.py:155-166`); a terminal run reports
  `{'kind':'failed'}`, and a running run is expected to report `{'kind':'running'}`.
  **measured** for terminal; **inferred** for running.

What remains — and needs a **live-run** measurement (no live specimen exists
right now):

- **In-flight ps visibility.** Terminal runs ARE listed by `fabro ps -a --json
  --server hp` (measured on both `.14` runs). Whether a run is reliably listed
  **while it is in-flight** is the open sub-condition — the console foreman and
  the console event-identity worker both have hedged observations of a remote ps
  listing **omitting an in-flight run mid-flight**. If the running run is absent
  from `ps -a` during its turn, `_discover_run` returns None every poll →
  silent `continue` → `decide_stall` never runs. This is the leading remaining
  **hypothesis** for the exact failing condition.

## A design constraint the fix must confront (measured)

`_watch` RE-DISCOVERS the run via ps every poll instead of using the run's id
directly — because the id is not available mid-flight. In `WatchedFabroLauncher.launch`,
`port.run(...)` is BLOCKING and only populates `run_id_holder["run_id"]` on
RETURN (`_dispatcher_io_fabro_launcher.py`, `_run_fabro`), i.e. after the run has
already finished. So the watchdog genuinely cannot key its events probe on a
known run id during the turn; ps-discovery is the only handle it has today. A
robust fix must obtain the run id early (fabro emitting it at submit, parsing it
from `fabro run` streaming output, or a submit/attach split) OR make discovery
resilient to in-flight ps omission — it cannot simply "use the known run_id".

## Bearing on the cut (root-cause now closed for the remedy)

- **Aim 2 (fail-fast) — now specific and factory-safe.** Deliverable: make the
  watchdog's run-discovery work against the remote factory during the live turn,
  and REMOVE the silent `continue` blind spot (per-poll observability) so a
  discovery failure can never again hide for 11 days. Edits in
  `_dispatcher_io_fabro_launcher.py` (+ `_fabro_port.py` if discovery mechanism
  changes). Cross-ref `bd-ib-oj71` (dead-implementer breaker, distinct trigger),
  `livespec-impl-beads-oyg` (the watchdog's own origin item).
- **Aim 3 (telemetry).** The per-poll observability above is the orchestrator-side
  half and folds into the aim-2 fix; surfacing the kill/typed-failure outcome as a
  first-class signal is the incremental child. The fabro-side per-turn zero-output
  SOURCE datum stays deferred (`29f.6`).
- **Aim 1 trigger half — DEFERRED, decoupled.** Why the agent emits zero output
  pre-inference is NOT required for the fail-fast remedy (the watchdog should
  catch ANY silent turn regardless of cause) and needs live-specimen in-sandbox
  evidence; likely fabro/CC-side. The `.14` 2/2-vs-`ag0` 2/2 correlation remains
  unexplained at small n and is not strengthened to a cause.

## Still open

- Exact failing discovery sub-condition (in-flight ps omission vs status_kind on a
  running remote run) — needs a live run + `fabro ps -a --json --server hp`
  during it.
- The zero-output trigger (aim 1 trigger half), as above.
