"""The ONE assertion-count projection intake and terminal calibration share.

Plan slice S4 (`bd-ib-tbgxm4`) repairs the calibration `acceptance_count`
proxy. It counted leading-bullet and Gherkin markers in the item's
DESCRIPTION, which is neither the text the acceptance evaluator grades nor the
number the filing display shows an operator — so the two ends of the same
dispatch reported different counts, and the one the analysis pass consumed was
the wrong one.

This file covers the shared projection that makes them the same number by
construction: both ends read `count`, `source` and the rendered parse line
from ONE primitive over `effective_criteria`, so a divergence is not
expressible rather than merely unlikely.

Two directions of the old defect are asserted deliberately, because each
alone reads as a rounding quibble and together they show the proxy was
uncorrelated with the graded criteria. A description carrying bullets OUTSIDE
its Definition of Done section over-counted; a legacy-source item whose
criteria live in the field under-counted to zero.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    acceptance_count,
    build_calibration_record,
    calibration_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import filing_display
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_signals import assertion_count
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_assertion_count"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_assertion_count.py"
)

# FOUR leading-dash bullets, exactly ONE of them a gradeable assertion: the
# Definition of Done section holds one, and the three that follow sit under a
# later heading the section parse stops at. The legacy description regex read
# this item as four.
_DESCRIPTION_WITH_CONTEXT_BULLETS = (
    "## Definition of Done\n"
    "\n"
    "- The repaired assertion count comes from the sanctioned parser.\n"
    "\n"
    "References: ## Grooming and slice-size calibration\n"
    "\n"
    "## Context\n"
    "\n"
    "- a context bullet\n"
    "- another context bullet\n"
    "- a third context bullet\n"
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": "bd-ib-tbgxm4",
        "type": "feature",
        "status": "active",
        "title": "Repair factory sizing telemetry",
        "description": _DESCRIPTION_WITH_CONTEXT_BULLETS,
        "origin": "freeform",
        "gap_id": None,
        "rank": "a3",
        "assignee": "fabro",
        "depends_on": (),
        "captured_at": "2026-10-06T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "acceptance_criteria": None,
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-tbgxm4",
        status="green",
        stage="done",
        pr_number=4242,
        merge_sha="abc123",
        detail="merged, post-merge janitor green",
    )


def _record(*, item: WorkItem):
    return build_calibration_record(
        item=item,
        outcome=_outcome(),
        repo_name="livespec-orchestrator-beads-fabro",
        journal_records=(),
        wall_clock_seconds=12.5,
        token_cost_micros=4200,
        dispatch_context_size=900,
        merged_pr_diff_size=145,
    )


# --- the shared projection -------------------------------------------------


def test_the_projection_reports_the_count_source_and_parse_line_of_the_parser() -> None:
    """Every field is read off `effective_criteria`, never re-derived."""
    module = _module()
    item = _item()
    resolved = effective_criteria(item=item)

    projection = module.assertion_count_for(item=item)

    assert projection.count == len(resolved.assertions)
    assert projection.source == resolved.source
    assert projection.parse_display == resolved.parse_display()


def test_the_projection_reports_a_legacy_source_by_its_own_name() -> None:
    """A criteria-field item resolves and reports `criteria-field`, not a default."""
    module = _module()
    item = _item(
        description="Plain prose with no Definition of Done section.",
        acceptance_criteria="- One criteria-field assertion.\n",
    )

    projection = module.assertion_count_for(item=item)

    assert projection.count == 1
    assert projection.source == "criteria-field"
    assert "definition-of-done: missing" in projection.parse_display


# --- terminal calibration reads the projection -----------------------------


def test_terminal_calibration_counts_assertions_not_description_bullets() -> None:
    """The over-counting direction: four bullets, one gradeable assertion."""
    item = _item()

    assert acceptance_count(item=item) == 1


def test_terminal_calibration_counts_a_legacy_source_item_rather_than_zero() -> None:
    """The under-counting direction: criteria in the field read as zero before."""
    item = _item(
        description="Plain prose with no Definition of Done section.",
        acceptance_criteria="- One criteria-field assertion.\n- A second one.\n",
    )

    assert acceptance_count(item=item) == 2


def test_the_calibration_record_and_journal_carry_the_resolved_source() -> None:
    """The count alone cannot say WHICH text was counted; the source can."""
    module = _module()
    item = _item()
    projection = module.assertion_count_for(item=item)

    record = _record(item=item)
    journal = calibration_journal_record(record=record)

    assert record.acceptance_count == projection.count
    assert record.acceptance_count_source == projection.source
    assert journal["acceptance_count"] == projection.count
    assert journal["acceptance_count_source"] == "description-definition-of-done"


# --- intake reads the same projection --------------------------------------


def test_intake_filing_display_leads_with_the_projection_parse_line(tmp_path: Path) -> None:
    """Intake's pre-confirmation display renders the projection's own line."""
    module = _module()
    item = _item()

    first_line = filing_display(item=item, cwd=tmp_path).splitlines()[0]

    assert first_line == module.assertion_count_for(item=item).parse_display


def test_intake_and_terminal_calibration_report_the_same_count(tmp_path: Path) -> None:
    """The two ends of one dispatch agree, which is the whole repair."""
    module = _module()
    item = _item()
    projection = module.assertion_count_for(item=item)

    assert projection.parse_display in filing_display(item=item, cwd=tmp_path)
    assert acceptance_count(item=item) == projection.count
    assert f"{projection.count} gradeable assertion(s)" in projection.parse_display


def test_the_tdd_assertion_count_reads_the_same_projection() -> None:
    """Slice S3's `tdd.assertion_count` and this proxy cannot disagree."""
    module = _module()
    item = _item()

    assert assertion_count(item=item) == module.assertion_count_for(item=item).count
