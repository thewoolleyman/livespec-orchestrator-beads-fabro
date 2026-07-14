# Handoff — codex-credential-broker

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
   on interactive use (timer/daemon). **Open sub-question:** drive it by invoking
   codex itself (letting its own proactive refresh do the work — fewer moving
   parts, keeps OpenAI's rotation semantics inside codex) versus calling the token
   endpoint directly with the host's real refresh token. Prefer the former.
   Note the refresh only *fires* within 5 min of expiry, so a naive "run codex
   hourly" cron is enough — it is a no-op until it is needed.
2. An **expiry alarm** — surface when the host token is within N days of `exp`, so
   the cliff is never a surprise. Cheap, and it is the part that actually
   prevents the outage.

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

- `bd-ib-a89` — the landed seatbelt (CLOSED).
- `bd-ib-ss7rkr` — the re-verification that surfaced this; remaining half is the
  docs/contract realignment.
- `contracts.md` §"Worker credential projection" + `scenarios.md` Scenarios 18/19
  — the ratified contract. The "host is sole owner / worker is a read-only
  consumer" clauses stay TRUE under the broker; the design strengthens them.
- Sibling thread `codex-factory-telemetry` — hit the same fabro fail-closed-env
  wall and the same `worker_runtime.rs` re-injection seam.
