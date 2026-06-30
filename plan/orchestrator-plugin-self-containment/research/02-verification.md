# Verification — orchestrator plugin self-containment

**Thread:** `plan/orchestrator-plugin-self-containment/`
**Repo:** `livespec-orchestrator-beads-fabro`
**Verified against:** `01f2493` (the commit that opened this thread; the
merge-base of `master` and the in-flight contract branch).
**Mode:** read-only verification pass. No code was mutated; every claim
below was read against the live tree at `01f2493`.

This document records the verification of the four **open verification
points** that `research/01-design.md` §"Open verification points for the
implementer" left for the implementer. One of the four (VP3) **corrected**
the design: the host-side dispatcher is **not** dependency-clean on
stdlib + `_vendor/` alone — it has exactly one unvendored third-party
import that must be vendored. The other three confirmed the design as
written, with sharpened detail captured below.

---

## VP1 — Does Fabro accept a `workflow.toml` whose `.fabro/` is NOT at the invocation repo root?

**YES — safe as designed.** Fabro never reads a `.fabro/` file at the
invocation repo root at dispatch time; it already runs from a `/tmp`
overlay run-config carrying an **absolute** graph path. Relocating the
workflow into the packaged payload therefore does not change what Fabro
sees, provided the workflow is relocated **as a unit**.

