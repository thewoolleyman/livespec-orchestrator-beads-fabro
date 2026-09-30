# factory-test-first-enforcement — opening research

_Author: the factory-configurable-model-fallback-priority session (Claude Fable
5.1), 2026-09-30, on the maintainer's ruling that the factory not doing
test-first development is unacceptable. The finding surfaced while watching
dispatch `01M3R6ACRHVB` (`bd-ib-kc7vzk`) under plan epic `bd-ib-jxvgq5`; the
maintainer ruled it OUT of that plan's scope and opened this one, to be driven
from a separate session. Every number below was measured on 2026-09-30 and the
command that produced it is recorded so a successor can re-take it._

## 1. The finding

The factory produces Red-Green-Replay commits without doing test-first work.
The implementation is written first; the Red commit is cut afterwards by
moving the implementation aside, committing one test, moving it back, and
amending. The commit shape the `red_green_replay` hook enforces is identical
either way, so nothing in the pipeline has ever observed the order of work.

**Sandbox inspection, run `01M3R6ACRHVB` on hp (24 to 34 minutes in):** eleven
new modules and six modified ones, about 3,600 lines, zero test files; then
`just check-types` and a full pytest run before any test existed; the first
path staged was the retired `_codex_model_tiers.py`, not a test. Run
`01M3R750MNDH` (`bd-ib-xtgwpz`) showed the same order at 20 minutes: six new
modules, zero tests. The maintainer's verbatim ruling on seeing it: "This is a
failure. Unacceptable. It must be a bad prompt or something. There's no excuse
for the factory not doing TDD."

**Fleet-wide measurement.** The gap between a commit's `TDD-Red-Captured-At`
and `TDD-Green-Verified-At` trailers is the time between "the failing test was
committed" and "the implementation made it pass". For genuine test-first work
that interval contains the implementation time.

| Sample (origin/master) | commits | p25 | median | p75 | under 2 min | 2 to 15 min | over 15 min |
|---|---|---|---|---|---|---|---|
| last 300 trailered commits (predecessor, 04:18 UTC) | 281 | 156 s | 260 s | 514 s | 31 | 228 | 22 |
| last 600 non-merge, product-touching, Red+Green pair (this note, 06:33 UTC) | 147 | 152 s | 197 s | 407 s | 17 | 120 | 10 |

Of the 147 product-touching commits in the second sample, 123 were authored by
Fabro; none carried the `TDD-Suite-Green-*` shape (the hook's leg 5, product
code with no Red at all), and 15 carried no trailers (stage checkpoints and
server-side reverts). So the loophole is not the suite-green leg; it is that a
median of three to four minutes between Red and Green, for changes that are
routinely hundreds of lines, is the stash-and-unstash dance, for Fabro-authored
and human-session commits alike. Reproduce with:

```bash
git log origin/master -n 600 --no-merges \
  --format='%x1e%H%x1f%(trailers:key=TDD-Red-Captured-At,valueonly)%x1f%(trailers:key=TDD-Green-Verified-At,valueonly)%x1f%(trailers:key=TDD-Suite-Green-Verified-At,valueonly)%x1f%an%x1f%s'
# split records on \x1e, fields on \x1f; keep commits whose `git show --name-only`
# lists a non-test .py; bucket by trailer shape; gap = Green minus Red.
```

## 2. Why, in order of weight

1. **The hook enforces a commit shape, and a shape can be produced after the
   fact.** `livespec_dev_tooling.checks.red_green_replay` (the lefthook
   `commit-msg` leg) sees only staged bytes at two moments: the Red commit and
   the Green amend. Test-first and implement-then-backfill produce
   byte-identical commits and trailer blocks.
2. **The implement prompt never asks for test-first.**
   `.claude-plugin/.fabro/workflows/implement-work-item/prompts/implement.md`,
   "What to do", step 2 (line 215 of 224): "Implement it via the ritual above,
   in as few cohesive commits as the work naturally splits into (test+impl land
   atomically in one commit)." Read literally that is an instruction to build
   the change and then package it, and "as few commits" pushes a large item
   toward one big-bang commit. The Red-Green-Replay section starts at line 152,
   after 130 lines about LLOC ceilings and formatter evasion, and it is written
   entirely in terms of what to STAGE, never what to WRITE first. Five hardening
   edits since July touched this prompt; none was about order.
