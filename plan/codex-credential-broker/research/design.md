# Design — host-as-broker for the Codex worker credential

Ledger epic: `bd-ib-rck`. Landed prerequisite: `bd-ib-a89` (the refresh-sentinel
containment seatbelt). Origin: the `bd-ib-ss7rkr` re-verification, 2026-07-14.

All codex-core claims below are **code-verified against `rust-v0.137.0`** — the
version `@zed-industries/codex-acp@0.16.0` actually pins (confirmed in its
`Cargo.toml`, which pins `codex-core` and `codex-login` to that git tag). Paths
are relative to `codex-rs/`.

## 1. The real problem — and it is self-inflicted

Neither fabro nor Codex is fighting us. The difficulty comes from one decision:

> We fan a **single-seat, interactive, desktop subscription credential** out to
> **N ephemeral concurrent worker containers**.

Codex assumes it is the sole owner of `~/.codex` on one machine. Nothing in its
design contemplates a fleet. Every painful thing downstream is a consequence:

```
sole-owner assumption
  -> a worker could refresh/rotate and invalidate the host's credential
  -> so we DESTROY the worker's refresh token (the sentinel)
  -> so the worker can never refresh
  -> so the access token MUST outlive the entire run
  -> so we need a freshness gate (4h budget + 1h margin)
  -> so a short-lived host credential REFUSES dispatches
  -> and container clock skew / spurious 401s become live hazards
```

The boring with-the-grain answer is **use an API key** — API keys do not expire,
do not rotate, and are designed for fleet/service use. The entire complexity
here exists solely to spend subscription quota instead of metered API billing.
That is a legitimate cost decision, but it should be named: it is the *whole*
source of the problem, and this design does not remove it — it makes it safe.

### What fabro does about the same problem

Fabro hit this exact wall with its own GitHub push credential (~60-minute
lifetime vs 4-hour runs) and solved it by **refreshing ahead** — a loop that
keeps the credential fresh *during* the run, with the owner staying in charge.
That is upstream PR **#568**, which the factory already carries on
`factory-integration`.

We took the **opposite** fork: forbid refresh, and demand longevity. That is
strictly more brittle — no mid-run recovery, and it converts an ordinary token
event into a dead run. **This design moves us back onto fabro's fork.**

## 2. The seam codex-core actually provides

Codex's 401 handling is a state machine, `UnauthorizedRecovery`
(`login/src/auth/manager.rs:1186`), and its **first step is not a refresh**:

```
Reload  ->  RefreshToken  ->  Done
```

- **`Reload`** = `reload_if_account_id_matches(expected_account_id)`
  (`manager.rs:1450`) — it **re-reads `auth.json` from disk**.
- On `ReloadOutcome::ReloadedChanged` the caller **retries the request**
  (`PendingUnauthorizedRetry { retry_after_unauthorized: true, .. }`,
  `core/src/client.rs:1932-1937`).
- `account_id` must match (`Skipped` otherwise → permanent error). We copy
  `account_id` verbatim into the projection, so it matches.

**That seam exists precisely so an external owner can refresh the credential
file underneath a running Codex.** We are not using it: today's projected
`auth.json` is written once by a fabro prepare step and is then static for the
whole run, so `Reload` always finds no change and falls through to
`RefreshToken` — which presents the sentinel.

### The correction that matters (and why the seatbelt is load-bearing)

An earlier reading of this assumed the broker alone was sufficient. **It is
not.** The *proactive* refresh path does **not** reload from disk:

```rust
// manager.rs:1432-1439  — auth()
let auth = self.auth_cached()?;                      // IN-MEMORY cache
if Self::should_refresh_proactively(&auth)
    && let Err(err) = self.refresh_token().await     // straight to refresh
{
    tracing::error!("Failed to refresh token: {}", err);
    return Some(auth);                               // <- falls back to cache
}
```

There is **no file watcher and no periodic reload** anywhere in the login crate
(`reload()` is reachable only from the 401 path). So a host top-up on disk is
**invisible** to a running Codex until a 401 forces a `Reload`.

This is why `bd-ib-a89` (`CODEX_REFRESH_TOKEN_URL_OVERRIDE` → closed loopback
port) is a **prerequisite**, not a mere mitigation. With both pieces in place the
in-run recovery sequence is:

1. The cached access token nears expiry → proactive refresh fires → hits the
   loopback override → **fails fast locally** → `return Some(auth)` **falls back
   to the cached token** (it does not die).
2. The request goes out with the stale token → server returns **401**.
3. 401 recovery → **`Reload`** → re-reads `auth.json` → finds the broker's fresh
   token (`ReloadedChanged`) → **retry → 200**.

The sentinel is never presented, on any path.

## 3. The design

**Host remains the sole owner of the real refresh token.** That part of the
current contract is correct and does not change
(`contracts.md` §"Worker credential projection").

