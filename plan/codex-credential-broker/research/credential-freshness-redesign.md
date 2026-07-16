# Credential-freshness redesign — analysis & recommendation

Captured 2026-07-16 from a design review of the just-landed track (W1/W2/W3).
**Nothing here is built yet.** It reconsiders the *approach* to keeping the host
Codex credential fresh; it supersedes the landed *design intent* (the systemd
timer), NOT the landed *code*, pending a maintainer decision. The landed pieces
(`codex-cred-status`, `codex-cred-refresh`, the runbook) all remain valid building
blocks.

## The two mechanisms in play today

- **Freshness gate** — dispatch preflight, `assess_codex_credential_freshness`
  (`_dispatcher_projection.py`). Refuses a dispatch unless the token has **≥5h**
  left: `CODEX_FRESHNESS_RUN_BUDGET_SECONDS = 14400` (4h, an explicit *hard
  backstop*, "NOT an expected run length") + `CODEX_FRESHNESS_MARGIN_SECONDS =
  3600` (1h).
- **Refresher** — `dispatcher codex-cred-refresh` (W2): a GUARDED codex-invoke
  (fires `codex exec` only when within ~6 min of `exp`). Today it is wired **only**
  to the W3 systemd timer, NOT into the dispatch path.

## The problem this reconsiders

1. **The ~5h dead zone.** codex only rotates the access token in its ~5-min
   pre-expiry proactive window (or post-expiry via a 401). So the token must
   *traverse* the band from 5h-left to ~5min-left every cycle; during that band the
   gate refuses (< 5h) but codex won't refresh yet. Result: ~5h of dispatch
   refusals per ~10-day cycle. Rotating at the 5-min mark does not un-refuse the
   preceding band.
2. **The host-coupled timer.** The timer's *only* job is to poll codex's ~5-min
   window so the 10-day cliff never lands. It is standing host infra (systemd
   user unit) whose value is thin: an idle-expired token self-heals on the next
   dispatch anyway (post-expiry 401→refresh), and the W1 alarm already *warns*
   before the cliff.

## The design space

