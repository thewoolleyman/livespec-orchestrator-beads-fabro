"""The carrier map: a scope event that maps each plan assertion to what carries it.

Per the plan Definition-of-Done clause of `SPECIFICATION/contracts.md` (v115): a
scope event is a CARRIER-MAP event when its body carries a `carriers:` block —
one line per plan assertion, in Definition of Done order, naming either the
child work-item ids that carry it or the literal `plan-level proof`.
`record_scope_event` refuses a carrier-map event that leaves a plan assertion
unmapped, naming each unmapped assertion, and refuses one on an epic that lacks
the section. A ruling or deferral with NO `carriers:` block is unaffected: it is
recorded exactly as before and does not restate the map.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

# The block header, spelled here rather than imported, so the test is not
# agreeing with the product module about the one literal it is checking.
CARRIERS_BLOCK_PREFIX = "carriers:"

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)

_FIRST = "The released overseer runs in a real herdr session with the daemon in the top pane."
_SECOND = "The operator drives one loop through that session and sees the agent respond."


def _carries_a_carrier_map(*, body: str) -> bool:
    """Whether a scope-event body carries a `carriers:` block, matched BY LINE.

    A substring test cannot answer this. Every scope event ever recorded opens
    with the header `Requirement carriers:`, which ENDS in `carriers:` — so
    `"carriers:" in body` is True for an ordinary maintainer ruling that carries
    no map at all. The clause defines the block as "the line `carriers:`", and
    the line is what discriminates.
    """
    return CARRIERS_BLOCK_PREFIX in body.splitlines()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _two_assertion_plan(*, project_root: Path, slug: str = "herdr-release") -> str:
    """Create a plan whose Definition of Done carries exactly two assertions."""
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=project_root,
        config=_config(),
        slug=slug,
        title="Herdr release planning",
        research_filename="001-brainstorm.md",
        research_text="Research.\n",
        now="2026-10-04T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="You have run it yourself in a herdr session and seen it work.",
            assertions=(_FIRST, _SECOND),
        ),
    )
    return created["epic_id"]


def test_a_carrier_map_that_leaves_an_assertion_unmapped_is_refused(tmp_path: Path) -> None:
    module_path = _COMMANDS / "_plan_carrier_map.py"

    assert module_path.is_file()

    carrier_map = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._plan_carrier_map"
    )
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    epic_id = _two_assertion_plan(project_root=tmp_path)

    with pytest.raises(carrier_map.PlanCarrierMapRefusedError) as refusal:
        plan.record_scope_event(
            config=_config(),
            epic_id=epic_id,
            requirements=("R1 carries the plan-level Definition of Done",),
            deferrals=(),
            author="factory-test",
            now="2026-10-04T01:00:00Z",
            carriers=("1: bd-ib-child",),
        )

    # The refusal NAMES the unmapped assertion. An ordinal alone would send the
    # author counting bullets to find out which one it meant.
    assert _SECOND in str(refusal.value)
    assert "2" in str(refusal.value)
    # Nothing was recorded: the refusal is a precondition, not a rollback.
    assert plan.read_timeline(config=_config(), epic_id=epic_id) == ()


def test_a_complete_carrier_map_is_recorded(tmp_path: Path) -> None:
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    epic_id = _two_assertion_plan(project_root=tmp_path)

    plan.record_scope_event(
        config=_config(),
        epic_id=epic_id,
        requirements=("R1 carries the plan-level Definition of Done",),
        deferrals=("An asset store is deferred",),
        author="factory-test",
        now="2026-10-04T01:00:00Z",
        carriers=("1: bd-ib-child", "2: plan-level proof"),
    )

    [entry] = plan.read_timeline(config=_config(), epic_id=epic_id)
    assert _carries_a_carrier_map(body=entry.body)
    assert "- 1: bd-ib-child" in entry.body
    assert "- 2: plan-level proof" in entry.body
    # The scope event keeps carrying what it always carried.
    assert "Requirement carriers:" in entry.body
    assert "- An asset store is deferred" in entry.body


def test_a_ruling_with_no_carriers_block_is_recorded_unchanged(tmp_path: Path) -> None:
    """The `discuss-work-item` ruling path must stay exactly as it was.

    A ruling does not restate the map, so it is NOT a carrier-map event and the
    unmapped-assertion refusal must not reach it — on this epic BOTH assertions
    are unmapped, so a refusal that keyed on the section rather than on the
    `carriers:` block would refuse every ruling any plan ever records.
    """
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    epic_id = _two_assertion_plan(project_root=tmp_path)

    plan.record_scope_event(
        config=_config(),
        epic_id=epic_id,
        requirements=("The maintainer ruled the fork posture is not ratified",),
        deferrals=(),
        author="factory-test",
        now="2026-10-04T01:00:00Z",
    )

    [entry] = plan.read_timeline(config=_config(), epic_id=epic_id)
    assert not _carries_a_carrier_map(body=entry.body)
    assert "- The maintainer ruled the fork posture is not ratified" in entry.body
    # The collision the line-anchored helper exists for: the ruling's own header
    # ends in `carriers:`, so a substring check would call this a carrier map.
    assert "carriers:" in entry.body


@pytest.mark.parametrize(
    ("label", "description"),
    [
        ("no heading at all", "Plan anchor for plan/legacy-plan."),
        ("a different first heading", "## Context\n\nFiled before the clause existed.\n"),
        ("the heading with no bullet under it", "## Definition of Done\n"),
    ],
)
def test_a_carrier_map_on_an_epic_with_no_usable_section_is_refused(
    label: str, description: str
) -> None:
    """The second arm of the same clause sentence, across all three shapes.

    Without it, such an epic parses to ZERO assertions, so zero are unmapped and
    the map records clean — accepting a carrier map that maps nothing to nothing,
    which is the one reading the clause forbids outright.

    The third case is the one a `present`-only guard would wave through: the
    heading IS there, so the section is `present`, and it still carries no
    gradeable assertion. The parse already treats an empty section and an absent
    one as the same fact, and this refusal must too.
    """
    carrier_map = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._plan_carrier_map"
    )
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    reset_fake_singleton()
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    epic_id = "bd-ib-legacy"
    client.create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type="epic",
            title="A plan filed before the clause was ratified",
            description=description,
            assignee=None,
            created_at="2026-10-04T00:00:00Z",
        )
    )

    with pytest.raises(carrier_map.PlanCarrierMapRefusedError) as refusal:
        plan.record_scope_event(
            config=_config(),
            epic_id=epic_id,
            requirements=("R1",),
            deferrals=(),
            author="factory-test",
            now="2026-10-04T01:00:00Z",
            carriers=("1: bd-ib-child",),
        )

    assert "Definition of Done" in str(refusal.value), label
    assert plan.read_timeline(config=_config(), epic_id=epic_id) == ()
