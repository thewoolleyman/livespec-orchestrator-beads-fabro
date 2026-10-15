"""The run-row fields a host-wide availability read needs off `fabro ps -a`.

Availability evidence has to be discoverable from the factory's own run
records, which means the port's run-row projection has to EXPOSE the two
fields that identify an attempt's repository and its labels. Measured
2026-10-12 on hp (engine 0.254.0, 8869e88): every one of 1626 rows carries
`labels` and `repo_origin_url` beside `run_id`, `start_time`, `status`,
`total_usd_micros` and `wall_time_ms`.

The absent-key cases are not padding. `bd`-style `omitempty` sparseness is
the engine's convention too, so a row that carries no labels carries no
`labels` KEY — and a projection that filled one in would report an
entitlement nobody recorded.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroRunSummary,
    fabro_run_summaries_from_payload,
)

# The two fields this module exists to require. Asserted as a field-name
# set before any attribute is read, so a projection that never exposed
# them fails on a statement of the requirement rather than on an
# attribute error in the middle of a case.
_EXPOSED_FIELDS = frozenset({"labels", "repo_origin_url"})

_ORIGIN = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro"
_LABELS: dict[str, Any] = {
    "work.item.id": "bd-ib-vlctc3",
    "livespec.dispatch.id": "01M4N4V6SEEKVVP88ST0CASGCP",
    "livespec.dispatch.factory": "hp",
    "livespec.repository": "livespec-orchestrator-beads-fabro",
    "livespec.acp.implement.availability": "anthropic.com",
    "livespec.acp.implement.candidate": "sha256:b1a2c3d4e5f60718293a4b5c6d7e8f90",
}


def _row(*, payload: object) -> FabroRunSummary:
    """The single run row a payload projects, with the exposure asserted."""
    summaries = fabro_run_summaries_from_payload(payload=payload)
    assert len(summaries) == 1
    row = summaries[0]
    assert {field.name for field in fields(row)} >= _EXPOSED_FIELDS
    return row


def test_a_measured_run_row_exposes_its_labels_and_repository_origin() -> None:
    """The two host-wide-join fields, read as the engine writes them."""
    row = _row(
        payload=[
            {
                "run_id": "01M4TN6V5M5WSRA57JENX0MVXW",
                "status": {"kind": "succeeded"},
                "goal": "Work-item: bd-ib-vlctc3\n",
                "start_time": "2026-10-12T13:49:26Z",
                "total_usd_micros": 412000,
                "wall_time_ms": 1_440_071,
                "repo_origin_url": _ORIGIN,
                "labels": dict(_LABELS),
            }
        ]
    )

    assert row.repo_origin_url == _ORIGIN
    assert dict(row.labels) == _LABELS
    # The fields the projection already carried are untouched: the two new
    # ones ride beside them rather than in place of any of them.
    assert row.run_id == "01M4TN6V5M5WSRA57JENX0MVXW"
    assert row.status_kind == "succeeded"
    assert row.work_item_id == "bd-ib-vlctc3"
    assert row.total_usd_micros == 412000


def test_a_row_carrying_neither_field_reports_absence_rather_than_a_value() -> None:
    """An `omitempty`-sparse row exposes no labels and no origin, not an invented one."""
    row = _row(payload=[{"run_id": "01SPARSE", "status": "running"}])

    assert row.repo_origin_url is None
    assert dict(row.labels) == {}


def test_an_unmeasured_labels_shape_contributes_nothing() -> None:
    """A non-mapping `labels`, and non-text entries inside one, are dropped.

    Fail-closed for the reason `_detail_text` records about an unmeasured
    payload shape: this parser's own rendering of a foreign value would sit
    where the engine's label belongs, and no consumer could tell the
    difference between that and a label the dispatch really passed.
    """
    not_a_mapping = _row(payload=[{"run_id": "01LIST", "labels": ["work.item.id=x"]}])
    assert dict(not_a_mapping.labels) == {}

    mixed = _row(
        payload=[
            {
                "run_id": "01MIXED",
                "repo_origin_url": 42,
                "labels": {"livespec.repository": "orchestrator", "wall_time_ms": 1440071},
            }
        ]
    )
    assert dict(mixed.labels) == {"livespec.repository": "orchestrator"}
    assert mixed.repo_origin_url is None
