# dev-tooling/checks/

Impl-beads-PRIVATE enforcement scripts — checks that depend on the
beads-issue mapping this plugin defines and therefore cannot ship from
the shared `livespec-dev-tooling` package. Each `<name>.py` here is a
standalone module exposing `main() -> int` (0 = pass, non-zero = fail),
invoked from the `justfile`'s private block via
`uv run python dev-tooling/checks/<name>.py` (NOT `python -m`, since these
are in-repo, not part of the installed `livespec_dev_tooling.checks`
package).

Constraints an agent editing this directory must satisfy:

- **Output discipline.** `print` (ruff T20) and direct `sys.stderr.write`
  (`check-no-write-direct`) are banned. Diagnostics flow through structlog
  (JSON to stderr) — the only sanctioned output surface. structlog is not
  vendored in this repo's own tree, so it is imported from the installed
  `livespec_dev_tooling` package's vendored copy (its path is added to
  `sys.path` at import time); a file-level `# pyright:` pragma silences the
  untyped-structlog diagnostics.
- **Comment discipline.** No line-number anchors in docstrings or comments
  (`check-comment-line-anchors` scans `dev-tooling/`). Reference spec
  sections and symbol names, never line numbers.
- **Per-file 100% coverage** + a paired test at
  `tests/dev-tooling/checks/test_<name>.py` (`check-tests-mirror-pairing`).
- Keyword-only arguments, a `__main__` guard, and a sub-250 LLOC ceiling.

Current checks:

- `work_item_merge_evidence.py` — the beads-private port of the spec'd
  merge-evidence static check (SPECIFICATION/contracts.md
  §"`work_item_merge_evidence` static check"). Reads each closed issue's
  `AuditRecord` from `metadata` via the store; same git-reachability rules
  as the plaintext sibling's JSONL-shaped equivalent; epics exempt
  (child-closure checked instead). Passes trivially when the store is
  empty (the hermetic-fake default tier).
- `spec_id_presence_discipline.py` — executable guard for the narrowing of
  the OVERLOADED spec id field (`WorkItem.spec_commitment_hint`, persisted as
  the beads-native `spec_id` column, carrying both the `plan:<slug>` anchor
  marker and a genuine spec-clause commitment). AST-scans the orchestrator
  package and fails on a bare presence / truthiness test outside a measured
  allowlist; everything else must ask `is_spec_commitment` / `is_plan_anchor`
  from `commands/_plan_anchor.py`. It reports an ABSENCE, so it carries two
  positive controls — a discovery control over the package walk and a matcher
  control over `fixtures/spec_id_presence_control.py.txt` — and refuses to
  report a clean scan when either fails. Editing the allowlist means
  re-measuring: add an entry only after confirming the site fires without it.
- `no_fleet_toolchain_literals.py` — executable guard for
  SPECIFICATION/constraints.md §"Fleet-toolchain literal ban". AST-scans the
  orchestrator package and fails on any fleet-toolchain literal (`mise`, a fleet
  `just` recipe name, `lefthook`, `livespec_dev_tooling`, `livespec-step-timer`,
  or a bare default-branch name used as a ref) outside the single fleet-defaults
  module the `RepoIntegrationContract` schema designates. Only two literal shapes
  count — the constant IS the token, or the token sits in shell command position
  inside it — so comments, docstrings, `__all__` entries and operator-facing
  prose are out of scope by construction. There is NO allow-list of any kind:
  the payload's went with carrier C5-payload and the dispatcher package's went
  with carrier C7, which converted its six remaining sites onto the resolved
  integration contract or the fleet-defaults module. Each list carried a
  stale-entry control while it existed — a converted site's entry stopped
  matching and FAILED the check until it was deleted — which is what made both
  retirements mechanical rather than remembered. It reports an ABSENCE, so it
  carries four positive controls — package and payload discovery, a designation
  control asserting the ONE skipped module is the one the schema imports, and a
  matcher control over `fixtures/fleet_toolchain_literal_control.py.txt` — and
  refuses to report a clean scan when any fails. The payload scan reads the
  BUNDLE plus every directory this repo registers under its own
  `dispatcher.workflows`, per contracts.md §"Self-contained plugin dispatch"
  clause "A registered variant is the reserved workflow's peer, not its
  exception"; the payload discovery control and a completeness control are
  applied PER DIRECTORY, so a registered directory that is absent, half-written
  or scans to nothing FAILS naming that directory rather than reporting clean,
  and every finding is prefixed with the directory it came from. The two
  concerns live in two modules because they change for different reasons: this
  one owns the scope and the controls, while the sibling private helper
  `_fleet_toolchain_literals_matcher.py` owns what counts as a literal at all;
  the sibling private `_checked_workflow_payloads.py` owns WHICH directories
  either payload gate reads and is shared with `seam_equivalence.py`, so the two
  gates cannot come to disagree about the checked set.
