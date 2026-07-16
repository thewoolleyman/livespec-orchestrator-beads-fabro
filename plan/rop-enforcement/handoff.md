# Plan handoff — mechanically enforce Railway-Oriented error handling, and fix every mis-scoped fleet check

**Independent side track. Not started — this is a drafted plan for a fresh
session (or a factory dispatch) to pick up and drive.** Authored 2026-07-16
from a read-only investigation (three subagents + direct verification).
Nothing here is implemented.

> **Notation used in this document.** A check is in one of four states against
> this repo's real product code:
> - **DORMANT** — the check runs but walks a directory that does not exist, so it
>   scans zero files and exits 0. It enforces nothing.
> - **WARN-only** — the check *detects* real violations (it sees the real files)
>   but classifies them as advisory warnings and exits 0 instead of 1. It reports
>   but does not block.
> - **HARD-FAIL** — the check detects real violations and exits non-zero, blocking
>   the commit/push/CI. This is the enforced state.
> - **N/A** — the rule targets a code shape this repo's layout does not contain.
>
> "Re-point" means: change a path value in the `[tool.livespec_dev_tooling]`
> block of `pyproject.toml` from the dead `.claude-plugin/scripts/livespec/…`
> target to this repo's real package.

---

## The rule to enforce (normative statement of intent)

1. **Product code contains no `try/except` and never bubbles an exception as
   control flow.** Expected failures ride the Result railway (`returns.Result` /
   `returns.IOResult`, with `.map` / `.bind` / `.alt` / `.lash`). Genuine bugs
   raise built-in exceptions and propagate to the outermost supervisor `main()`
   — the single sanctioned catch site.
2. **Broadly catching `Exception` (or a bare `except:`) is mechanically banned.**
   Catching the exception superclass is exactly the anti-pattern that swallows
   genuine bugs into silent breadcrumbs; it must fail lint, not merely be
   discouraged.
3. **Observability and other side-effects are pass-through steps in the ROP
   chain, never bulkheads.** Infallible observability is a `.map(tap(effect))`
   step (the value rides through unchanged; you never hand-write `Success(...)` —
   the container re-wraps for you). Fallible-I/O observability lifts the boundary
   with `@impure_safe` and recovers its own expected failure back onto the value
   with `.lash`, so a telemetry I/O failure can never derail the main track and
   is never caught with `except`.
4. **Every mechanical rule applies to all first-party code except
   `.claude/skills/**`.** Today the rules under-cover: they are aimed at a
   package path that does not exist in this repo.

