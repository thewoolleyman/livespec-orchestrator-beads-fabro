"""Cursor and failure semantics of the watchdog's server stream read."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    STREAM_POLL_JOURNAL_STAGE,
    LivenessState,
    liveness_sample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    StallVerdict,
    decide_stall,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink


@dataclass(kw_only=True)
class _Api:
    responses: list[FabroHttpResult]
    calls: list[int | None] = field(default_factory=list)

    def stream(self, *, run_id: str, after: int | None, timeout_seconds: float) -> FabroHttpResult:
        _ = (run_id, timeout_seconds)
        self.calls.append(after)
        return self.responses.pop(0)


@dataclass(kw_only=True)
class _Port:
    api: _Api

    def server_api(self) -> _Api:
        return self.api


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _response(*, body: str, succeeded: bool = True) -> FabroHttpResult:
    return FabroHttpResult(
        status=200 if succeeded else 0,
        body=body,
        error=None,
        payload=None,
        succeeded=succeeded,
    )


def _sample(
    *, api: _Api, state: LivenessState, record: object | None, journal: _Journal
) -> float | None:
    return liveness_sample(
        plan=cast("DispatchPlan", SimpleNamespace(node_timeouts={})),
        port=cast("FabroPort", _Port(api=api)),
        run_id="01RUN",
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=100.0,
        state=state,
        run_record=record,
        journal=journal,
    ).last_event_epoch


def test_cursor_read_advances_only_from_the_server_stream_sequence() -> None:
    api = _Api(
        responses=[
            _response(
                body=json.dumps([{"stream_seq": 7, "recorded_at": 10_000}]),
            ),
            _response(
                body=json.dumps([{"stream_seq": 8, "recorded_at": 11_000}]),
            ),
        ]
    )
    state = LivenessState()
    journal = _Journal()

    first = _sample(api=api, state=state, record=None, journal=journal)
    second = _sample(api=api, state=state, record=None, journal=journal)

    assert (first, second, api.calls, state.stream_seq) == (10.0, 11.0, [None, 7], 8)


def test_a_stream_record_without_a_sequence_does_not_rewind_the_cursor() -> None:
    api = _Api(responses=[_response(body=json.dumps([{"recorded_at": 11_000}]))])
    state = LivenessState(stream_seq=8)

    assert _sample(api=api, state=state, record=None, journal=_Journal()) == 11.0
    assert state.stream_seq == 8


def test_failed_or_empty_stream_is_unobservable_not_a_quiet_repeat() -> None:
    api = _Api(
        responses=[
            _response(body=json.dumps([{"stream_seq": 7, "recorded_at": 10_000}])),
            _response(body="", succeeded=False),
            _response(body="[]"),
        ]
    )
    state = LivenessState()
    journal = _Journal()

    assert _sample(api=api, state=state, record=None, journal=journal) == 10.0
    assert _sample(api=api, state=state, record=None, journal=journal) is None
    assert _sample(api=api, state=state, record=None, journal=journal) is None
    assert [(record["stage"], record["observable"]) for record in journal.records] == [
        (STREAM_POLL_JOURNAL_STAGE, False),
        (STREAM_POLL_JOURNAL_STAGE, False),
    ]


def test_frozen_heartbeat_cannot_confirm_a_stall_while_every_stream_read_is_unobservable(
    tmp_path: Path,
) -> None:
    """A stale heartbeat alone cannot make a blind event stream look stalled."""
    api = _Api(responses=[_response(body="", succeeded=False) for _ in range(3)])
    state = LivenessState()
    journal = _Journal()
    heartbeat_path = tmp_path / "otel-heartbeat.json"
    HeartbeatSink(path=heartbeat_path).beat(key="bd-ib-7e4d7t", at=10.0)
    plan = cast(
        "DispatchPlan",
        SimpleNamespace(node_timeouts={}, work_item_id="bd-ib-7e4d7t"),
    )

    samples = tuple(
        liveness_sample(
            plan=plan,
            port=cast("FabroPort", _Port(api=api)),
            run_id="01RUN",
            heartbeat_path=heartbeat_path,
            dispatch_id=None,
            observed_at=observed_at,
            state=state,
            journal=journal,
        )
        for observed_at in (0.0, 900.0, 1500.0)
    )

    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.CONTINUE
    assert [(record["stage"], record["observable"]) for record in journal.records] == [
        (STREAM_POLL_JOURNAL_STAGE, False),
        (STREAM_POLL_JOURNAL_STAGE, False),
        (STREAM_POLL_JOURNAL_STAGE, False),
    ]


def test_newer_stage_transition_progresses_when_the_stream_read_fails() -> None:
    api = _Api(
        responses=[
            _response(body=json.dumps([{"stream_seq": 7, "recorded_at": 10_000}])),
            _response(body="", succeeded=False),
        ]
    )
    state = LivenessState()
    journal = _Journal()

    assert _sample(api=api, state=state, record=None, journal=journal) == 10.0
    assert (
        _sample(
            api=api,
            state=state,
            record={"stages": {"implement@1": {"started_at_epoch": 15.0}}},
            journal=journal,
        )
        == 15.0
    )


def test_newer_status_stage_transition_progresses_when_the_stream_read_fails() -> None:
    api = _Api(
        responses=[
            _response(body=json.dumps([{"stream_seq": 7, "recorded_at": 10_000}])),
            _response(body="", succeeded=False),
        ]
    )
    state = LivenessState()
    journal = _Journal()

    assert _sample(api=api, state=state, record=None, journal=journal) == 10.0
    assert (
        _sample(
            api=api,
            state=state,
            record={"status": {"finished_at_epoch": 16.0}},
            journal=journal,
        )
        == 16.0
    )


def test_a_non_newer_or_unreadable_stage_record_keeps_a_failed_stream_unobservable() -> None:
    api = _Api(
        responses=[
            _response(body="", succeeded=False),
            _response(body="", succeeded=False),
        ]
    )
    state = LivenessState(newest_event_epoch=16.0)
    journal = _Journal()

    assert (
        _sample(
            api=api,
            state=state,
            record={"stages": {"implement@1": {"finished_at": "1970-01-01T00:00:15Z"}}},
            journal=journal,
        )
        is None
    )
    assert (
        _sample(
            api=api,
            state=state,
            record={"status": "running"},
            journal=journal,
        )
        is None
    )


def test_launcher_path_observe_run_facts_survive_the_sample_call() -> None:
    api = _Api(
        responses=[
            _response(body=json.dumps([{"stream_seq": 7, "recorded_at": 10_000}])),
            _response(body="", succeeded=False),
        ]
    )
    state = LivenessState()
    journal = _Journal()
    plan = cast("DispatchPlan", SimpleNamespace(node_timeouts={}))
    port = cast("FabroPort", _Port(api=api))

    def poll(*, record: object | None) -> float | None:
        state.observe_run(record=record, journal=journal)
        return liveness_sample(
            plan=plan,
            port=port,
            run_id="01RUN",
            heartbeat_path=None,
            dispatch_id=None,
            observed_at=100.0,
            state=state,
        ).last_event_epoch

    assert poll(record=None) == 10.0
    progressed = poll(record={"stages": {"implement@1": {"started_at_epoch": 15.0}}})

    assert progressed == 15.0
    assert [(record["stage"], record["observable"]) for record in journal.records] == [
        (STREAM_POLL_JOURNAL_STAGE, False),
    ]
