# tests/livespec_impl_beads/

Tests for the `livespec_impl_beads` package under
`.claude-plugin/scripts/livespec_impl_beads/`. Mirrors the
package's directory shape one-to-one.

Top-level package modules are covered by `test_<name>.py` directly
under this directory:

- `test_types.py` — work-item / Spec Reader dataclass
  invariants and serialization round-trips.
- `test_store.py` — JSONL store primitives: append-only writes, line
  parsing, the latest-record-per-`id` materialization reduction, and
  the EXPECTED-error paths (missing file, malformed line, schema
  violation).
- `test_spec_reader.py` — the four read-only Spec Reader
  capabilities; asserts the adapter never mutates the spec tree.
- `test_errors.py` — the `errors.py` exception surface (message
  formatting and the carried context attributes).
- `test_ids.py` — id-generation helpers.

Subpackages (`commands/`, `migration/`) get their own subdirectory
with paired tests.

Coverage rules:

- 100% line + branch on every covered module; Hypothesis
  property-based tests are required where a pure transformation
  applies (store materialization, id generation, record mapping).
- Build minimal JSONL fixtures in `tmp_path`; do NOT read or write
  the repo's real work-items files. Append-only behavior is
  asserted by re-reading the file and checking record order, not by
  inspecting in-memory state alone.
