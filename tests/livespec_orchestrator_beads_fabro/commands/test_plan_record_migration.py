"""The plan-record migration's decisions: derive, refuse, anchor, seed, report.

Scenario 112's four scenarios are decisions before they are writes, so they are
asserted here against the decision surface and again in
`test_migrate_plan_records.py` against a tenant and a repository.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_plan_record_migration.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._plan_record_migration"
_PREFIX = "bd-ib"


def _epic(
    *,
    epic_id: str,
    title: str = "Plan topic",
    notes: str = "",
    hint: str = "",
    plan_slug: str = "",
    is_open: bool = True,
    has_next_action: bool = False,
) -> Any:
    module = importlib.import_module(_MODULE_NAME)
    return module.PlanEpic(
        epic_id=epic_id,
        title=title,
        notes=notes,
        spec_commitment_hint=hint,
        plan_slug=plan_slug,
        is_open=is_open,
        has_next_action=has_next_action,
    )


def test_the_decision_module_exposes_the_migration_surface() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    assert module.MIGRATION_SESSION == "plan-record-migration"
    assert sorted(module.__all__) == [
        "MIGRATION_SESSION",
        "PlanEpic",
        "PlanRecordMigrationReport",
        "SlugDecision",
        "UNSEEDED_ACTION_TEXT",
        "anchor_content",
        "derived_plan_slug",
        "render_report",
        "seeded_next_action",
        "slug_decisions",
        "total_writes",
    ]


def test_the_slug_is_derived_from_the_anchor_marker_first() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    derived = module.derived_plan_slug(
        epic=_epic(
            epic_id="bd-ib-kappa",
            title="A title nobody wants as the slug",
            notes="plan_slug=notes-lose",
            hint="plan:kappa",
        )
    )

    assert derived == "kappa"


def test_a_notes_line_wins_when_no_anchor_marker_is_present() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    # A genuine spec commitment is NOT an anchor marker, so it must not be
    # mistaken for a slug source; the notes line is the next authority.
    derived = module.derived_plan_slug(
        epic=_epic(
            epic_id="bd-ib-notes",
            title="A title nobody wants as the slug",
            notes="some prose\n  plan_slug=Noted Slug \nmore prose",
            hint="ratified-obligation-id",
        )
    )

    assert derived == "noted-slug"


def test_the_canonicalized_title_is_the_last_resort() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    # An empty `plan_slug=` line records nothing, so it is absent rather than
    # an instruction to write an empty slug.
    from_empty_notes_line = module.derived_plan_slug(
        epic=_epic(epic_id="bd-ib-empty", title="Retire The Overseer!", notes="plan_slug=   ")
    )
    from_no_notes = module.derived_plan_slug(
        epic=_epic(epic_id="bd-ib-title", title="Retire The Overseer!")
    )

    assert from_empty_notes_line == "retire-the-overseer"
    assert from_no_notes == "retire-the-overseer"


def test_an_epic_already_carrying_a_slug_produces_no_decision() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    decisions = module.slug_decisions(
        epics=[_epic(epic_id="bd-ib-tagged", plan_slug="already-tagged")]
    )

    assert decisions == ()


def test_a_colliding_derivation_is_refused_and_names_both_epics() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    decisions = module.slug_decisions(
        epics=[
            _epic(epic_id="bd-ib-holder", plan_slug="shared-topic"),
            _epic(epic_id="bd-ib-kappa", hint="plan:kappa"),
            _epic(epic_id="bd-ib-collides", title="Shared Topic"),
        ]
    )

    assert [(decision.epic_id, decision.slug, decision.holder_id) for decision in decisions] == [
        ("bd-ib-kappa", "kappa", None),
        ("bd-ib-collides", "shared-topic", "bd-ib-holder"),
    ]


def test_a_slug_claimed_earlier_in_the_same_run_refuses_the_second_epic() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    decisions = module.slug_decisions(
        epics=[
            _epic(epic_id="bd-ib-first", title="Same Topic"),
            _epic(epic_id="bd-ib-second", title="Same Topic"),
        ]
    )

    assert [(decision.epic_id, decision.holder_id) for decision in decisions] == [
        ("bd-ib-first", None),
        ("bd-ib-second", "bd-ib-first"),
    ]


def test_an_absent_anchor_is_written_with_the_epic_id_or_unassigned() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    assert module.anchor_content(current=None, epic_id="bd-ib-alpha") == "bd-ib-alpha"
    assert module.anchor_content(current=None, epic_id=None) == "unassigned"


def test_an_unassigned_anchor_completes_and_a_named_one_stands() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    assert module.anchor_content(current="unassigned\n", epic_id="bd-ib-alpha") == "bd-ib-alpha"
    assert module.anchor_content(current="unassigned\n", epic_id=None) is None
    assert module.anchor_content(current="bd-ib-alpha\n", epic_id="bd-ib-other") is None


def test_a_handoff_naming_an_impl_route_seeds_a_tracking_decision_human_pointer() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    action = module.seeded_next_action(
        handoff_body="- next action: run impl:bd-ib-ott6 through the factory\n",
        prefix=_PREFIX,
    )

    assert (action.kind, action.ref) == ("human", "bd-ib-ott6")
    assert action.text == (
        "Confirm required-result tracking and budget before dispatching bd-ib-ott6."
    )
    assert action.required_result is None
    assert action.budget is None


def test_a_handoff_naming_a_bare_work_item_id_also_requires_a_tracking_decision() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    action = module.seeded_next_action(
        handoff_body="next action: dispatch bd-ib-ott6.2 next\n",
        prefix=_PREFIX,
    )

    assert (action.kind, action.ref) == ("human", "bd-ib-ott6.2")


def test_a_prose_action_naming_no_work_item_seeds_kind_human() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    # `follow-up` is hyphenated prose, not a tenant-prefixed id: reading it as
    # a route would point an unattended resume at nothing.
    action = module.seeded_next_action(
        handoff_body="next action: ask the maintainer for the follow-up ruling\n",
        prefix=_PREFIX,
    )

    assert (action.kind, action.ref) == ("human", "")
    assert action.text == "ask the maintainer for the follow-up ruling"
    assert action.required_result is None
    assert action.budget is None


def test_no_handoff_and_an_ambiguous_handoff_both_seed_kind_none() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    absent = module.seeded_next_action(handoff_body=None, prefix=_PREFIX)
    ambiguous = module.seeded_next_action(
        handoff_body="next action: first\nnext action: second\n",
        prefix=_PREFIX,
    )

    assert (absent.kind, absent.ref, absent.text) == (
        "none",
        "",
        module.UNSEEDED_ACTION_TEXT,
    )
    assert (ambiguous.kind, ambiguous.ref) == ("none", "")
    assert absent.required_result is None
    assert absent.budget is None
    assert ambiguous.required_result is None
    assert ambiguous.budget is None


def test_the_report_renders_writes_skips_and_refusals() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    report = module.PlanRecordMigrationReport(
        slugs_written=("bd-ib-kappa plan_slug=kappa",),
        anchors_written=("plan/kappa/associated_work_item_id -> bd-ib-kappa",),
        next_actions_seeded=("bd-ib-kappa kind=none ref=''",),
        skipped=("bd-ib-tagged already carries plan_slug=tagged",),
        refused=("bd-ib-collides derives plan_slug=shared, already carried by bd-ib-holder",),
    )

    rendered = module.render_report(report=report)

    assert module.total_writes(report=report) == 3
    assert rendered.splitlines() == [
        "migrate-plan-records: 3 write(s)",
        "wrote: bd-ib-kappa plan_slug=kappa",
        "wrote: plan/kappa/associated_work_item_id -> bd-ib-kappa",
        "wrote: bd-ib-kappa kind=none ref=''",
        "skipped: bd-ib-tagged already carries plan_slug=tagged",
        "refused: bd-ib-collides derives plan_slug=shared, already carried by bd-ib-holder",
    ]


def test_an_empty_report_counts_zero_writes() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    report = module.PlanRecordMigrationReport(
        slugs_written=(),
        anchors_written=(),
        next_actions_seeded=(),
        skipped=(),
        refused=(),
    )

    assert module.total_writes(report=report) == 0
    assert module.render_report(report=report) == "migrate-plan-records: 0 write(s)\n"
