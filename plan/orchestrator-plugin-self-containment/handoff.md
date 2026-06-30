# Handoff — orchestrator-plugin-self-containment (livespec-orchestrator-beads-fabro)

**Thread:** `plan/orchestrator-plugin-self-containment/`
**Repo:** `/data/projects/livespec-orchestrator-beads-fabro`
**Scope:** markdown/docs-only planning thread (no product `.py`).

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

## Read-first chain (open these, in order)

1. **`research/01-design.md`** (this thread) — the full design, the
   verified change set, the per-change drift/refinement notes, the
   verified-symbol index, and the four open verification points for the
   implementer. This is the authoritative design of record.
2. The live code surfaces it cites, in
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
3. `SPECIFICATION/contracts.md` — H2 homes for clause #6 (lines `:882`,
   `:916`).

## The change set (full detail in `research/01-design.md`)

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
5. **No dependency change, no sandbox change** (`_bootstrap.py` +
   `_vendor/` + stdlib satisfy the host-side dispatcher imports from the
   flattened payload).
6. **Codify the contract** in `SPECIFICATION/contracts.md`: the Fabro
   workflow ships in the plugin payload; the dispatcher resolves it via
   the plugin root — making fleet == adopter consumption the documented
   contract.

## NEXT ACTION

Drive the change set through the orchestrator's own lifecycle:

1. **`/livespec:propose-change`** against this repo's `SPECIFICATION/` for
   **clause #6** (the Fabro workflow ships in the plugin payload; the
   dispatcher resolves it via the plugin root; fleet == adopter
   consumption). Then **`/livespec:revise`** to ratify it (co-edit
   `tests/heading-coverage.json` if it adds/renames a `## ` heading).
2. **`groom`** the change set into ledger work-items for **#1–#5**
   (slices: packaging move + test fixups; resolver re-anchor; factory
   shell off the source clone; self-update/fleet-manifest guards). Layer
   dependencies so the resolver re-anchor (#2) and the packaging move (#1)
   land before the factory shell change (#3) is validated end-to-end.
3. **implement** each ready slice through the normal worktree → PR →
   rebase-merge flow.

**Ledger anchoring (why no epic yet).** The formal ledger epic + the
work-items for #1–#5 should be **anchored once the orchestrator
plugin/ledger machinery is refreshed** — the capture path (`groom` /
`capture-work-item`) is currently affected by the **same staleness this
thread fixes**, so filing now would be filing through a broken path.
**Until then, this markdown thread is the durable record**; the design in
`research/01-design.md` is complete enough to anchor the epic and groom
the slices the moment the machinery is healthy.

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