The chain (all in
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/`):

1. `_workflow_toml` (`commands/dispatcher.py` ~`:2024`) resolves the
   `workflow.toml` path.
2. `_materialize_overlay` (`commands/dispatcher.py` ~`:1201`) materializes
   a per-dispatch overlay run-config in `/tmp`
   (`fabro-run-config-<id>.toml`).
3. `render_run_config_overlay` (`commands/_dispatcher_plan.py` ~`:788`)
   absolutizes the graph path:
   `resolved_graph = graph_path if graph_path.is_absolute() else
   workflow_dir / graph_path` (~`:856-861`), where
   `workflow_dir = committed.parent.resolve()` (passed from
   `dispatcher.py` ~`:1790`). The absolute graph path is substituted into
   the materialized run-config.
4. The Fabro run executes with `cwd = plan.repo` — the dispatch **TARGET**
   repo (`commands/_dispatcher_io.py` ~`:218-220`), **never** the
   orchestrator. Fabro is never invoked with the orchestrator as its repo
   root, so it never looks for a `.fabro/` at the orchestrator root.
5. `workflow.fabro` uses relative `@prompts/...` references, which are
   resolved against the graph file's **own absolute path** — so the
   prompts must travel with the graph.

**Only requirement:** relocate `implement-work-item/` as a **UNIT** —
`workflow.toml` + `workflow.fabro` + `prompts/` together — so the
relative `@prompts/...` references continue to resolve against the moved
graph file. The absolute-overlay rewrite is exactly why a non-repo-root
`.fabro/` is tolerated; this is what the rewrite exists for.

---

## VP2 — Is `CLAUDE_PLUGIN_ROOT` exported into the host-side dispatcher subprocess?

**NO — `CLAUDE_PLUGIN_ROOT` is set nowhere; anchor on `__file__`-relative
`parents[3]`.** A repo-wide search found no shell script, entrypoint,
Dockerfile, or compose file that exports `CLAUDE_PLUGIN_ROOT`. The
dispatcher is launched **bare** — `orchestrator-image/real-work-dispatch.sh`
`exec`s `python3 …/bin/dispatcher.py` (~`:470-483`) with only `GH_TOKEN`
exported into the process environment. The resolver therefore **cannot**
rely on the env var being present.

`parents[3]` **is** the plugin root in **both** layouts, because the
dispatcher module sits at
`<plugin-root>/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py`:

| index | SOURCE (`.claude-plugin/`) | FLATTENED cache (`${CLAUDE_PLUGIN_ROOT}`) |
|---|---|---|
| `parents[3]` | `.claude-plugin/` (plugin root) | plugin root (cache) |
| `parents[4]` | repo root | **over-climbs** (parent of cache) |

So `parents[4]` over-climbs by one in the cache, which is the root cause
of the **E-3a** dispatch failure.

**Fix both resolvers** — `_workflow_toml` (~`:2024`) and
`_candidate_dispatcher_bin` (~`:1004`) — to anchor on `parents[3]`, and in
`_candidate_dispatcher_bin` **drop the now-wrong `.claude-plugin` path
segment** (~`:1013`): it does not exist in the flattened cache. **Keep**
the existing `--workflow <path>` override seam (~`:2025`) as the explicit
escape hatch. An optional `os.environ.get("CLAUDE_PLUGIN_ROOT")` Python
override (preferred when present, else fall back to `parents[3]`) is fine
— it is a plain `os.environ` read, **not** a manifest substitution token,
so the Codex structural gate
`dev-tooling/checks/codex_plugin_structure.py` does not flag it.

---

## VP3 — Can the dispatcher run on stdlib + `_vendor/` alone? **THE CORRECTION**

**NO — the design's change #5 ("no dependency change") is FALSIFIED.** The
host-side dispatcher has exactly **one** unvendored third-party import:
`typing_extensions`, reached on the dispatcher's own import path from two
sites:

- `.claude-plugin/scripts/_vendor/livespec_runtime/cross_repo/resolve.py:38`
  — `from typing_extensions import assert_never` (reached via
  `commands/dispatcher.py:149`).
- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_otel_receive.py:70`
  — `from typing_extensions import override` (reached via
  `commands/dispatcher.py:241`).

A clean `python3 -S` probe with **only** `scripts/` + `scripts/_vendor/`
on the path (i.e. simulating the flattened cache with no site-packages)
fails with `ModuleNotFoundError: No module named 'typing_extensions'`.

**A stdlib swap is unsafe.** The deployment target is Python **3.10.16**,
but `typing.assert_never` is **3.11+** and `typing.override` is **3.12+**
— so the symbols cannot be re-pointed at stdlib `typing` on the target
interpreter.

**Why it is masked today:** the orchestrator image apt-installs
`python3-typing-extensions` (`orchestrator-image/Dockerfile:41`), so the
import resolves inside the container. The gap is precisely the
**flattened-cache adopter host** — an adopter who merely enables the
plugin has no apt layer providing `typing_extensions`, so the dispatcher
would fail to import. This is the exact "fleet == adopter" parity the
thread is chartered to close.

**Fix:** vendor `typing_extensions` into `.claude-plugin/scripts/_vendor/`
with a `NOTICES.md` entry, so it travels in the flattened payload. Keep
the vendored `livespec_runtime` **unmodified** (it imports
`typing_extensions` as a top-level module, which is satisfied once
`_vendor/` is on `sys.path` — `_bootstrap.py` already inserts it). This is
a **PREREQ slice**, not a no-op.

---

## VP4 — Which sibling host scripts move off the clone-A pattern?

**Only `real-work-dispatch.sh` moves off the orchestrator-source clone
("clone A"); the two acceptance harnesses STAY source-mode.**

- `orchestrator-image/real-work-dispatch.sh` — `provision_clones`
  (~`:432`) clones the orchestrator (`DISPATCHER_REPO` →
  `DISPATCHER_CLONE`); `sync_dispatcher_deps` then runs `uv sync`
  (~`:342-344`); the script `exec`s
  `$DISPATCHER_CLONE/.claude-plugin/scripts/bin/dispatcher.py` (~`:473`).
  **THIS CHANGES**: run the dispatcher from the **enabled plugin payload**
  (the installed cache, flattened — no `.claude-plugin/` segment), **drop
  clone A**, and **drop/guard the `uv sync`** (the flattened cache has no
  `pyproject.toml` / `uv.lock` / `.python-version` to sync, and after VP3
  the deps travel vendored).
- `orchestrator-image/tier2-dispatch-proof.sh` (bind-mounts the
  orchestrator self-target, ~`:233-244`) — **STAYS source-mode** (it
  proves dispatch against the bind-mounted source on purpose).
- `orchestrator-image/acceptance-live-golden-master.sh` (source-mounts the
  golden master, ~`:226`, ~`:430-444`) — **STAYS source-mode** (it is the
  source-mount golden-master acceptance).
- `orchestrator-image/orchestrator-entrypoint.sh:179` — a **cosmetic**
  printed operator hint naming the clone path; update the printed string
  only, no behavior change.

**RESIDUAL (follow-up acceptance gap).** The golden-master acceptance
proves **only** the source-mount dispatch path, **not** the
enabled-plugin / flattened-cache path. A paired acceptance work-item is
needed to end-to-end test "fleet == adopter" dispatch **from the installed
cache** — otherwise the very path this thread makes correct stays
unexercised by CI.

---

## Net effect on the design

| VP | Design claim | Verification outcome |
|---|---|---|
| VP1 | #1 relocation is safe given the absolute overlay | **Confirmed.** Relocate as a unit (toml + fabro + prompts). |
| VP2 | #2 `parents[3]` is the env-var-free anchor | **Confirmed.** `CLAUDE_PLUGIN_ROOT` is never exported; `parents[3]` is the anchor; drop the `.claude-plugin` segment in the bin resolver. |
| VP3 | #5 "no dependency change" | **CORRECTED.** One unvendored import (`typing_extensions`) MUST be vendored — a prereq slice. |
| VP4 | #3 which scripts move | **Confirmed + residual.** Only `real-work-dispatch.sh` moves; acceptance harnesses stay source-mode; a cache-path acceptance work-item is a follow-up. |
