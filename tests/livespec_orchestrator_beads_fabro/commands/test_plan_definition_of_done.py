"""The plan-level Definition of Done: authored at creation, parsed with subject=plan.

Per the plan Definition-of-Done clause of `SPECIFICATION/contracts.md` (v115):
a plan epic's `description` MUST carry the section as its FIRST heading, and the
`plan` front-end MUST author it at plan creation while recording the maintainer's
own statement of what done means VERBATIM in the plan's initial research note,
beside the assertions derived from it.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)

# The maintainer's own words, as the herdr plan's note records them. Kept
# multi-line on purpose: "verbatim" has to survive a line break, which a
# blockquote or list-marker rendering of the statement would silently destroy.
_STATEMENT = (
    "You have run it directly yourself in a herdr session and seen it work.\n"
    "Don't declare done until you have actually used it."
)
_ASSERTIONS = (
    "The released overseer runs in a real herdr session with the daemon in the top pane.",
    "The operator drives one loop through that session and sees the agent respond.",
)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def test_creating_a_plan_authors_the_section_and_records_the_statement_verbatim(
    tmp_path: Path,
) -> None:
    module_path = _COMMANDS / "_plan_definition_of_done.py"

    assert module_path.is_file()

    section_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._plan_definition_of_done"
    )
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    reset_fake_singleton()

    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="herdr-release",
        title="Herdr release planning",
        research_filename="001-brainstorm.md",
        research_text="## Findings\n\nThe daemon needs a pane of its own.\n",
        now="2026-10-04T00:00:00Z",
        definition_of_done=section_module.PlanDefinitionOfDone(
            statement=_STATEMENT,
            assertions=_ASSERTIONS,
        ),
    )

    # The section is the epic description's FIRST heading. `present` is True only
    # in that case, which is why it is asserted through the ONE sanctioned parse
    # rather than by eyeballing the text: a description whose first heading is
    # something else does NOT carry the section, however it reads.
    description = _fake().show_issue(issue_id=created["epic_id"])["description"]
    parsed = definition_of_done(description=description)
    assert parsed.present
    assert tuple(one.text for one in parsed.assertions) == _ASSERTIONS

    # The maintainer's statement is in the initial research note, byte-verbatim
    # across its own line break, beside the assertions derived from it.
    note = (tmp_path / "plan" / "herdr-release" / "research" / "001-brainstorm.md").read_text(
        encoding="utf-8"
    )
    assert _STATEMENT in note
    for assertion in _ASSERTIONS:
        assert assertion in note
    # The research the session brought with it is not displaced by the record.
    assert "The daemon needs a pane of its own." in note


# A plan section carrying exactly what the clause calls a bare bullet: one
# bullet outside any sub-heading, no `Reason:` line, and no `References:` line.
_BARE_SECTION = (
    "Plan anchor for plan/herdr-release.\n"
    "\n"
    "## Definition of Done\n"
    "\n"
    "- The released overseer runs in a real herdr session with the daemon in the top pane.\n"
)


def test_a_bare_plan_bullet_is_host_captured_and_owes_no_reason_or_reference() -> None:
    section_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._plan_definition_of_done"
    )

    assert "plan_definition_of_done" in section_module.__all__

    parsed = section_module.plan_definition_of_done(description=_BARE_SECTION)

    assert parsed.present
    # The plan default. No `factory_captured` mode exists for a plan assertion,
    # because no factory run executes against an epic.
    assert [one.proof_mode for one in parsed.assertions] == ["host_captured"]
    # No finding is owed for the absent `Reason:` line: the bullet declared the
    # plan default rather than opting out of it, so there is nothing to justify.
    assert parsed.malformed_proof_modes == ()
    # No finding is owed for the absent reference line either — a plan MAY
    # precede the specification it will ratify.
    assert parsed.references == ()


def test_the_same_section_read_as_a_work_item_is_still_factory_captured() -> None:
    """The control that proves the mode came from `subject`, not from a moved default.

    Without it, a change that flipped the default for EVERY caller would pass the
    test above identically — and would silently drop every work item's factory
    leg, which is the one outcome the proof-mode enumeration exists to prevent.
    """
    parsed = definition_of_done(description=_BARE_SECTION)

    assert [one.proof_mode for one in parsed.assertions] == ["factory_captured"]


def test_a_plan_human_attested_sub_heading_still_owes_its_reason_line() -> None:
    """`Human-attested` is the one plan sub-heading whose `Reason:` line is required.

    `Host-captured` is permitted and REDUNDANT for a plan — it declares the
    default — so it owes nothing. Treating the two alike in either direction is
    the drift the shared sub-heading table exists to prevent.
    """
    section_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._plan_definition_of_done"
    )
    description = (
        "## Definition of Done\n"
        "\n"
        "- The operator drives one loop and sees the agent respond.\n"
        "\n"
        "### Host-captured\n"
        "\n"
        "- The released build answers on the operator host.\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "- The maintainer agrees the loop felt right.\n"
    )

    parsed = section_module.plan_definition_of_done(description=description)

    assert [one.proof_mode for one in parsed.assertions] == [
        "host_captured",
        "host_captured",
        "human_attested",
    ]
    assert parsed.malformed_proof_modes == ("Human-attested",)
