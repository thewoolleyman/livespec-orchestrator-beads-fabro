"""The human attestation of a held spec-change-tier item, written and read back.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` gives a held item a
human way through: a human attests that an existing H2 heading of the ratified
specification states the item's asked-for behaviour. The attestation is "a human
override of the governing-heading verdict ... not a cached model verdict", and
while "that attested input and the cited clause's heading and body are
unchanged" every taking uses the attested `stated` verdict. "A change elsewhere
in the specification does not void it; a change to the attested input or to the
cited clause voids it."

THE LOAD-BEARING CASES ARE THE THREE VOIDS AND THE ONE SURVIVAL. A reading that
never voided would keep a released item released after the clause it relies on
was rewritten; a reading that voided on any revision would re-hold an item for a
change that touched nothing it cites. Each void is therefore asserted beside the
unrelated revision that must NOT void it, on the SAME fixture.

THE MODULE IS REACHED THROUGH ITS PATH FIRST, so the Red fails on a genuine
assertion about the module's existence rather than on an import error.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import clauses_named
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from types import ModuleType

_MODULE = "livespec_orchestrator_beads_fabro.commands._spec_tier_attestation"
_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_spec_tier_attestation.py"
)

_HEADING = "## Clause A"
_OTHER_HEADING = "## Clause B"
_FIRST_ASSERTION = "The first thing the item asks for."
_SECOND_ASSERTION = "The second thing the item asks for."
_TREE = {"contracts.md": f"# Contracts\n\n{_HEADING}\n\nBody A.\n\n{_OTHER_HEADING}\n\nBody B.\n"}


def _module() -> ModuleType:
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(_MODULE)


def _item(*, description: str | None = None) -> WorkItem:
    return WorkItem(
        id="bd-ib-attest",
        type="feature",
        status="backlog",
        title="Attest an existing clause",
        description=(
            f"## Definition of Done\n\n- {_FIRST_ASSERTION}\n- {_SECOND_ASSERTION}\n\n"
            f"References: {_HEADING}\n"
            if description is None
            else description
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _comment(*, item: WorkItem | None = None, heading: str = _HEADING) -> str:
    module: Any = _module()
    clause = clauses_named(spec_tree=_TREE, headings=[heading])[0]
    return module.attestation_comment(
        item=_item() if item is None else item,
        actor="human:chad",
        clause=clause,
        spec_version="12",
    )


def test_the_comment_records_the_actor_the_clause_and_what_was_attested() -> None:
    module: Any = _module()

    recorded = module.recorded_attestation(comments=(_comment(),))

    assert recorded is not None
    assert recorded.actor == "human:chad"
    assert recorded.heading == _HEADING
    assert recorded.spec_file == "contracts.md"
    assert recorded.spec_version == "12"
    clause = clauses_named(spec_tree=_TREE, headings=[_HEADING])[0]
    assert recorded.clause_digest == module.clause_digest(clause=clause)
    body = _comment()
    assert _FIRST_ASSERTION in body
    assert _SECOND_ASSERTION in body
    assert "Attest an existing clause" in body


def test_the_cited_clause_stands_while_the_input_and_the_clause_are_unchanged() -> None:
    module: Any = _module()
    comments = (_comment(),)

    standing = module.standing_attestation(item=_item(), comments=comments, spec_tree=_TREE)

    assert standing is not None
    assert standing.heading == _HEADING
    assert standing.body == clauses_named(spec_tree=_TREE, headings=[_HEADING])[0].body


def test_a_change_elsewhere_in_the_specification_does_not_void_it() -> None:
    module: Any = _module()
    elsewhere = {
        **_TREE,
        "contracts.md": _TREE["contracts.md"].replace("Body B.", "Body B, rewritten."),
        "scenarios.md": "# Scenarios\n\n## A new scenario\n\nText.\n",
    }

    standing = module.standing_attestation(
        item=_item(), comments=(_comment(),), spec_tree=elsewhere
    )

    assert standing is not None
    assert standing.heading == _HEADING


def test_a_change_to_the_cited_clause_voids_it() -> None:
    module: Any = _module()
    rewritten = {"contracts.md": _TREE["contracts.md"].replace("Body A.", "Body A, rewritten.")}

    assert (
        module.standing_attestation(item=_item(), comments=(_comment(),), spec_tree=rewritten)
        is None
    )


def test_a_cited_heading_that_no_longer_resolves_voids_it() -> None:
    module: Any = _module()
    removed = {"contracts.md": _TREE["contracts.md"].replace(_HEADING, "## Renamed clause")}

    assert (
        module.standing_attestation(item=_item(), comments=(_comment(),), spec_tree=removed) is None
    )


def test_a_change_to_the_attested_input_voids_it() -> None:
    module: Any = _module()
    edited = _item(
        description=(
            f"## Definition of Done\n\n- {_FIRST_ASSERTION}\n- A third thing.\n\n"
            f"References: {_HEADING}\n"
        )
    )

    assert module.standing_attestation(item=edited, comments=(_comment(),), spec_tree=_TREE) is None


def test_the_newest_attestation_is_the_one_that_counts() -> None:
    module: Any = _module()
    older = _comment(heading=_OTHER_HEADING)
    newer = _comment()

    standing = module.standing_attestation(item=_item(), comments=(older, newer), spec_tree=_TREE)

    assert standing is not None
    assert standing.heading == _HEADING


def test_no_attestation_means_nothing_stands() -> None:
    module: Any = _module()

    assert module.recorded_attestation(comments=()) is None
    assert (
        module.standing_attestation(item=_item(), comments=("an ordinary rider",), spec_tree=_TREE)
        is None
    )


def test_a_rider_quoting_the_marker_is_not_an_attestation() -> None:
    module: Any = _module()
    quoted = "A rider that quotes the marker below.\n\n" + _comment()

    assert module.recorded_attestation(comments=(quoted,)) is None


def test_a_record_missing_a_comparison_field_is_not_an_attestation() -> None:
    module: Any = _module()
    truncated = "\n".join(
        line for line in _comment().splitlines() if not line.startswith("clause-digest")
    )

    assert module.recorded_attestation(comments=(truncated,)) is None
