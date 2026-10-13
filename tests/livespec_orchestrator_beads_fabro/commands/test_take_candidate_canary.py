"""The committed candidate-canary fixture template renders a dispatchable brief.

Assertion under test: *a committed fixture template defines the canary
work-item's title, description, Definition of Done and References*.

The template is graded through the SANCTIONED parses rather than by reading its
bytes for the strings this test would have chosen — `definition_of_done` is the
one path the ratified clause allows for the section, and `spec_h2_headings` is
what the host-side wall resolves a reference against. A byte-level assertion
would pass on a template the real gate refuses, which is the exact failure the
fixture exists to remove: canaries 5 and 6 of plan `fabro-currency` died at
`dod_gate` on an item whose `References` line named a heading that governs
something else.

`import_module` rather than a top-level import so the FIRST assertion here is
the template's own presence: at Red the template does not exist, which is a
genuine assertion failure rather than a collection error.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_findings import (
    spec_h2_headings,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = _REPO_ROOT / "orchestrator-image" / "candidate-canary-work-item-template.md"
_MODULE = "livespec_orchestrator_beads_fabro.commands.take_candidate_canary"
_ITEM_ID = "bd-ib-cnry01"
_FACTORY = "hp"


def test_the_committed_fixture_template_defines_the_canary_title_and_description() -> None:
    assert _TEMPLATE.is_file(), f"no committed canary fixture template at {_TEMPLATE}"
    module = import_module(_MODULE)

    fixture = module.render_canary_fixture(
        template_text=_TEMPLATE.read_text(encoding="utf-8"),
        item_id=_ITEM_ID,
        factory=_FACTORY,
    )

    assert _ITEM_ID in fixture.title
    assert fixture.title.splitlines() == [fixture.title]
    assert _ITEM_ID in fixture.description
    assert _FACTORY in fixture.description
    # No placeholder may survive rendering: an unsubstituted one reaches the
    # ledger as literal text and the brief then names an item that is not this
    # one.
    assert "@@" not in fixture.title
    assert "@@" not in fixture.description


def test_the_committed_fixture_templates_definition_of_done_parses_and_resolves() -> None:
    assert _TEMPLATE.is_file(), f"no committed canary fixture template at {_TEMPLATE}"
    module = import_module(_MODULE)
    fixture = module.render_canary_fixture(
        template_text=_TEMPLATE.read_text(encoding="utf-8"),
        item_id=_ITEM_ID,
        factory=_FACTORY,
    )

    section = definition_of_done(description=fixture.description)

    assert section.present
    assert len(section.assertions) == 1
    assert section.malformed_proof_modes == ()
    assert section.references
    headings = spec_h2_headings(repo=_REPO_ROOT)
    # An empty heading set means the spec tree could not be read, which is the
    # one reading that would make the subset assertion below vacuous.
    assert headings
    assert set(section.references) <= headings