- `seam_equivalence.py` — the CI half of SPECIFICATION/contracts.md
  §"Repository integration contract", clause "Typed workflow inputs and the
  seam-equivalence check". Scans the committed `implement-work-item` payload —
  the graph, the run config and every node prompt — plus every directory this
  repo registers under its own `dispatcher.workflows` (contracts.md
  §"Self-contained plugin dispatch" clause "A registered variant is the reserved
  workflow's peer, not its exception"), for `{{ inputs.<name> }}`
  tokens and asserts three things about the INTEGRATION subset of them: the
  referenced set equals the set the Dispatcher renders from the
  `ResolvedIntegrationContract` in both directions; the rendered names and the
  schema's projectable fields are one vocabulary (same set, and the same word
  per field, which is what makes the two sets comparable at all); and every
  token sits in a position the pinned fabro build expands. The rendered-position
  allowlist is EVIDENCE-BASED and fail-closed — `acp.command`, edge `condition`,
  a `[[run.prepare.steps]]` `script`, and a prompt body — because a templated
  duration attribute leaves the node with NO timeout and reports nothing. The
  equality excludes the six ACP adapter inputs and the three PER-ITEM POLICY
  inputs (`review_fix_visit_cap`, `merge_on_review_cap_outcome`, `merge_hold`),
  and that exclusion is checked rather than assumed: the three families
  must be pairwise disjoint and must cover every input the payload declares.
  Only the EQUALITY is scoped that way — the resolved-position rule binds every
  declared input whatever its family, because the engine does not know which
  family a name belongs to. The policy family also carries a leg of its own:
  each of its three inputs is rendered on EVERY dispatch rather than intersected
  with what a payload declares, so a payload (bundle or registered variant) that
  fails to declare one earns an `undeclared-policy-input` finding — fabro would
  reject the run. That is what holds a variant to the bundle's token set for the
  family the equality cannot speak about. It
  reports an ABSENCE over a payload that references no integration token yet, so
  it carries three positive controls — a discovery control asserting the scan
  still returns the adapter tokens that ARE there, a completeness control
  asserting the directory holds a whole workflow, and a matcher
  control over `fixtures/seam_equivalence_control.fabro.txt`, whose tokens sit in
  a `timeout`, a `stall_timeout` and a comment — and refuses to report a clean
  payload when any fails. The first two are evaluated PER CHECKED DIRECTORY, so
  a registered variant that is absent, half-written or scans to nothing fails
  naming that directory instead of being certified by the bundle's own controls,
  and every finding is prefixed with the directory it came from. The equality's
  rendered comparand is the ONE Dispatcher-rendered set derived from the BUNDLE,
  never re-derived per variant: a variant that declared fewer inputs would
  otherwise shrink its own comparand and pass vacuously, which is exactly the
  "a variant referencing fewer tokens is a finding, not a pass" rule.
  Four modules, because the concerns change
  for different reasons: this one owns the payload reading, the composition and
  the controls; the sibling private `_seam_equivalence_scan.py` owns where a
  token may sit and which positions the pinned engine expands, and carries the
  evidence behind that allowlist; the sibling private
  `_seam_equivalence_findings.py` owns the three input families and what each
  disagreement is called, and takes only sets so the rules are readable and
  testable with no payload on disk; the sibling private
  `_checked_workflow_payloads.py` owns which directories a payload gate reads
  and is shared with `no_fleet_toolchain_literals.py`.
- `fabro_graph_validity.py` — hands every committed factory graph to
  `fabro validate` itself. A `workflow.fabro` the engine rejects takes the WHOLE
  factory down the moment it merges, and it has happened twice —
  `all_conditional_edges` on 2026-07-16 and again in release 0.146.0 on
  2026-09-09 — both times past tests that checked DOT structure or the built plan
  instead of asking the engine. It reads the SAME payload set the two other
  payload gates read (`_checked_workflow_payloads.py`), then globs those
  directories' parents for a `workflow.fabro` the enumeration does not name, so
  an unregistered sibling graph is a finding rather than an unvalidated file. Its
  matcher control is a MUTANT OF THE REAL GRAPH rather than a hand-authored
  fixture: for each graph it makes one node's single unconditional edge
  conditional — the exact shape both outages had — and requires the engine to
  REJECT that mutant naming `all_conditional_edges`, so a `fabro` that accepts
  everything, a wrong subcommand, or a path the binary never read all fail the
  control instead of certifying the graph. The ONE lever,
  `LIVESPEC_FABRO_GRAPH_VALIDATION`, is consulted only on the branch where NO
  binary resolved, and never suppresses a validation that could have run. Its
  default `warn_when_fabro_absent` is deliberate rather than lax: `fabro` is a
  host artifact, absent by construction in a GitHub Actions runner and inside a
  Fabro sandbox — where this aggregate runs as the in-run janitor gate — so
  fail-closed would stop the factory rather than harden it. The absence is never
  silent: one error-level record per graph not looked at, plus a summary saying
  so. `fail_when_fabro_absent` makes that absence fatal and belongs wherever the
  binary is expected; a value outside that closed space is a failure, never a
  fallback.
- `work_item_state_invariants.py` — the beads-private work-item-state
  doctor check (SPECIFICATION/contracts.md §"Work-item beads-issue
  mapping" invariants block; L1a slice S6). Walks every materialized
  work-item and emits the fail-soft non-sentinel-`rank` + rank-key-length
  WARNINGS for live heads (advisory, exit 0) plus the hard
  `active ⟹ assignee` and stored
  `blocked ⟹ blocked_reason ∈ {needs-human, infra-external}` ERRORS
  (exit non-zero). No git / network I/O; passes trivially on the empty
  hermetic-fake tenant.
