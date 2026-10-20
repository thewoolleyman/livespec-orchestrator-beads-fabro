"""Tests for the gap-tied work-item record composed for an uncovered heading.

Every case drives the composed record through the REAL store write and reads
it back off the beads seam, rather than asserting on the in-memory
dataclass. The two halves of the assertion are store-side: `origin` and
`gap_id` are FIELDS on the record and become `origin:` / `gap-id:` LABELS
only when the store writes them, so a record whose fields are right and
whose labels never land reads as correct at every in-memory surface — and
the labels are what livespec core's two doctor invariants and the plugin's
own staleness check actually query.

The module is imported through `importlib` inside each case, with the
module path asserted first, so the Red this was authored against failed on
a genuine assertion rather than at collection.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._heading_gaps import (
    SpecHeading,
    derive_heading_gap_id,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._heading_gap_filing"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_heading_gap_filing.py"
)
_HEADING = "## The skill surface"
_CAPTURED_AT = "2026-10-20T00:00:00Z"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _gap() -> SpecHeading:
    return SpecHeading(
        spec_root="SPECIFICATION",
        spec_file="contracts.md",
        heading=_HEADING,
        gap_id=derive_heading_gap_id(spec_file="contracts.md", heading=_HEADING),
    )


def _composed() -> WorkItem:
    """The record the module under test composes for one uncovered heading."""
    assert _MODULE_PATH.is_file(), f"the filing primitive is not shipped at {_MODULE_PATH}"
    module = importlib.import_module(_MODULE)
    composed: object = module.heading_gap_work_item(
        gap=_gap(),
        prefix=_config().prefix,
        rank="m",
        captured_at=_CAPTURED_AT,
    )
    assert isinstance(composed, WorkItem)
    return composed


def _filed_record(*, item: WorkItem) -> dict[str, Any]:
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return cast("dict[str, Any]", client.show_issue(issue_id=item.id))


def test_the_filed_record_carries_the_origin_gap_tied_label() -> None:
    record = _filed_record(item=_composed())
    assert "origin:gap-tied" in record["labels"]


def test_the_filed_record_carries_the_heading_derived_gap_id_label() -> None:
    """The id is the heading's own, so the label anchors to the heading it names."""
    expected = derive_heading_gap_id(spec_file="contracts.md", heading=_HEADING)
    record = _filed_record(item=_composed())
    assert f"gap-id:{expected}" in record["labels"]


def test_the_title_names_the_heading_verbatim() -> None:
    """Verbatim, because the heading IS the key the coverage entry matches on.

    A paraphrase would leave an operator unable to find the row to fill.
    """
    assert _HEADING in _composed().title


def test_the_description_names_the_coverage_entry_to_fill() -> None:
    """The row's registry file and all three of its identifying fields.

    Naming only the heading would leave the implementing change guessing which
    of the registry's 252 rows it owes a test value to.
    """
    description = _composed().description
    assert "tests/heading-coverage.json" in description
    assert "SPECIFICATION" in description
    assert "contracts.md" in description
    assert _HEADING in description
    assert "test" in description


def test_the_record_is_gap_tied_and_awaits_the_admission_valve() -> None:
    """`pending-approval` is the create-time shell the intake router then routes."""
    composed = _composed()
    assert composed.origin == "gap-tied"
    assert composed.status == "pending-approval"
    assert composed.type == "task"


def test_the_record_carries_the_rank_and_capture_instant_it_was_given() -> None:
    """Both are the caller's to supply: one orders a multi-gap pass, one is the clock."""
    composed = _composed()
    assert composed.rank == "m"
    assert composed.captured_at == _CAPTURED_AT


def test_two_compositions_of_one_heading_differ_only_in_their_work_item_id() -> None:
    """The gap-id is the heading's; the work-item id is freshly minted per filing."""
    first = _composed()
    second = _composed()
    assert first.gap_id == second.gap_id
    assert first.id != second.id
    assert first.id.startswith(_config().prefix)
