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

## ▶▶ EXECUTION STATE (2026-07-15) — ✅ TRACK COMPLETE (epic `bd-ib-rck` CLOSED)

**All three work-items landed via the factory, verified, accepted → `done`; epic
`bd-ib-rck` CLOSED.** W1 alarm/status (PR #646), W2 guarded refresher (PR #662),
W3 host timer + operator docs (PR #664). No spec change was needed — the work
implements the ratified `contracts.md:2136` "host is sole owner + refresher" MUST
(freshness threshold implementation-owned, `:2140`). **The ONE remaining action is
a MANUAL MAINTAINER STEP: install the host systemd user timer** per
`orchestrator-image/README.md` §"Host Codex credential refresher timer" — the
unattended refresher is NOT live on the host until that install runs. Everything
below is the execution record.

### ⤳ POST-COMPLETION DESIGN RECONSIDERATION (2026-07-16) — read before installing the timer

A design review after the track landed questioned the timer/gate architecture and
produced a design-of-record, now graduated to its own plan thread:
**`plan/credential-freshness-redesign/handoff.md`** (design of record:
`plan/credential-freshness-redesign/research/credential-freshness-redesign.md`) —
read it before wiring up the systemd timer, because the recommendation is to
**NOT** rely on the timer and
instead move to **preflight refresh in the dispatch path + a right-sized gate +
liveness check + the W1 alarm** (drops the host-coupled timer, no codex-internals
coupling). Key grounded findings: the Codex access token is a **session-bound JWT**
(`session_id` + `jti`, 240h, `iss=auth.openai.com`) — not stateless; refresh tokens
rotate (single-use); **OpenAI explicitly discourages sharing one credential across
concurrent workers** (`learn.chatgpt.com/docs/auth/ci-cd-auth`); and the freshness
gate's margin is load-bearing in a way not previously credited — it **temporally
separates rotation from worker execution**, which is what makes our concurrent
credential-sharing safe. **Mid-run refresh is DEFERRED** pending one open question
(does a refresh bump `session_id` and thus invalidate outstanding access tokens?),
resolvable with zero risk by instrumenting `codex-cred-status` to capture
`session_id` on the next natural refresh. The redesign is analysis-only — the landed
W1/W2/W3 code stays valid; the decision to supersede the timer is the maintainer's.

Work-items filed under epic `bd-ib-rck` (2026-07-15):

| item | id | status | dep | scope |
|---|---|---|---|---|
| W1 alarm/status | `bd-ib-26lpjp` | **DONE (PR #646, merged + verified + accepted → CLOSED)** | — | `dispatcher codex-cred-status`: read host auth.json, decode exp, emit remaining + `alarm`/`refresh_due`; NEW pure `_dispatcher_codex_refresh` module (PBT) + promoted `decode_codex_access_token_exp` |
| W2 refresher | `bd-ib-fcipkv` | **DONE (PR #662, merged + verified + accepted → CLOSED)** | W1 ✓ | `dispatcher codex-cred-refresh`: GUARDED codex-invoke (exp-gated `codex exec`) |
| W3 timer/docs | `bd-ib-6xv5l5` | **DONE (PR #664, merged + verified + accepted → CLOSED)** | W1 ✓, W2 ✓ | host systemd/cron under `with-livespec-env.sh` + operator runbook (config/docs, TDD-exempt) |

The epic `bd-ib-rck` description was scope-corrected in the ledger to match this.
The two CRUX / `docker exec` bullets under "DONE (2026-07-14)" below are RETAINED
only as historical reference — they belong to the DROPPED per-worker top-up, NOT
to the remaining job.

**W1 dispatch (2026-07-15):** host-direct via `dispatcher.py loop --repo . --budget
1 --mode shadow --item bd-ib-26lpjp`. Converged, PR #646 merged, post-merge janitor
green, ~27 min, 2 fix loops. Verified live on merged master; **accepted → CLOSED
(done)**. W2's dependency on W1 is therefore cleared.

### W2 first dispatch FAILED then re-dispatched — root cause (READ THIS)

The first W2 dispatch (fabro run `01KXK9CG3MZW`, routed to the **codex-acp** worker)
**failed at the `pr` node** and parked `blocked/human_input_required`:

> `git push to refs/heads/feat/bd-ib-fcipkv was remote-rejected: GitHub App cannot
> create or update workflow .github/workflows/bump-pin-from-dispatch.yml without
> workflows permission … operator decision needed to publish with credentials that
> have workflow permission OR adjust the branch contents`

**Root cause = a TRANSIENT stale-workflow-file push race, NOT a code defect and NOT
a missing grant.** Verified against the fabro `factory-integration` source + the run
log:
- The `pr` node does a plain `git push HEAD:refs/heads/feat/<id>` (`prompts/pr.md`),
  with **no rebase onto latest origin/master**.
- GitHub's workflow-scope gate rejects a pushed branch whose `.github/workflows/`
  state **differs from the current default branch**. W2's sandbox cloned master
  BEFORE the 16:59 UTC `bump-pin-from-dispatch.yml` change (dev-tooling pin →
  v0.48.1, commit `8ef9714`) and pushed at 17:18 UTC, so its workflow file was
  stale vs master → rejected. W1 (PR #646) did not straddle a pin-bump → clean.
- The **git-push (origin) token is HARDCODED to `{contents:write}`** in
  `resolve_clone_credentials` (`fabro-github/src/lib.rs`) — it does NOT read
  `github_permissions`. So neither the `workflow.toml`
  `[run.integrations.github.permissions]` block **nor** the GitHub-App/installation
  `workflows:write` grant reaches the push token. **Adding `workflows` to
  `workflow.toml` would NOT fix this** (that block only feeds the preflight check +
  the `gh`/`GITHUB_TOKEN` env). Fixing the push path would need a fabro fork rebuild.

**Recovery taken (2026-07-15):** `fabro rm -f 01KXK9CG3MZW` (abandoned the blocked
run; container torn down) → `bd update bd-ib-fcipkv --status ready` → re-dispatched
W2 host-direct with the **Claude default adapter** (W1's proven form) in a window
where no workflow-file change had landed in ~3h. **Result: clean converge — fabro run
`01KXKPFGMQ7JG…`, PR #662 merged, post-merge janitor green.** Verified live on merged
master: `dispatcher codex-cred-refresh --dry-run --json` emits the designed payload
(`outcome:noop-not-due`, `invoked_codex:false`, correct guard; host token exp
2026-07-19, ~3.75 days). **Accepted → CLOSED (done).** The transient-race diagnosis
held: the identical work landed clean on a run that did not straddle a pin-bump.

**GitHub-App note:** the dispatch App `livespec-pr-bot` (App ID `3668528`,
installation `131208965` on `thewoolleyman`, covering this repo) ALREADY has
`Workflows: Read and write` at both the App definition and the accepted
installation. That grant is harmless but **latent** — it does not reach the
hardcoded contents-only push token, so it neither fixed nor is needed for W2. Left
in place.

**SYSTEMIC (separate factory-hardening, out of scope for THIS track):** any
dispatch whose run straddles a `.github/workflows/` change on master will hit the
same push-gate. Durable fixes, in order of cleanliness: (a) `pr` node rebases the
branch onto fresh `origin/master` before pushing (prose-only change to `pr.md` —
makes workflow files match master, no gate); (b) fork change to mint the push token
with `workflows:write` (needs a fabro rebuild + re-pin — governed by the fabro pin
constraints); (c) exclude `.github/workflows/**` from sandbox branch deltas. Track
this under factory hardening, not the credential-broker epic.

### W3 dispatch — one inherited-CI failure, then green (execution record)

W3's FIRST dispatch (fabro run `01KXKVCQVYFT…`) **failed at the janitor gate on a
condition it did not cause**: `check-master-ci-green`. W3's own branch was clean
(README-only; local `just check` = `1672 passed, 1 skipped, 100% coverage`,
lint/format/types green). The gate fails closed because the LATEST `master` CI run
(release 0.35.0, commit `7a1e02a`) had gone red when `uv sync` **timed out
downloading cpython-3.10.16** — a CI-infra network flake, unrelated to W3, that
blocks EVERY dispatch's janitor while it stands. Recovery: `gh run rerun 29452285810`
(the full re-run succeeded where the agent's earlier `--failed` variant was refused)
→ CI came back **green** → `fabro rm -f` the failed run + reset `bd-ib-6xv5l5` to
`ready` → re-dispatched → **PR #664 merged, post-merge janitor green**. Verified the
runbook content on merged master; **accepted → CLOSED**.

**Factory-friction note (recurring, not this epic's bug):** `check-master-ci-green`
is a global fail-closed gate — a single transient `uv`/cpython-download flake on the
latest master CI run stalls all dispatches until a fresh green master CI run exists
(via re-run or the next master push). Worth a factory-hardening item (retry the
network fetch, or make the gate tolerate a re-runnable flake) alongside the
stale-workflow push-gate item above.

**NEXT ACTIONS — track complete; ONE manual step remains:**
1. **MANUAL MAINTAINER STEP — install the host timer.** Follow
   `orchestrator-image/README.md` §"Host Codex credential refresher timer": install
   `~/.config/systemd/user/livespec-codex-cred-refresh.{service,timer}` and
   `systemctl --user enable --now livespec-codex-cred-refresh.timer`. Until this
   runs, the unattended refresher is NOT live and the 10-day cliff is only
   *surfaced* by `codex-cred-status` (alarm), not *prevented*.
2. (Optional) File the two factory-hardening items noted above (stale-workflow
   push-gate; `check-master-ci-green` flake tolerance) — outside this epic.

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