Rules 1–3 are the error-handling discipline this repo's own
`SPECIFICATION/constraints.md:31-33` already claims to follow ("Result-track for
expected errors; raised exceptions for unexpected … ROP-style composition of
expected errors at the supervisor boundary"). Today that claim is aspirational,
not enforced. This plan closes the gap between the stated constraint and the
actual code.

---

## Why this matters (the trigger)

A review of the dispatcher's review-gate telemetry emitter
(`_dispatcher_review_gate.py:96-103`) surfaced a `try / except Exception` that
swallows *any* error — including genuine bugs — into a quiet
`review-gate-telemetry-skipped` journal breadcrumb. That is the exact
bug-hiding pattern the "raised exceptions for unexpected" half of the discipline
exists to prevent.

Pulling that thread revealed the systemic cause: **this repo's own constraints
mandate Railway-Oriented Programming, it inherits the checks that would enforce
it, but those checks are pointed at a path that does not exist here — so the
code silently drifted to exception-based error handling, unchecked.** There are
**13** `except Exception` bulkheads in product code today, and all 13 pass lint
cleanly (see the inventory below).

---

## Root cause (code-verified)

`load_config` (`.venv/lib/python3.10/site-packages/livespec_dev_tooling/config.py:473-533`)
has two regimes:

- **No `[tool.livespec_dev_tooling]` block** → it falls back to the livespec-core
  historical layout (`_livespec_core_config`, `config.py:161-214`), where every
  source tree is `.claude-plugin/scripts/livespec/…`.
- **Block present** (this repo's case) → it starts from an empty baseline and
  uses only the keys the block declares; any omitted key stays empty.

This repo declares the block, and — to avoid an "empty-baseline flip" that would
have blanked out unrelated checks — it restated the **core** layout verbatim
(`pyproject.toml:264-303`). But this repo's real package is
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/` (127 tracked `.py`
files), **not** `.claude-plugin/scripts/livespec/` (0 files — the directory does
not exist). So every source-tree path in the block is a dead target.

The subtle failure mode: the checks have a "role key absent → log an info no-op →
exit 0" guard (e.g. `no_except_outside_io.py:87`). Because this repo *declares*
the keys (pointing them at the dead path) rather than omitting them, that guard
does **not** trip. The check proceeds to walk a nonexistent tree, finds zero
files, and exits 0 with zero findings — **silent** under-coverage, not a loud
skip.

Two regimes of checks exist, and they degrade differently:

- **Config-tree-walking checks** call `iter_py_files(root=cwd/tree)` over the
  declared trees. Pointed at the dead path, they scan nothing → **DORMANT**.
- **Git-universe checks** call `resolve_check_universe()` (`config.py:796-819`),
  which walks `git ls-files '*.py'` minus `_vendor/`, `tests/`, `templates/`,
  `@generated`, and `.claude/skills/` (`config.py:569,638`). These *do* see the
  real 127 files — but they consult the config trees only to decide
  **error-vs-warn severity**. Pointed at the dead path, the severity classifier
  never matches a real file, so every real violation is demoted to **WARN-only**.

---

## The missing prerequisite: the Result primitive (the `.map` question, answered)

You cannot ban `try/except` without first giving the code the railway to put
expected failures on. That railway is the `returns` library, and it already
exists in the fleet:

- **`returns.Result` has `.map`** — the direct equivalent of Rust's
  `Result::map` (map the success value, pass the failure track through
  untouched) — plus `.bind`, `.alt`, `.lash`, `.apply`, `.value_or`, `.unwrap`.
  Verified in the vendored copy at
  `/data/projects/livespec/.claude-plugin/scripts/_vendor/returns/result.py:73`
  (with the `Success`/`Failure` implementations at `:361`/`:424`).
- It ships the side-effect helpers this plan needs: `returns.functions.tap`
  (run an effect, return the argument unchanged) and the `@safe` / `@impure_safe`
  decorators that lift a raising function into a `Result` / `IOResult` **at the
  library boundary** — the one sanctioned place an exception becomes a value,
  with no hand-written `try/except`.
- **livespec-core runs on it** for real: `livespec/.claude-plugin/scripts/
  livespec/commands/_seed_railway_writes.py` builds
  `IOResult.from_value(seed_input).bind(...)` pipelines, and `templates.py:70`
  returns `Result[Path, TemplateResolutionFailure]`.
- It is **vendored** (115 pure-Python files) alongside `fastjsonschema`,
  `structlog`, `typing_extensions` — which is exactly how core satisfies the
  same "no PyPI runtime dependencies; vendor under `_vendor/`" constraint this
  repo carries (`SPECIFICATION/constraints.md:34-37`).

**This orchestrator repo simply never vendored or adopted it** — its `_vendor/`
holds only `livespec_runtime/`, `livespec_spec_clauses.py`, `typing_extensions.py`.
That absence is why its error handling degraded into raw `except Exception`.

**Decision: vendor core's existing `returns`; do not hand-roll.** Core already
carries and maintains it, and the dormant `public_api_result_typed` check already
expects the `returns` API (`Result`/`IOResult`/`@safe`/`@impure_safe`). A
hand-rolled minimal `Result` is the only alternative and is strictly worse
(reinventing a maintained library that a sibling repo already vendors), justified
only if avoiding the 115-file footprint were a hard requirement — it is not.

---

## The observability pattern (the specific guidance this plan mandates)

Two shapes, chosen by whether the side-effect can fail:

**Infallible observability** (increment an in-memory counter, append to a buffer,
format a string) — a `tap` inside a `.map`:

```python
result.map(tap(lambda v: metrics.incr("dispatch.ok")))   # value rides through unchanged
```

There is nothing to catch and nothing to hand-wrap. This is the literal "just
map" case.

**Fallible-I/O observability** (write a span file, POST to an OTLP endpoint — the
review-gate case, which does `mkdir` + `open("a").write(...)`, both of which
raise `OSError` on disk-full / permission / bad path) — lift the boundary, then
recover the expected failure back onto the value so it cannot derail the track:

```python
@impure_safe                       # the library performs the ONE sanctioned catch, not us
def emit_span(v) -> IOResult[T, EmitError]:
    spans_path.open("a").write(line)
    return v

pipeline.bind(emit_span).lash(lambda _err: IOResult.from_value(value))
#             ^ I/O on the railway         ^ expected emit failure collapses back to the value
```

The invariant, stated for the implementing session: an observability step's
**expected** failures ride the Result railway and are collapsed to the success
value — never an `except Exception`, never a change to the pipeline's outcome —
while a genuine **bug** in observability code still propagates (it is a bug; it
must surface). This is `bind`+`lash` rather than `map` only because a fallible
effect returns an `IOResult` instead of a bare value; the "no `try/except` in our
code" rule holds either way.

**Worked before/after** — the emitter that started this thread
(`_dispatcher_review_gate.py`): the current
`try: _emit(...) except Exception: _append_review_gate_skip(...)` bulkhead
(lines 96–103) becomes an `@impure_safe emit_span` bound into the dispatch
pipeline with a `.lash` that recovers to the dispatch outcome. The telemetry can
still fail softly (its failure is journaled on the error arm before the `.lash`),
but a bug inside it now surfaces instead of hiding, and the emission can never
skip the merged item's ledger disposition.

---

## The full mis-scope inventory (find-them-all)

Real package = `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/**`
(127 `.py`). Other first-party trees: `.claude-plugin/scripts/bin/` (13),
`dev-tooling/checks/` (5), `.claude/hooks/` (2). Excluded by the target rule:
`.claude/skills/**` (does not exist here yet).

### Tier 1 — DORMANT, fixable by re-pointing pyproject keys

| Check | Walks | Fix |
| --- | --- | --- |
| `no_except_outside_io` — **the core ROP rule**; bans all `try/except` outside `io/` + supervisor `main()` | `source_trees` (`no_except_outside_io.py:95`) | re-point `source_trees` + `io_trees` + `commands_trees` |
| `no_raise_outside_io` — bans `raise` outside `io/` + supervisor | `source_trees` (`no_raise_outside_io.py:99`) | same |
| `check_coverage_incremental` | `source_tree_prefixes` (`:275`) | re-point `source_tree_prefixes` + `mirror_pairings` |
| `commit_pairs_source_and_test` | `source_tree_prefixes` (`:139`) | re-point `source_tree_prefixes` |

### Tier 1 — DORMANT, but N/A (no code shape to point at)

This repo has no pure `parse/`/`validate/` layer and no `schemas/dataclasses/`
tree, so these rules have nothing to target. Decide per the "no-analog" decision
below — either introduce the shape or accept N/A.

| Check | Wants | Why N/A here |
| --- | --- | --- |
| `public_api_result_typed` — public fns return `Result`/`IOResult` or carry `@safe`/`@impure_safe` | `pure_trees` (`:128`) | no `parse/`/`validate/` pure layer |
| `newtype_domain_primitives` | `dataclasses_tree` (`:124`) | no `schemas/dataclasses` tree |

### Tier 2 — WARN-only, flip to HARD-FAIL by re-pointing the severity classifier

These already *detect* real-package violations via the git universe; only their
severity is under-scoped (classifier keyed on the dead `source_trees` /
`covered_trees`). Re-pointing those keys flips them to blocking.

`assert_never_exhaustiveness`, `no_inheritance`, `private_calls`,
`keyword_only_args`, `match_keyword_only`, `global_writes`, `all_declared`
(all via `source_trees`); `no_write_direct`, `no_lloc_soft_warnings` (via
`covered_trees`).

### Tier 3 — hardcoded in the installed library; pyproject cannot reach them

These bake `.claude-plugin/scripts/livespec` (or `tests/livespec/parse`) into the
module body as a constant, so re-pointing pyproject does nothing. They need a
**livespec-dev-tooling library change** (make the path config-driven, or drive
off the git universe like the Tier-2 checks already do).

| Check | Hardcode | State |
| --- | --- | --- |
| `supervisor_discipline` | `_LIVESPEC_TREE` (`:46,75`) | DORMANT |
| `main_guard` | `_LIVESPEC_TREE` (`:50,94`) | WARN-only |
| `rop_pipeline_shape` | `_LIVESPEC_TREE` (`:44,100`) | WARN-only (and no `@rop_pipeline` here) |
| `tests_mirror_pairing` | `_SOURCE_TREES_TO_TESTS` (`:45-49`) | misses the real pkg |
| `pbt_coverage_pure_modules` | `tests/livespec/parse|validate` (`:41-44`) | DORMANT + N/A |
| `check_mutation` | `livespec/parse|validate` (`:1,5`) | DORMANT + N/A |

### Already correct — DO NOT touch

`file_lloc` (armed via `file_lloc_hard_gate = true`, the working model),
`comment_line_anchors`, `no_fmt_directives`, `red_green_replay` (its
`_IMPL_PREFIXES` already lists `livespec_orchestrator_beads_fabro/`),
`claude_md_coverage`, `no_direct_destructive_cli`, `wrapper_shape`,
`tests_no_subprocess_spawn`, all 5 repo-local `dev-tooling/checks/*.py`, **Ruff**,
and **Pyright** — the last two already cover the real package and are not
mis-pointed.

### Ruff / Pyright / `.claude/skills` — the "everything except skills" edge

- **Ruff** correctly covers the real package. It does **not** exclude
  `.claude/skills/**` (`pyproject.toml:84`) — to make the target rule explicit,
  add `.claude/skills/**` to `extend-exclude`. Ruff currently **excludes**
  `.claude/hooks/**`, so the 2 first-party hook files go unlinted (see decision
  below).
- **Pyright** covers the real package and excludes `.claude/skills` by omission
  (already satisfies the rule). It also excludes `.claude/hooks` by omission.
- **The git-universe checks already implement the exact target rule**: they exempt
  only `.claude/skills/` and deliberately keep `.claude/hooks/**` in scope
  (`config.py:569,615-627`). Mirror that into Ruff (exclude skills, cover hooks).

---

## Enforcement mechanisms (evaluated, with verdicts)

- **Ruff `BLE` (flake8-blind-except) — ADOPT (immediate).** `BLE001` flags
  `except Exception:` and bare `except:` exactly. It is **not** currently in the
  `select` list (`pyproject.toml:87-117` has 27 categories incl. `TRY`, but not
  `BLE`) — which is why the 13 bulkheads lint clean. Ruff already scopes the real
  package, so adding `"BLE"` bans the superclass-catch across all 127 files in one
  line, with zero config-entanglement. This is the fastest, narrowest lever for
  Rule 2.
- **`no_except_outside_io` / `no_raise_outside_io` — ADOPT (via re-point).** These
  are the *structural* ROP rules (no `try/except` and no `raise` outside the `io/`
  boundary + supervisor `main()`), stronger than `BLE` (which only bans the blind
  catch). Arming them makes the railway the only option in the pure layers. They
  already exist; they just need the source trees re-pointed.
- **`public_api_result_typed` — ADOPT if a pure layer is introduced.** Enforces
  Rule 1's "public APIs return `Result`". N/A until this repo has a `pure_trees`
  analog (see decision).
- **Custom `dev-tooling/checks/` AST check — only as a fallback.** The existing
  harness (pattern: `dev-tooling/checks/status_conformance.py`, wired into `just
  check` + CI) can express repo-specific rules the above cannot. Not needed for
  Rules 1–2 (Ruff + the inherited checks cover them); hold in reserve.
- **ArchUnitPython — EVALUATED, NOT ADOPTED for this rule.** Per its own docs it
  analyzes imports, class structure, and metrics via the AST but **does not
  inspect function bodies** — you cannot express "no function catches `Exception`"
  with it. It is zero-dependency and stdlib-only, so it remains a candidate for
  *layer/dependency* rules later, but it is the wrong tool for banning a
  statement-level construct, which Ruff `BLE` + the inherited AST checks already
  do better.

---

## The plan (phased — ordering is load-bearing)

You cannot flip the bans to hard-fail before the railway exists and the bulkheads
are migrated, or all work stops on a wall of red. Sequence:

**Phase 0 — provide the primitive.** Vendor `returns` from core into
`.claude-plugin/scripts/_vendor/returns/` (mirror core's copy + its
`.vendor.jsonc` manifest entry). Add a short `_vendor`/ROP usage note. No behavior
change yet.

**Phase 1 — migrate the bulkheads + arm the narrow ban.** Convert the 13
`except Exception` sites to the observability/ROP pattern (review-gate emitter
first, as the worked example). Then add `"BLE"` to Ruff `select` and add
`.claude/skills/**` to `extend-exclude`. BLE goes green because the bulkheads are
gone. This delivers Rule 2 end-to-end with a small, self-contained blast radius.

**Phase 2 — re-scope the config-driven checks.** Re-point the dead pyproject keys
(`source_trees`, `io_trees`, `commands_trees`, `supervisor_entry_files`,
`covered_trees`, `source_tree_prefixes`, first `mirror_pairings` entry) to the
real package + `bin/` + `dev-tooling/` + `.claude/hooks/`. This **arms the 4
Tier-1 dormant checks and flips the 9 Tier-2 WARN-only checks to hard-fail against
127 previously-unenforced files at once.** Before flipping, harvest the current
WARN output (the Tier-2 checks already warn against real files today) to get a
free violation inventory, and fix per-check/per-tree so the flip lands green.
Mind the empty-baseline-flip warning and the TOML-ordering constraints (bare keys
must sit above the `[[mirror_pairings]]` array-of-tables — `pyproject.toml:276`).

**Phase 3 — upstream the library-hardcoded checks.** For the 6 Tier-3 checks,
land a `livespec-dev-tooling` change that makes their scope config-driven (or
git-universe-driven, matching the Tier-2 pattern), then bump this repo's pin and
re-point. Decide the no-analog checks here too.

---

## Decisions for the implementing session

1. **Result primitive: vendor `returns` (recommended) vs hand-roll a minimal
   `Result`.** Recommend vendoring core's copy — proven, maintained, matches the
   API the dormant checks expect.
2. **Re-point strategy: staged (recommended) vs big-bang.** Recommend staged —
   fix each check's real violations using the pre-flip WARN output, then flip that
   check, rather than turning everything red simultaneously.
3. **The 6 library-hardcoded checks: upstream a config-driven fix (recommended)
   vs local override vs accept-dormant.** Recommend upstreaming — it fixes every
   fleet consumer, not just this repo, and matches how the Tier-2 checks already
   resolve severity off the git universe.
4. **No-analog checks (`public_api_result_typed`, `newtype_domain_primitives`,
   `pbt_coverage_pure_modules`, `check_mutation`): introduce a pure `parse`/
   `validate` layer vs leave N/A.** This repo genuinely has no pure-computation
   layer split today; forcing one is a larger architectural change. Recommend
   leaving N/A for now and documenting it, revisiting if a pure layer emerges.
5. **`.claude/hooks/**` coverage.** The git-universe checks deliberately cover the
   2 hook files, but Ruff and Pyright currently exclude them. Per the "everything
   except skills" rule, bring Ruff/Pyright in line (lint + type-check the hooks) —
   unless there is a deliberate reason to exempt them, in which case document it.

---

## Blast radius & risks

- **Phase 2 is a large, deliberate red.** Re-pointing arms/flips ~13 checks
  against 127 files that have never been enforced. Expect the first run to surface
  many real violations (13 blind-excepts already known; unknown counts of
  `raise`-outside-io, `private_calls`, `keyword_only`, `all_declared`, etc.).
  This is the point — but it must be staged, not big-banged, or it blocks all
  other work.
- **The empty-baseline-flip trap** (`pyproject.toml:248-261`): the keys were set
  to the *core* layout specifically to reproduce the pre-block `Config`
  byte-for-byte. Re-pointing is the intended fix, but every omitted key still
  reverts to empty — so re-point deliberately and keep every currently-declared
  key present.
- **Shared-library coordination.** Phase 3 touches `livespec-dev-tooling`, a
  fleet-shared package; changes there ripple to every consumer and need the normal
  upstream + version-bump discipline.
- **Vendored-`returns` footprint.** 115 files enter `_vendor/`; ensure the
  `.vendor.jsonc` manifest and `vendor_manifest` check accept it (core's manifest
  is the template).

---

## First steps for the implementing session

1. **Baseline.** Run `just check` and capture which checks pass trivially vs warn.
   Grep the WARN output of the Tier-2 checks for the real-package violation
   inventory.
2. **Phase 0.** Vendor `returns` from `/data/projects/livespec/.claude-plugin/
   scripts/_vendor/returns/` + manifest entry; confirm `vendor_manifest` +
   Pyright accept it.
3. **Phase 1.** Migrate `_dispatcher_review_gate.py` to the `@impure_safe` +
   `.lash` pattern (the worked example), then the other 12 bulkheads; add `"BLE"`
   to Ruff `select` and `.claude/skills/**` to `extend-exclude`; confirm green.
4. **Phase 2.** Re-point the dead pyproject keys; fix per-check using the Phase-1
   inventory; land the flips green.
5. **Phase 3.** Upstream the config-driven fix for the 6 hardcoded checks; bump
   the pin; re-point; resolve the no-analog decision.
6. Formalize as a proper plan thread (`/plan rop-enforcement`) and anchor a ledger
   epic if driving to completion.

---

## Evidence / references (file:line)

- **The 13 blind-except bulkheads** (all lint-clean because `BLE` is off):
  `_dispatcher_review_gate.py:98`, `_dispatcher_reflector_oob.py:253`,
  `_dispatcher_notify.py:249`, `_dispatcher_self_update.py:275`,
  `_dispatcher_cost_gate.py:77,98,203`, `_otel_receive.py:254,324`,
  `_otel_enrich.py:272`, `_dispatcher_calibration_emit.py:84`,
  `_dispatcher_reflection.py:324`, `acceptance.py:187` (all under
  `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/`).
- **Config resolution & two regimes:** `livespec_dev_tooling/config.py:473-533`
  (`load_config`), `:161-214` (`_livespec_core_config`), `:796-819`
  (`resolve_check_universe`), `:569,638` (`.claude/skills` exemption),
  `:615-627` (`.claude/hooks` kept in scope).
- **The dead pyproject keys:** `pyproject.toml:264-303`; the empty-baseline-flip
  warning `:248-261`; Ruff config `:77-163` (no `BLE` in `select`, no `skills`
  exclude); Pyright `:171-173`.
- **The inherited ROP checks:**
  `livespec_dev_tooling/checks/no_except_outside_io.py` (docstring cites
  `Result.bind`/`Result.alt`), `no_raise_outside_io.py`,
  `public_api_result_typed.py:53-54` (`_RESULT_NAMES`,
  `_RAILWAY_LIFTING_DECORATORS`), `no_inheritance.py:63-133` (the
  ban-a-construct + two-tier-severity template).
- **`returns` in the fleet:** vendored at
  `/data/projects/livespec/.claude-plugin/scripts/_vendor/returns/result.py:73`
  (`.map`), `pointfree/{map,bind,alt,lash,cond}.py`, `functions.py` (`tap`),
  `unsafe.py`; used at `livespec/.../commands/_seed_railway_writes.py` and
  `templates.py:70`. No-PyPI-deps constraint: `SPECIFICATION/constraints.md:34-37`.
- **ArchUnitPython** (`github.com/LukasNiessen/ArchUnitPython`, v1.3.0): analyzes
  imports/classes/metrics via AST; does **not** inspect function bodies; zero
  runtime deps, stdlib-only, Python 3.10+.
