# S4 implementation record — Fabro-owned bounded in-node ACP candidate failover

Written 2026-09-12 by the session resuming plan epic `bd-ib-jxvgq5` after the
S4 hand-build. It records where S4 landed, what verified it, and the facts the
still-unfiled slices S5, S6 and S7 must consume. The design itself lives in
the Fabro fork (`docs/plans/2026-09-12-acp-fallback-chain.md` on
`factory-integration`), not here; this note is the orchestrator-side pointer
and the consumer contract as actually built.

## Where S4 landed

- Ledger item: `bd-ib-mujvyn`, the sole S4 child of plan epic `bd-ib-jxvgq5`.
  It is HOST-ROUTED (`factory_safety: mutates-host-machinery`): the change is
  to the Fabro engine the factory runs on, and the fork has no ledger tenant,
  so neither the factory sandbox nor the execution-mirror convention could
  carry it. The hand-build path it used is recorded in
  `.ai/fabro-fork-hand-build.md`.
- Fork pull request: <https://github.com/thewoolleyman/fabro/pull/9>, branch
  `factory-acp-fallback-s4`, one commit `72ba3b61c` on top of
  `origin/factory-integration` `4b8cc85e0` (fork PR 8, `bd-ib-bindom`).
- Merge: rebase-merged into `factory-integration` on 2026-09-12; merge SHA
  `20bf91e066c40f0304d8d67c1d1ea7adc3d88ac0`. Under rebase-merge the branch
  SHAs do not survive: the landed series is `b5a329d1d` (feat) then
  `20bf91e06` (the clippy follow-up), verified by a content check on
  `origin/factory-integration`, not by branch containment.
- Deployment: NOT done by S4. On 2026-09-12 hp runs `fabro 0.254.0 (4b8cc85)`
  (measured on the host by the filing session) and vps runs
  `fabro 0.254.0 (977cb67 2026-09-09)` (measured locally on vps by this
  session), so the two factories already diverged before S4 merged and
  neither carries S4. Pinning the capability-bearing build on both hosts is
  S7.

## Verification record

Merge gates, all run in the fork worktree against `72ba3b61c` with the shared
build cache (the fork's CI runs only on `main`, so these local gates are the
whole merge gate for `factory-integration`):

- `cargo nextest run` for `fabro-workflow`, `fabro-acp`, `fabro-types`: green,
  1,587 tests, including the eight behavioural chain tests in
  `acp_chain_tests.rs` and the versioned-event round-trips (recorded by the
  implementing session on the ledger, 2026-09-12T11:05Z).
- `cargo +nightly-2026-04-14 fmt --all`: applied (same record).
- The two gates the implementing session's wind-down killed were re-run by
  this session on 2026-09-12 and found real work: the pinned-nightly clippy
  reported thirteen `-D warnings` errors, every one inside the new S4 code
  (eleven in `fabro-workflow`, one in `fabro-types`, one in `fabro-server`:
  single-pattern matches, unused `self`, by-value slice arguments, an
  unreadable literal, a disallowed blocking `read_to_string` in an async
  test, a disallowed synchronous `Command::new` in a sync fixture helper, and
  two paths not brought into scope). They were fixed in follow-up commit
  `e1612071d` on the branch (landed as `20bf91e06`), with no behaviour change.
- After that fix, on the same tree: clippy exit 0; `cargo nextest run` for
  `fabro-workflow`, `fabro-types`, `fabro-acp` and `fabro-server` 2,317
  passed, 31 skipped; the `fabro-cli` `system_info` / `acp` targets 6
  passed. The run was launched through this repository's detached gate
  runner (`tmp/gate-runs/20260912T114422Z-1331824`) after the agent
  harness killed the same command three times for host memory pressure
  during the `fabro-server` test link.
- Two findings from those gates are NOT S4's and are recorded here so the next
  fork walk does not re-derive them. First, `fabro-server`'s three graph-render
  tests (`get_graph_returns_svg`, `render_graph_from_manifest_*`) fail under
  a per-crate `cargo nextest run -p fabro-server` with "render subprocess
  returned invalid output: stdout: running 0 tests": the handler spawns a
  render subprocess resolved from `CARGO_BIN_EXE_fabro` or a `fabro` binary
  beside the test executable, and a per-crate run has neither, so the test
  binary is re-executed as the renderer. Exporting
  `CARGO_BIN_EXE_fabro=<target>/debug/fabro` makes all three pass; S4 touched
  none of that code. Second, `cargo +nightly-2026-04-14 fmt --check --all`
  flags two files S4 never touched, `fabro-manifest/src/lib.rs` and
  `fabro-workflow/src/git.rs`, both from fork PR 8 (`bd-ib-bindom`): the
  carrier tip `4b8cc85e0` is not fmt-clean under the pinned nightly, which the
  fork's main-only CI could not have caught. S4 deliberately does not carry
  that reformat; it belongs to the PR 8 thread.

