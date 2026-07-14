# Handoff — codex-factory-telemetry

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

**NEXT ACTION:** The transport + integration-branch + spec arc is **CLOSED**. The only
remaining work in this thread is the EMITTER and the RECEIVER:

1. **`bd-ib-98c.1` — fabro-side ACP node/turn span instrumentation** (OUTWARD-FACING;
   rides the now-merged-into-`factory-integration` OTLP transport). Two factory caveats
   are recorded on that ledger item and MUST be honored — the `apply_worker_env`
   allowlist (fabro's server spawns workers with `env_clear` + a narrow copy that does
   NOT include `OTEL_*`, so a server-spawned worker will not export) and the
   `OTEL_EXPORTER_OTLP_PROTOCOL=http/json` overlay (our receiver is json-only; the
   upstream exporter now defaults to `http/protobuf`, so without the overlay spans are
   silently dropped).
2. **`bd-ib-98c.2` — receiver-side dataset mapping + content-redaction scrub** (OURS,
   Python, factory-safe → dispatchable via Red-Green-Replay).

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

## Do NOT

- Do not implement the emitter (`bd-ib-98c.1`) or receiver mapping
  (`bd-ib-98c.2`) inline here — FILE/route ripe work; those build separately.
  THIS active action (the transport PR) is OUTWARD-FACING upstream work the dark
  factory cannot build, so it is driven operator-side (here), not dispatched.
- Do not let any emitter ship unredacted prompts / tool I/O / raw API bodies out
  of the sandbox (mirror the CC content-flags-off hygiene) — that's `bd-ib-98c.2`.
- Do not open the upstream PR until BOTH review loops (Codex + Fable) are clean.
