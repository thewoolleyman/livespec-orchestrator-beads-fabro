"""The terminal calibration span's TDD order projection.

Plan slice S3 (`bd-ib-3h5vfq`) puts seven `tdd.*` fields plus the implement
adapter on the terminal `dispatcher.calibration` span. This file covers the
whole projection end to end: the assembly from the commit-series and
hook-event derivations, the sanctioned assertion count, the journal record's
flat keys, the span attributes actually rendered, and the receive-side
allowlist that decides whether any of it survives egress.

Three behaviours are asserted deliberately rather than assumed. An
unobservable field is OMITTED from the span (never shipped as the literal
string "None", and never as zero). The journal keeps the explicit null,
because a JSON null on the journal is the honest record of "we looked and
there was nothing". And every projected key is named in
`ATTRIBUTE_ALLOWLIST` — the receive stage rebuilds attributes from that
allowlist, so an unnamed key is dropped with no error and the signal would be
silently empty.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    build_calibration_record,
    calibration_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_span import (
    calibration_request_line,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits import TddCommitSignals
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import TddOrderSignals
from livespec_orchestrator_beads_fabro.commands._otel_scrub import ATTRIBUTE_ALLOWLIST
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_signals"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_tdd_signals.py"
)

_EXPECTED_KEYS = (
    "tdd.red_commit_count",
    "tdd.green_commit_count",
    "tdd.suite_green_count",
    "tdd.red_green_gap_seconds_median",
    "tdd.first_product_write_before_red",
    "tdd.order_refusals",
    "tdd.assertion_count",
    "livespec.implement.adapter",
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": "bd-ib-3h5vfq",
        "type": "feature",
        "status": "active",
        "title": "Publish factory TDD calibration signals",
        "description": "Do the thing.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a2",
        "assignee": "fabro",
        "depends_on": (),
        "captured_at": "2026-10-02T00:00:00Z",
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
        work_item_id="bd-ib-3h5vfq",
        status="green",
        stage="done",
        pr_number=4242,
        merge_sha="abc123",
        detail="merged",
    )


def _commits() -> TddCommitSignals:
    return TddCommitSignals(
        red_commit_count=5,
        green_commit_count=5,
        suite_green_count=1,
        red_green_gap_seconds_median=197.4,
    )


def _span_attributes(*, line: str) -> dict[str, object]:
    body = json.loads(line)
    span = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    return {entry["key"]: entry["value"] for entry in span["attributes"]}


# --- assembly --------------------------------------------------------------


def test_the_signals_assemble_from_the_commit_and_hook_derivations() -> None:
    module = _module()

    signals = module.tdd_signals(
        item=_item(acceptance_criteria="- One thing.\n- Another thing.\n"),
        commits=_commits(),
        order=TddOrderSignals(order_refusals=3, first_product_write_before_red=True),
        adapter="claude-acp",
    )

    assert signals.red_commit_count == 5
    assert signals.green_commit_count == 5
    assert signals.suite_green_count == 1
    assert signals.first_product_write_before_red is True
    assert signals.order_refusals == 3
    assert signals.assertion_count == 2
    assert signals.adapter == "claude-acp"


def test_the_gap_median_is_projected_as_whole_seconds() -> None:
    module = _module()

    signals = module.tdd_signals(
        item=_item(),
        commits=_commits(),
        order=TddOrderSignals(order_refusals=0, first_product_write_before_red=False),
        adapter="claude-acp",
    )

    assert signals.red_green_gap_seconds_median == 197


def test_the_assertion_count_uses_the_sanctioned_effective_criteria_parser() -> None:
    module = _module()
    # Four bullets, each one gradeable assertion the evaluator segments.
    criteria = "- First thing.\n- Second thing.\n- Third thing.\n- Fourth thing.\n"

    assert module.assertion_count(item=_item(acceptance_criteria=criteria)) == 4
    # A Definition of Done section in the description outranks the field, which
    # is the same precedence the acceptance evaluator applies.
    assert (
        module.assertion_count(
            item=_item(
                description="## Definition of Done\n\n- Only one assertion.\n",
                acceptance_criteria=criteria,
            )
        )
        == 1
    )


def test_an_absent_commit_series_leaves_every_commit_field_unobservable() -> None:
    module = _module()

    signals = module.tdd_signals(
        item=_item(),
        commits=None,
        order=TddOrderSignals(order_refusals=None, first_product_write_before_red=None),
        adapter=None,
    )

    assert signals.red_commit_count is None
    assert signals.green_commit_count is None
    assert signals.suite_green_count is None
    assert signals.red_green_gap_seconds_median is None
    assert signals.order_refusals is None
    assert signals.first_product_write_before_red is None
    assert signals.adapter is None


def test_an_absent_gap_median_stays_absent_rather_than_rounding_to_zero() -> None:
    module = _module()

    signals = module.tdd_signals(
        item=_item(),
        commits=TddCommitSignals(
            red_commit_count=1,
            green_commit_count=0,
            suite_green_count=0,
            red_green_gap_seconds_median=None,
        ),
        order=TddOrderSignals(order_refusals=None, first_product_write_before_red=None),
        adapter=None,
    )

    assert signals.red_green_gap_seconds_median is None
    assert signals.red_commit_count == 1


def test_the_unobserved_constant_is_every_field_absent() -> None:
    module = _module()

    fields = module.tdd_signal_fields(signals=module.UNOBSERVED_TDD_SIGNALS)

    assert set(fields) == set(_EXPECTED_KEYS)
    assert all(value is None for value in fields.values())


# --- projection ------------------------------------------------------------


def test_the_journal_record_carries_every_projected_key_including_nulls() -> None:
    module = _module()
    record = build_calibration_record(
        item=_item(acceptance_criteria="- One thing.\n"),
        outcome=_outcome(),
        repo_name="livespec-orchestrator-beads-fabro",
        journal_records=(),
        wall_clock_seconds=12.0,
        token_cost_micros=7,
        dispatch_context_size=40,
        merged_pr_diff_size=50,
        tdd=module.tdd_signals(
            item=_item(acceptance_criteria="- One thing.\n"),
            commits=_commits(),
            order=TddOrderSignals(order_refusals=0, first_product_write_before_red=False),
            adapter="claude-acp",
        ),
    )

    journal = calibration_journal_record(record=record)

    assert journal["tdd.red_commit_count"] == 5
    assert journal["tdd.green_commit_count"] == 5
    assert journal["tdd.suite_green_count"] == 1
    assert journal["tdd.red_green_gap_seconds_median"] == 197
    assert journal["tdd.first_product_write_before_red"] is False
    assert journal["tdd.order_refusals"] == 0
    assert journal["tdd.assertion_count"] == 1
    assert journal["livespec.implement.adapter"] == "claude-acp"


def test_an_unwired_tdd_input_journals_explicit_nulls_not_zeros() -> None:
    record = build_calibration_record(
        item=_item(),
        outcome=_outcome(),
        repo_name="repo",
        journal_records=(),
        wall_clock_seconds=1.0,
        token_cost_micros=None,
        dispatch_context_size=1,
        merged_pr_diff_size=None,
    )

    journal = calibration_journal_record(record=record)

    for key in _EXPECTED_KEYS:
        assert journal[key] is None, key


def test_the_span_renders_every_observed_tdd_attribute() -> None:
    module = _module()
    record = build_calibration_record(
        item=_item(acceptance_criteria="- One thing.\n- Two things.\n"),
        outcome=_outcome(),
        repo_name="livespec-orchestrator-beads-fabro",
        journal_records=(),
        wall_clock_seconds=12.0,
        token_cost_micros=7,
        dispatch_context_size=40,
        merged_pr_diff_size=50,
        tdd=module.tdd_signals(
            item=_item(acceptance_criteria="- One thing.\n- Two things.\n"),
            commits=_commits(),
            order=TddOrderSignals(order_refusals=3, first_product_write_before_red=True),
            adapter="claude-acp",
        ),
    )

    attributes = _span_attributes(line=calibration_request_line(record=record, now_ns=1))

    assert attributes["tdd.red_commit_count"] == {"intValue": "5"}
    assert attributes["tdd.green_commit_count"] == {"intValue": "5"}
    assert attributes["tdd.suite_green_count"] == {"intValue": "1"}
    assert attributes["tdd.red_green_gap_seconds_median"] == {"intValue": "197"}
    assert attributes["tdd.first_product_write_before_red"] == {"boolValue": True}
    assert attributes["tdd.order_refusals"] == {"intValue": "3"}
    assert attributes["tdd.assertion_count"] == {"intValue": "2"}
    assert attributes["livespec.implement.adapter"] == {"stringValue": "claude-acp"}


def test_an_unobservable_field_is_omitted_from_the_span_never_stringified() -> None:
    record = build_calibration_record(
        item=_item(),
        outcome=_outcome(),
        repo_name="repo",
        journal_records=(),
        wall_clock_seconds=1.0,
        token_cost_micros=None,
        dispatch_context_size=1,
        merged_pr_diff_size=None,
    )

    attributes = _span_attributes(line=calibration_request_line(record=record, now_ns=1))

    for key in _EXPECTED_KEYS:
        assert key not in attributes, key
    assert "None" not in json.dumps(
        {key: value for key, value in attributes.items() if key.startswith("tdd.")}
    )


def test_every_projected_key_survives_the_receive_side_allowlist() -> None:
    module = _module()

    assert set(module.tdd_signal_fields(signals=module.UNOBSERVED_TDD_SIGNALS)) <= set(
        ATTRIBUTE_ALLOWLIST
    ), "a key absent from the host-side allowlist is DROPPED on receipt"
    assert set(_EXPECTED_KEYS) <= set(ATTRIBUTE_ALLOWLIST)


def test_the_projected_key_set_is_declared_once_and_matches_the_contract() -> None:
    module = _module()

    assert module.TDD_PROJECTED_KEYS == _EXPECTED_KEYS