Three components:

### (a) Host credential refresher

The host's `~/.codex/auth.json` is refreshed only when a codex process runs on
the host. If the maintainer does not use codex interactively, it goes stale and
the factory stalls at the freshness gate ("run `codex login`"). The broker needs
a host-side refresher that owns this — a timer/daemon that keeps the host
credential fresh, independent of interactive use.

**Open:** whether to drive this by invoking codex itself (letting its own
proactive refresh do the work) or by calling the token endpoint directly with
the host's real refresh token. Prefer the former — fewer moving parts, and it
keeps OpenAI's rotation semantics entirely inside codex.

### (b) Per-worker top-up

For each **running** worker, the host re-projects a fresh `access_token` into
that worker's `/workspace/.codex/auth.json`, keeping `refresh_token` = sentinel
and `account_id` verbatim (so `Reload`'s account check still matches).

**CRUX FEASIBILITY QUESTION — ANSWERED 2026-07-14.** Today the file is
materialized *inside* the container by a fabro prepare step from the
`CODEX_AUTH_JSON` env var, so the host has no handle on it. The answer:

**❌ Bind-mount is DEAD. Do not pursue it.** fabro's docker sandbox
(`fabro-sandbox/src/docker.rs`) sets `binds: None` (`:1122`) and *test-enforces*
it: `container_config_has_no_bind_mounts_or_socket` (`:2053`) asserts
`host_config.binds.is_none()`. No bind mounts, no docker socket, by deliberate
upstream design. Adding one would mean fighting an explicit security invariant.

**✅ `docker exec` / `docker cp` via fabro's OWN label contract is VIABLE — and
is the design.** fabro labels every managed sandbox container
(`fabro-sandbox/src/managed_labels.rs`):

```rust
pub(crate) const MANAGED_LABEL: &str = "sh.fabro.managed";   // = "true"
pub(crate) const RUN_ID_LABEL:  &str = "sh.fabro.run_id";    // = <RunId>
```

Those labels exist precisely so a managed container can be identified
(`is_managed`, `validate_managed_container`, `reconnect(container_id)`). And the
Dispatcher **already knows the fabro run id** — `parse_running_run_id` /
`parse_run_id_for_work_item` in `_dispatcher_run_status.py` parse it from
`fabro ps -a --json`. So the host can resolve run → container with no new fabro
API and no upstream change:

```bash
docker ps -q \
  --filter label=sh.fabro.managed=true \
  --filter label=sh.fabro.run_id=<run_id>
# then write the refreshed snapshot into it:
docker exec -i <container_id> sh -c 'cat > /workspace/.codex/auth.json'
```

**Blast-radius note.** This gives the host write access into a container running
agent-authored code. That is acceptable *for this specific file*: we are
rewriting a credential the agent already holds, with the refresh token still
replaced by the sentinel — the container gains **no privilege it did not already
have**. It does NOT justify a general host→container write channel; keep the
surface to exactly this one file.

**Open sub-question:** the host must not clobber the file mid-read. Prefer
write-temp-then-`mv` inside the container (atomic rename on the same filesystem)
so codex's `Reload` never observes a partial file.

### (c) Relax the freshness gate

Once the broker tops workers up, the gate can drop from "the credential MUST
outlive a 4h run + 1h margin" to "valid now, with a small margin". That removes
the dispatch refusals and makes container clock skew a non-event.

Keep a floor: the gate should still refuse when the host credential is *already*
expired or unusable, because no amount of topping up saves that.

## 4. What this retires

- The sentinel is never presented to OpenAI, on any path (proactive or 401).
- Mid-run credential recovery becomes possible; today a token event kills the run.
- Dispatch refusals on a short-lived host credential go away.
- Container clock skew stops being a hazard.
- We move onto the same fork fabro already took for its own credential (#568).

## 5. What this does NOT fix

- The metered-vs-subscription cost decision, which is the true root cause.
- The **Claude** side: `CLAUDE_CODE_OAUTH_TOKEN` is injected into every sandbox
  and is the same *class* of credential (single-seat subscription in a fleet).
  Its refresh behavior has **not** been verified. It may be fine; it may have the
  same shape. Treat as an open question, not a known-good.
- Token/cost telemetry, which is absent for an unrelated reason (the ACP path
  hardcodes `usage: None` — see the `codex-factory-telemetry` thread).

## 6. Sequencing

1. **Answer the crux** (mount vs exec) by reading `fabro-sandbox/src/local.rs`.
2. Host refresher (a) — it is independently useful, since a stale host
   credential stalls the factory today regardless of the broker.
3. Per-worker top-up (b), shaped by (1).
4. Relax the gate (c), last — it is the only step that *weakens* a safety
   property, so it should land only once (a)+(b) are proven in a real dispatch.
