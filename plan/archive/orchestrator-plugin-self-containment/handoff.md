# Handoff — orchestrator-plugin-self-containment (livespec-orchestrator-beads-fabro)

**Thread:** `plan/orchestrator-plugin-self-containment/` (ARCHIVED)
**Repo:** `/data/projects/livespec-orchestrator-beads-fabro`
**Scope:** markdown/docs-only planning thread (no product `.py`).

## ✅ STATUS: CLOSED — ARCHIVED (2026-07-02)

The thread's objective LANDED. The self-contained-dispatch contract is
codified (`## Self-contained plugin dispatch`, v021 commit `b84cc98`;
extended v022 `0fb3f24` with factory GitHub App auth) and implemented:
Slices 1+2+3 merged (PRs #217/#219/#220, released **0.3.1** `52af5e2`),
and the Slice-4 substance landed afterwards — the orchestrator image now
**bakes the plugin scripts payload** (`6601a9d`) and
`real-work-dispatch.sh` no longer clones the orchestrator source
(clone-A retired); releases 0.3.2 / 0.4.0 followed. No ledger epic was
ever anchored (the capture path was affected by the same staleness this
thread fixed); the remaining residual — the enabled-plugin / real-path
E2E acceptance (Slice 6) — is now **ledger-tracked as epic `bd-ib-mxr`**
(first slice `bd-ib-cyv` closed), so this markdown thread is no longer
the durable record. The "worktrees pending reap" below were reaped.
Everything below is the historical record, kept verbatim.

> **Status is read LIVE — never a checkbox queue here.** This thread has
> **no ledger epic yet** (see "Ledger anchoring" below): the formal epic +
> work-items are deferred until the orchestrator plugin/ledger machinery is
> refreshed, because the capture path is currently affected by the SAME
> staleness this thread fixes. **Until the epic is anchored, THIS markdown
> thread is the durable record.** Once anchored, read status with:
> ```bash
> with-livespec-env.sh bd children <epic-id> --json
> ```
> (`with-livespec-env.sh` injects the tenant password.)

## Locked decision (maintainer — do NOT relitigate)

Make the `livespec-orchestrator-beads-fabro` plugin **SELF-CONTAINED** so
the dark factory dispatches from the **ENABLED PLUGIN** with **no
orchestrator-source clone** — so fleet members and adopters consume the
orchestrator **IDENTICALLY** (just enable the plugin). This is the real
fix for the factory being inoperable from a cache install: the console's
**E-3a** dispatch failure (dispatcher **exit 3**, "workflow config does
not exist"). It is a **host-side packaging + path-resolution** change,
**NOT** an architecture change — the Fabro Docker sandbox needs nothing
from the orchestrator source (it clones the TARGET repo itself).

**Verdict:** ACHIEVABLE-WITH-WORK; no hard architectural blocker.

## Reframe (session 8): the console unblock flows through the host enabled-plugin path; Slice 4 is a follow-on

**Bottom line.** The epic's blocker is **E-3a** — `orchestrate run` from the
**ENABLED PLUGIN** fails with **dispatcher exit 3, "workflow config does not
exist"**. That failure is the **HOST-SIDE dispatcher reading the
enabled-plugin cache** and not finding the Fabro workflow there. **Slices
1 + 2 + 3 fix exactly that:** the host dispatcher now resolves the workflow
from the **plugin-root payload** (`_plugin_root()`), runs on **stdlib +
vendored deps** (no apt/uv), and carries **cache-safe guards** (no write to
a read-only cache; empty sibling projection without a fleet manifest).

**Therefore the console unblock is:**

1. **Land Slices 1 + 2 + 3** — PRs #217, #219 **merged**; #220
   **auto-merging**.
2. **Cut release `0.3.1`** by merging release-please **PR #218** (it carries
   Slices 1 + 2 + 3).
3. **Refresh the orchestrator plugin cache to `0.3.1`** in the console
   session. **This cache refresh IS the actual unblock step.** The prior
   handoff DEPRIORITIZED the cache refresh under the wrong assumption that it
   "doesn't fix dispatch" — **that note is CORRECTED:** the cache refresh is
   precisely what swaps the console off the stale (pre-self-containment)
   plugin onto the fixed one whose host-side dispatcher resolves the
   plugin-root workflow.
4. **Resume the console E-3a → E-3b → E-4** from the fixed enabled plugin.

**CAVEAT.** Refreshing an *enabled* plugin cache may require a client-side
`/plugin update` **+ restart** (the same limitation seen with the openbrain
pin). Flag this as possibly **maintainer / console-session-side**, not work
a dispatched agent can necessarily complete unattended.

**Slice 4 is NOT on the console critical path.** Slice 4 (#3,
`real-work-dispatch.sh` off clone-A) targets the **UNATTENDED containerized
substrate**, which **already worked** — its clone-A ships `.fabro/` at the
repo root, so the source-mode factory the fleet runs today is unaffected by
the cache-install gap. Slice 4 is **reclassified a FOLLOW-ON** (see its
design-gap note under NEXT ACTION).

## Read-first chain (open these, in order)

1. **`research/01-design.md`** (this thread) — the full design, the
   verified change set, the per-change drift/refinement notes, the
   verified-symbol index, and the four open verification points for the
   implementer. This is the authoritative design of record.
2. **`research/02-verification.md`** (this thread) — the read-only
   verification pass (against `01f2493`) that ANSWERED the four open
   points: VP1/VP2/VP4 confirmed the design; **VP3 corrected it** (change
   #5 — `typing_extensions` must be vendored). Read it paired with the
   design doc.
3. The live code surfaces it cites, in
   `/data/projects/livespec-orchestrator-beads-fabro`:
   - `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py`
     — `_workflow_toml` (~`:2024`), `_candidate_dispatcher_bin` (~`:1004`),
     `_self_update_after_merge` (~`:1016`), `--workflow` arg (~`:2194`).
   - `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_plan.py`
     — `render_run_config_overlay` (~`:788`, absolute-graph rewrite at
     `:856-861`).
   - `orchestrator-image/real-work-dispatch.sh` — clone-A dispatch at
     `:473` (KEEP the TARGET clone; replace the orchestrator clone).
   - `.fabro/workflows/implement-work-item/` — the workflow payload to
     relocate INTO `.claude-plugin/`.
4. `SPECIFICATION/contracts.md` — the LANDED clause #6
   (`## Self-contained plugin dispatch`, ~line `:918` on `master` at
   `b84cc98`).

## The change set (full detail in `research/01-design.md`)

> **A read-only verification pass (`research/02-verification.md`, against
> `01f2493`) corrected the change set.** VP1/VP2/VP4 confirmed the design;
> **VP3 falsified #5** — the host-side dispatcher has one unvendored
> third-party import (`typing_extensions`) that MUST be vendored, so #5 is
> now a **PREREQ slice**, not "no dependency change". #6 (the contract
> clause) has **already LANDED on `master`** (commit `b84cc98`, v021). The
> dependency-ordered slice plan is in **NEXT ACTION** below.

1. **Ship `.fabro/workflows/implement-work-item/` INSIDE
   `.claude-plugin/`** so it installs under the plugin root. Update the
   two integration tests that bind repo-root `.fabro/`
   (`test_workflow_dot_non_convergence_scenario14.py`,
   `test_workflow_acp_adapter_parameterized.py`). (Prior design said "the
   payload-shape test" — there is no single such test; the design doc
   records the real affected tests.)
2. **Re-anchor the resolvers** (`_workflow_toml`,
   `_candidate_dispatcher_bin`) off `parents[4]` onto the **plugin root**.
   `parents[3]` IS the plugin root in BOTH source (`.claude-plugin/`) and
   flattened cache (`${CLAUDE_PLUGIN_ROOT}`) — a robust, env-var-free
   anchor; prefer `--workflow` override → `$CLAUDE_PLUGIN_ROOT` env →
   `__file__`-relative `parents[3]`.
3. **Point the factory at the enabled plugin** instead of cloning the
   orchestrator (`real-work-dispatch.sh:473`). KEEP the target host clone
   and Fabro's in-sandbox target clone. Drop/guard the in-container
   `uv sync` (the flattened cache has no `pyproject.toml`).
4. **Guard the post-merge self-update canary** (already fail-open; make it
   an explicit no-op when there is no writable orchestrator checkout) and
   make the **fleet-manifest sibling-clone projection optional/empty** for
   non-fleet adopters.
5. **Vendor `typing_extensions`** (CORRECTED — was "no dependency
   change"). The host-side dispatcher reaches one unvendored third-party
   import: `typing_extensions` (`assert_never` via
   `_vendor/livespec_runtime/cross_repo/resolve.py:38`; `override` via
   `commands/_otel_receive.py:70`). A stdlib swap is unsafe on the target
   Python 3.10.16. Vendor it into `scripts/_vendor/` + a `NOTICES.md`
   entry; keep `livespec_runtime` unmodified. **PREREQ slice.** (See
   `research/02-verification.md` VP3.)
6. **Codify the contract** in `SPECIFICATION/contracts.md`: the Fabro
   workflow ships in the plugin payload; the dispatcher resolves it via
   the plugin root — making fleet == adopter consumption the documented
   contract. **LANDED** on `master` (commit `b84cc98`, v021;
   `## Self-contained plugin dispatch`).

## NEXT ACTION

Clause #6 (the contract) LANDED on `master` (commit `b84cc98`, v021), and
the host-side implementation (#1 + #2 + #4) has now LANDED too: **Slice 1
and Slice 2 are MERGED; Slice 3 is auto-merging.** The console unblock
(Reframe above) is now **release + cache refresh**, not more dispatcher
code. What remains as code is **Slice 4 (#3, the containerized substrate)**
— reclassified a FOLLOW-ON, NOT on the console critical path — and **Slice 6
(the enabled-plugin acceptance, VP4 residual)**, which pairs with it.

**Recommended slice / dependency order (progress marked):**

- **Slice 1 (ATOMIC #1 + #2) — MERGED, PR #217 (commit `be34561`).**
  Relocated `.fabro/workflows/implement-work-item/` (`workflow.toml` +
  `workflow.fabro` + `prompts/`, as a unit) → `.claude-plugin/.fabro/…` so
  the payload ships under the plugin root, **and** re-anchored both
  resolvers (`_workflow_toml`, `_candidate_dispatcher_bin`) through a new
  **`_plugin_root()` helper** (`CLAUDE_PLUGIN_ROOT` env override →
  `__file__`-relative `parents[3]`), keeping the `--workflow` seam; updated
  the two integration tests
  (`test_workflow_dot_non_convergence_scenario14.py`,
  `test_workflow_acp_adapter_parameterized.py`). #1 + #2 landed in ONE PR
  as required.
- **Slice 2 (PREREQ) — MERGED, PR #219 (commit `10f820d`).** Vendored
  `typing_extensions 4.15.0` (PSF-2.0) at
  `.claude-plugin/scripts/_vendor/typing_extensions.py`, recorded in
  `.vendor.jsonc` + `NOTICES.md`, with a clean `-S` no-site
  import-regression test
  (`tests/bin/test_host_side_self_contained_import.py`).
  `livespec_runtime` left unmodified. **Mechanism note:** `_vendor/*.py` is
  excluded from the `red_green_replay` impl-prefixes, so this landed as a
  **single `build(deps):` commit with `TDD-Suite-Green-*` trailers** — the
  correct ritual for a vendoring change, NOT the `fix:` + Red→Green 2-step.
- **Slice 3 (#4) — PR #220 (commit `6017f19`), AUTO-MERGING.**
  Read-only-cache guards: added `_is_writable_orchestrator_checkout` plus a
  `self-update-skipped` clean no-op (the fail-open `0jxs` supervisor is
  KEPT), and made `_resolve_sibling_clones` return empty when there is no
  manifest. **IMPORTANT — invariant retirement:** this RETIRED the pre-v021
  invariant "refuse dispatch on an unfetchable fleet manifest" (its test was
  repurposed →
  `test_dispatch_proceeds_with_empty_siblings_when_fleet_manifest_is_unfetchable`),
  because the v021 contract clause `## Self-contained plugin dispatch`
  mandates the **empty projection** for non-fleet adopters. A
  **malformed** manifest still refuses.
- **Slice 4 (#3) — FOLLOW-ON, NOT on the console critical path. Do NOT
  dispatch blindly (see design-gap note below).** Retire clone-A in
  `real-work-dispatch.sh` (run the dispatcher from the released plugin
  payload), drop/guard the in-container `uv sync`, and update the cosmetic
  `orchestrator-entrypoint.sh:179` hint. KEEP the dispatch-TARGET host
  clone and Fabro's in-sandbox target clone. Leave `tier2-dispatch-proof.sh`
  and `acceptance-live-golden-master.sh` source-mode.

  > **Slice-4 design-gap note (why this is a focused design pass, not an
  > auto-merging slice agent).** `real-work-dispatch.sh`'s clone-A
  > provisions **MORE than the dispatcher code** — it also supplies the
  > orchestrator's own `.beads/config.yaml` tenant config + `metadata.json`
  > regen (via `bd init`) + (formerly) `uv sync`. The orchestrator image
  > bakes in **NO plugin payload** (it is a generic `gh`/`mise`/`fabro`
  > toolchain image). So moving Slice 4 off clone-A needs a real design
  > choice: **how the container consumes the released plugin payload AND
  > provisions the orchestrator's tenant config without a full source
  > clone.** This deserves a focused design pass. **Slice 6 pairs with it.**
- **Slice 5 (#6) — DONE.** The `## Self-contained plugin dispatch`
  contract clause LANDED on `master` (commit `b84cc98`, v021). The
  parallel branch `spec-self-contained-plugin-dispatch` (a divergent
  re-take of the same v021 work, branched from `01f2493` before the clause
  landed) is **superseded** — abandon/clean it up rather than merge it.
- **Slice 6 (FOLLOW-ON, VP4 residual) — pairs with Slice 4.** Migrate/extend
  the golden-master acceptance to prove the **enabled-plugin /
  flattened-cache** dispatch path end-to-end — the current golden master
  proves only the source-mount path. File as a paired acceptance work-item
  alongside the Slice-4 design pass.

When the ledger machinery is healthy, **`groom`** #1–#5 into the slices
above (#6 already ratified), then **implement** each ready slice. If the
spec clause ever needs amendment, drive it via **`/livespec:propose-change`**
+ **`/livespec:revise`** (co-edit `tests/heading-coverage.json` on any
`## ` heading change).

**Ledger anchoring (why no epic yet).** The formal ledger epic + the
work-items for #1–#5 should be **anchored once the orchestrator
plugin/ledger machinery is refreshed** — the capture path (`groom` /
`capture-work-item`) is currently affected by the **same staleness this
thread fixes**, so filing now would be filing through a broken path.
**Until then, this markdown thread is the durable record**; the design in
`research/01-design.md` is complete enough to anchor the epic and groom
the slices the moment the machinery is healthy.

## Side-findings (non-blocking, for later)

Surfaced while landing Slices 1–3; none block the console unblock. Logged
here so they are not re-discovered cold.

- **CORE `propose_change.py` / `revise.py` resolve a RELATIVE `--spec-target`
  verbatim against cwd** (not joined to `--project-root`) — a cross-repo
  footgun. Workaround: **pass an ABSOLUTE `--spec-target`.** Candidate
  CORE-tenant work-item.
- **CORE `doctor_static.py` accepts only `--project-root`, not
  `--spec-target`** — asymmetric with the propose/revise surface above.
- **The local Codex TUI sits on a "Hooks need review — 4 hooks new/changed"
  trust prompt** that blocks `check-codex-skill-picker` locally. That check
  is **skip-by-default in CI / pre-commit / pre-push** (CI self-skips), so it
  does **not** block merges. Environmental, not a repo defect.

## Worktrees pending reap

Merged feature worktrees under `~/.worktrees/livespec-orchestrator-beads-fabro/`
to reap **once no agent is active** (use the repo reaper, e.g.
`just reap-stale-worktrees`, not hand-deletion):

- `spec-self-contained-plugin-dispatch` — PR #215
- `docs-self-containment-verification` — PR #216
- `slice1-plugin-root-resolver` — PR #217
- `slice2-vendor-typing-extensions` — PR #219
- `slice3-readonly-cache-guards` — PR #220

**Also:** release-please **PR #218 ("release 0.3.1") is OPEN** and should be
merged (it is App-authored) to **cut the release that carries Slices 1 + 2 +
3** — the prerequisite for the console cache refresh in the Reframe above.

## Working discipline (non-negotiable)

- This is a **markdown/docs-only** thread → `docs(plan):` commit subject;
  **EXEMPT** from the red-green-replay TDD ritual. The actual code change
  set (#1–#5) is product `.py` / shell and follows red-green-replay when
  implemented — that is the implement phase, not this planning thread.
- Operate only in a dedicated worktree under
  `~/.worktrees/livespec-orchestrator-beads-fabro/<branch>`; use
  `mise exec -- git …`; never `--no-verify`; on a hook failure, fix the
  cause or HALT and report.
- Open a PR and enable auto-merge (`gh pr merge <n> --auto --rebase`); do
  not merge manually or force-push another session's branch.
- Secrets are probe-only (`printenv NAME | wc -c`); no human-scale time
  framings.
- VERIFY any code symbol/path before asserting it — the design doc's
  references were read against `master` at `0b0fa50`; re-confirm line
  numbers (they drift) by symbol name, not by line.

## Reporting

Report to the coordinator when the clause-#6 propose-change/revise lands,
when the epic is anchored + groomed, and at each implementation PR merge.