- **(A) Preflight refresh.** Run `codex-cred-refresh` at dispatch, before the gate.
  Cheap, and **no codex-internals coupling** — the worker reads the fresh token at
  process *startup* (an ordinary config read). Self-heals an idle-expired token at
  the next dispatch → removes the timer's reason to exist. Limitation: it cannot
  *force* early rotation (codex won't rotate a mid-life token), so it does not kill
  the dead zone by itself.
- **Mid-run top-up.** Host tracks each running worker's `exp` and pushes a fresh
  access token into the live sandbox via `docker exec` (resolved by fabro's
  `sh.fabro.run_id` label); the worker's **401→Reload** path adopts it. Kills the
  dead zone + gate + timer. Costs: (a) it depends on codex-core's *undocumented*
  in-memory-cache + reload-only-on-401 + retry-after-401 behavior — a hard,
  silently-breakable coupling; (b) it does concurrent-refresh-*during*-execution
  (see findings #3/#4 — the pattern OpenAI warns against).
- **(B) Direct OAuth token-endpoint refresh.** Rotate at *any* time from the host,
  bypassing codex. Kills the dead zone and the timer. Cost: reimplements codex's
  refresh-token rotation → desync with codex's own auth state (documented, real).

The rotation *mechanism* is identical in (A) and mid-run top-up (host runs codex,
codex refreshes itself); they differ only in **delivery** — static-at-startup vs.
dynamic-mid-run. The mid-run delivery is the sole source of the internals coupling.

## Investigation findings (2026-07-16) — ground truth

1. **The access token is a SESSION-BOUND RS256 JWT, not a stateless one.** Local
   decode of `~/.codex/auth.json` (structural fields only): `iss =
   https://auth.openai.com`, 240h lifetime, and claims including **`session_id`**
   and **`jti`**. Those are exactly the handles a server needs to tie an access
   token to a session and revoke it — so per-session/per-token revocation is
   *architecturally possible* here. (This corrects an earlier optimistic assumption
   that access tokens are stateless and therefore un-revokable on rotation.)
2. **Refresh tokens rotate (single-use); multi-client sharing desyncs.**
   Documented: once a refresh token is used, the old one is invalid; when clients
   share one auth file, whichever refreshes first invalidates the others' OAuth
   state (hermes-agent#22903, cc-switch#4474). Our seatbelt + sentinel already
   avoids this for workers (only the host ever holds/uses the refresh token).
3. **OpenAI explicitly discourages concurrent credential sharing.** CI/CD auth doc:
   "Use one `auth.json` per runner or per serialized workflow stream. Do not share
   the same file across concurrent jobs or multiple machines." Scoped to "trusted
   private automation with serialized access, **not** concurrent multi-worker
   scenarios." Our one-credential-fanned-to-N-workers factory is precisely the
   pattern they warn against.
4. **OPEN QUESTION (unresolved non-invasively): does a refresh BUMP `session_id`?**
   - Case 1 — session stable across refresh → old access tokens live to their own
     `exp` (no thundering-herd on rotation).
   - Case 2 — refresh bumps the session → outstanding access tokens with the old
     `session_id` are invalidated at rotation (a fleet-wide, simultaneous failure
     of every worker holding the shared token).
   The `session_id` claim makes Case 2 *possible*; OpenAI's anti-concurrency
   guidance is *consistent* with it; neither *proves* it. **The only definitive
   test is a before/after `session_id` comparison across a real refresh, and there
   is no safe way to trigger one now** — codex has no force-refresh, and an
   out-of-band refresh would rotate (and thus break) the live refresh token →
   forced `codex login`.

## The gate's real role (reframed by finding #4)

The gate's 1h margin does more than guarantee runway: it **temporally separates
rotation from worker execution.** Under the gate, every live worker holds the same
current token and finishes with ≥1h to spare, so rotation (at ~5min-before-exp)
*never overlaps a running worker*. That temporal separation is exactly what makes
our unsupported concurrent-sharing **safe against a session bump** — whether or not
Case 2 holds. Mid-run refresh deliberately destroys that separation.

## Recommendation

**Adopt the conservative shape; defer mid-run refresh on the open question.**

1. **Keep a right-sized gate + preflight refresh (A) + a liveness check + the W1
   alarm; drop the timer.**
   - *Right-size the run budget.* 4h is a backstop; measured runs are ~30 min. Set
     the budget to a measured p99 + margin; the dead zone shrinks ~1:1.
   - *Preflight refresh.* Wire `codex-cred-refresh` into the dispatcher preflight
     (before the gate). Removes the timer (idle self-heals at next dispatch) with
     **no** codex-internals coupling and **no** concurrent-refresh-during-execution.
   - *Liveness check.* Supplement/replace the runway refuse with "can we mint a
     valid access token at all?" The only true hard stop is refresh-token death →
     `codex login`.
2. **Defer mid-run top-up, gated on finding #4.** It is clearly-safe to build
   *only* if `session_id` is stable across refresh (Case 1). If it bumps (Case 2),
   mid-run refresh fights the vendor model (it would have to top up every in-flight
   worker atomically at each rotation, any miss = a dead run) — advise against.
3. **Resolve #4 with ZERO risk.** Instrument `codex-cred-status`/`-refresh` to
   record `session_id` (+ `jti`) whenever it observes the token change, so the next
   *natural* refresh near expiry reveals whether `session_id` bumped — no
   live-credential test, answered within one ~10-day cycle.

## Status

Analysis only; no product code changed. The landed W1/W2/W3 remain in place and
correct. This redesign is tracked in the ledger (see the handoff's "Related");
the decision to supersede the timer (W3's timer, not its runbook) is the
maintainer's.

## Sources

- OpenAI/ChatGPT Codex auth docs: `learn.chatgpt.com/docs/auth`,
  `learn.chatgpt.com/docs/auth/ci-cd-auth`.
- Refresh-rotation desync in the wild: `github.com/NousResearch/hermes-agent`
  issue 22903; `github.com/farion1231/cc-switch` issue 4474.
- Local: structural decode of `~/.codex/auth.json` (`session_id`, `jti`, 240h,
  RS256, `iss=auth.openai.com`).
