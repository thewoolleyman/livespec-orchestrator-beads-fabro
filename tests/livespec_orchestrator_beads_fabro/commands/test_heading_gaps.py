"""Tests for the governed spec tree's H2-heading enumeration.

The CLI above this module is driven end to end by
`test_detect_impl_gaps.py`. These cases cover what that surface cannot
observe: the heading-enumeration rules that decide which headings EXIST
at all, and the two spellings a spec root can reach the coverage
registry under.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._heading_gaps import (
    derive_heading_gap_id,
    live_headings,
    scan_heading_gaps,
)
from returns.io import IOSuccess
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io


def _write_spec(*, root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "history" / "v001").mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (root / name).write_text(content)


def test_every_governed_nlspec_file_is_walked(tmp_path: Path) -> None:
    """All five template-declared NLSpec names are in the governed population.

    Enumerated as one case rather than five, and asserted as the WHOLE set
    rather than by membership, so a name dropped from the population fails
    here instead of silently removing a file's headings from every run.
    """
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "spec.md": "## From spec\n",
            "contracts.md": "## From contracts\n",
            "constraints.md": "## From constraints\n",
            "non-functional-requirements.md": "## From nfr\n",
            "scenarios.md": "## From scenarios\n",
        },
    )
    headings = live_headings(spec_root=spec, project_root=tmp_path)
    assert {heading.spec_file for heading in headings} == {
        "spec.md",
        "contracts.md",
        "constraints.md",
        "non-functional-requirements.md",
        "scenarios.md",
    }


def test_headings_keep_document_order_within_a_file(tmp_path: Path) -> None:
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "## Zebra\n\n## Apple\n\n## Mango\n"})
    headings = live_headings(spec_root=spec, project_root=tmp_path)
    assert [heading.heading for heading in headings] == ["## Zebra", "## Apple", "## Mango"]


def test_files_are_walked_in_sorted_order(tmp_path: Path) -> None:
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={"spec.md": "## From spec\n", "constraints.md": "## From constraints\n"},
    )
    headings = live_headings(spec_root=spec, project_root=tmp_path)
    assert [heading.spec_file for heading in headings] == ["constraints.md", "spec.md"]


def test_only_h2_headings_are_enumerated(tmp_path: Path) -> None:
    """H1, H3 and a deeper heading are not registry rows, so they are not gaps."""
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "spec.md": (
                "# An H1\n\n## An H2\n\n### An H3\n\n#### An H4\n\n"
                "Not a heading: ##missing space\n"
            )
        },
    )
    headings = live_headings(spec_root=spec, project_root=tmp_path)
    assert [heading.heading for heading in headings] == ["## An H2"]


def test_trailing_whitespace_is_stripped_from_a_heading(tmp_path: Path) -> None:
    """The registry records the rstripped line, so the match must key on it too."""
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "## Padded heading   \n"})
    headings = live_headings(spec_root=spec, project_root=tmp_path)
    assert [heading.heading for heading in headings] == ["## Padded heading"]


def test_a_scenario_prefixed_heading_is_granular_only_in_scenarios(tmp_path: Path) -> None:
    """Both halves in one case: they are one rule, and each is the other's control.

    Asserted together because a build that enumerated `## Scenario:` headings
    everywhere, and one that enumerated them nowhere, each satisfy one half on
    its own.
    """
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "contracts.md": "## Scenario: out of registry scope\n\n## In scope\n",
            "scenarios.md": "## Scenario: tracked granularly\n",
        },
    )
    headings = live_headings(spec_root=spec, project_root=tmp_path)
    assert [(heading.spec_file, heading.heading) for heading in headings] == [
        ("contracts.md", "## In scope"),
        ("scenarios.md", "## Scenario: tracked granularly"),
    ]


def test_a_heading_inside_a_fenced_block_is_still_enumerated(tmp_path: Path) -> None:
    """Parity with the registry, which was built by a fence-blind enumeration.

    Skipping it here would make a registry row that the shared heading-coverage
    gate REQUIRES identify no live heading.
    """
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={"spec.md": "## Real heading\n\n```markdown\n## Quoted heading\n```\n"},
    )
    headings = live_headings(spec_root=spec, project_root=tmp_path)
    assert [heading.heading for heading in headings] == ["## Real heading", "## Quoted heading"]


def test_a_spec_root_inside_the_project_is_labelled_by_its_relative_path(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "nested" / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "## A heading\n"})
    [heading] = live_headings(spec_root=spec, project_root=tmp_path)
    assert heading.spec_root == "nested/SPECIFICATION"


def test_a_spec_root_outside_the_project_is_labelled_by_its_own_name(
    tmp_path: Path,
) -> None:
    """The registry could only ever name such a root by its directory name."""
    spec = tmp_path / "outside" / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "## A heading\n"})
    [heading] = live_headings(spec_root=spec, project_root=tmp_path / "project")
    assert heading.spec_root == "SPECIFICATION"


def test_each_heading_carries_its_own_derived_gap_id(tmp_path: Path) -> None:
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "## Absent heading\n"})
    [heading] = live_headings(spec_root=spec, project_root=tmp_path)
    assert heading.gap_id == derive_heading_gap_id(spec_file="spec.md", heading="## Absent heading")


def test_scan_without_a_since_version_reports_every_live_heading(tmp_path: Path) -> None:
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "## One\n\n## Two\n"})
    scan = scan_heading_gaps(spec_root=spec, project_root=tmp_path)
    assert isinstance(scan, IOSuccess)
    assert [gap.heading for gap in unsafe_perform_io(scan.unwrap()).gaps] == ["## One", "## Two"]


def test_scan_with_an_existing_since_version_succeeds(tmp_path: Path) -> None:
    """A version that EXISTS is the control for the failure case below.

    Without it, a scan that failed on every `since_version` would satisfy the
    absent-version assertion exactly as well as a correct one.
    """
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "## One\n"})
    scan = scan_heading_gaps(spec_root=spec, project_root=tmp_path, since_version=1)
    assert is_successful(scan)


def test_scan_with_an_absent_since_version_rides_the_failure_track(tmp_path: Path) -> None:
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "## One\n"})
    scan = scan_heading_gaps(spec_root=spec, project_root=tmp_path, since_version=999)
    assert not is_successful(scan)
    assert "v999" in str(unsafe_perform_io(scan.failure()))
