# Handoff — codex-credential-broker

## ⇥ THIS IS A NEW TRACK — start a fresh session for it

This thread was spun off from the `codex-factory-telemetry` track (it surfaced
while re-verifying `bd-ib-ss7rkr`). It is its **own track with its own epic
(`bd-ib-rck`)** and should be picked up in a **fresh team-up session** dedicated
to it — do NOT run it inside the telemetry session, or the two will tangle.

- **Continue the ORIGINAL track separately:** `plan/codex-factory-telemetry/handoff.md`.
  That track is NOT finished (its emitter + receiver remain) and must not be
  orphaned. Whoever spins up this broker track should confirm the telemetry track
  has its own live session or is explicitly parked.
- **Cross-track relationship:** SIBLINGS, no hard code dependency (beads: a
  `related` edge, `bd-ib-rck` ↔ `bd-ib-98c`). The one real link is soft +
  operational: telemetry's end-to-end verification needs a live dispatch, so a
  dead Codex credential (this track's whole point) would block telemetry's e2e
  proof. And both touch the same fabro worker-env re-injection seam
  (`worker_runtime.rs:90-99`) / `_dispatcher_overlay.py` — coordinate there,
  don't widen fabro's fail-closed `apply_worker_env`. See §"Related" at the end.

## What this thread is

Retire the class of credential problem caused by fanning a **single-seat,
interactive ChatGPT/Codex subscription credential** out to **N ephemeral
concurrent workers**. Replace today's "cripple-and-gate" projection (destroy the
worker's refresh token, then require the access token to outlive the whole run)
with **host-as-broker**: the host owns the real refresh token, keeps its own
credential fresh, and tops up each *running* worker's projected `auth.json` so
codex-core's `Reload` seam recovers in-run.

Ledger epic: **`bd-ib-rck`**.

## ▶ CURRENT STATE + NEXT ACTION (read this first)

## ▶▶ EXECUTION STATE (2026-07-15) — FACTORY-DRIVEN, IN FLIGHT

The remaining job (host refresher + expiry alarm) is now being built THROUGH THE
FACTORY (maintainer directive: prefer factory dispatch). No spec change is needed
— it implements the ratified `contracts.md:2136` "host is sole owner + refresher"
MUST; the freshness threshold is implementation-owned (`:2140`).

Work-items filed under epic `bd-ib-rck` (2026-07-15):

| item | id | status | dep | scope |
|---|---|---|---|---|
| W1 alarm/status | `bd-ib-26lpjp` | **merged (PR #646) + verified; parked in `acceptance`** | — | `dispatcher codex-cred-status`: read host auth.json, decode exp, emit remaining + `alarm`/`refresh_due`; NEW pure `_dispatcher_codex_refresh` module (PBT) + promoted `decode_codex_access_token_exp` |
| W2 refresher | `bd-ib-fcipkv` | backlog | W1 | `dispatcher codex-cred-refresh`: GUARDED codex-invoke (exp-gated `codex exec`) |
| W3 timer/docs | `bd-ib-6xv5l5` | backlog | W1,W2 | host systemd/cron under `with-livespec-env.sh` + operator runbook (config/docs, TDD-exempt) |

The epic `bd-ib-rck` description was scope-corrected in the ledger to match this.
The two CRUX / `docker exec` bullets under "DONE (2026-07-14)" below are RETAINED
only as historical reference — they belong to the DROPPED per-worker top-up, NOT
to the remaining job.

**Dispatch status (2026-07-15):** W1 dispatched host-direct via `dispatcher.py loop
--repo . --budget 1 --mode shadow --item bd-ib-26lpjp`. Outcome: **converged, PR
#646 merged, post-merge janitor green (all 63 targets), ~27 min wall-clock, 2 fix
loops.** VERIFIED live on merged master: `dispatcher codex-cred-status --json`
emits the designed payload (token exp 2026-07-19, ~3.98 days, `alarm:false`,
`refresh_due:false`, exit 0). The AI acceptance pass confirmed; item is now
**parked in `acceptance` under the `ai-then-human` policy — awaiting the
maintainer's final acceptance** to reach `done`.

**⛔ GATE: W2/W3 are dependency-blocked until W1 is `done`.** The lane authority
(`_vendor/livespec_runtime/work_items/lifecycle.py:191,201`) clears a same-repo
dependency ONLY when the target is `done`; `acceptance` still resolves `OPEN`. So
W2 (dep W1) and W3 (dep W1,W2) cannot be admitted until the maintainer accepts W1.
This is not self-acceptable — `ai-then-human` reserves final acceptance for a human.

**NEXT ACTIONS:**
1. Maintainer accepts W1 → `done`:
   `/livespec-orchestrator-beads-fabro:drive --action accept:bd-ib-26lpjp`
   (or `… drive.py --action accept:bd-ib-26lpjp --repo .` under the env wrapper).
2. Once W1 is `done`: promote W2 `backlog→ready` and dispatch it through the
   factory (same host-direct `loop` invocation, `--item bd-ib-fcipkv`).
3. Then W3 (`--item bd-ib-6xv5l5`).
4. Install the host timer (manual maintainer step, documented by W3's deliverable).

---

**DONE (2026-07-14):**

- **Seatbelt LANDED — `bd-ib-a89`, PR #618, merged (master `2e98870`).** Every
  worker sandbox now gets `CODEX_REFRESH_TOKEN_URL_OVERRIDE` pinned at a closed
  loopback port (`http://127.0.0.1:1/...`), which contains BOTH the refresh
  sentinel (`manager.rs:932-935`) and any revoke attempt (`revoke.rs:155`) inside
  the container. This closed the spurious-401 path AND the container-clock-skew
  path that bypassed the freshness gate.
- **Design written** — `research/design.md`. Read it before doing anything here.
- **Root-cause re-verification** — recorded on `bd-ib-ss7rkr` (the item that
  surfaced all of this; its one remaining half is the docs/contract realignment).

- **CRUX FEASIBILITY QUESTION — ANSWERED (2026-07-14).** See
  `research/design.md` §3(b). Short version:
  - **Bind-mount is DEAD.** fabro's docker sandbox sets `binds: None`
    (`fabro-sandbox/src/docker.rs:1122`) and *test-enforces* it —
    `container_config_has_no_bind_mounts_or_socket` (`:2053`). No bind mounts,
    no docker socket, by deliberate upstream design. Do not fight it.
  - **`docker exec` via fabro's OWN label contract is the way.** fabro labels
    every managed sandbox container `sh.fabro.managed=true` +
    `sh.fabro.run_id=<RunId>` (`fabro-sandbox/src/managed_labels.rs`), and the
    Dispatcher ALREADY parses the fabro run id (`parse_running_run_id` in
    `_dispatcher_run_status.py`). So run → container resolves with no new fabro
    API and no upstream change:
    `docker ps -q --filter label=sh.fabro.managed=true --filter label=sh.fabro.run_id=<id>`,
    then write the refreshed snapshot in. Every piece already exists.

- **🔴 SCOPE CORRECTED (2026-07-14) — most of the broker is YAGNI.** Measuring the
  LIVE host credential falsified the design's core assumption. The access token
  lives **240 hours (10 days)**, not the ~1h OAuth norm:

  ```
  issued 2026-07-09T15:29:23Z -> expires 2026-07-19T15:29:23Z  (240h)
  freshness gate needs 5h (4h run budget + 1h margin)
  ```

  So: the gate can only refuse in the FINAL 5 HOURS of each 10-day cycle (~2% of
  the window), and a 4h run against a ≥5h-guaranteed token **cannot realistically
  expire mid-run**. That means **the per-worker top-up — the centerpiece of the
  design — solves a problem that barely exists. DO NOT BUILD IT.** Relaxing the
  freshness gate is likewise now a pure safety downgrade for zero benefit. DROP
  both.

**NEXT ACTION (the whole remaining job): build the HOST CREDENTIAL REFRESHER**
(design §3(a)).

The real operational risk is a **10-DAY CLIFF**, not mid-run expiry. The host's
`~/.codex/auth.json` is refreshed ONLY when a codex process runs on the host near
expiry (`should_refresh_proactively` fires within 5 minutes of `exp`). If the
maintainer does not happen to use codex interactively inside that window, the
credential **expires** and the factory **hard-stops** — the freshness gate then
refuses every dispatch with "run `codex login`".

Build:

1. A host-side refresher that keeps `~/.codex/auth.json` fresh without depending
   on interactive use (timer/daemon). **Mechanism: GUARDED codex-invoke** —
   resolved 2026-07-15, see the correction below.
2. An **expiry alarm** — surface when the host token is within N days of `exp`, so
   the cliff is never a surprise. Cheap, and it is the part that actually
   prevents the outage. Reuses `_decode_codex_access_token_exp`
   (`_dispatcher_projection.py`); pure over auth.json text, no network.

## 🔴 MECHANISM CORRECTION (2026-07-15) — the naive-cron claim was WRONG

An earlier draft of item 1 said: *"drive it by invoking codex itself … a naive
'run codex hourly' cron is enough — it is a no-op until it is needed."* Measuring
the installed codex CLI (`/home/ubuntu/.local/bin/codex`) falsified that:

- **Codex exposes NO force-refresh command.** `codex login` has only
  `status`/`help`; `codex login status` and `codex doctor --json` are **read-only**
  — verified: `~/.codex/auth.json` is byte-identical (`sha256` unchanged,
  doctor's `auth.credentials` check is `durationMs = 0`) before/after running them.
  Neither triggers a refresh and neither makes a token-endpoint call.
- **The ONLY in-codex refresh trigger is a real `codex exec` request**, and it
  refreshes only inside the 5-min pre-`exp` proactive window or via the
  post-`exp` 401→`Reload`→`RefreshToken` path (the host holds the REAL refresh
  token, so both work host-side). `codex exec` is **NOT a no-op** — it spends
  subscription quota on EVERY run. A naive hourly cron = ~240 real requests per
  10-day cycle to catch one refresh. Do not build the naive cron.

**Corrected design — GUARDED refresher.** We already decode `exp` precisely, so
gate the codex call on OUR OWN exp check: a cheap exp-read no-op for ~10 days,
then fire `codex exec` (trivial prompt) only when `exp - now` is inside the
proactive window / just past expiry. Cron every ~5 min → ~1–3 tiny requests per
cycle, refresh lands BEFORE expiry, no stale window, rotation stays inside codex.

**Alternative NOT taken (noted for the record):** call the OpenAI token endpoint
directly with the host refresh token — refreshes proactively at any time (zero
stale window, zero model quota) but reimplements codex's refresh-token ROTATION
and risks desync with codex's own auth state. Revisit only if the guarded
codex-invoke proves unreliable near expiry.

## ✅ NO SPEC CHANGE NEEDED (2026-07-15)

`contracts.md` §"Worker credential projection" (`:2136`) already ratifies: *"The
orchestrator **host** MUST be the sole owner and **refresher** of the long-lived
provider refresh credential."* And `:2140` makes *"the numeric freshness
threshold … implementation-owned."* So the host refresher + alarm IMPLEMENT an
existing, currently-unimplemented MUST (a spec→impl gap) — no
`/livespec:propose-change` / `/livespec:revise` ceremony. File the work under
epic `bd-ib-rck`; mechanism + thresholds are implementation-owned.

**Live measurement (2026-07-15):** host token `exp` = 2026-07-19T15:29Z, ~4.4
days out (issued 2026-07-09, 240h lifetime — matches the scope-correction
measurement). The cliff is near; the alarm is the priority piece.

## ⚠️ The correction that makes the seatbelt load-bearing (do not lose this)

An earlier reading assumed the broker alone was sufficient. **It is not.**

codex-core's **proactive** refresh path does NOT reload from disk: `auth()`
(`manager.rs:1432-1439`) reads the **in-memory cached** auth and goes straight to
`refresh_token()`. There is **no file watcher and no periodic reload** anywhere in
the login crate — `reload()` is reachable ONLY from the 401 path. So a host
top-up on disk is **invisible** to a running Codex until a 401 forces a `Reload`.

The seatbelt is therefore a **PREREQUISITE**, not a mitigation. With both pieces
in place, in-run recovery works like this:

1. Cached access token nears expiry → proactive refresh fires → hits the loopback
   override → **fails fast locally** → `return Some(auth)` **falls back to the
   cached token** (it does NOT die — `manager.rs:1436-1437`).
2. Request goes out with the stale token → server returns **401**.
3. 401 recovery → **`Reload`** (`manager.rs:1195`) → re-reads `auth.json` → finds
   the broker's fresh token (`ReloadedChanged`) → caller retries
   (`retry_after_unauthorized: true`, `core/src/client.rs:1932-1937`) → **200**.

The sentinel is never presented, on any path.

## Second prerequisite (independently useful — do it even if the broker stalls)

**The HOST's own `~/.codex/auth.json` must actually stay fresh.** It is refreshed
only when a codex process runs on the host. If the maintainer does not use codex
interactively, it goes stale, and the factory stalls at the freshness gate
("run `codex login`"). The broker needs a host-side refresher (timer/daemon) that
owns this. This is worth building on its own, since a stale host credential
stalls the factory *today* regardless of the broker.

## Sequencing (from `research/design.md` §6)

1. **Answer the crux** (mount vs exec) — see NEXT ACTION.
2. **Host refresher** — independently useful (see above).
3. **Per-worker top-up** — shaped entirely by (1).
4. **Relax the freshness gate** — LAST. It is the only step that *weakens* a
   safety property, so it lands only once (2)+(3) are proven in a real dispatch.
   Keep a floor: still refuse when the host credential is already expired.

## Do NOT

- Do NOT re-tighten or remove the `CODEX_REFRESH_TOKEN_URL_OVERRIDE` seatbelt. It
  is load-bearing for the broker (see the correction above), not redundant with it.
- Do NOT assume a host disk top-up is picked up by a running Codex on its own.
  It is not. Only a 401 triggers the reload.
- Do NOT widen fabro's `apply_worker_env` allowlist to pass things through. Fabro
  is fail-closed by design and provides an explicit re-injection seam
  (`worker_runtime.rs:90-99`); use it. (The `codex-factory-telemetry` thread hit
  the same wall and reached the same conclusion.)
- Do NOT treat the Claude side as known-good. `CLAUDE_CODE_OAUTH_TOKEN` is
  injected into every sandbox and is the same CLASS of credential (single-seat
  subscription in a fleet). Its refresh behavior is **unverified**.

## Related

- **Sibling track `codex-factory-telemetry`** (epic `bd-ib-98c`; handoff
  `plan/codex-factory-telemetry/handoff.md`). **Ledger edge:** `bd-ib-rck`
  `related` `bd-ib-98c` (NOT `blocks` — no hard code dependency either way). The
  relationship:
  - **Soft, directional, operational:** telemetry's end-to-end verification needs
    a live dispatch, which needs a valid Codex credential — THIS track's concern.
    A dead host credential (the 10-day cliff) hard-stops the factory, so it would
    block telemetry's e2e proof. Keeping the credential fresh unblocks that.
  - **Shared code surface:** the seatbelt `bd-ib-a89` added
    `CODEX_REFRESH_TOKEN_URL_OVERRIDE` to `_dispatcher_overlay.py`; telemetry's
    emitter adds `OTEL_*` at the SAME fabro `worker_runtime.rs:90-99` re-injection
    seam. Coordinate there; do not widen fabro's fail-closed `apply_worker_env`.
- `bd-ib-a89` — the landed seatbelt (CLOSED).
- `bd-ib-ss7rkr` — the re-verification that surfaced this; remaining half is the
  docs/contract realignment.
- `contracts.md` §"Worker credential projection" + `scenarios.md` Scenarios 18/19
  — the ratified contract. The "host is sole owner / worker is a read-only
  consumer" clauses stay TRUE under the broker; the design strengthens them.
