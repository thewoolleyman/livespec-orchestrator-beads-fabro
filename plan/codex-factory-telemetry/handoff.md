# Handoff — codex-factory-telemetry

## ⇥ CONTINUE THIS TRACK — it is NOT finished (do not let it be orphaned)

This is the ORIGINAL track. Its `factory-integration` + spec-ratification arc is
DONE, but its reason-for-being — the **emitter + receiver** (`bd-ib-98c.1` /
`bd-ib-98c.2`) — remains. Resume from §"CURRENT STATE + NEXT ACTION" below.

- **A sibling track was spun off from here (2026-07-15):**
  `codex-credential-broker` (epic `bd-ib-rck`; handoff
  `plan/codex-credential-broker/handoff.md`). It surfaced while re-verifying
  `bd-ib-ss7rkr` during this session and now has its own track + fresh session.
  That is why the credential work is NOT in this handoff — it did not vanish, it
  moved.
- **Cross-track relationship:** SIBLINGS, no hard code dependency (beads:
  `bd-ib-98c` `related` `bd-ib-rck`, NOT `blocks`). The one real link is soft +
  operational: **this track's end-to-end verification needs a live dispatch, so a
  dead Codex credential (the broker's domain) would block that e2e proof.** Also
  both touch the same fabro worker-env re-injection seam
  (`worker_runtime.rs:90-99`) / `_dispatcher_overlay.py`. See §"Related tracks" at
  the end.

## What this thread is

Restore end-to-end factory observability for the **Codex era**. The
Honeycomb telemetry pipeline is Claude-Code-native and has been dark for
every run since ~2026-06-13 because the factory now drives work with
Codex (`@zed-industries/codex-acp@0.16.0`), which emits none of the
telemetry the pipeline captures. The receive/egress plane is intact and
armed on every dispatch; the gap is purely the **emitter**. Approach 2
(fabro-side OTLP from the ACP handler) is selected. The first buildable
piece — the fabro-side OTLP **transport** (`bd-ib-i4r`) — is an
OUTWARD-FACING upstream Fabro PR, currently in the adversarial-review gate
below.

## ▶ CURRENT STATE + NEXT ACTION (read this first)

**EMITTER RE-PLAN FILED (2026-07-15) — read `emitter-replan.md` first; it supersedes
the falsification narrative below.** The monolithic emitter `bd-ib-98c.1` was
re-planned (grounded in two fresh code investigations), adversarially reviewed by
Fable, and re-sliced into dependency-layered children. `bd-ib-98c.1` is now CLOSED
(`no-longer-applicable` = re-sliced, not dropped). New ledger structure under
`bd-ib-98c`:
- **✅ `bd-ib-98c.3` (F1) — DONE + VERIFIED END-TO-END (2026-07-16); CLOSED.** Emits
  the four review-gate attributes (incl. the ship-on-cap signal) by parsing
  `fabro events --json`. Built + adversarially reviewed (Codex + Fable), plus the
  ts-ordering verdict-mislabel fix (`bd-ib-98c.9`, also CLOSED). PROVEN in
  production: 9 real dispatches emitted review-gate telemetry with 0 skips
  (`tmp/fabro-dispatch-journal.jsonl`); the Honeycomb `livespec-dispatcher` dataset
  (7d) holds 64 `review.gate` spans with all four attributes INTACT — 49 approve /
  8 fix+ship-on-cap / 7 unknown — so the standing "ship-on-cap rate" question is now
  answered live (e.g. `bd-ib-fcipkv` ran fix×2 → hit the cap → shipped, captured as
  `pr_shipped_on_cap=true`). (The parser correctly emits `verdict=unknown` when a run
  has no terminal approve/fix edge — an honest fallback, not a mislabel.)
- **`bd-ib-98c.4-.7` (O1-O4) — the outward-facing fabro emitter spine**, strict
  order: activate the inert worker exporter (env re-injection + `http/json`) →
  cross-process traceparent → node-lifecycle spans → ACP turn spans. Rides
  `bd-ib-i4r`.
- **`bd-ib-98c.8` (O5, deferred)** — ACP token/cost via the already-enabled
  `unstable_session_usage` seam.
- **`bd-ib-98c.2` (receiver) — allowlist half DONE + PROVEN; `http/json` half BLOCKED
  on O1.** The allowlist widening for the four review-gate attributes is live on
  master (`_otel_scrub.py:127-130`) and verified end-to-end above (F1 spans land in
  Honeycomb, not silently dropped). Remaining: the `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`
  overlay serves the O-track emitter path and rides O1 (`bd-ib-98c.4`) — keep this item
  open until then. (Evidence recorded on the ledger item, 2026-07-16.)

**▶ NEXT ACTION (2026-07-16): the factory-safe work on this track is DONE + verified
(F1 + the receiver allowlist). O1 Step 0 is RESOLVED — the target spans split across
two processes, so O1 has two levers (see `o1-worker-exporter-plan.md`):**

- **O1 does NOT wait on #576's upstream merge.** The transport is already carried +
  pinned live in `factory-integration` (`fabro 0.254.0 (15b89ab)`), so O1 builds on
  that branch NOW. #576 was flipped to **READY (2026-07-16)**; that only starts
  upstream acceptance and does not gate O1.
- **Lever A — server-start OTEL env (ops, no fabro code).** The host server mints the
  top-level `run` span (`server.rs:4339`), inert only because the server starts with no
  OTEL env. Fix = add `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`
  + `OTEL_SERVICE_NAME=fabro` (NO HEADERS) to the launch env. **Operator-gated:** it
  requires restarting the fleet-shared server, which interrupts in-flight dispatches —
  schedule a quiet window (as of this writing a dispatch was 22 min in). Provable in
  Honeycomb the same day with no code/rebuild.
- **Lever B — worker re-injection (fabro Rust).** The ACP work runs in the spawned
  `__run-worker` subprocess whose `OTEL_*` is stripped by `env_clear()` + the
  `spawn_env.rs` allowlist; re-inject the same three vars at `worker_runtime.rs:89-98`
  (never the allowlist — keeps the Honeycomb key off the worker). This is outward-facing
  fabro, hand-built operator-side via Codex + Fable review loops (NOT factory-safe).

**Both levers are maintainer-gated (a live-server restart / an operator-driven fabro
build). The two `run` spans stay disconnected until O2 (`bd-ib-98c.5`) joins them.**

Full decomposition, the eight code-verified constraints, the rejected stderr-sentinel
design, and every file:line citation live in `emitter-replan.md`. Everything below
this block is retained as the historical arc.

**DONE this arc (2026-07-14):**
- **Upstream OTLP transport PR — [fabro-sh/fabro#576](https://github.com/fabro-sh/fabro/pull/576)**:
  DRAFT, **CI GREEN**. Adversarial review COMPLETE — Codex (gpt-5.5 high) 7 passes →
  clean; Fable 5 three passes → clean-except-nitpicks (cleared). Left DRAFT for the
  maintainer's ready-flip. Source: `~/.worktrees/fabro/otlp-span-export` (branch
  `otlp-span-export`, tip `da277a4e5`, pushed to `origin`=thewoolleyman/fabro).
- **Factory integration branch + LIVE PIN**: `factory-integration` (now pushed to
  `origin` = thewoolleyman/fabro — see the next bullet; local worktree
  `~/.worktrees/fabro/factory-integration`, cut off `fork-0254-backport`) = **0.254 +
  #568 + daemon-timeout-fix + reviewed OTLP** (commit `15b89ab0d`). Release binary built
  and **PINNED LIVE**: `~/.fabro/bin/fabro` = `fabro 0.254.0 (15b89ab)`; server restarted
  OAuth-only (pid on `127.0.0.1:32276`), `fabro doctor` green. Rollback binary:
  `~/.fabro/bin/fabro.f7ff19e-pre-otlp.bak` (restore it + restart to revert). Base is
  0.254 — DO NOT modernize without the `workflow.fabro` #474 migration (`bd-ib-6qu`).
- **🔴 `factory-integration` WAS LOCAL-ONLY — NOW PUSHED (2026-07-14).** The branch the
  LIVE factory binary is built from existed ONLY on the maintainer's disk: no remote
  tracking ref, and `thewoolleyman/fabro` had no such branch, so commit `15b89ab` was
  unreachable from any fork branch and the running binary was **unreproducible if that
  disk were lost**. (Caught by the doctor LLM pass over the spec proposal — the earlier
  handoff's "(thewoolleyman/fabro)" claim was aspirational, not true.) Now pushed:
  `origin/factory-integration` = `15b89ab0d449e9192ef4a2d5f232de6269c723ce`, matching the
  live pin exactly. Composition bottom-up: `f630c9351` (#568 push-credential-refresh) →
  `f7ff19eea` (fork-local env-configurable daemon-readiness timeout) → `15b89ab0d` (#576
  OTLP export).
- **`factory-integration` DOCUMENTED (2026-07-14)** — the branch-name standard is now
  recorded in all three places it belongs:
  - **Spec — RATIFIED as `v035`** (proposal PR #602 → revise PR #604, both merged;
    master `c513397`). `SPECIFICATION/constraints.md` now carries the LIVE H2
    `## Fabro runtime constraints`. It targets `constraints.md` — this repo's
    non-functional-requirements analogue; there is NO `non-functional-requirements.md`
    here (that filename is livespec CORE's, which `constraints.md` explicitly inherits
    from). TWO edits landed: (1) the new H2 with five rules — carrier-branch name (+ MUST
    be pushed to `origin`), composition (base + EVERY pending fix, upstream-unreleased OR
    fork-local, never a subset), base ceiling (MUST NOT pin ≥ 0.256 until `bd-ib-6qu`),
    rebuild/re-pin (the host binary AND the orchestrator image, which bakes a COPY —
    else the containerized server silently runs the old fabro), runbook lockstep; and
    (2) an amendment to the file preamble, whose "mechanically-checkable / lint-enforced"
    claim the new section would otherwise flatly contradict. The volatile carried-fix
    LIST lives in the runbook, NOT the spec, so the constraint cannot go stale. No
    `scenarios.md` co-edit (operator-procedure rule over an external binary — no
    plugin-observable behavior to exercise); `tests/heading-coverage.json` gained the new
    heading with `"test": "TODO"` + reason.
  - **PREAMBLE AMENDMENT — maintainer-acknowledged, do not silently re-tighten.** The
    revise tripped the intent-preservation gate (`spec.md` §"Intent preservation and
    design-record authority"): amending the ratified "every constraint is
    mechanically-checkable / lint-enforced" preamble is a change to a ratified statement,
    NO design record is cited for it, and the gate forbids a delegated pass from
    self-resolving that. The conflict + the absence of a governing record were surfaced;
    the maintainer CONFIRMED the amendment on 2026-07-14. The acknowledgment is recorded
    in `SPECIFICATION/history/v035/proposed_changes/fabro-factory-integration-branch-standard-revision.md`
    → `## Decision and Rationale`. The amended preamble keeps binary/decidable, scopes
    lint/test enforcement to constraints governing PLUGIN CODE, and requires a constraint
    over an external runtime to NAME its deciding command (`fabro --version` here).
  - **Runbook:** `orchestrator-image/README.md` §"Host Fabro server" gained a
    `### factory-integration — the carrier branch for unreleased fixes` subsection (the
    carried-fix table + build/pin/rollback commands), and its "Current binary" paragraph
    — which still claimed `f7ff19e` / "0.254 + #568" — was corrected to the live
    `fabro 0.254.0 (15b89ab)`.
  - **Agent orientation:** `AGENTS.md` §"Host Fabro server" (the canonical file;
    `.claude/CLAUDE.md` symlinks to it) carried the same stale `f7ff19e` claim — also
    corrected.
- **FOLLOW-ON FILED: `bd-ib-j9x`** — a dispatch-preflight engine-version gate, to make the
  < 0.256 ceiling MECHANICALLY enforced instead of review-time-only (the seam already
  exists: `contracts.md` §"Dispatch-time baseline conformance gate"; the preflight code
  carries no engine-version check today). Kept deliberately OUT of the naming proposal:
  a preflight gate is plugin-observable behavior and so MUST carry its own Gherkin
  scenario, whereas the naming standard is an operator-procedure rule.

**NEXT ACTION:** The transport + integration-branch + spec arc is **CLOSED**. The EMITTER
and RECEIVER remain — but a 2026-07-14 code investigation of both sides **FALSIFIED the
plan both ledger items were written against**. Read the ledger comments before touching
either; the full file:line evidence is on `bd-ib-98c.1` (fabro side) and `bd-ib-98c.2`
(receiver side). Summary of what is actually true:

**`bd-ib-98c.1` — fabro-side instrumentation (OUTWARD-FACING). Its stated plan cannot be
built as written.**

- 🔴 **The ACP events it plans to map DO NOT EXIST.** Repo-wide grep over fabro
  `factory-integration` returns ZERO hits for `UsageUpdate`, `TurnComplete`, and
  `time_to_first_token`. The item's "map UsageUpdate/TurnComplete → span fields" plan is
  built on an API that isn't there. (`turn_id` exists, but on the unrelated chat/sessions
  surface, not the workflow/ACP path.)
- 🔴 **NOTHING TO ENRICH — every span must be created NEW.** fabro's entire production
  span inventory is THREE sites repo-wide (`run/mod.rs:96`, `server.rs:4339`,
  `automation_scheduler.rs:187`); `fabro-workflow` has ZERO non-test
  `#[instrument]`/`span!` sites. The tracing tree is ONE SPAN DEEP. Wiring the env alone
  would export exactly one flat `run` span per process — no nodes, no turns.
- 🔴 **NO token/cost data on the ACP path.** `acp.rs:424` hardcodes `usage: None`, so
  `StageCompleted.billing` is always `None`. Token counts only exist on the API backend
  (`fabro-agent`), and the factory drives `acp.command`. Zero token/cost attributes
  without new upstream work. Same for per-tool-call spans: `fabro-acp/src/session.rs`
  handles ONE `SessionUpdate` variant and `.otherwise_ignore()`s the rest, so ACP
  `ToolCall` notifications are dropped on the floor.
- ✅ **The `apply_worker_env` caveat is CONFIRMED** — and narrower than feared. The ACP
  handler runs in a server-spawned `fabro __run-worker` subprocess (production ALWAYS
  takes the subprocess path; the in-process branch is test-only). `apply_worker_env`
  (`fabro-server/src/spawn_env.rs:29`, allowlist `:6-26`) is `env_clear()` + EXACT-NAME
  copy — no `OTEL_*`, no prefix matching — so the exporter is inert there. BUT the worker
  DOES install our layer already (`logging.rs:419`/`:453`), so **only the env is
  missing**. Preferred fix: explicit re-injection at `worker_runtime.rs:90-99` (the
  established pattern, beside `FABRO_LOG`/`FABRO_CONFIG`), NOT widening the fail-closed
  allowlist. Do NOT blanket-copy `OTEL_*` — that would sweep `OTEL_EXPORTER_OTLP_HEADERS`
  (the Honeycomb API key) into the worker env.
- 🔴 **Trace context does not cross the process boundary.** Server and worker each create
  their own `info_span!("run", id)` with no `traceparent` passed. Enabling OTLP on both
  today yields TWO DISCONNECTED TRACES per run. A W3C `traceparent` must be injected at
  the same `worker_runtime.rs` seam and extracted before the worker's run span.
- The `OTEL_EXPORTER_OTLP_PROTOCOL=http/json` overlay caveat still stands (our receiver is
  json-only; the upstream exporter now defaults to `http/protobuf`).

**`bd-ib-98c.2` — receiver side (OURS, Python, factory-safe). Its scope is INVERTED:
both stated halves are already done, and the real work is the opposite.**

- ✅ (a) "add a `service.name` → dataset mapping" — **already generic.**
  `_otel_enrich_export.py:51-58` is literally
  `return resource_attrs.get("service.name", _DEFAULT_DATASET)`. No mapping table exists
  or is needed.
- ✅ (b) "content-redaction scrub" — **already fail-closed.** `_otel_scrub.py` is an
  ALLOWLIST (never a denylist); prompts / tool I/O / raw bodies cannot leak because their
  keys simply aren't in it. There is no redaction pass to write.
- 🔴 **THE REAL WORK — and it is a SILENT TRAP.** Because the allowlist is fail-closed,
  it will also DROP the emitter's NEW fields: `_otel_enrich.py:213` does
  `if not is_allowed_attr(key=key): continue` — no error, no warning, no log line. All
  four review-gate attributes (`review.verdict`, `review.fix_rounds`, `review.hit_cap`,
  `pr.shipped_on_cap` — the fields that exist specifically to answer the ship-on-cap
  question) are currently DROPPED. So the emitter could be built perfectly, spans would
  arrive in Honeycomb, and every field the effort exists to capture would be missing.
  **Do not treat "spans appear" as proof the emitter works.** The corrected
  allowlist-widening set is on the ledger item; pin it against what the emitter actually
  emits rather than a guess.
- **SEQUENCING: this MUST land before or with `bd-ib-98c.1`,** or the first end-to-end
  dispatch is a FALSE SUCCESS.

**GAP-DETECTOR NOTE (expected, do NOT "fix" by filing work-items):** the post-step
`capture-impl-gaps` on the v035 cut flags **15 new gaps** — every BCP14 clause in
`## Fabro runtime constraints` plus the 2 amended-preamble clauses. NONE was filed, by
deliberate disposition: they are operator-procedure clauses over an EXTERNAL binary that
no plugin code can ever satisfy, so work-items for them would be permanently unclosable
ledger noise. The gap detector is mechanical over BCP14 clauses, so any
not-implementable-in-code constraint becomes a standing phantom gap (the pre-existing
baseline was already 182). The ONE legitimate mechanization is `bd-ib-j9x` (below), which
is what would actually retire these 15.

**ARCHIVE-CHECK: NOT ARCHIVABLE — leave this thread active.** `.claude-plugin/prose/plan.md`
§"Step 5 — Archive on epic close" binds the lifecycle hard: a thread is active *if and only
if* its epic is open, archived *if and only if* the epic is closed. Epic `bd-ib-98c` is OPEN
(BACKLOG) with two open children (`bd-ib-98c.1` emitter, `bd-ib-98c.2` receiver). Archive
only after those close and the epic closes.

**NOT blocking:** dispatch-level end-to-end OTLP verification is DEFERRED to the emitter
wiring (`bd-ib-98c.1`/`bd-ib-98c.2`) — the pinned binary is health-verified but the OTLP
layer stays INERT until the sandbox/server OTEL env + `apply_worker_env` allowlist +
`OTEL_EXPORTER_OTLP_PROTOCOL=http/json` land. See the INTEGRATION BRANCH section.

## Read-first chain (open these, in order, before acting)

1. `plan/codex-factory-telemetry/research/observability-gap.md` — the full
   reasoning: evidence (dataset dark-dates), mechanism, what's intact/reusable,
   the three approaches, open questions.
2. `plan/codex-factory-telemetry/research/codex-otel-support.md` — the
   2026-07-12 outcome of "can Codex emit OTel?" (verdict `no-native-otel`;
   Approach 2 selected) + the ready build steps.
3. `plan/codex-factory-telemetry/otlp-transport-pr-body.md` — the working PR
   text for the transport PR (reviewed + refined in the gate below).
4. `~/.worktrees/fabro/otlp-span-export/` — the fabro worktree holding the
   transport commit (branch `otlp-span-export` off `upstream/main`, pushed to
   `origin` = thewoolleyman/fabro). The changed files: `lib/crates/fabro-cli/src/{otel.rs,logging.rs,main.rs}`,
   `lib/crates/fabro-cli/Cargo.toml`, workspace `Cargo.toml`, `Cargo.lock`.
5. `plan/fabro-token-refresh/handoff.md` — the sibling thread whose fabro PR
   **#568** (`push-credential-refresh-ahead`) is the OTHER active fabro PR that
   the integration branch (next phase) must combine with this one.

## ✅ TRANSPORT PR DONE — active action is now the INTEGRATION BRANCH

**The OTLP transport (`bd-ib-i4r`) is COMPLETE through the review gate.** Draft PR
**[fabro-sh/fabro#576](https://github.com/fabro-sh/fabro/pull/576)** is OPEN
(commit `da277a4e5`) with **CI GREEN** (Format / Clippy / Test-Linux / Docs pass;
macOS skipped). Both adversarial loops CONVERGED: Codex 7 passes → clean; Fable 3
passes → clean-except-nitpicks (cleared). Left as DRAFT for the maintainer's final
ready-flip. **The current action is the NEXT PHASE below (integration branch),
gated on the maintainer's base-version decision.** The review-gate detail that
follows is retained as historical record.

## ACTIVE ACTION (historical) — the OTLP transport PR review gate

State as of 2026-07-14: the transport (`bd-ib-i4r`) is CODED and pushed to
`origin/otlp-span-export` (single commit, amended across review passes — use the
branch tip, not a fixed SHA). `cargo clippy -p fabro-cli --all-targets` is clean
and the `parse_protocol` unit test passes. Codex adversarial review IN PROGRESS:
- pass 1 → blocking-client swap (async `reqwest-client` would panic on the SDK
  batch processor's non-tokio thread) + `catch_unwind` on provider build +
  protobuf default.
- pass 2 → re-confirmed + hardened.
- pass 3 → found a REAL CI gap: my local `cargo clippy -p fabro-cli` missed the
  CI bar `cargo +nightly-2026-04-14 clippy --locked --workspace --all-targets --
  -D warnings` (workspace lint `print_stderr = "warn"` → the two `eprintln!` fail
  CI). FIXED via module-level `#![expect(clippy::print_stderr, …)]`. Also hardened
  empty/whitespace endpoint → unset, and softened the `catch_unwind` claim (the
  panic hook still fires; `panic = unwind` so the catch is effective).
- **CI-equivalent validation (`fmt` + clippy `-D warnings` + test under
  nightly-2026-04-14) is the current gate — running.**
- **DRAIN-ON-EXIT DECISION — RESOLVED (maintainer ruled 2026-07-14): keep
  pattern-consistent.** `otel::shutdown()` stays best-effort on the normal-exit
  path (mirroring fabro's own `fabro_telemetry::shutdown()`); Codex's repeated
  BLOCKING on this is classified **non-actionable-by-design** (the gap pre-exists
  in fabro). A consistent "drain both telemetries on all exit paths" is a POSSIBLE
  SEPARATE fabro follow-up, NOT part of this transport PR.
- **CODEX LOOP CONVERGED** (pass 7, 2026-07-14): `NO BLOCKING OR ACTIONABLE
  FINDINGS` at branch tip `7e7f87483`. 7 passes total; real bugs found+fixed:
  async-client panic on the SDK batch thread → blocking client; CI-only clippy
  failures (`print_stderr`, `absolute_paths`, `single_match_else`) my weaker local
  command missed; silent localhost fallback on malformed endpoint → resolve locally
  + `.with_endpoint()`; synthetic layer attrs (tracked-inactivity/threads/location)
  disabled. **FABLE LOOP now running.**
- **FABLE LOOP** (branch tip `52c38e12c`): pass 1 found 3 ACTIONABLE + 4 NITPICK,
  all fixed + CI-green — different lens than Codex: per-signal
  `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL` precedence; env-var names routed through
  `fabro_static::EnvVars` (added `OTEL_*` consts — the fabro convention); dropped the
  redundant `force_flush()` (was doubling worst-case exit stall); `fabro_http` egress
  bypass documented as deliberate; `opentelemetry*` trimmed to `features=["trace"]`;
  `tonic`/`prost` lockfile disclosure. Pass 2 (branch tip `13edac58f`) caught a real
  feature-unification bug (`tracing-opentelemetry`'s `metrics` default force-enabled
  the SDK metrics, and — verified — `opentelemetry-otlp`'s `http-proto`/`http-json`
  features enable `metrics` unconditionally, so a trace-only reduction is NOT
  achievable; reverted to plain deps + honest docs) plus PR-text accuracy + a
  protocol-warning nitpick. All fixed + CI-green. Pass 3 running. Then open PR + watch
  CI. Codex + Fable both independently verified the CODE clean (endpoint fail-safe,
  catch_unwind, blocking client, call sites, imports); remaining churn is doc-precision.
- **CI-equivalent validation GREEN** (branch tip `209485b19`): `fmt --check`,
  `clippy --locked --workspace --all-targets -- -D warnings`, and the unit test all
  pass under `nightly-2026-04-14`. (Pass 3 also caught real CI-only clippy errors —
  `absolute_paths` on the `crate::otel::otel_layer()` inserts and `single_match_else`
  on the `catch_unwind` — both fixed.)
The commit is a pure, opt-in, additive OTLP/HTTP exporter for fabro's EXISTING
`tracing` spans (no new instrumentation; inert unless an OTLP endpoint env is
set). It introduces no new `reqwest` version (reuses the lockfile's existing
`reqwest 0.12`).

**Do this, in order (each step is restartable from the artifacts above):**

### Step A — Codex adversarial review loop (BLOCKING)

Run from the fabro worktree (`cd ~/.worktrees/fabro/otlp-span-export`), as a
subshell/subagent. Model `gpt-5.5` high (codex default). Review BOTH the CODE
diff AND the PR text (`plan/codex-factory-telemetry/otlp-transport-pr-body.md`):

```bash
cd ~/.worktrees/fabro/otlp-span-export
codex exec review --base upstream/main "<criteria prompt below>"
```

Iterate: apply every ACTIONABLE finding in the worktree, `git commit --amend
--no-edit` (keep it one commit) + `git push --force-with-lease`, re-run. STOP
when the review returns nothing but nitpicks / non-actionable / OK items.

### Step B — Fable adversarial review loop (BLOCKING, after A is clean)

Spawn Fable (`Agent` with `model: fable`) from the fabro worktree to review the
same CODE diff + PR text against the same criteria. Iterate + amend + push-force
until only nitpicks/non-actionable remain.

### Review criteria (BOTH loops, BOTH code + PR text)

- completeness (nothing half-wired; the PR text matches the diff)
- narrow fix of the stated problem only
- low blast radius
- loose coupling / high cohesion
- preserves ALL existing APIs and patterns
- **NO REGRESSIONS in fabro OR livespec**

### Step C — Open the upstream PR + monitor CI

Once BOTH loops are clean: open the PR to upstream and watch CI to green.

```bash
gh pr create --repo fabro-sh/fabro --base main \
  --head thewoolleyman:otlp-span-export \
  --title "feat(cli): opt-in OTLP/HTTP export for tracing spans" \
  --body-file plan/codex-factory-telemetry/otlp-transport-pr-body.md
# then: gh pr checks <url> --watch   (monitor until green; report back)
```

Then update this handoff + `bd-ib-i4r` (ledger) with the PR URL and CI state.

## INTEGRATION BRANCH — DONE + PINNED LIVE (2026-07-14)

`factory-integration` (in `thewoolleyman/fabro`, off `fork-0254-backport`) =
**0.254 + #568 + daemon-timeout-fix + the reviewed OTLP transport** (commit
`15b89ab0d`; the #576 patch applied cleanly onto 0.254 and compiles + tests pass).
Release binary built (`fabro 0.254.0 (15b89ab)`) and **PINNED in the live host
factory**: `~/.fabro/bin/fabro` swapped (backup `~/.fabro/bin/fabro.f7ff19e-pre-otlp.bak`),
server restarted OAuth-only (pid 3016327 on `127.0.0.1:32276`), `fabro doctor` green
(GitHub App configured; `[✗] LLM Providers` = correct). Base is 0.254 (forced by
fabro #474 — do not modernize without the workflow migration `bd-ib-6qu`).

REMAINING for this thread:
- ~~**NFR-spec doc**~~ — DONE 2026-07-14; see CURRENT STATE above. The rule landed as a
  pending proposal against `SPECIFICATION/constraints.md` (this repo's NFR analogue),
  plus the runbook + `AGENTS.md` co-updates.
- **Dispatch-level end-to-end verification:** the pin is health-verified, but the
  OTLP layer is INERT until the emitter env-wiring lands. Actually lighting up
  `fabro-sandbox` spans is `bd-ib-98c.1`/`bd-ib-98c.2` (server OTEL env + the
  `apply_worker_env` allowlist + `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`). A
  no-regression proof-dispatch would re-prove the 0.254+#568 base (already proven via
  #481) + the inert OTLP addition; a MEANINGFUL end-to-end dispatch belongs with the
  emitter wiring (where it also tests span flow).

## NEXT PHASE (historical) — factory integration branch

Create an **integration branch in our fork** (`thewoolleyman/fabro`) that
contains BOTH active fabro PRs:
- `#568` (`push-credential-refresh-ahead`) — the >60-min token-refresh fix.
- `otlp-span-export` — this OTLP transport.

Build fabro from that integration branch and **pin that build in the factory**
(the host fabro server `~/.fabro/bin/fabro` and/or the sandbox image) so the
factory runs with BOTH fixes ahead of any upstream release. Then **document the
integration branch NAME in the non-functional spec** as the STANDARD branch to
use whenever we carry pending fabro PR fixes not yet in an official
upstream version/tag. (Proposed name: `factory-integration` — confirm with the
maintainer; the spec write goes through `/livespec:propose-change`.)

NOTE the fabro-token-refresh `#474` constraint: any fabro ≥ 0.256 breaks
`workflow.fabro` (de-templated `acp.command`). The current host self-host is
`0.254 + #568`. An integration branch built on modern main (0.293) would
reintroduce the `#474` workflow break unless the workflow is migrated — so the
integration base is a real decision (rebase both PRs onto `v0.254` vs. accept
the workflow migration). Surface this to the maintainer before building.

## Ledger status (corrected 2026-07-14 — the earlier "not yet filed" was stale)

- **Epic `bd-ib-98c`** — open anchor for this thread.
- **CHILDREN ALREADY FILED (2026-07-13), dependency-layered:**
  `bd-ib-i4r` → `bd-ib-98c.1` → `bd-ib-98c.2`.
  - `bd-ib-i4r` — the fabro OTLP **transport** (THIS PR's ledger item). OUTWARD.
  - `bd-ib-98c.1` — fabro ACP node/turn span instrumentation (rides `bd-ib-i4r`).
    Scope EXPANDED 2026-07-14 (ledger comment) to also emit the four review-gate
    attributes: `review.verdict`, `review.fix_rounds`, `review.hit_cap`,
    `pr.shipped_on_cap`. OUTWARD.
  - `bd-ib-98c.2` — receiver-side dataset mapping + scrub (OUR Python,
    factory-safe). Rides `bd-ib-98c.1`.
- The host OTLP **receiver** prerequisite landed 2026-07-12 (livespec PR #539:
  `_otel_receive` bind `127.0.0.1` → `172.17.0.1`); it is armed on every
  dispatch. Lighting up `fabro-sandbox` is now purely the emitter work.
- Wire format for OUR json-only receiver stays `http/json` (the step-2 protobuf
  RECEIVER work is still DROPPED). **BUT** the upstream exporter now DEFAULTS to
  `http/protobuf` (the OTLP spec default — changed during the Codex review for
  upstream-acceptability; it honors `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`). So
  the fabro sandbox OTEL overlay MUST set `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`
  for the emitter path, or our json-only receiver rejects the protobuf POST and
  spans are silently dropped. **FACTORY ACTION — belongs to `bd-ib-98c.2`
  receiver-side wiring** (noted on that ledger item 2026-07-14).
- **SECOND FACTORY CAVEAT (surfaced by Codex pass 5):** fabro's server spawns
  workers through `apply_worker_env` — an env allowlist (`env_clear` + narrow
  copy) that does NOT include `OTEL_*`. So if the fabro orchestration/node spans
  we want are emitted from a SERVER-SPAWNED WORKER, that worker won't have the
  OTEL overlay and won't export. The emitter wiring (`bd-ib-98c.1`) must confirm
  WHICH process emits the target spans (cli / server / directly-launched
  `__run-worker` export fine; server-spawned workers need `OTEL_*` added to the
  allowlist — which carries an `OTEL_EXPORTER_OTLP_HEADERS` secret-exposure
  decision). Do NOT assume the sandbox OTEL overlay reaches the worker.

## Historical / reference

- **Grooming analysis (2026-07-13):** scoped the Approach-2 spine against the
  actual code; the children above are the result.
- **Review-gate telemetry (2026-07-14):** the four `review.*`/`pr.shipped_on_cap`
  fields were added to answer "how often does the factory ship a PR despite the
  review node never approving (ship-on-cap)?" — not answerable from Honeycomb
  today (Fabro's internal graph nodes emit nothing; the `fabro.*`/`dispatcher.*`
  stream froze 2026-06-14). Now recorded on `bd-ib-98c.1`.

## Coordination

Coordinate with the **`fabro-token-refresh`** thread: its `#568` is the OTHER
fabro PR the integration branch combines. Agree on nothing new for the transport
(wire format `http/json`, `service.name=fabro` settled); the integration-branch
base-version decision (`#474`) is the shared concern.

## Related tracks

- **`codex-credential-broker`** (epic `bd-ib-rck`; handoff
  `plan/codex-credential-broker/handoff.md`) — spun off from THIS track on
  2026-07-15 (surfaced while re-verifying `bd-ib-ss7rkr`). Ledger edge:
  `bd-ib-98c` `related` `bd-ib-rck` — SIBLINGS, **not** a `blocks` chain.
  - **Soft, directional, operational dependency:** this track's end-to-end
    verification (`bd-ib-98c.1` emitter → a live proof dispatch) needs a valid
    Codex credential. A dead host credential (the broker's 10-day-cliff concern)
    hard-stops the factory, so it would block that e2e proof. Keeping the
    credential fresh (the broker's surviving scope) unblocks it. No build-time
    code dependency — only verification-time.
  - **Shared code surface to coordinate at:** the broker's landed seatbelt
    (`bd-ib-a89`) added `CODEX_REFRESH_TOKEN_URL_OVERRIDE` to
    `_dispatcher_overlay.py`. This track's emitter adds `OTEL_*` at the SAME fabro
    `worker_runtime.rs:90-99` re-injection seam. Follow that established overlay
    pattern; do NOT widen fabro's fail-closed `apply_worker_env`.
- **`fabro-token-refresh`** — see §"Coordination" above (shares the
  `factory-integration` base + `#474`).

## Do NOT

- Do not implement the emitter (`bd-ib-98c.1`) or receiver mapping
  (`bd-ib-98c.2`) inline here — FILE/route ripe work; those build separately.
  THIS active action (the transport PR) is OUTWARD-FACING upstream work the dark
  factory cannot build, so it is driven operator-side (here), not dispatched.
- Do not let any emitter ship unredacted prompts / tool I/O / raw API bodies out
  of the sandbox (mirror the CC content-flags-off hygiene) — that's `bd-ib-98c.2`.
- Do not open the upstream PR until BOTH review loops (Codex + Fable) are clean.
