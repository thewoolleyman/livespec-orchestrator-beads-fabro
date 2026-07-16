# rop-sweep-consumer-cleanup — bring this repo's error handling onto the ROP railway

**Part of the `rop-sweep-*` coordinated set (do these ASAP, together).** Sibling
plans, findable fleet-wide via `plan/rop-sweep-*`:
- **`rop-sweep-library-checks`** (in `livespec-dev-tooling`) — makes the 6
  scope-hardcoded checks config-driven and adds a drift-guardrail check. **This
  plan's Phase 3 depends on it.**
- **`rop-sweep-fleet-policy`** (in `livespec` core) — fleet enforcement audit, the
  Ruff `BLE` policy, and the scaffold-template fix that prevents this drift.

**Independent side track. Not started — a drafted plan for a fresh session (or a
factory dispatch).** Authored 2026-07-16 from a read-only investigation.

> **Notation.** A check is **DORMANT** (runs but walks a nonexistent tree → scans
> zero files → exits 0, enforcing nothing), **WARN-only** (detects real
> violations but classifies them advisory → exits 0), **HARD-FAIL** (detects and
> blocks), or **N/A** (targets a code shape this repo's layout lacks).
> "Re-point" = change a path in `pyproject.toml`'s `[tool.livespec_dev_tooling]`
> block from the dead `.claude-plugin/scripts/livespec/…` target to this repo's
> real package.

---

## What this plan is (and what it is not)

This is **repo-local catch-up**, not a fleet-wide reform. The fleet audit
(recorded in `rop-sweep-fleet-policy`) found that **this repo is the drifted
outlier**:

| Repo | `except Exception` files | `source_trees` config | `returns` vendored |
| --- | --- | --- | --- |
| `livespec` (core) | 0 | correct (own pkg) | yes, used |
| `livespec-orchestrator-git-jsonl` | 0 | ✓ points at own pkg | no (clean by lighter convention) |
| **`livespec-orchestrator-beads-fabro` (this)** | **10 files / 13 sites** | **✗ points at core's `livespec`** | **no** |

The sibling `git-jsonl` is the model: `source_trees` is a *per-repo* key and it
already re-points at its own package. This repo copied core's layout at scaffold
time and never re-pointed, so its Railway-Oriented-Programming (ROP) checks went
dormant and 13 blind-except bulkheads accumulated unchecked. The job here is to
catch up to what core and git-jsonl already do.

---

## The rule (this repo must satisfy it; the fleet already mandates it)

The discipline is fleet-universal, written in
`livespec/SPECIFICATION/constraints.md` ("Result-track for expected errors;
raised exceptions for unexpected … ROP-style composition"). Restated for this
repo:

1. **No `try/except` in product code; never bubble an exception as control flow.**
   Expected failures ride the Result railway (`returns.Result` / `IOResult`, with
   `.map` / `.bind` / `.alt` / `.lash`). Genuine bugs raise built-ins and
   propagate to the outermost supervisor `main()` — the single sanctioned catch.
2. **Broadly catching `Exception` (or bare `except:`) is mechanically banned** and
   must fail lint, not merely be discouraged.
3. **Observability is a `.map(tap(effect))` pass-through step, never a bulkhead.**
   The value rides through unchanged; you never hand-write `Success(...)`. If the
   effect throws an **unexpected** error (full disk, bad path), it propagates —
   "the call can throw" is never itself a reason to catch, because everything can
   throw. The railway (`Result` / a **narrowed** `@impure_safe(exceptions=(…))` /
   `.lash`) is used only for a specific, enumerated failure this path has
   *deliberately chosen to tolerate*, never a blanket guard. A critical downstream
   step is protected from an observability failure by **ordering** (commit the
   critical state before the tap), not by catching.

---

## Root cause (code-verified)

`pyproject.toml`'s `[tool.livespec_dev_tooling]` block points every source-tree
key at `.claude-plugin/scripts/livespec/…` — a path that does not exist here (the
real package is `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/`, 127
tracked `.py`). The keys are *present but dead*, so the checks' "role key absent →
no-op" guard does not trip; they walk a nonexistent tree, find nothing, and exit
0 — silent under-coverage. See `rop-sweep-fleet-policy` for why this class of
drift is possible (the scaffold template) and `rop-sweep-library-checks` for the
subset that pyproject cannot reach.

---

## The missing prerequisite: vendor `returns` (the `.map` primitive)

You cannot ban `try/except` without giving the code a railway. `returns` — with
`.map` (Rust's `Result::map`), `.bind`, `.alt`, `.lash`, and `returns.functions.tap`
plus the `@safe`/`@impure_safe` boundary decorators — is vendored and used in core
(`/data/projects/livespec/.claude-plugin/scripts/_vendor/returns/result.py:73`;
`livespec/.../commands/_seed_railway_writes.py`), and vendoring satisfies the
no-PyPI-runtime-deps rule (`SPECIFICATION/constraints.md:34-37`). **Decision:
vendor core's copy; do not hand-roll.**

---

## The observability pattern (the specific guidance)

The question is not "can the effect fail?" (everything can) but "is this a failure
I have *deliberately anticipated and chosen to tolerate*?"

**Default — `.map(tap(effect))`**, for infallible and fallible-I/O effects alike:

```python
result.map(tap(lambda v: emit_span(v)))   # value rides through unchanged
```

An **unexpected** error inside the effect propagates to the supervisor like any
bug. We do not wrap it "just in case" — that is the bulkhead we are removing.

**Rare exception — a specific, named, EXPECTED failure this path tolerates** rides
the railway via a **narrowed** lift only:

```python
@impure_safe(exceptions=(ConnectionError,))   # ONLY the anticipated error, not all Exception
def post_span(v) -> IOResult[T, OSError]:
    collector.post(v); return v

pipeline.bind(post_span).lash(lambda _err: IOResult.from_value(value))
```

**Protecting a critical step is ordering, not catching.** Worked before/after —
the emitter that started this thread. Today `_dispatcher_review_gate.py:96-103` is
a `try: _emit(...) except Exception: _append_review_gate_skip(...)` bulkhead, and
its call site (`_dispatcher_loop.py:214`) emits telemetry **before**
`post_run_dispositions` (`:154`) — which is what let a telemetry throw skip a
merged item's disposition. Fix: move the disposition **ahead** of a plain
`.map(tap(emit))` step and delete the `try/except`. An unexpected write failure
then surfaces instead of hiding into a `review-gate-telemetry-skipped` breadcrumb,
and cannot skip the disposition (it already committed).

---

## This repo's mis-scope inventory (config-fixable)

Real package = `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/**` (127
`.py`); other first-party trees: `bin/` (13), `dev-tooling/checks/` (5),
`.claude/hooks/` (2). Excluded by the target rule: `.claude/skills/**`.

**Tier 1 — DORMANT, armed by re-pointing:** `no_except_outside_io` (the core ROP
rule — bans `try/except` outside `io/` + supervisor `main()`; via `source_trees` +
`io_trees` + `commands_trees`), `no_raise_outside_io`,
`check_coverage_incremental` + `commit_pairs_source_and_test` (via
`source_tree_prefixes`).

**Tier 2 — WARN-only, flipped to HARD-FAIL by re-pointing the severity classifier
(`source_trees`/`covered_trees`):** `assert_never_exhaustiveness`,
`no_inheritance`, `private_calls`, `keyword_only_args`, `match_keyword_only`,
`global_writes`, `all_declared`, `no_write_direct`, `no_lloc_soft_warnings`.

**N/A here:** `public_api_result_typed`, `newtype_domain_primitives` — this repo
has no pure `parse`/`validate` layer or `schemas/dataclasses` tree to target.
Decide whether to introduce one or accept N/A (recommend accept + document).

**Not config-fixable — see `rop-sweep-library-checks`:** the 6 checks whose scope
is hardcoded in `livespec-dev-tooling` (`supervisor_discipline`, `main_guard`,
`rop_pipeline_shape`, `tests_mirror_pairing`, `pbt_coverage_pure_modules`,
`check_mutation`). This repo cannot fix them; the library plan does.

**Already correct here — do not touch:** `file_lloc` (via `file_lloc_hard_gate =
true`), `comment_line_anchors`, `no_fmt_directives`, `red_green_replay`,
`claude_md_coverage`, `no_direct_destructive_cli`, `wrapper_shape`,
`tests_no_subprocess_spawn`, the 5 repo-local `dev-tooling/checks/*.py`, Ruff, and
Pyright.

**Ruff / skills edge:** Ruff covers the real package but does **not** exclude
`.claude/skills/**` (`pyproject.toml:84`) — add it to `extend-exclude`. Ruff also
currently excludes `.claude/hooks/**`; per the "everything except skills" rule,
consider bringing the 2 hook files under Ruff/Pyright (the git-universe checks
already cover them). The fleet-wide `BLE` policy is in `rop-sweep-fleet-policy`;
this repo enabling `"BLE"` locally is part of Phase 1 below.

---

## The plan (phased — ordering is load-bearing)

**Phase 0 — provide the primitive.** Vendor `returns` from core into
`.claude-plugin/scripts/_vendor/returns/` + `.vendor.jsonc` manifest entry;
confirm `vendor_manifest` + Pyright accept it. No behavior change.

**Phase 1 — migrate the 13 bulkheads + arm the narrow ban.** Convert the 13
`except Exception` sites per the observability pattern (review-gate emitter first).
Expect most to become a plain `.map(tap(...))` with critical work reordered ahead
of the tap; only a site with a genuinely *named, expected* failure keeps a
narrowed lift. Add `"BLE"` to Ruff `select` and `.claude/skills/**` to
`extend-exclude`. BLE goes green because the blanket catches are gone.

**Phase 2 — re-scope the config-driven checks.** Re-point the dead pyproject keys
(`source_trees`, `io_trees`, `commands_trees`, `supervisor_entry_files`,
`covered_trees`, `source_tree_prefixes`, first `mirror_pairings` entry) to the
real package + `bin/` + `dev-tooling/` + `.claude/hooks/` — copy git-jsonl's
correctly-pointed block as the model. This arms the 4 Tier-1 dormant checks and
flips the 9 Tier-2 WARN-only checks to hard-fail against 127 previously-unenforced
files at once. Harvest the current WARN output first for a violation inventory,
fix per-check/per-tree, then land the flip green. Mind the empty-baseline-flip
warning (`pyproject.toml:248-261`) and the TOML-ordering constraint (bare keys
above `[[mirror_pairings]]`).

**Phase 3 — pick up the 6 library-hardcoded checks** once
`rop-sweep-library-checks` lands them config-driven: bump this repo's
`livespec-dev-tooling` pin and re-point their (now config-driven) scope keys.

---

## Decisions for the implementing session

1. **Vendor `returns` (recommended) vs hand-roll a minimal `Result`.** Recommend
   vendoring core's copy.
2. **Re-point staged (recommended) vs big-bang.** Recommend staged, using the
   pre-flip WARN output.
3. **N/A checks: introduce a pure layer vs accept N/A (recommended).** This repo
   has no pure-computation split; recommend documenting N/A and revisiting later.
4. **`.claude/hooks/**` coverage:** bring the 2 hook files under Ruff/Pyright
   (per the target rule) unless there's a deliberate exemption to document.

---

## Blast radius & risks

- **Phase 2 is a large, deliberate red** (127 files, never enforced). Stage it;
  do not big-bang.
- **Empty-baseline-flip trap** (`pyproject.toml:248-261`): keep every declared key
  present when re-pointing.
- **Phase 3 depends on `rop-sweep-library-checks`** landing first; do not try to
  fix the 6 hardcoded checks from this repo.

---

## First steps

1. Baseline `just check`; grep the Tier-2 WARN output for the violation inventory.
2. Phase 0: vendor `returns` from `/data/projects/livespec/.claude-plugin/scripts/
   _vendor/returns/`.
3. Phase 1: migrate `_dispatcher_review_gate.py` (reorder disposition ahead of a
   plain `.map(tap(emit))`; delete the `try/except`), then the other 12 bulkheads;
   enable Ruff `"BLE"` + `.claude/skills/**` exclude; confirm green.
4. Phase 2: re-point the pyproject keys (copy git-jsonl's block as the model); fix
   per-check; land green.
5. Phase 3: after `rop-sweep-library-checks`, bump the pin + re-point the 6.
6. Formalize (`/plan rop-sweep-consumer-cleanup`) + anchor a ledger epic if driving
   to completion.

---

## Evidence / references (file:line)

- **The 13 bulkheads (lint-clean because `BLE` is off):**
  `_dispatcher_review_gate.py:98`, `_dispatcher_reflector_oob.py:253`,
  `_dispatcher_notify.py:249`, `_dispatcher_self_update.py:275`,
  `_dispatcher_cost_gate.py:77,98,203`, `_otel_receive.py:254,324`,
  `_otel_enrich.py:272`, `_dispatcher_calibration_emit.py:84`,
  `_dispatcher_reflection.py:324`, `acceptance.py:187`.
- **Config resolution:** `livespec_dev_tooling/config.py:473-533` (`load_config`),
  `:796-819` (`resolve_check_universe`), `:569,638` (`.claude/skills` exemption),
  `:615-627` (`.claude/hooks` kept in scope).
- **The dead pyproject keys:** `pyproject.toml:264-303`; empty-baseline warning
  `:248-261`; Ruff `:87-117` (no `BLE`), `:84` (no `skills` exclude).
- **The model to copy:** git-jsonl's `pyproject.toml` `source_trees =
  [".claude-plugin/scripts/livespec_orchestrator_git_jsonl"]`.
- **`returns` in core:** `/data/projects/livespec/.claude-plugin/scripts/_vendor/
  returns/result.py:73` (`.map`), `functions.py` (`tap`); used in
  `livespec/.../commands/_seed_railway_writes.py`, `templates.py:70`.
