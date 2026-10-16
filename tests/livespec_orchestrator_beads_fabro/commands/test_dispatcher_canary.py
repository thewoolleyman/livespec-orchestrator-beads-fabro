"""The committed canary fixture — what it defines, and what refuses it.

The fixture is the whole point of `bd-ib-tixpma`: canaries 5 and 6 of plan
`fabro-currency` were taken against a real backlog item whose reference line
named a heading governing something else, so both were refused at `dod_gate` and
measured the ITEM rather than the engine. These tests pin the committed fixture
against the ONE ratified Definition-of-Done parse the gate's host-side wall also
reads, so a fixture that would be refused there cannot sit in the repository
looking fileable.

The module is reached through `import_module` rather than a top-level import so
the first assertion of each test is a genuine one about the artifact rather than
a collection error about the module.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_canary"
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_canary.py"
)


def _canary() -> Any:
    return import_module(_MODULE_NAME)


def test_the_committed_fixture_template_defines_the_canary_work_item() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    fixture_path = _REPO_ROOT / canary.CANARY_FIXTURE_RELATIVE_PATH
    assert fixture_path.is_file(), canary.CANARY_FIXTURE_RELATIVE_PATH

    parsed = canary.read_canary_fixture(repo=_REPO_ROOT)
    assert isinstance(parsed, canary.CanaryFixture), parsed

    # A title, and a description that is NOT the title: the title must not be
    # the description's own first heading, because that is what the ratified
    # parse keys the Definition of Done on.
    assert parsed.title.strip()
    assert parsed.title not in parsed.description

    section = definition_of_done(description=parsed.description)
    assert section.present
    assert section.assertions
    assert section.references
    assert section.malformed_proof_modes == ()

    # The fixture's one deliverable is the dedicated marker file, so its
    # assertion has to name that file rather than any product surface.
    assert canary.CANARY_MARKER_RELATIVE_PATH in section.assertions[0].text


def test_a_fixture_without_a_title_line_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(text="no heading at all\n")

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "no `# ` title line" in refused.detail


def test_a_fixture_whose_title_line_is_empty_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(text="#  \n\n## Definition of Done\n")

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "title line carries no text" in refused.detail


def test_a_fixture_whose_description_carries_no_section_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(text="# Canary\n\nprose only\n")

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "no Definition of Done section" in refused.detail


def test_a_fixture_whose_section_carries_no_assertion_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(
        text="# Canary\n\n## Definition of Done\n\nReferences: ## Fabro runtime constraints\n"
    )

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "no gradeable assertion" in refused.detail


def test_a_fixture_whose_section_carries_no_reference_line_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(
        text="# Canary\n\n## Definition of Done\n\n- The marker file carries one line.\n"
    )

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "no `References:` line" in refused.detail


def test_an_unreadable_fixture_names_the_path_rather_than_raising(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.read_canary_fixture(repo=tmp_path)

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert canary.CANARY_FIXTURE_RELATIVE_PATH in refused.detail
    assert str(tmp_path) in refused.detail
