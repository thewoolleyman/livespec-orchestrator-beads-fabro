# Plan handoff — codex-yolo-sandbox (ARCHIVED 2026-07-19)

**CLOSED. Epic `bd-ib-1jye` and all six children are closed; the contract is
ratified in `SPECIFICATION/history/v043`.** Nothing here is open work. This file
is kept as the design record and the defect post-mortem — read it before touching
`.claude-plugin/hooks/codex_yolo_*.py`, the Codex gate, or the drift canary.

## What this track is

Make every Codex sub-session launched through the codex-companion plugin run in full-access
"YOLO" mode (`danger-full-access`: full disk + network, no OS sandbox), so a dispatched Codex
reviewer can actually run `pytest`/`gh` instead of silently passing code it never executed —
and make that permanent for fleet members and official adopters, **without forking**
`openai/codex-plugin-cc` (the maintainer ruled the fork out).

## DONE and landed — do NOT redo

- **S2 LANDED via the factory** (PR #791, `afe5ff1`): `.claude/hooks/codex_yolo_gate.py`
  (`gate_state` + `read_marker` + a manifest-derived `refresh` path), the committed
  `codex_full_access.fleet_listed` marker in `.livespec.jsonc`, a justfile refresh target, and
  `codex_yolo_reapply.main()` wired to no-op when the gate is OFF. Precedence:
  `LIVESPEC_CODEX_FULL_ACCESS` (both directions) > committed marker > OFF.
- **HOOK-CHAIN FIX LANDED** (PR #793, `483c100`) — read this before touching the hooks again.
  Adversarial review of S1 + empirical probing found **three silent-failure defects**, both of the very class this epic exists to eliminate (Codex quietly back on stock
  `read-only`, so a reviewer that cannot execute passes code it never ran):
  1. **S1's rewrite lost the shell's per-file isolation.** The `.sh` ran each cached
     `codex.mjs` in its OWN `python3 -c` subprocess, so a failure died there and the loop moved
     on. One process meant one escape aborted everything: `read_text_or_none` caught only
     `OSError` while `UnicodeDecodeError` derives from `ValueError`, and `write_text` was
     unguarded — so a non-UTF-8 or unwritable file crashed the hook at SessionStart AND left
     every alphabetically-later cached version stock, with NO canary warning. Fixed at both
     sites plus an explicit per-file bulkhead.
  2. **S2's gate read its marker from `Path.cwd()`.** The marker lives at
     `<repo>/.livespec.jsonc`, so starting a session anywhere but the repo root — a
     subdirectory sufficed — found nothing, reported OFF, and silently no-opped the hook. Now
     anchored on the hook's own `__file__`.
  3. **The drift canary could be silenced in the exact case it exists for** (PR #795,
     `463a573`). `classify_state` called a file `patched` if the bare env-var name
     `CODEX_COMPANION_SANDBOX` appeared ANYWHERE in it. So an upstream restructure — which
     IS the drift condition — combined with any passing mention of that name classified an
     UNPATCHED file as patched: no rewrite, no warning, Codex silently on stock `read-only`.
     Not hypothetical: the unmerged upstream toggle proposal in
     [`research.md`](./research.md) is named `CODEX_COMPANION_SANDBOX_MODE`, which CONTAINS
     our sentinel as a substring, so if it ever lands the canary goes quiet on the very
     release that broke us. Now matches the full `PATCHED` expression; `SENTINEL` is deleted
     (a second, looser spelling of "is it patched" WAS the bug). Failure direction is now
     safe: a cosmetic upstream reformat reports `drift` (loud) instead of a restructure
     reporting `patched` (silent). Verified all three live cached versions still classify
     `patched`, so the tightening creates no false drift.
    4. **S3 + C1 landed clean, and grooming is why** (PRs #800, #803). Both were dispatched with
     explicit acceptance criteria written after reading the actual APIs. S3's criteria named a
     landmine in advance — `owning_repo_root()` resolves `__file__.parents[2]`, correct for
     `.claude/hooks/` but WRONG once shipped from the plugin cache, where it would point at the
     plugin and leave the gate silently OFF for EVERY adopter — and directed the agent to
     `CLAUDE_PROJECT_DIR`; it complied and the shipped hook is correct. C1's criteria flagged
     that it touches product `.py` and so needs the Red->Green pair (unlike the hooks slices'
     suite-green leg), and separated the REAL executed argv from call sites that merely emit
     suggestion strings. **Ungroomed one-paragraph items produced defects; groomed ones did
     not.** Groom before dispatching.
- **The transferable lesson:** 100% line+branch coverage did not catch either one. Coverage
    cannot see a MISSING `except` clause, nor an assertion that never discriminates. Mutation
    testing found two more dead assertions (a `sorted()` that the filesystem's own ordering
    masked; a footgun-guard read-flag arm deletable without any test failing). **Probe hook
    behavior against the OLD implementation empirically; do not infer it from coverage.**

- **The fix is already LIVE in this repo** (PR #730, `737f562`): a one-line chokepoint rewrite
  in the codex plugin cache — `buildThreadParams` / `buildResumeParams` in `lib/codex.mjs`
  resolve to `danger-full-access`, with `CODEX_COMPANION_SANDBOX` as a downgrade escape-hatch —
  plus `.claude/hooks/codex-yolo-reapply.sh` re-applied from `hooks.SessionStart` (ordered AFTER
  `just ensure-plugins`, because a plugin refresh clobbers the cache), and
  `sandbox_mode = "danger-full-access"` in `~/.codex/config.toml` (host-local, not in git).
  Proven end-to-end: patched default → `NET=200` + out-of-workspace write;
  `CODEX_COMPANION_SANDBOX=read-only` → `NET=000`. **Network is the discriminator** —
  `read-only` AND `workspace-write` are both network-OFF, so `NET=200` proves
  `danger-full-access` specifically.
- **Upstream research** (PR #739, `bb845ec`): this is NOT new ground — 12+ issues and 5+ PRs
  upstream, **none merged**, and the sharpest root-cause issues have zero maintainer comments.
  Full survey + the "why" analysis: [`research.md`](./research.md). Consequence: do NOT wait on
  upstream; self-carry.
- **Design**: [`permanent-fix-design.md`](./permanent-fix-design.md) — options A/B/C, the two
  distinct failure surfaces, the mandatory drift canary, and the spec-ratification path.
- **Adopter gate DECIDED** (PR #742, `0184180`): **ON** for fleet members + official adopters,
  **opt-in** for everyone else — keyed on the core fleet manifest
  `.livespec-fleet-manifest.jsonc` (`members` ∪ `adopters`) parsed by
  `livespec_dev_tooling.fleet.contract.parse_manifest`; project identity via the fleet
  contract's `resolve_owner`.
- **S1 LANDED — hand-implemented, supervised** (PR #782, `667b24d`), after the factory
  failed it twice on token-expiry. `.claude/hooks/codex_yolo_reapply.py` is now a pure,
  importable module (`classify_state` / `apply_patch` / `read_text_or_none` /
  `cached_codex_mjs_paths` + `main`), the `.sh` is a thin `exec python3` wrapper, and the
  **drift canary** writes a loud stderr WARNING for any cached `codex.mjs` carrying neither
  the stock string nor our `CODEX_COMPANION_SANDBOX` sentinel. Runtime behavior unchanged:
  always-on, repo-local, idempotent, fail-open.
  - **Enabling work it forced, now also landed.** `.claude/hooks` was a
    `source_tree_prefixes` + `covered_trees` entry with **no `mirror_pairings` entry** — an
    incoherence that stayed latent only because no `.py` under it had ever changed on a
    branch. The first one that did failed `check-check-coverage-incremental` (it derives its
    changed set from `source_tree_prefixes`, then resolves each path to a mirror-paired
    test). So the PR also pairs `.claude/hooks` -> `tests/hooks`, covers the two
    pre-existing untested hooks (`beads_access_guard`, `livespec_footgun_guard`), and
    deletes three provably-unreachable arms in `livespec_footgun_guard.py` that blocked its
    100%-branch gate. **All three hook modules are now at 100% line + branch.**
  - **Gotcha for the next slice:** the replay check classifies `.claude/hooks/**.py` as
    **non-product**, so a hooks changeset takes the **green-verified / suite-green leg**, NOT
    a Red-Green pair — use a `chore(...)` subject. A `feat:`/`fix:` subject declares Red
    intent and, with no product impl staged, is routed to Red mode, which then rejects any
    commit staging more than one test file (`multi-test-file`).
- **AGENTS.md orientation note** (PR #731).
- **S5's spec proposal LANDED** (`61363e7` + `e968bb4`); item `.2` sits at `acceptance` — the
  maintainer may want to accept/close it.

## The ledger — epic `bd-ib-1jye`

| ID | Slice | Status |
| --- | --- | --- |
| `bd-ib-1jye.1` | S1 — tested re-apply module + drift canary | `closed` |
| `bd-ib-1jye.2` | S5 — spec ratification (`v043`) | `closed` |
| `bd-ib-1jye.3` | S2 — manifest-gating helper | `closed` |
| `bd-ib-1jye.4` | S3 — ship the hook FROM the plugin | `closed` |
| `bd-ib-1jye.5` | C1 — orchestrator-owned full-access `codex exec` | `closed` |
| `bd-ib-1jye.6` | de-duplicate the two hook copies | `closed` |

The epic `bd-ib-1jye` itself is CLOSED. No open work remains on this track.

Each item's full spec lives in its beads record — `with-livespec-env.sh -- bd show <id>`.

## Outcome

Every slice landed and was verified empirically, not merely gate-green:

| Item | Slice | Landed |
| --- | --- | --- |
| `.1` | S1 — tested re-apply module + drift canary | #782 (fixed by #793, #795) |
| `.2` | S5 — spec ratification | #812 amend -> #813 ratify (`v043`) |
| `.3` | S2 — manifest-gating helper | #791 (fixed by #793) |
| `.4` | S3 — ship the hook FROM the plugin | #800 |
| `.5` | C1 — orchestrator-owned full-access `codex exec` | #803 |
| `.6` | de-duplicate the two hook copies | #814 |

Final shape: ONE source of truth at `.claude-plugin/hooks/`, distributed via the
plugin's own `hooks.json`; the repo-local copies and the redundant
`.claude/settings.json` SessionStart entry are gone (the double-run is resolved).
The contract is normative in `constraints.md` §"Codex full-access runtime
constraints", and Scenario 21 covers discovery plus full-access posture.

## The lesson this track actually taught

**A green gate is not evidence.** `just check` at 100% line+branch coverage
passed while FOUR silent-failure defects shipped, every one of them the same
class the epic existed to eliminate — Codex quietly back on `read-only`, so a
reviewer that cannot execute passes code it never ran:

1. The shell->Python rewrite lost the shell's per-file subprocess isolation, so
   one unreadable `codex.mjs` crashed SessionStart AND left every later cached
   version stock, with no canary warning (#793).
2. The gate read its marker relative to `Path.cwd()`, so starting a session in
   any subdirectory silently reported OFF (#793).
3. The canary treated a bare env-var-name substring as "patched", so an upstream
   file merely MENTIONING `CODEX_COMPANION_SANDBOX` silenced it — and the
   unmerged upstream toggle is named `CODEX_COMPANION_SANDBOX_MODE`, containing
   it as a substring (#795).
4. The pre-implementation spec draft would have RATIFIED defect 3 as a
   requirement, plus three other claims that contradicted the shipped code
   (#812).

Coverage cannot see a MISSING `except` clause, an assertion that never
discriminates, or a sentinel that matches too much. What found all four was
adversarial review plus differential probing against the OLD implementation.
Mutation testing separately exposed two dead assertions in tests that reported
100%.

**Corollary for dispatch:** ungroomed one-paragraph work-items produced defects;
items groomed with acceptance criteria written after reading the real APIs did
not. S3's criteria named its landmine in advance (an `__file__`-relative repo
root that would have been silently OFF for every adopter once shipped from the
plugin cache) and the agent followed them. Groom before dispatching, and review
what the factory produces — auto-merge lands a PR as soon as checks pass.

**Harness trap, still true:** bare `python3` on this host is a mise shim that
HANGS with no output when `HOME` points somewhere without mise config. Use an
absolute interpreter (`/usr/bin/python3.13`) for any probe overriding `HOME`.

## Hard rules and gotchas — each of these cost real time

- **NO detached / `setsid` / `nohup` watchers.** The maintainer explicitly objected to a
  background process auto-dispatching with no session attached and no oversight. If you want a
  watcher, use a harness-owned background task (tracked, killable, dies with the session).
- **`.overseer-state` holds EXACTLY ONE token** on its first line — `ready`,
  `blocked: <one-line reason>`, or `winding-down`. It is NOT a handoff surface; durable notes
  belong in THIS file. A long note there is reported fleet-wide as a malformed state file.
- **Dispatcher readiness ≠ `bd ready`.** The board lane IS the stored status, so an item must be
  stored status `ready`. Raw `bd create` files items as `open`, and the dispatcher then rejects
  them ("not in the ready set") — fix with `bd update <id> -s ready`. A killed dispatch can also
  leave an item stuck `active`; reset it to `ready` before re-dispatching.
- **`dispatcher loop --budget N`**: `N` is a dispatch COUNT, not dollars.
- **`loop --item <id>` validates readiness UP FRONT** and rejects a still-blocked item, so it
  cannot be used to "wait until it unblocks."
- Run every `bd` / dispatcher command under
  `/data/projects/1password-env-wrapper/with-livespec-env.sh -- …`. The beads-access guard also
  false-positives on the bare word "bd" appearing in unrelated shell (e.g. inside an `echo`), so
  write notes with a file tool rather than `echo`.
- **`.claude/hooks/` is a `source_tree_prefixes` entry**: touching a hook file requires a paired
  `tests/` change (`check-commit-pairs-source-and-test`), and `check-tests-no-subprocess-spawn`
  forbids testing the `.sh` by spawning it — which is exactly why S1 must become a tested Python
  module with a thin shell wrapper.
- Repo mutation protocol: worktree → PR → merge → cleanup; never commit on the primary checkout.
  Docs/shell/config changesets use `chore(...)` / `docs(...)` and skip the Red-Green ritual, but
  S1's new product `.py` DOES require the Red→Green pair.

## Deferred / explicitly not doing

- **Forking `openai/codex-plugin-cc`** — the maintainer ruled it out.
- **Upstreaming a sandbox toggle (option B)** — good citizenship, but the research shows upstream
  is a graveyard (nothing merged, no maintainer engagement); do not block this track on it.

## Goal

Make every Codex sub-session launched through the `codex:codex-rescue` subagent /
codex-companion runtime **always run in full-access "YOLO" mode** — full disk +
network, no OS sandbox, no approval prompts — so Codex is **never blocked by
sandbox restrictions** and can run tests (pytest/uv), `git`, and `gh`.

**Why this matters (the trigger):** a Codex adversarial review of work-item
`bd-ib-98c.3` (F1) ran read-only with **no network and no writable temp**, so it
could not run `pytest` ("uv failed on read-only cache init") or `gh pr diff`
("could not reach GitHub"). It reviewed statically and **passed the code as
correct**. A parallel Fable reviewer that *could* execute ran the parser against a
real event stream and caught **two real bugs** (a `review.verdict` mislabel and a
non-fail-soft emission leg). A crippled reviewer that can't execute is worse than
no reviewer — it gives false confidence. Same limitation degrades every
rescue/diagnosis Codex run.

## Root cause (code-verified, file:line)

The codex-companion plugin does **not** run `codex exec` with CLI flags. It spawns
`codex app-server` and drives it over JSON-RPC (`scripts/lib/app-server.mjs:190`,
argv is literally just `["app-server"]`). Sandbox + approval are set as **per-thread
JSON-RPC params** on every `thread/start` / `thread/resume`, and the plugin
**hardcodes restrictive values and never emits Codex's third, unrestricted mode
(`danger-full-access`) anywhere in its source:**

- **`task` (the rescue path):** `scripts/codex-companion.mjs:491` —
  `sandbox: request.write ? "workspace-write" : "read-only"`. So `task` = read-only;
  `task --write` = workspace-write. **Neither enables network** (see below), and
  neither is full-access.
- **`review`:** `scripts/lib/codex.mjs:1012` — literal `sandbox: "read-only"`,
  no caller override.
- **`adversarial-review`:** `scripts/codex-companion.mjs:414` — literal
  `sandbox: "read-only"`. Its arg parser (`codex-companion.mjs:713-719`) does not
  even recognize `--write`, so there is **no flag to escape read-only** for reviews.
- `approvalPolicy` is unconditionally `"never"` (`scripts/lib/codex.mjs:63-83`) —
  approvals are NOT the blocker; the sandbox is. (`codex exec`/app-server headless
  never prompts anyway.)

**Two critical wrinkles that defeat the "obvious" fixes:**

1. **`~/.codex/config.toml` is moot here.** It has no `sandbox_mode` set, but even
   if it did, the plugin sends an **explicit per-thread `sandbox` param that
   overrides config**. Setting `sandbox_mode = "danger-full-access"` in config.toml
   will NOT change these runs. (Confirmed: Codex's config-vs-explicit precedence
   makes the explicit param authoritative.)
2. **Network is off even under `workspace-write`.** Codex's `workspace-write`
   defaults `network_access = false`; only `danger-full-access` bakes in network.
   So even `task --write` cannot reach GitHub/PyPI without more.

The restriction is **Codex's own Landlock/seccomp/bubblewrap sandbox** acting on the
`sandbox` value it is told — verified NOT a host limit (host `/tmp` is writable and
`curl api.github.com` returned 200 from the same environment).

The plugin files live in the **cache**:
`/home/ubuntu/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/{codex-companion.mjs, lib/codex.mjs, lib/app-server.mjs}`.

## Codex's actual capability (the target state)

- Sandbox modes: `read-only` / `workspace-write` / `danger-full-access`. Only
  `danger-full-access` = full disk + network, no restrictions.
- CLI flag (**use this** — explicit and documented):
  `codex exec --dangerously-bypass-approvals-and-sandbox` → forces
  `DangerFullAccess`. (`--yolo` is an accepted but UNDOCUMENTED shorthand alias in
  0.144.3 — hidden from `--help`/completion, but the parser accepts it identically
  to the full flag; prefer the explicit form. `--full-auto` maps to
  workspace-write; do NOT use it for full access.)
- app-server transport equivalent of `--dangerously-bypass-approvals-and-sandbox`
  = sending `sandbox: "danger-full-access"` on the thread — which is exactly the
  value the plugin never sends.

## Options (for the new session to decide)

| # | Approach | Durability | Notes |
| --- | --- | --- | --- |
| 1 | Patch the 3 cached sandbox sites → `danger-full-access` directly | ❌ clobbered on plugin update | Fastest, but silently reverts on any `codex plugin` refresh. Only acceptable with a re-apply hook or version pin. |
| 2 | Fork `openai-codex` (thewoolleyman fork): make the 3 sites resolve to `danger-full-access`, gated behind an env/config toggle (e.g. `CODEX_COMPANION_SANDBOX=danger-full-access`) + add a `--sandbox`/`--full-access` flag to the review parser; install the fork | ✅ durable | Maintenance: track upstream. Fits the repo's existing fork-carry discipline (cf. the fabro `factory-integration` pattern). |
| 3 | Upstream a PR to `openai-codex` making the companion sandbox configurable (respect a per-call `sandbox` option + a default-full-access toggle) | ✅ durable, best long-term | Slow — depends on upstream merge. |
| 4 | **Bypass the plugin for execute-needing reviews:** call Codex directly via `codex exec --dangerously-bypass-approvals-and-sandbox "<prompt>"` (or an app-server client sending `sandbox: "danger-full-access"`) instead of the hardcoded-read-only `review`/`adversarial-review` path | ✅ fully under our control | Fast interim; a small wrapper the orchestrator invokes for reviews. Does NOT fix the `task`/rescue path (still workspace-write). |

**Recommendation:** (4) as an immediate interim so review runs can execute *today*,
plus (2) or (3) for durability so the standard rescue *and* review paths are YOLO
and survive plugin updates. The user wants the whole sub-session always-YOLO (the
`task` ternary at `codex-companion.mjs:491` included), so the durable fix must cover
all three sites, not just reviews.

## Risks (surfaced, user has accepted always-YOLO)

`danger-full-access` removes Landlock/seccomp confinement and enables unrestricted
network with **no per-command gate** (exec mode never prompts). A prompt-injected or
hallucinated destructive/exfil command runs immediately against the operator's full
filesystem + network. In this dark-factory context Codex is **already** the sole
implementer agent with in-repo git/gh/pytest access, so the marginal increase is:
losing cwd-confinement (writes anywhere on host) + always-on network. A middle
ground exists if full-access is more than wanted — `workspace-write` +
`[sandbox_workspace_write] network_access = true` (network on, writes confined to
cwd) — but the stated ask is YOLO. Whatever the fix, it MUST survive plugin updates
(option 1 alone does not).

## First steps for the new session

1. **Reproduce:** run a `codex:codex-rescue` review and confirm read-only/no-network
   (it will fail to `pytest`/`gh`). Baseline.
2. **Pick the option** (recommend 4 interim + 2/3 durable).
3. **Implement the interim (4):** a review wrapper that shells
   `codex exec --dangerously-bypass-approvals-and-sandbox` and returns the result;
   verify it can run `pytest` + `gh` inside a repo.
4. **Implement the durable fix (2/3):** the 3 sandbox sites →
   `danger-full-access` (env/config-gated), + a review-parser `--full-access` flag.
5. **Survives-update guard:** pin the plugin version, add a post-install re-patch
   hook, or carry the fork — so a marketplace refresh can't silently re-sandbox.
6. Formalize as a proper plan thread (`/plan codex-yolo-sandbox`) + anchor a ledger
   epic if driving it to completion.

## Evidence / references

- Companion runtime (cache): `scripts/codex-companion.mjs` (`:414` adversarial-review,
  `:491` task ternary, `:461-495` executeTaskRun, `:713-719` review arg parser);
  `scripts/lib/codex.mjs` (`:63-83` buildThreadParams — approvalPolicy always
  "never", sandbox defaults "read-only"; `:1002-1015` runAppServerReview, `:1012`
  literal read-only); `scripts/lib/app-server.mjs:190` (spawns `codex app-server`).
- Codex CLI `codex-cli 0.144.3`: `--dangerously-bypass-approvals-and-sandbox`
  → `SandboxMode::DangerFullAccess`. It also accepts an **undocumented `--yolo`
  alias** (hidden from `--help`/completion, but the parser accepts `--yolo`
  identically to the full flag while rejecting near-miss typos like `--yo` — so it
  is a real hidden alias, not inference; prefer the explicit flag). `codex exec`
  hardcodes
  `AskForApproval::Never`; CLI flag > config precedence
  (`resolve_permission_config_syntax`); config keys `sandbox_mode`,
  `[sandbox_workspace_write] network_access`, `default_permissions=":danger-full-access"`
  (mutually exclusive with `sandbox_mode`); no `CODEX_*` env forces sandbox
  (`CODEX_HOME` only relocates config dir).
- Verified host is not the limiter: host `/tmp` writable, `curl api.github.com` → 200.
