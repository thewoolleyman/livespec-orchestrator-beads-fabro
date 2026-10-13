"""The canary's whole change is one accepted line in the candidate-canary log.

Assertion under test: *the fixture work-item's change is a one-line edit to a
dedicated canary marker file that the repository's check suite accepts*.

Two halves, and the second is what makes the first worth asserting. That the
committed log is accepted today says only that nothing rejects it; the case
below appends the exact entry the rendered fixture NAMES and asserts the log is
still accepted, which is the edit a canary will actually make. The malformed and
missing-heading cases are the positive controls: without them, an acceptance
that can never fail would read identically to one that was earned.

The expected entry is read OUT of the rendered fixture rather than rebuilt here.
The committed template is the single definition of that line; a second
definition in this test would drift from it and still pass, which is precisely
how a canary acquires a brief nothing can satisfy.

Every case opens on the committed log's own presence, so the Red moment is a
genuine assertion failure about the deliverable rather than an attribute error
about the module that grades it.
"""

from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = _REPO_ROOT / "orchestrator-image" / "candidate-canary-work-item-template.md"
_MARKER_RELPATH = "orchestrator-image/candidate-canary-log.md"
_MARKER = _REPO_ROOT / _MARKER_RELPATH
_MODULE = "livespec_orchestrator_beads_fabro.commands.take_candidate_canary"
_ITEM_ID = "bd-ib-cnry02"
_FACTORY = "hp-candidate"
_BACKTICKED = re.compile(r"`([^`]+)`")


def _module() -> ModuleType:
    assert _MARKER.is_file(), f"no committed candidate-canary log at {_MARKER}"
    return import_module(_MODULE)


def _rendered_assertion() -> str:
    """The single gradeable assertion of the rendered fixture's Definition of Done."""
    fixture = _module().render_canary_fixture(
        template_text=_TEMPLATE.read_text(encoding="utf-8"),
        item_id=_ITEM_ID,
        factory=_FACTORY,
    )
    section = definition_of_done(description=fixture.description)
    assert len(section.assertions) == 1
    return section.assertions[0].text


def _named_entry() -> str:
    """The single entry line the rendered fixture's one assertion names."""
    quoted = _BACKTICKED.findall(_rendered_assertion())
    entries = [candidate for candidate in quoted if candidate.startswith("- ")]
    assert len(entries) == 1, f"the assertion must name exactly one entry line, not {quoted}"
    return entries[0]


def test_the_committed_candidate_canary_log_is_accepted_by_the_check_suite() -> None:
    module = _module()

    findings = module.marker_entry_findings(marker_text=_MARKER.read_text(encoding="utf-8"))

    assert findings == ()
    assert module.CANARY_MARKER_RELPATH == _MARKER_RELPATH


def test_the_fixture_names_one_entry_line_against_the_committed_log() -> None:
    assertion = _rendered_assertion()

    assert _MARKER_RELPATH in assertion
    entry = _named_entry()
    assert entry.splitlines() == [entry]
    assert _ITEM_ID in entry
    assert _FACTORY in entry


def test_appending_the_named_entry_leaves_the_log_accepted() -> None:
    module = _module()
    committed = _MARKER.read_text(encoding="utf-8")

    edited = f"{committed.rstrip()}\n{_named_entry()}\n"

    assert edited != committed
    assert module.marker_entry_findings(marker_text=edited) == ()


def test_a_malformed_appended_line_is_a_finding_naming_it() -> None:
    module = _module()
    committed = _MARKER.read_text(encoding="utf-8")

    findings = module.marker_entry_findings(
        marker_text=f"{committed.rstrip()}\nnot a bullet entry\n"
    )

    assert len(findings) == 1
    assert "not a bullet entry" in findings[0]


def test_a_log_with_no_entries_heading_is_a_finding() -> None:
    findings = _module().marker_entry_findings(
        marker_text="# Candidate-canary log\n\nno heading here.\n"
    )

    assert len(findings) == 1
    assert "Entries" in findings[0]


def test_a_log_with_the_heading_and_no_entry_is_a_finding() -> None:
    findings = _module().marker_entry_findings(marker_text="# Candidate-canary log\n\n## Entries\n")

    assert len(findings) == 1
    assert "no entry" in findings[0]