Independent review before merge: a Codex (gpt-5.5) leg and an Opus leg each
answered YES on transport, the non-retryable error variant and the exhaustion
categories, and NO on durability and the side-effect onset ledger (Opus also
NO on exhaustion). Every finding was implemented before the commit: every
ledger write is an emit plus an awaited `RunEventLogger` flush barrier and
visit state is reconstructed from the run's own event stream; an empty ledger
after a started turn fails closed; the `pr` onset probe checks both the
publish branch and its pull request; exhaustion is a structured
`agent.acp.exhausted` terminal event; an all-preflight-skipped chain
terminates the RUN through `Error::TerminateRun`; the attempt counter is
written at the attempt boundary (`internal.acp_attempt.<node>`); pre-transition
outer retries keep legacy semantics with a fresh deadline; foreign schema
versions round-trip as `Unknown`; `agent.acp.failover` carries
`attempted_durations_ms`.

## Consumer contract as built (read before filing S5, S6 or S7)

- **Capability string:** the server's `GET /system/info` response carries an
  additive `capabilities: string[]` containing `acp.fallback_chain.v1`, and
  `fabro system info --json --server <factory>` prints it. S7's remote
  capability probe keys on that exact string; an older engine omits the
  field, which the S7 consumer must treat as "capability absent", never as an
  error.
- **Transport:** one optional string node attribute `acp.fallback_chain`
  holding a JSON document with `schema_version: 1`, `primary_generation`,
  `full_chain`, an optional `onset_probe`, and an ordered `candidates` array.
  `acp.command` must still be present and must equal
  `candidates[0].command` byte-for-byte; `acp.config` plus a chain refuses.
  Every refusal is a validation error before any adapter starts. A node
  without the attribute runs the legacy single-adapter path byte-identically.
- **Fabro carries NO signature table.** The Dispatcher already owns the
  measured built-in table (`_acp_builtin_signatures.py`); S7 must render the
  EFFECTIVE signatures (configured plus built-in) into each candidate's
  `availability_signatures` when it emits the chain input. One table, one
  owner.
- **Events S5 must project holds from:** `agent.acp.failover` (one per
  preflight or reactive transition; `schema_version` 1, stable `event_id`,
  from/to candidate identities, `hold_key`, typed `cause` and `scope`,
  `primary_generation`, `full_chain`, `attempted`, `attempted_durations_ms`,
  `skipped`, `chain_deadline_epoch_ms`) and `agent.acp.exhausted` (the typed
  terminal outcome naming the final candidate and cause). The side-effect
  ledger event `agent.acp.side_effect` is engine-internal evidence and is
  not a hold source. `agent.acp.started` gained additive `candidate_index`
  and `chain_deadline_epoch_ms`. The native `agent.failover` event is
  untouched and pinned by a stored-fixture round-trip test.
- **Narrowing recorded in the fork design record, not a contract change:**
  candidates are command-form only; an `acp.config` node cannot carry a
  chain in this slice because the Dispatcher only ever renders
  `acp.command`.

## Dispatcher-side observation for S2 (rider, not filed)

`_acp_failure_matching.GENERIC_STATUS_LITERALS` (the vocabulary a bare HTTP
400/404 already contains, which a text signature may not claim on its own)
lacks the literal `404 not found`, while `_STATUS_MARKERS` uses that exact
phrase to recognise a generic 404. Verified 2026-09-12 by reading the module
in `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`. A
configured text signature whose only literal is `404 not found` would
therefore count as naming something outside the generic vocabulary and
discriminate a generic 404 it should not. The fork classifier mirrors the
Dispatcher's table, so the fix belongs in both. This is left for the
maintainer to file or fold into S5; nothing was changed here.

## Runbook facts corrected in the same change

- `AGENTS.md` and `orchestrator-image/README.md` named `977cb67` (and
  `af624d5`) as the build on both hosts. The measured state on 2026-09-12 is
  hp `4b8cc85`, vps `977cb67`: divergent. Both files now say so with dates.
- The README's carried-fix table gained the S4 row. It did not carry a row for
  fork PR 8 (`bd-ib-bindom`, `4b8cc85e0`, "contain backgrounded ACP commands
  before retry") either; that row belongs to the thread that landed PR 8 and
  is reported to the maintainer rather than authored here.
