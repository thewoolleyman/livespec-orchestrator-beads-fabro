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
- `work_item_state_invariants.py` — the beads-private work-item-state
  doctor check (SPECIFICATION/contracts.md §"Work-item beads-issue
  mapping" invariants block; L1a slice S6). Walks every materialized
  work-item and emits the fail-soft non-sentinel-`rank` + rank-key-length
  WARNINGS for live heads (advisory, exit 0) plus the hard
  `active ⟹ assignee` and stored
  `blocked ⟹ blocked_reason ∈ {needs-human, infra-external}` ERRORS
  (exit non-zero). No git / network I/O; passes trivially on the empty
  hermetic-fake tenant.
