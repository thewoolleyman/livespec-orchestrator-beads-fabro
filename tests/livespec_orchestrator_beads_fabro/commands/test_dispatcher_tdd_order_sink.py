"""Run-scoped aggregation of the sandbox order guard's decision spans.

The guard emits one `tdd.order.decision` span per product-write verdict and
stamps each with the dispatch correlation it inherited. This sink is the host
side of that: it accrues per-dispatch counters so the terminal calibration
span can carry `tdd.order_refusals` and
`tdd.first_product_write_before_red` without re-querying Honeycomb.

Two properties are load-bearing and each has its own test. The aggregate is
keyed per DISPATCH, so a second dispatch of the same item does not inherit the
first one's refusals. And a dispatch with NO recorded decisions reads as
unobservable (`None`), never as zero refusals — a silent zero is exactly the
"clean run" reading a dropped signal would fabricate.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._otel_enrich_tail import IngestedSpan

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_tdd_order_sink.py"
)

_RESOURCE = {"service.name": "livespec-tdd-order-guard"}


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _decision_span(
    *,
    decision: str = "refuse",
    head_state: str = "closed",
    work_item_id: str | None = "bd-ib-3h5vfq",
    dispatch_id: str | None = "dispatch-7",
    name: str = "tdd.order.decision",
) -> dict[str, object]:
    attributes: list[dict[str, object]] = [
        {"key": "tdd.decision", "value": {"stringValue": decision}},
        {"key": "tdd.head_state", "value": {"stringValue": head_state}},
        {"key": "tdd.path", "value": {"stringValue": "pkg/thing.py"}},
    ]
    if work_item_id is not None:
        attributes.append({"key": "work.item.id", "value": {"stringValue": work_item_id}})
    if dispatch_id is not None:
        attributes.append({"key": "livespec.dispatch.id", "value": {"stringValue": dispatch_id}})
    return {"name": name, "attributes": attributes}


def test_refusals_accrue_per_dispatch_and_read_back_as_a_count(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")

    assert sink.record_decision(span=_decision_span(), resource_attrs=_RESOURCE, at=1.0) is True
    assert sink.record_decision(span=_decision_span(), resource_attrs=_RESOURCE, at=2.0) is True
    assert (
        sink.record_decision(
            span=_decision_span(decision="allow", head_state="open-red"),
            resource_attrs=_RESOURCE,
            at=3.0,
        )
        is True
    )

    signals = sink.signals_for(keys=("dispatch-7", "bd-ib-3h5vfq"))
    assert signals.order_refusals == 2


def test_a_second_dispatch_of_the_same_item_does_not_inherit_the_first_refusals(
    tmp_path: Path,
) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")

    _ = sink.record_decision(
        span=_decision_span(dispatch_id="dispatch-1"), resource_attrs=_RESOURCE, at=1.0
    )

    assert sink.signals_for(keys=("dispatch-1",)).order_refusals == 1
    assert sink.signals_for(keys=("dispatch-2",)).order_refusals is None


def test_a_first_write_under_an_open_red_is_not_a_write_before_red(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")

    _ = sink.record_decision(
        span=_decision_span(decision="allow", head_state="open-red"),
        resource_attrs=_RESOURCE,
        at=1.0,
    )
    _ = sink.record_decision(
        span=_decision_span(decision="refuse", head_state="closed"),
        resource_attrs=_RESOURCE,
        at=2.0,
    )

    signals = sink.signals_for(keys=("dispatch-7",))
    assert signals.first_product_write_before_red is False
    assert signals.order_refusals == 1


def test_a_first_write_with_no_open_red_is_a_write_before_red(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")

    _ = sink.record_decision(
        span=_decision_span(decision="allow", head_state="no-trailers"),
        resource_attrs=_RESOURCE,
        at=1.0,
    )
    _ = sink.record_decision(
        span=_decision_span(decision="allow", head_state="open-red"),
        resource_attrs=_RESOURCE,
        at=2.0,
    )

    assert sink.signals_for(keys=("dispatch-7",)).first_product_write_before_red is True


def test_an_unrecorded_dispatch_reads_as_unobservable_not_as_zero(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")

    signals = sink.signals_for(keys=("dispatch-never-seen", ""))

    assert signals.order_refusals is None
    assert signals.first_product_write_before_red is None


def test_a_span_that_is_not_an_order_decision_is_not_recorded(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")

    assert (
        sink.record_decision(span=_decision_span(name="run_turn"), resource_attrs=_RESOURCE, at=1.0)
        is False
    )
    assert sink.record_decision(span={"attributes": []}, resource_attrs=_RESOURCE, at=1.0) is False
    assert sink.signals_for(keys=("dispatch-7",)).order_refusals is None


def test_an_uncorrelated_decision_is_not_recorded_against_any_dispatch(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")

    assert (
        sink.record_decision(
            span=_decision_span(work_item_id=None, dispatch_id=None),
            resource_attrs=_RESOURCE,
            at=1.0,
        )
        is False
    )
    assert not (tmp_path / "tdd-order.json").exists()


def test_the_resource_block_can_supply_the_correlation(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")

    assert (
        sink.record_decision(
            span=_decision_span(work_item_id=None, dispatch_id=None),
            resource_attrs={**_RESOURCE, "livespec.dispatch.id": "dispatch-9"},
            at=1.0,
        )
        is True
    )
    assert sink.signals_for(keys=("dispatch-9",)).order_refusals == 1


def test_a_malformed_attribute_entry_is_skipped_rather_than_blinding_the_span(
    tmp_path: Path,
) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")
    span: dict[str, object] = {
        "name": "tdd.order.decision",
        "attributes": [
            "a bare string",
            {"key": 7, "value": {"stringValue": "x"}},
            {"key": "tdd.decision", "value": "not-a-mapping"},
            {"key": "tdd.head_state", "value": {"intValue": "3"}},
            {"key": "livespec.dispatch.id", "value": {"stringValue": "dispatch-7"}},
        ],
    }

    assert sink.record_decision(span=span, resource_attrs=_RESOURCE, at=1.0) is True

    signals = sink.signals_for(keys=("dispatch-7",))
    assert signals.order_refusals == 0
    assert signals.first_product_write_before_red is True


def test_a_span_with_no_attributes_list_still_records_from_the_resource(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")
    span: dict[str, object] = {"name": "tdd.order.decision", "attributes": "not-a-list"}

    assert (
        sink.record_decision(
            span=span,
            resource_attrs={**_RESOURCE, "work.item.id": "bd-ib-3h5vfq"},
            at=1.0,
        )
        is True
    )
    assert sink.signals_for(keys=("bd-ib-3h5vfq",)).order_refusals == 0


def test_an_unreadable_or_corrupt_store_reads_as_empty_rather_than_raising(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "tdd-order.json"
    sink = module.TddOrderSink(path=path)

    _ = path.write_text("not json at all", encoding="utf-8")
    assert sink.signals_for(keys=("dispatch-7",)).order_refusals is None

    _ = path.write_text('["a list, not an object"]', encoding="utf-8")
    assert sink.signals_for(keys=("dispatch-7",)).order_refusals is None

    _ = path.write_text('{"dispatch-7": "not an entry object"}', encoding="utf-8")
    assert sink.signals_for(keys=("dispatch-7",)).order_refusals is None

    _ = path.write_text('{"dispatch-7": {"refusals": "not an int"}}', encoding="utf-8")
    assert sink.signals_for(keys=("dispatch-7",)).order_refusals == 0


def test_a_write_failure_is_reported_without_raising(tmp_path: Path) -> None:
    module = _module()
    # A directory where the store file belongs makes every write fail.
    path = tmp_path / "tdd-order.json"
    path.mkdir()
    sink = module.TddOrderSink(path=path)

    assert sink.record_decision(span=_decision_span(), resource_attrs=_RESOURCE, at=1.0) is False


def test_the_persisted_shape_is_a_stable_per_key_counter_object(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "tdd-order.json"
    sink = module.TddOrderSink(path=path)

    _ = sink.record_decision(
        span=_decision_span(decision="refuse", head_state="closed"),
        resource_attrs=_RESOURCE,
        at=12.5,
    )

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["dispatch-7"] == {
        "decisions": 1,
        "refusals": 1,
        "first_head_state": "closed",
        "first_at": 12.5,
    }
    assert stored["bd-ib-3h5vfq"] == stored["dispatch-7"]


def test_the_ingest_helper_records_every_decision_span_in_one_batch(tmp_path: Path) -> None:
    module = _module()
    sink = module.TddOrderSink(path=tmp_path / "tdd-order.json")
    spans = (
        IngestedSpan(resource_attrs=_RESOURCE, span=_decision_span()),
        IngestedSpan(resource_attrs=_RESOURCE, span=_decision_span(name="run_turn")),
        IngestedSpan(resource_attrs=_RESOURCE, span=_decision_span()),
    )

    assert module.record_tdd_order_decisions(sink=sink, spans=spans, at=4.0) == 2
    assert sink.signals_for(keys=("dispatch-7",)).order_refusals == 2


def test_the_ingest_helper_is_a_no_op_when_no_sink_is_wired(tmp_path: Path) -> None:
    module = _module()
    spans = (IngestedSpan(resource_attrs=_RESOURCE, span=_decision_span()),)

    assert module.record_tdd_order_decisions(sink=None, spans=spans, at=4.0) == 0
    assert list(tmp_path.iterdir()) == []
