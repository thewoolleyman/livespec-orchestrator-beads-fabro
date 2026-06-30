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

Clause #6 (the contract) has **already LANDED** on `master` (commit
`b84cc98`, v021). What remains is the **implementation** of #1–#5, groomed
into the dependency-ordered slices below and driven through the normal
worktree → PR → rebase-merge flow.

**Recommended slice / dependency order:**

- **Slice 1 (ATOMIC #1 + #2).** Relocate
  `.fabro/workflows/implement-work-item/` (`workflow.toml` +
  `workflow.fabro` + `prompts/`, **as a unit**) →
  `.claude-plugin/.fabro/…` **and** re-anchor both resolvers
  (`_workflow_toml`, `_candidate_dispatcher_bin`) to the plugin root
  (`__file__`-relative `parents[3]`; optional `$CLAUDE_PLUGIN_ROOT`
  override; **keep** the `--workflow` seam), dropping the now-wrong
  `.claude-plugin` segment in `_candidate_dispatcher_bin`; update the two
  integration tests (`test_workflow_dot_non_convergence_scenario14.py`,
  `test_workflow_acp_adapter_parameterized.py`). **#1 and #2 MUST land in
  ONE PR** — any intermediate `master` where the resolver and the workflow
  location disagree breaks the source-mode factory the fleet runs today.
- **Slice 2 (PREREQ, parallel with Slice 1).** Vendor `typing_extensions`
  into `scripts/_vendor/` + `NOTICES.md` entry + a clean `python3 -S`
  import-regression test (only `scripts/` + `_vendor/` on the path). Keep
  `livespec_runtime` unmodified.
- **Slice 3 (#4, after Slice 1).** Read-only-cache guards: make the
  post-merge self-update an explicit `self-update-skipped` no-op when
  there is no writable orchestrator checkout, and render an empty
  fleet-manifest sibling projection for non-fleet adopters. (Shares
  `dispatcher.py` with Slice 1 — sequence after it.)
- **Slice 4 (#3, after Slices 1 + 2).** Retire clone-A in
  `real-work-dispatch.sh` (run the dispatcher from the enabled plugin
  cache), drop/guard the in-container `uv sync`, and update the cosmetic
  `orchestrator-entrypoint.sh:179` hint. KEEP the dispatch-TARGET host
  clone and Fabro's in-sandbox target clone. Leave `tier2-dispatch-proof.sh`
  and `acceptance-live-golden-master.sh` source-mode.
- **Slice 5 (#6) — DONE.** The `## Self-contained plugin dispatch`
  contract clause LANDED on `master` (commit `b84cc98`, v021). The
  parallel branch `spec-self-contained-plugin-dispatch` (a divergent
  re-take of the same v021 work, branched from `01f2493` before the clause
  landed) is **superseded** — abandon/clean it up rather than merge it.
- **Slice 6 (FOLLOW-UP, VP4 residual).** Migrate/extend the golden-master
  acceptance to prove the **enabled-plugin / flattened-cache** dispatch
  path — the current golden master proves only the source-mount path. File
  as a paired acceptance work-item.

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