3. **Items are sized for big-bang.** `bd-ib-kc7vzk` carries 14 acceptance
   assertions and 26 rule ids. Even a disciplined agent designs the module
   layout first for an item that size.

Two smaller defects fell out of the same dump. The rendered prompt carries the
whole work-item goal twice: Fabro prepends it, and the template's `{{ goal }}`
at line 5 repeats it, about 100 of 322 rendered lines. And the agent's first
commit-in-progress staged the retired module rather than a test.

## 3. Maintainer decisions (2026-09-30)

- **A (prompt rewrite): agreed.**
- **B (sandbox order hook): agreed.**
- **C (measure it): agreed, with a requirement.** "Lean into Honeycomb and
  OpenTelemetry observability like we have everywhere else. We should
  instrument it." Not a journal-only counter.
- **D (size items for cycles): open question**, answered in section 5. The
  maintainer's framing: "We already have the grooming phase. What sort of
  deterministic and mechanical gates can we put on items to ensure they get
  broken down, but still not force things that legitimately need to be one run
  to be artificially broken down?"
- **Scope:** this is factory tooling in THIS repository (prompt, hooks,
  Dispatcher telemetry, intake gate), a separate plan from
  `factory-configurable-model-fallback-priority`, driven from a separate
  session.

## 4. Design for A, B and C

### A. Make the prompt say what we mean

Rewrite "What to do" as the loop and move it to the top of the prompt, before
the LLOC and formatter rules:

1. Pick one acceptance assertion.
2. Write one failing test for it. Run it and watch it fail on an assertion.
3. Red-commit that test alone.
4. Write the minimum implementation. Green-amend.
5. Repeat for the next assertion. One cycle per assertion.

State the order rule explicitly: no product file may be created or modified
before the first Red commit exists, and after that only while HEAD is an open
Red. Delete "as few cohesive commits as the work naturally splits into". Keep
the new-module stub technique, stated as the ONLY permitted product write
before a Red commit, and state its limit (a stub that makes the assertion
fail, never one that passes it). Drop the `{{ goal }}` duplication once the
Fabro-prepended goal is confirmed on every adapter, or drop the prepend; not
both copies.

