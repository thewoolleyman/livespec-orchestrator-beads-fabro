"""Gap-id parity: the heading derivation ⇄ the shared `livespec_spec_clauses` primitive.

The heading-derived gap-id rides the vendored `livespec_spec_clauses`
derivation — byte-identical to `livespec`'s `dev-tooling/spec_clauses.py` —
rather than a second hash recipe local to this repository. A gap-id is a
LABEL on a live work-item, so a second recipe here is a second way for two
repositories to disagree about one item's identity.

This module pins the two together from both ends:

- A frozen golden vector set pins the ABSOLUTE `gap-<8>` values of the
  shared derivation, shared with the core-side parity test. Recomputing
  them through the derivation under test would make every assertion true
  by construction.
- The heading form is pinned to that same derivation applied with the
  heading as the heading path and NO rule text, which is also what keeps
  a heading-derived id disjoint from every clause-derived one: a clause
  always carries non-empty rule text.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._heading_gaps import derive_heading_gap_id
from livespec_spec_clauses import derive_gap_id, extract_rules_from_file

# Frozen golden parity vectors (identical to the core-side test's
# set): (spec_file, heading_path, rule_text) -> gap_id.
_GOLDEN_VECTORS: list[tuple[str, str, str, str]] = [
    (
        "contracts.md",
        "Top > Section A",
        "Every reader MUST validate the input.",
        "gap-jpm575mi",
    ),
    (
        "scenarios.md",
        "(top)",
        "Implementations SHOULD prefer the typed API.",
        "gap-bvw44he4",
    ),
    (
        "spec.md",
        "A > B > C",
        "Callers MUST NOT pass null.",
        "gap-3qvhzogi",
    ),
    (
        "constraints.md",
        "Heading",
        "Plugins SHOULD NOT shell out.",
        "gap-zfrssonu",
    ),
]

# Frozen golden heading-derived ids, for the same reason: a changed payload
# separator, a different hash or a dropped field must surface here rather
# than be absorbed by a recomputed expectation.
_GOLDEN_HEADING_VECTORS: list[tuple[str, str, str]] = [
    ("spec.md", "## Absent heading", "gap-yazf6mdi"),
    ("contracts.md", "## Absent heading", "gap-ogmdtdb2"),
    ("scenarios.md", "## Shared heading", "gap-ycahxxq5"),
]


def test_derive_gap_id_matches_golden_parity_vectors() -> None:
    for spec_file, heading_path, rule_text, expected_gap_id in _GOLDEN_VECTORS:
        actual = derive_gap_id(
            spec_file=spec_file,
            heading_path=heading_path,
            rule_text=rule_text,
        )
        assert actual == expected_gap_id


def test_derive_heading_gap_id_matches_golden_heading_vectors() -> None:
    for spec_file, heading, expected_gap_id in _GOLDEN_HEADING_VECTORS:
        assert derive_heading_gap_id(spec_file=spec_file, heading=heading) == expected_gap_id


def test_heading_gap_id_is_the_shared_derivation_with_no_rule_text() -> None:
    """The heading form IS the shared derivation, not a parallel recipe."""
    assert derive_heading_gap_id(spec_file="spec.md", heading="## Absent heading") == derive_gap_id(
        spec_file="spec.md", heading_path="## Absent heading", rule_text=""
    )


def test_a_heading_id_can_never_collide_with_a_clause_id_from_the_same_heading() -> None:
    """A clause carries non-empty rule text, so the two id spaces stay disjoint.

    The control is a REAL extraction rather than a hand-written triple: the
    shared extractor is what decides a clause's rule text, and a clause whose
    text it stripped to nothing would be the one collision that matters.
    """
    content = "# Top\n\n## Absent heading\n\nEvery reader MUST validate the input.\n"
    rules = extract_rules_from_file(spec_file="spec.md", content=content)
    assert [rule.line_text for rule in rules] == ["Every reader MUST validate the input."]
    heading_id = derive_heading_gap_id(spec_file="spec.md", heading="## Absent heading")
    assert heading_id not in {rule.gap_id for rule in rules}
