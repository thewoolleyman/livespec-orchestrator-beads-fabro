"""Run identity, duration and token evidence the candidate emits reach the port.

Two pieces of evidence the Petri-era engine emits (0.378.0-nightly.0, measured
2026-10-08 — research note 006 of `plan/fabro-currency`) had nowhere to land:

- `ps --json` records carry `wall_time_ms` beside `total_usd_micros`. The run id
  and the cost were already read; the duration was dropped on the floor, so the
  cost evidence reached the audit path with no measure of what it bought.
- the event stream carries `token.emitted` bodies, which is the first time any
  token signal has existed at all. On the pinned 0.254 build there is none:
  `fabro events` carried no cost or token fields whatsoever, which is the
  measurement `_dispatcher_cost`'s own docstring records.

WHAT IS DELIBERATELY NOT ASSERTED HERE, because it was never measured. Research
notes 006 and 007 name the `token.emitted` EVENT but record none of its body's
field names. So the reader below is NAME-TOLERANT across the usual spellings
rather than bound to one this repository has never seen, and it returns `None`
when it recognizes nothing — it does not invent a schema and then report zero
tokens, because a confident zero is indistinguishable from an unparsed body and
the two support opposite conclusions about whether the engine emits the signal.

That tolerance is the honest encoding of the Definition of Done's own
qualifier, "when the candidate emits them": the port is ready for the field the
moment a measured body names it, and silent until then.

The two new surfaces are reached through `importlib` with a `hasattr`
assertion first, rather than imported at module top. A top-level import of a
name that does not yet exist dies at COLLECTION, which proves only that the
module lacks the name — not that the behaviour is unimplemented.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

_RECORDS = "livespec_orchestrator_beads_fabro.commands._fabro_port_records"
_RUN_ID = "01M4DCQPCX6Z"


def _petri_ps_record() -> list[dict[str, Any]]:
    """A `ps --json` record carrying the full Petri-era reader field set."""
    return [
        {
            "goal": "Work-item: bd-ib-227cbw\n",
            "labels": [],
            "parent_id": None,
            "repo_origin_url": "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro",
            "run_id": _RUN_ID,
            "source_directory": "/workspace",
            "start_time": "2026-10-08T08:00:00Z",
            "status": {"kind": "succeeded", "reason": "completed"},
            "total_usd_micros": 412_000,
            "wall_time_ms": 903_221,
            "workflow_graph_name": "ImplementWorkItem",
            "workflow_name": "implement-work-item",
            "workflow_slug": "implement-work-item",
        }
    ]


def test_the_ps_record_carries_run_identity_cost_and_duration() -> None:
    records = importlib.import_module(_RECORDS)
    summaries = records.fabro_run_summaries_from_payload(payload=_petri_ps_record())
    summary = summaries[0]

    assert hasattr(summary, "wall_time_ms")

    assert summary.run_id == _RUN_ID
    assert summary.work_item_id == "bd-ib-227cbw"
    assert summary.total_usd_micros == 412_000
    assert summary.wall_time_ms == 903_221


def test_a_record_without_a_wall_time_reports_none_not_zero() -> None:
    """A 0.254 record carries no `wall_time_ms`, and absence is not a duration."""
    records = importlib.import_module(_RECORDS)
    legacy: list[dict[str, Any]] = [
        {"run_id": _RUN_ID, "status": "succeeded", "goal": "x", "total_usd_micros": None}
    ]

    summary = records.fabro_run_summaries_from_payload(payload=legacy)[0]

    assert hasattr(summary, "wall_time_ms")
    assert summary.wall_time_ms is None
    assert summary.total_usd_micros is None


def _token_event(*, seq: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": _RUN_ID,
        "stream_seq": seq,
        "kind": "token.emitted",
        "id": f"e{seq}",
        "recorded_at": 1_760_000_000_000 + seq,
        "item": {
            "seq": seq,
            "recorded_at": 1_760_000_000_000 + seq,
            "record": {"kind": "token.emitted", "body": {"event": "token.emitted", **body}},
        },
    }


def test_token_emitted_events_are_summed_across_the_stream() -> None:
    records = importlib.import_module(_RECORDS)

    assert hasattr(records, "fabro_token_usage_from_payload")

    payload = json.loads(
        json.dumps(
            [
                _token_event(seq=1, body={"input_tokens": 1_200, "output_tokens": 340}),
                _token_event(seq=2, body={"input_tokens": 800, "output_tokens": 160}),
            ]
        )
    )

    usage = records.fabro_token_usage_from_payload(payload=payload)

    assert usage is not None
    assert usage.input_tokens == 2_000
    assert usage.output_tokens == 500
    assert usage.total_tokens == 2_500


def test_a_stream_with_no_token_events_reports_none() -> None:
    """The 0.254 case: no token signal exists, and the port must not invent one."""
    records = importlib.import_module(_RECORDS)

    assert hasattr(records, "fabro_token_usage_from_payload")

    payload = json.loads(
        json.dumps([{"timestamp": "2026-08-20T03:21:37Z", "event": "run.completed"}])
    )

    assert records.fabro_token_usage_from_payload(payload=payload) is None


def test_an_unrecognized_token_body_reports_none_rather_than_zero() -> None:
    """A confident zero would be indistinguishable from an unparsed body."""
    records = importlib.import_module(_RECORDS)

    assert hasattr(records, "fabro_token_usage_from_payload")

    payload = json.loads(json.dumps([_token_event(seq=1, body={"some_unmeasured_shape": 7})]))

    assert records.fabro_token_usage_from_payload(payload=payload) is None