The prompt is this repository's own file. A search of the installed
`livespec_dev_tooling` package for the "Red-Green-Replay (REQUIRED" heading
and for `implement.md` found no template source, so the rewrite lands here
and is not fleet-templated (scope: the whole installed package tree under
`.venv`; if a sibling repo carries its own copy, that is that repo's item).

### B. Enforce order mechanically in the sandbox

The Claude ACP adapter loads project settings (`settingSources: user,
project, local`, verified by the predecessor in
`@agentclientprotocol/claude-agent-acp`), so this repository's
`.claude/settings.json` PreToolUse hooks already run inside the factory
sandbox. Today they are three Bash-matcher hooks (background guard, the
`livespec_footgun_guard`, and the beads access guard). Add:

- **A PreToolUse hook on `Write`, `Edit` and `MultiEdit`** that refuses any
  write to a product path unless HEAD is an open Red. "Open Red" is the
  discriminator `red_green_replay` leg 4 already uses: HEAD's message carries
  `TDD-Red-Test-File-Checksum:` and does not carry `TDD-Green-Verified-At:`.
  "Product path" is `_derive_impl_prefixes(config)` from the same module;
  reuse it rather than re-deriving the prefix list, so the two hooks cannot
  disagree about what counts as product.
- **The same rule in the Bash guard** for shell writes into product paths
  (`>`, `>>`, `tee`, `sed -i`, `cp`/`mv` targets, heredocs), using the
  segment-based tokenizer the footgun guard already has.
- **One carve-out, stated in the deny message:** creating a file that does
  not exist at HEAD is allowed while a test file is modified and uncommitted
  (the new-module stub). Modifying an existing product file is never allowed
  outside an open Red. This leaves one residual gap, an all-new-module item
  built entirely as "stubs" before the first Red; C's telemetry is what makes
  that visible, and D3's per-cycle signal is what bounds it.
- **Deny, never fail-open on the decision.** The footgun guard fails open on
  tokenizer errors, which is right for a warning. For this hook the decision
  itself must be deterministic; a tokenizer error on the Bash leg may fall
  open, but a Write/Edit to a product path with a closed HEAD is a refusal.

The hook applies to human sessions in this repository as well, which the
numbers in section 1 say is warranted. It does NOT cover a Codex-driven
implement node: Codex has no PreToolUse hook surface, so the Codex path relies
on A plus C's detection. Today the implement node's default adapter is
Claude ACP, so B covers the default path.

### C. Instrument it, through the existing OTel path to Honeycomb

The Dispatcher already runs an OTLP/HTTP receiver that the sandbox reaches at
`LIVESPEC_SANDBOX_OTEL_ENDPOINT` (default `http://172.17.0.1:4318`,
`_dispatcher_projection.py`), a host-local enrich and scrub stage
(`_otel_enrich.py`, `_otel_scrub.py`) and Honeycomb egress
(`_otel_enrich_export.py`, dataset routed by `service.name`). Per terminal
dispatch it emits one `dispatcher.calibration` span (`_dispatcher_calibration_span.py`,
service `livespec-dispatcher`, scope `livespec.dispatcher.calibration`). Three
signals ride that path; none needs a new service.

1. **Hook decisions as spans.** The B hook emits one span per decision to the
   sandbox endpoint when it is set, and is a no-op when it is not (human
   sessions without a receiver). Attributes: `tdd.decision` (allow or
   refuse), `tdd.path`, `tdd.head_state` (open-red, closed, no-trailers),
   `tdd.reason`, `tdd.tool`. Join it to the run through the W3C
   `traceparent` the fork's O2 change already injects, so a refusal is
   visible on the run's trace, and pass it through the scrub discipline.
2. **Per-run order fields on the calibration span.** From the run's commit
   series and hook events: `tdd.red_commit_count`, `tdd.green_commit_count`,
   `tdd.suite_green_count`, `tdd.red_green_gap_seconds_median`,
   `tdd.first_product_write_before_red` (boolean), `tdd.order_refusals`,
   `tdd.assertion_count` (from D1). These are the fields that would have shown
   the fleet-wide pattern months ago.
3. **A Honeycomb board and trigger.** A derived column for "post-hoc Red"
   (median gap under a threshold, or first product write before Red), a board
   over `livespec-dispatcher` showing its share per repo and per adapter, and a
   trigger when the share rises. The same query answers the acceptance
   question for A and B: after they land, the median gap must move from
   minutes to the implementation time, and refusals must trend to zero.

## 5. D: deterministic sizing gates that do not force artificial splits

### What the ratified design already says

`SPECIFICATION/contracts.md` section "Grooming and slice-size calibration"
rules by gate TYPE: the structural Definition-of-Ready gates (exactly one
coherent "done"; autonomously verifiable acceptance; dependencies linked) are
HARD; the SIZE gate is ADVISORY because it is data-derived; the reactive
ceiling (bail after N fix-loops into the `backlog` bounce) is the
non-convergence trigger and the predictive intake flag's training signal; and
the calibration analysis pass proposes ceilings a maintainer may adopt. So a
hard assertion cap at intake is not merely a bad idea, it contradicts ratified
text and would need `propose-change`.

### What the data says about that design today

The local journal holds 445 calibration records (`tmp/fabro-dispatch-journal.jsonl`,
read through `calibration_analysis.load_calibration_records`):

| field | converged (292) | non-converged (153) |
|---|---|---|
| `acceptance_count` median / max | 0 / 24 | 0 / 32 |
| `merged_pr_diff_size` present | 292 | 0 |
| `fix_loop_count` median | 6 | 0 |
| `bounced_to_regroom` | 0 | 0 |

Three of the four inputs the predictive gate depends on are unusable:

- `acceptance_count` reads bullet and Gherkin markers from the item's
  DESCRIPTION (`_dispatcher_calibration.acceptance_count`), not the criteria
  field the acceptance judge grades, so its median is zero on both sides.
- `merged_pr_diff_size` exists only on merged runs, so it can never
  discriminate a failure; a proxy that is present only on success cannot
  predict non-convergence.
- `bounced_to_regroom` is zero in 445 records: the reactive ceiling the spec
  names as the training signal has never fired. Non-converged runs die with
  `fix_loop_count` zero, before any fix loop.

`analyze_calibration` over those records proposes exactly one ceiling,
`dispatch_context_size` at 1283 with 442 runs above it and 3 below, which is
noise. The calibrated size gate is therefore not wrong in design; it has had
no signal to calibrate on.

### The gates to add, all deterministic, none of them "split it"

- **D1. Count assertions with the sanctioned parser.** Record
  `assertion_count` from `effective_criteria(item=...).criteria_lines`
  (`_dispatcher_acceptance_criteria.py`), the exact segmentation the
  evaluator grades, at intake and on the calibration span, replacing the
  description regex. Deterministic, and the same number the operator sees in
  `parse_display()` at filing time.
- **D2. A ceiling with a declared exception, not a refusal.** Above the
  adopted ceiling, intake and groom route the item to `backlog` UNLESS the
  item carries an explicit single-run justification (a metadata object, for
  example `size_justification` with `rationale`, `author`, `at`), and a
  dispatch of a justified item tags its run `tdd.size_justified=true`. The
  rule is mechanical: count above ceiling AND no justification means
  `backlog`; count above ceiling AND justification means dispatch. A person
  states in one sentence why the work must be one run; the ledger keeps who
  said so; and the calibration learns whether justified oversize items
  converge. That is the escape hatch for legitimately single-run work, and it
  costs a sentence, not a split. Whether this is a conformance realization of
  the advisory gate or a new hard route is a spec question: if it REFUSES
  dispatch it changes the ratified "advisory" wording and goes through
  `propose-change`; if it only routes at intake with the human able to
  override, it is the advisory gate as ratified.
- **D3. Make "too big" a per-cycle signal, not a per-item guess.** Once A and
  B hold, every assertion is one Red-Green cycle and the run's own commit
  series is a deterministic instrument: product LLOC per cycle, minutes per
  cycle, and Red count against assertion count at the fix-loop cap. A cycle
  over an adopted LLOC or minutes ceiling, or a run that reaches the cap with
  fewer Reds than assertions, is the empirical "this slice was too big"
  signal, and it feeds the non-convergence bounce that today never fires. Pair
  this with two proxy repairs: capture diff size at PR open (branch against
  base) so failed runs carry it, and make the bounce path observable end to
  end.

What NOT to do: a hard assertion cap at intake (forces artificial splits and
contradicts the ratified advisory rule); diff LLOC as a predictive gate (it is
post-hoc by construction); any ceiling chosen by hand now. The ceiling values
come from D1 and D3 data after roughly fifty runs; `bd-ib-kc7vzk` at 14
assertions and 26 rule ids is the motivating outlier, not the threshold.

## 6. Prior art scanned

`bd list --status all --limit 0 --json` over all 1,083 items, filtered
client-side for test-first, TDD order, post-hoc Red, size gate, assertion
cap, calibration analysis, adopted ceiling, goal duplication and
`implement.md`: 13 hits, none about order of work. Touchpoints:
`livespec-impl-beads-fh7cff` (closed) shipped the calibration analysis pass;
the `bd-ib-fqh` family (closed) built the goal render that now doubles the
goal; `livespec-impl-beads-zsl` (blocked) is the upstream brace-in-comment
Fabro UI bug and is unrelated. No open item owns any of A to D.

## 7. Proposed slices (to groom; dependency-layered)

- **S1** Prompt rewrite and goal de-duplication (A). No product `.py`;
  factory-safe.
- **S2** Order hook on Write, Edit, MultiEdit and Bash, with the OTel decision
  span (B plus C signal 1). Product `.py` under `.claude/hooks/`; must be
  built test-first itself, and its own commit series is the first evidence.
- **S3** Calibration span TDD fields, Honeycomb board and trigger (C signals
  2 and 3). Depends on S2 for refusal counts, not for the commit-derived
  fields.
- **S4** `assertion_count` through the sanctioned parser, PR-open diff size,
  bounce path made observable (D1 and the proxy repairs).
- **S5** Ceiling-with-justification intake and groom gate (D2). Route to
  `propose-change` first if it refuses rather than routes.
- **S6** Per-cycle signal into the bounce (D3). Depends on S2, S3 and S4.

## 8. Immediate next action

The maintainer, in the session that drives this plan: review sections 4 and 5,
decide D2's spec tier, record the scope event naming S1 to S6 as requirement
carriers and the Codex-adapter gap as an explicit deferral, then groom and file
the slices as children of this epic.
