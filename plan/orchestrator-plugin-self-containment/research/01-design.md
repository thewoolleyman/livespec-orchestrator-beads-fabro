# Design — orchestrator plugin self-containment

**Thread:** `plan/orchestrator-plugin-self-containment/`
**Repo:** `livespec-orchestrator-beads-fabro`
**Verified against:** `master` at `0b0fa50` (worktree base).

This document is the design + change set for making the
`livespec-orchestrator-beads-fabro` plugin SELF-CONTAINED. Every code
symbol and path below was read against the live tree before being
asserted; corrections to the prior verbal design are called out inline
under **DRIFT** / **REFINEMENT** markers.

---

## Locked decision (maintainer — do not relitigate)

Make the `livespec-orchestrator-beads-fabro` plugin **self-contained** so
the dark factory dispatches from the **ENABLED PLUGIN** with **no
orchestrator-source clone** — so fleet members and adopters consume the
orchestrator **identically** (just enable the plugin). This is the real
fix for the factory being inoperable from a cache install (the console's
**E-3a** dispatch failure: dispatcher exit 3, "workflow config does not
exist").

---

## Problem (verified)

The host-side dispatcher resolves its Fabro workflow from the
orchestrator **repo root**, which only exists when the orchestrator
**source** is on disk:

- `_workflow_toml` — `commands/dispatcher.py:2024`. When `args.workflow`
  is `None` it computes
  `package_root = Path(__file__).resolve().parents[4]` and returns
  `package_root / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"`.
- `_candidate_dispatcher_bin` — `commands/dispatcher.py:1004`. Same
  `parents[4]` walk, returning
  `package_root / ".claude-plugin" / "scripts" / "bin" / "dispatcher.py"`.

The module lives at
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py`,
so the `parents[]` chain is:

| index | SOURCE layout | FLATTENED install layout |
|---|---|---|
| `parents[0]` | `commands/` | `commands/` |
| `parents[1]` | `livespec_orchestrator_beads_fabro/` | `livespec_orchestrator_beads_fabro/` |
| `parents[2]` | `scripts/` | `scripts/` |
| `parents[3]` | `.claude-plugin/` | **plugin-root / `${CLAUDE_PLUGIN_ROOT}`** |
| `parents[4]` | **repo root** | parent of plugin-root (**over-climb**) |

`.fabro/` is a sibling of `.claude-plugin/` at the repo root (verified:
`.fabro/workflows/implement-work-item/{workflow.toml,workflow.fabro,prompts/*.md}`),
i.e. **outside** the packaged payload. The installer flattens
`.claude-plugin/scripts/` → `scripts/` under the cache root, so:

1. A cache-installed plugin has **no `.fabro/`** at all (it never
   shipped), and
2. Even the `.claude-plugin/scripts/bin/dispatcher.py` literal in
   `_candidate_dispatcher_bin` is wrong post-flatten (there is no
   `.claude-plugin` path segment in the cache), and `parents[4]`
   **over-climbs by one** (it points at the parent of the cache root).

So `orchestrate run` from an enabled plugin cannot find the workflow →
dispatch fails (the **E-3a** "workflow config does not exist", dispatcher
exit 3). The factory works **only** where the orchestrator **source**
sits on disk (the fleet), never for an adopter who merely enabled the
plugin.

### How the source clone reaches dispatch today (verified)

`orchestrator-image/real-work-dispatch.sh` fresh-`git clone`s **two**
repos inside the container:

- **"Clone A" — the orchestrator ITSELF** (`DISPATCHER_REPO`, default
  `livespec-orchestrator-beads-fabro`) into `DISPATCHER_CLONE`
  (`/workspace/livespec-orchestrator-beads-fabro`). The dispatcher then
  runs from there: `real-work-dispatch.sh:473` execs
  `python3 "$1/.claude-plugin/scripts/bin/dispatcher.py" …` with `$1` =
  `DISPATCHER_CLONE`. (Same invocation shape in
  `tier2-dispatch-proof.sh:233` and
  `acceptance-live-golden-master.sh:433`; the operator hint in
  `orchestrator-entrypoint.sh:179` names the same path.) This is the ONLY
  reason the orchestrator source is on disk at dispatch time, and the
  ONLY way `.fabro/` reaches the resolver. The Dockerfile does **not**
  `COPY` `.fabro/` into the image (verified) — it is fetched fresh by the
  clone.
- **The dispatch TARGET repo** (`TARGET_REPO`) into `TARGET_CLONE`
  (`/workspace/dispatch-target`). `dispatcher.py loop --repo
  <target-clone>` keys ledger resolution off this. Fabro clones the
  target **again** fresh inside its own sandbox (Architecture C); this
  host-side clone is the Dispatcher's own venue.

---

## Why the fix is safe (verified)

The Fabro Docker **SANDBOX** needs **nothing** from the orchestrator
source: it clones the TARGET repo itself and runs a generic toolchain
image. The orchestrator clone exists only to give the **host-side
dispatcher** (a) its own Python package (already in the packaged payload)
and (b) the `.fabro/` workflow (not yet in the payload). So this is a
**host-side packaging + path-resolution** change, **not** an architecture
change. The host-side dispatcher's imports are satisfied from the
flattened payload alone: `_bootstrap.py` (`scripts/bin/_bootstrap.py`)
inserts `scripts/` and `scripts/_vendor/` onto `sys.path`, and `_vendor/`
carries `livespec_runtime/` + `livespec_spec_clauses.py`.

---

## Change set

Each item carries its **verified surface** and any **DRIFT/REFINEMENT**
vs. the prior verbal design.

### 1. Ship `.fabro/` inside the packaged payload

Move (or mirror) `.fabro/workflows/implement-work-item/` —
`workflow.toml`, `workflow.fabro`, and the five `prompts/*.md`
(`implement.md`, `pr.md`, `review.md`, `fix.md`, `review-fix.md`) — to
live **inside `.claude-plugin/`** so the installer copies it under the
cache root (`${CLAUDE_PLUGIN_ROOT}/.fabro/…`).

**Fabro repo-root-convention tension (flag for implementer).** `.fabro/`
is also Fabro's own repo-root convention. The per-dispatch overlay
already rewrites the graph path to **absolute** before Fabro runs it:
`render_run_config_overlay` (defined in
`commands/_dispatcher_plan.py:788`, **not** in `dispatcher.py`; call site
`dispatcher.py:1788` passes `workflow_dir=committed.parent.resolve()`)
computes `resolved_graph = graph_path if graph_path.is_absolute() else
workflow_dir / graph_path` and substitutes the absolute path into the
materialized run-config (`_dispatcher_plan.py:856-861`). Because the
resolver only needs `committed` (the `workflow.toml` path) to point at
the real file, a **packaged location + the existing absolute-overlay**
should satisfy Fabro regardless of where `workflow.toml` physically
lives. The implementer MUST verify Fabro tolerates a `.fabro/` that is
not at the invocation's repo root (the materialized overlay is written
outside the workflow dir already, which is exactly why the absolute
rewrite exists).

**DRIFT — "the plugin-distribution payload-shape test".** There is **no**
single dedicated payload-shape test in this repo (unlike livespec CORE's
`tests/test_plugin_distribution.py`). The tests that actually bind the
repo-root `.fabro/` location are TWO integration tests, both resolving
`_REPO_ROOT = Path(__file__).resolve().parents[2]` and reading the
shipped workflow from `_REPO_ROOT / ".fabro" / "workflows" /
"implement-work-item"`:

- `tests/integration/test_workflow_dot_non_convergence_scenario14.py`
  (`_WORKFLOW_DOT` at line 33)
- `tests/integration/test_workflow_acp_adapter_parameterized.py`
  (`_WORKFLOW_DIR` / `_WORKFLOW_DOT` at lines 19-20)

These path constants must update to the new packaged location when the
workflow relocates. The MANY unit tests that build a fixture
`[workflow] graph = "workflow.fabro"` string (e.g.
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher.py`,
`…_otel_overlay.py`, `…_dual_cred.py`,
`tests/integration/test_worker_credential_projection_scenarios18_19.py`)
construct their **own** temp fixtures and are **unaffected** by the
relocation. The Codex structural gate
`dev-tooling/checks/codex_plugin_structure.py` does not enumerate
`.fabro/`; consider whether a new structural assertion should require the
packaged `.fabro/` payload (so a future drop of it fails CI).

### 2. Switch the resolvers off `parents[4]` to a plugin-root anchor

Affects `_workflow_toml` (`dispatcher.py:2024`) and
`_candidate_dispatcher_bin` (`dispatcher.py:1004`). The existing
`--workflow <path>` override (arg declared at `dispatcher.py:2194`,
`default=None`; honored at `dispatcher.py:2025-2026`) is the ready seam
and stays as the explicit escape hatch.

**REFINEMENT — anchor on `parents[3]`, not the env var alone.** The prior
design said "a `${CLAUDE_PLUGIN_ROOT}`-anchored path with a source-repo
fallback for `--plugin-dir .`". Two facts sharpen this:

- `${CLAUDE_PLUGIN_ROOT}` is an env var the Claude runtime sets for a
  **skill** invocation, but the dispatcher runs as a **bare host-side
  subprocess** (`python3 …/bin/dispatcher.py`, launched by
  `real-work-dispatch.sh`), so `CLAUDE_PLUGIN_ROOT` may **not** be
  exported into that process. The implementer MUST verify whether it is;
  do not assume it.
- The dispatcher module is at
  `<plugin-root>/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py`
  in **both** layouts, so **`parents[3]` IS the plugin root** in source
  (`.claude-plugin/`) AND in the flattened cache (`${CLAUDE_PLUGIN_ROOT}`).
  This is a robust, env-var-free anchor.

Recommended resolution order (capture, implementer confirms):
`--workflow` override → `$CLAUDE_PLUGIN_ROOT` env when present → else
`__file__`-relative `parents[3]` (the plugin root in both layouts). Then:

- `_workflow_toml` → `<plugin-root> / ".fabro" / "workflows" /
  "implement-work-item" / "workflow.toml"`.
- `_candidate_dispatcher_bin` → `<plugin-root> / "scripts" / "bin" /
  "dispatcher.py"` (drop the now-wrong `.claude-plugin` segment; it does
  not exist in the cache).

This single anchor change removes BOTH the over-climb and the missing
`.fabro/`, and needs no `CLAUDE_PLUGIN_ROOT` export.

**REFINEMENT — #1 and #2 MUST land in ONE atomic PR.** The `.fabro/`
relocation (#1) and the resolver re-anchor (#2) are a single indivisible
slice: any intermediate `master` state where the resolver and the
workflow location **disagree** — resolver re-anchored to `parents[3]`
while `.fabro/` is still at the repo root, or `.fabro/` moved into
`.claude-plugin/` while the resolver still walks `parents[4]` — breaks the
**source-mode factory the fleet runs today**. They cannot be split across
PRs; the slice is correct only as the atomic pair.

### 3. Point the factory at the enabled plugin, not a source clone

`orchestrator-image/real-work-dispatch.sh` clones the orchestrator
("Clone A", `DISPATCHER_CLONE`) and runs
`$DISPATCHER_CLONE/.claude-plugin/scripts/bin/dispatcher.py`
(`:473`). Change the dispatch to run from the **enabled plugin's
installed cache** (`${CLAUDE_PLUGIN_ROOT}/scripts/bin/dispatcher.py` —
note: flattened, **no** `.claude-plugin/` segment) instead of
git-cloning the orchestrator.

**KEEP** the dispatch-TARGET host clone (`TARGET_CLONE`) and Fabro's
in-sandbox target clone — those are legitimate (they are the **target**,
not the orchestrator). Sibling host scripts share the clone-A pattern and
must be reconciled or scoped: `tier2-dispatch-proof.sh:233`,
`acceptance-live-golden-master.sh:433/226`, and the operator hint in
`orchestrator-entrypoint.sh:179`.

**Flag for implementer — the in-container `uv sync`.**
`real-work-dispatch.sh` `uv sync`s the freshly-cloned orchestrator tree
so its Python deps resolve. A flattened plugin cache ships **no**
`pyproject.toml` / `uv.lock` / `.python-version`, so there is nothing to
`uv sync`; the dispatcher must run on **stdlib + `_vendor/` alone** (the
`_bootstrap.py` `sys.path` insert is what makes this work — see change
#5). Drop / guard the `uv sync` step when running from the cache, and
confirm the dispatcher has no third-party import that is not vendored.

### 4. Guard the post-merge self-update canary + fleet-manifest projection

`_self_update_after_merge` (`dispatcher.py:1016`) → `_self_update`
(`:1072`) stages and CANARIES a self-merge before promoting it; it
assumes a **writable git checkout** it can `git pull` (the
`_candidate_dispatcher_bin` canary target). A **read-only plugin cache**
has no such checkout.

**DRIFT — it is ALREADY fail-open.** The whole body is wrapped in a broad
supervisor that journals `self-update-error` and **swallows** any
exception (`dispatcher.py:1048-1069`; the load-bearing `0jxs` operability
invariant). So a read-only cache would **not crash** today — but the
canary becomes meaningless / wasteful there. The fix is to make it an
**explicit no-op** (a clean `self-update-skipped` journal reason for "no
writable orchestrator checkout") rather than relying on the fail-open
swallow to mask a never-applicable code path.

The fleet-manifest sibling-clone projection — `_resolve_sibling_clones`
(called `dispatcher.py:1777`) and `_fetch_fleet_manifest_text`
(`dispatcher.py:1809`, a host-side `gh api` read of
`.livespec-fleet-manifest.jsonc` from livespec master) — must be made
**optional / empty** for a non-fleet adopter (no fleet manifest, no
sibling clones to project). Render an empty `siblings` cleanly rather
than refusing the dispatch.

### 5. Vendor `typing_extensions`; no sandbox change

**CORRECTED by `research/02-verification.md` VP3 — the prior "no
dependency change" claim was FALSIFIED.** The host-side dispatcher's
imports are *almost* satisfied from the flattened payload: `_bootstrap.py`
(`scripts/bin/_bootstrap.py`) inserts `scripts/` and `scripts/_vendor/`
onto `sys.path`, and `_vendor/` carries `livespec_runtime/` and
`livespec_spec_clauses.py`. But the dispatcher's import path reaches
**exactly one** unvendored third-party module — `typing_extensions` —
from two sites:

- `scripts/_vendor/livespec_runtime/cross_repo/resolve.py:38`
  (`assert_never`, via `dispatcher.py:149`), and
- `commands/_otel_receive.py:70` (`override`, via `dispatcher.py:241`).

A clean `python3 -S` probe (only `scripts/` + `_vendor/` on the path)
fails `ModuleNotFoundError: typing_extensions`. A stdlib swap is unsafe:
the target is Python **3.10.16**, where `assert_never` is 3.11+ and
`override` is 3.12+. It is masked today only because the orchestrator
image apt-installs `python3-typing-extensions` (`Dockerfile:41`) — the gap
is precisely the flattened-cache adopter host.

**Fix:** vendor `typing_extensions` into `scripts/_vendor/` with a
`NOTICES.md` entry; keep the vendored `livespec_runtime` **unmodified**
(its top-level `typing_extensions` import resolves once `_vendor/` is on
`sys.path`). The Fabro sandbox image stays untouched. This is a **PREREQ
slice**, not a no-op — see `research/02-verification.md` VP3 and the
`uv sync` note under change #3.

### 6. Codify the contract

Add a clause to the orchestrator's `SPECIFICATION/contracts.md` stating
that the Fabro workflow **ships in the plugin payload** and the
dispatcher resolves it via the **plugin root**
(`${CLAUDE_PLUGIN_ROOT}` / `__file__`-relative plugin root), so
**fleet == adopter** consumption is the documented contract (enable the
plugin; no orchestrator-source clone). Candidate homes (verified H2s in
`SPECIFICATION/contracts.md`): near `## Dispatch-time baseline conformance
gate` (line 882) or `## Dispatcher admission, WIP cap, and post-merge
acceptance` (line 916); a fresh H2 (e.g. "Self-contained plugin dispatch")
is also reasonable. Any new/renamed `## ` heading co-edits
`tests/heading-coverage.json` per the revise discipline.

---

## Verdict

**ACHIEVABLE-WITH-WORK; no hard architectural blocker.** The Fabro
sandbox already needs nothing from the orchestrator source; the
absolute-graph overlay already decouples the workflow from a repo-root
location; `parents[3]` already names the plugin root in both layouts. The
work is host-side packaging (#1, #3), path-resolution (#2), the
`typing_extensions` vendoring prereq (#5, per `research/02-verification.md`
VP3), defensive guards for the read-only-cache world (#4), and the
contract clause (#6).

**Follow-up acceptance gap (VP4 residual).** After #1–#5 land, the
source-mount golden-master acceptance still proves **only** the
source-mount dispatch path — **not** the enabled-plugin / flattened-cache
path. A separate follow-up acceptance work-item MUST migrate or extend the
golden master to end-to-end exercise "fleet == adopter" dispatch **from
the installed cache**, or the very path this thread makes correct stays
unexercised by CI. See `research/02-verification.md` VP4.

## Open verification points for the implementer (NOW ANSWERED)

> All four are resolved in `research/02-verification.md` (verified against
> `01f2493`). VP1, VP2, VP4 **confirmed** the design; VP3 **corrected** it
> (change #5 — `typing_extensions` must be vendored). Retained below for
> the question→answer trail.

1. Does Fabro accept a `workflow.toml` whose `.fabro/` is **not** at the
   invocation repo root, given the absolute-graph overlay? (change #1)
2. Is `CLAUDE_PLUGIN_ROOT` exported into the host-side dispatcher
   subprocess, or must the resolver fall back to `__file__`-relative
   `parents[3]`? (change #2)
3. Can the dispatcher run with **no** `uv sync` (stdlib + `_vendor/`
   only) from the flattened cache — any non-vendored third-party import?
   (changes #3, #5)
4. Which sibling host scripts (`tier2-dispatch-proof.sh`,
   `acceptance-live-golden-master.sh`, `orchestrator-entrypoint.sh`) must
   move off the clone-A pattern vs. stay source-mode for golden-master
   acceptance? (change #3)

## Out of scope (related, tracked elsewhere)

The `templates/impl-plugin` → `orchestrator-plugin` rename is filed as
`livespec-m0xu` in the CORE tenant — **not** part of this thread.

## Verified-symbol index (quick reference)

| Symbol / path | Location | Role |
|---|---|---|
| `_workflow_toml` | `commands/dispatcher.py:2024` | resolves `workflow.toml` via `parents[4]` + repo-root `.fabro/` (CHANGE #2) |
| `_candidate_dispatcher_bin` | `commands/dispatcher.py:1004` | canary target via `parents[4]` + `.claude-plugin/scripts/bin/` (CHANGE #2) |
| `--workflow` override | `commands/dispatcher.py:2194` (decl), `:2025` (honored) | explicit escape seam (kept) |
| `render_run_config_overlay` | `commands/_dispatcher_plan.py:788`; call `dispatcher.py:1788` | rewrites graph path to absolute (`:856-861`) |
| `_self_update_after_merge` / `_self_update` | `commands/dispatcher.py:1016` / `:1072` | post-merge canary; fail-open (`:1048-1069`) (CHANGE #4) |
| `_resolve_sibling_clones` / `_fetch_fleet_manifest_text` | `dispatcher.py:1777` / `:1809` | fleet-manifest sibling projection (CHANGE #4) |
| `_bootstrap.py` | `scripts/bin/_bootstrap.py` | `sys.path` insert of `scripts/` + `_vendor/` (CHANGE #5) |
| `_vendor/` | `scripts/_vendor/{livespec_runtime,livespec_spec_clauses.py}` | vendored runtime (CHANGE #5) |
| Clone-A dispatch | `orchestrator-image/real-work-dispatch.sh:473` | runs orchestrator clone's `bin/dispatcher.py` (CHANGE #3) |
| Repo-root `.fabro/` payload | `.fabro/workflows/implement-work-item/{workflow.toml,workflow.fabro,prompts/*.md}` | ships outside the payload today (CHANGE #1) |
| `.fabro/` integration tests | `tests/integration/test_workflow_dot_non_convergence_scenario14.py:33`, `test_workflow_acp_adapter_parameterized.py:19-20` | bind repo-root `.fabro/` (CHANGE #1) |
| `contracts.md` H2 homes | `SPECIFICATION/contracts.md:882`, `:916` | clause #6 candidate sections |
