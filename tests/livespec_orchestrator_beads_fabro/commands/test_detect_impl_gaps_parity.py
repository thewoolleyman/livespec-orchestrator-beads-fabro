"""Gap-id parity test: detector ⇄ shared `livespec_spec_clauses` primitive.

The detector single-sources its clause extraction + gap-id
derivation from the vendored `livespec_spec_clauses` module
(byte-identical to `livespec`'s `dev-tooling/spec_clauses.py`).
This test pins the two together so the gap-id derivation can
never silently drift:

- `detect_impl_gaps.RuleMatch` IS the shared `RuleMatch` (a
  re-export, not a separate dataclass).
- The detector's `detect_rules` over a fixed spec yields gap-ids
  identical to the shared `derive_gap_id` applied to the same
  (spec_file, heading_path, rule_text) triples.
- A frozen golden vector set (shared with the core-side parity
  test) pins the absolute gap-id values.
"""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import detect_impl_gaps
from livespec_spec_clauses import (
    RuleMatch as SharedRuleMatch,
)
from livespec_spec_clauses import (
    derive_gap_id,
)

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


def _write_spec(*, root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "history" / "v001").mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (root / name).write_text(content)


def test_detector_rulematch_is_the_shared_primitive() -> None:
    # The detector re-exports the shared dataclass rather than
    # defining its own — single-sourcing the clause type.
    assert detect_impl_gaps.RuleMatch is SharedRuleMatch


def test_derive_gap_id_matches_golden_parity_vectors() -> None:
    for spec_file, heading_path, rule_text, expected_gap_id in _GOLDEN_VECTORS:
        actual = derive_gap_id(
            spec_file=spec_file,
            heading_path=heading_path,
            rule_text=rule_text,
        )
        assert actual == expected_gap_id


def test_detect_rules_gap_ids_match_shared_derivation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "spec.md": (
                "# Top\n\n"
                "## Section A\n\n"
                "Every reader MUST validate the input.\n"
                "Callers MUST NOT pass null.\n"
            ),
        },
    )
    rules = detect_impl_gaps.detect_rules(spec_root=spec)
    assert rules, "fixture spec should yield at least one rule"
    for rule in rules:
        expected = derive_gap_id(
            spec_file=rule.spec_file,
            heading_path=rule.heading_path,
            rule_text=rule.line_text,
        )
        assert rule.gap_id == expected
