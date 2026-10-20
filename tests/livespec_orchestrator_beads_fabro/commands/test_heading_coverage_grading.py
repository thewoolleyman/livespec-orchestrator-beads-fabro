"""Tests for grading the coverage registry's rows.

The CLI that renders these verdicts is driven end to end by
`test_detect_impl_gaps.py`. These cases cover the grading decisions
themselves, and in particular the three rows that must produce NO finding —
without which a build that flagged every uncovered heading would satisfy
each positive case here while burying the real defects under this
repository's 128 sanctioned debt rows.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._heading_coverage_grading import (
    CoverageFinding,
    grade_coverage_entries,
)
from livespec_orchestrator_beads_fabro.commands._heading_coverage_map import (
    TODO_SENTINEL,
    CoverageEntry,
)

_EXISTING_NODE = "tests.integration.test_present.test_present_case"


def _entry(
    *,
    position: int = 0,
    spec_root: str = "SPECIFICATION",
    spec_file: str = "spec.md",
    heading: str = "## A heading",
    test: str = TODO_SENTINEL,
) -> CoverageEntry:
    return CoverageEntry(
        position=position,
        spec_root=spec_root,
        spec_file=spec_file,
        heading=heading,
        test=test,
    )


def _write_existing_test(*, project_root: Path) -> None:
    module = project_root / "tests" / "integration" / "test_present.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text("def test_present_case() -> None:\n    pass\n")


def test_a_row_naming_an_existing_test_covers_its_triple_and_owes_nothing(
    tmp_path: Path,
) -> None:
    _write_existing_test(project_root=tmp_path)
    grading = grade_coverage_entries(entries=(_entry(test=_EXISTING_NODE),), project_root=tmp_path)
    assert grading.covered == frozenset({("SPECIFICATION", "spec.md", "## A heading")})
    assert grading.findings == ()


def test_a_dangling_row_covers_nothing_and_owes_a_named_finding(tmp_path: Path) -> None:
    grading = grade_coverage_entries(
        entries=(_entry(test="tests.integration.test_gone.test_case"),),
        project_root=tmp_path,
    )
    assert grading.covered == frozenset()
    [finding] = grading.findings
    assert finding.defect == "dangling-test"
    assert "tests.integration.test_gone.test_case" in finding.detail
    assert "## A heading" in finding.detail


def test_a_row_stating_no_test_value_covers_nothing_and_owes_a_named_finding(
    tmp_path: Path,
) -> None:
    grading = grade_coverage_entries(entries=(_entry(test=""),), project_root=tmp_path)
    assert grading.covered == frozenset()
    [finding] = grading.findings
    assert finding.defect == "incomplete-entry"
    assert "states no test value" in finding.detail


def test_the_todo_sentinel_covers_nothing_and_owes_nothing(tmp_path: Path) -> None:
    """The discriminator between a defect and sanctioned debt."""
    grading = grade_coverage_entries(entries=(_entry(),), project_root=tmp_path)
    assert grading.covered == frozenset()
    assert grading.findings == ()


def test_a_row_identifying_no_heading_is_not_graded_here(tmp_path: Path) -> None:
    """It covers nothing and owes nothing THIS pass — its own verdict is elsewhere."""
    grading = grade_coverage_entries(entries=(_entry(heading=""),), project_root=tmp_path)
    assert grading.covered == frozenset()
    assert grading.findings == ()


def test_one_real_row_covers_a_triple_its_duplicate_todo_row_leaves_open(
    tmp_path: Path,
) -> None:
    """A `TODO` row beside a real one must not re-open a heading a test exercises.

    This is what keeps "exactly one gap per heading" true: the registry is
    hand-edited, so one heading legitimately reaches two rows.
    """
    _write_existing_test(project_root=tmp_path)
    grading = grade_coverage_entries(
        entries=(_entry(position=0), _entry(position=1, test=_EXISTING_NODE)),
        project_root=tmp_path,
    )
    assert grading.covered == frozenset({("SPECIFICATION", "spec.md", "## A heading")})
    assert grading.findings == ()


def test_findings_keep_registry_file_order(tmp_path: Path) -> None:
    """So two runs over an unchanged registry surface the identical stderr."""
    grading = grade_coverage_entries(
        entries=(
            _entry(position=0, heading="## First", test=""),
            _entry(position=1, heading="## Second", test="tests.gone.test_x.test_y"),
        ),
        project_root=tmp_path,
    )
    assert [finding.defect for finding in grading.findings] == [
        "incomplete-entry",
        "dangling-test",
    ]


def test_a_finding_renders_its_defect_and_its_detail() -> None:
    rendered = CoverageFinding(defect="dangling-test", detail="entry 7 (…)").render()
    assert rendered == "FINDING: dangling-test — entry 7 (…)"
