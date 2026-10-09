"""`fabro inspect --json` returns a LIST, and our parsers must read it.

The payload fixtures here are trimmed copies of real `fabro inspect --json`
output captured from the pinned build (fabro 0.254.0, 8de6611) on 2026-08-20,
not hand-invented shapes. Six real failed-run payloads were measured: every
one wrapped its record in a single-element list, and every one carried a
`failure` block keyed `('category', 'message')` (four of six also carrying
`causes`) in addition to the outer `('detail', 'reason')` block.

Before this test, both parsers guarded on `isinstance(payload, dict)` and so
returned `None` for every real payload, silently. That made the structured
failure block that `_dispatcher_fabro_failure.py` exists to read permanently
unreachable in production.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_port_failure import (
    fabro_failure_detail_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_status_kind_from_payload,
)

_REAL_INSPECT_PAYLOAD: list[dict[str, Any]] = [
    {
        "run_id": "01M0EFZND0Z7K2SY1H21Q59GVF",
        "parent_id": None,
        "status": {"kind": "failed", "reason": "workflow_error"},
        "conclusion": {
            "timestamp": "2026-08-20T03:21:37.561802885Z",
            "status": "failed",
            "failure": {
                "reason": "workflow_error",
                "detail": {
                    "message": "stage abandon failed with no outgoing fail edge",
                    "category": "deterministic",
                },
            },
            "final_git_commit_sha": "25d7983efc964251287e239bfb3996d0f760abb6",
        },
        "checkpoint": {
            "failure": {
                "message": "stage abandon failed with no outgoing fail edge",
                "category": "deterministic",
            },
        },
    },
]


def test_status_kind_reads_the_single_element_list_fabro_actually_returns() -> None:
    assert fabro_status_kind_from_payload(payload=_REAL_INSPECT_PAYLOAD) == "failed"


def test_failure_detail_reads_the_single_element_list_fabro_actually_returns() -> None:
    detail = fabro_failure_detail_from_payload(payload=_REAL_INSPECT_PAYLOAD)

    assert detail is not None
    assert detail.category == "deterministic"


def test_mapping_payloads_still_parse_unchanged() -> None:
    mapping = _REAL_INSPECT_PAYLOAD[0]

    assert fabro_status_kind_from_payload(payload=mapping) == "failed"
    assert fabro_failure_detail_from_payload(payload=mapping) is not None


def test_unusable_payloads_still_return_none() -> None:
    assert fabro_status_kind_from_payload(payload=None) is None
    assert fabro_status_kind_from_payload(payload=[]) is None
    assert fabro_failure_detail_from_payload(payload=None) is None
    assert fabro_failure_detail_from_payload(payload=["not-a-record"]) is None
