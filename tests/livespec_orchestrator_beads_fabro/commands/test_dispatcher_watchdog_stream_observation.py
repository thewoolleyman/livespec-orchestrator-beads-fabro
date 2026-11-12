"""Cursor and failure semantics of the watchdog's server stream read."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    STREAM_POLL_JOURNAL_STAGE,
    LivenessState,
    liveness_sample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult


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


def _response(*, body: str, succeeded: bool = True, status: int | None = None) -> FabroHttpResult:
    return FabroHttpResult(
        status=status if status is not None else (200 if succeeded else 0),
        body=body,
        error=None,
        payload=json.loads(body) if succeeded and body else None,
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


def test_a_single_event_mapping_is_an_observable_page() -> None:
    api = _Api(
        responses=[
            _response(body=json.dumps({"stream_seq": 9, "recorded_at": 12_000})),
        ]
    )
    state = LivenessState(stream_seq=8)

    assert _sample(api=api, state=state, record=None, journal=_Journal()) == 12.0
    assert state.stream_seq == 9


def test_a_failed_stream_is_unobservable_and_journals_its_http_status() -> None:
    api = _Api(
        responses=[
            _response(body=json.dumps([{"stream_seq": 7, "recorded_at": 10_000}])),
            _response(body="", succeeded=False, status=404),
        ]
    )
    state = LivenessState()
    journal = _Journal()

    assert _sample(api=api, state=state, record=None, journal=journal) == 10.0
    assert _sample(api=api, state=state, record=None, journal=journal) is None
    assert journal.records == [
        {
            "stage": STREAM_POLL_JOURNAL_STAGE,
            "run_id": "01RUN",
            "observable": True,
            "status": 200,
        },
        {
            "stage": STREAM_POLL_JOURNAL_STAGE,
            "run_id": "01RUN",
            "observable": False,
            "status": 404,
            "reason": "stream-read-unobservable",
        },
    ]


def test_an_empty_successful_page_is_observable_and_keeps_the_quiet_window() -> None:
    api = _Api(
        responses=[
            _response(body=json.dumps({"data": [], "meta": {"has_more": False}})),
        ]
    )
    state = LivenessState(newest_event_epoch=10.0, stream_seq=7)
    journal = _Journal()

    assert _sample(api=api, state=state, record=None, journal=journal) == 10.0
    assert (api.calls, state.stream_seq) == ([7], 7)
    assert journal.records == [
        {
            "stage": STREAM_POLL_JOURNAL_STAGE,
            "run_id": "01RUN",
            "observable": True,
            "status": 200,
        }
    ]


def test_an_unchanged_stage_projection_does_not_read_the_event_stream_again() -> None:
    """A quiet bound poll costs its one by-id stages read and no stream read."""
    api = _Api(
        responses=[
            _response(body=json.dumps([{"stream_seq": 7, "recorded_at": 10_000}])),
            _response(body=json.dumps({"data": [], "meta": {"has_more": False}})),
        ]
    )
    state = LivenessState()
    record = {"data": [{"id": "implement@1", "status": "running"}]}

    first = _sample(api=api, state=state, record=record, journal=_Journal())
    second = _sample(api=api, state=state, record=record, journal=_Journal())

    assert (first, second, api.calls) == (10.0, 10.0, [None])


def test_a_stage_start_from_the_by_id_projection_is_liveness_progress() -> None:
    """A failed event read does not hide the transition the stage read observed."""
    api = _Api(responses=[_response(body="", succeeded=False)])

    progress = _sample(
        api=api,
        state=LivenessState(),
        record={
            "data": [
                {
                    "id": "implement@1",
                    "handler": "agent",
                    "status": "running",
                    "started_at_epoch": 15.0,
                }
            ]
        },
        journal=_Journal(),
    )

    assert progress == 15.0


def test_a_poll_reads_all_event_pages_and_carries_the_newest_cursor() -> None:
    api = _Api(
        responses=[
            _response(
                body=json.dumps(
                    {
                        "data": [{"stream_seq": 7, "recorded_at": 10_000}],
                        "meta": {"has_more": True},
                    }
                )
            ),
            _response(
                body=json.dumps(
                    {
                        "data": [{"stream_seq": 8, "recorded_at": 11_000}],
                        "meta": {"has_more": False},
                    }
                )
            ),
        ]
    )
    state = LivenessState()
    journal = _Journal()

    assert _sample(api=api, state=state, record=None, journal=journal) == 11.0
    assert (api.calls, state.stream_seq) == ([None, 7], 8)
    assert journal.records == [
        {
            "stage": STREAM_POLL_JOURNAL_STAGE,
            "run_id": "01RUN",
            "observable": True,
            "status": 200,
        }
    ]


def test_a_poll_timeout_is_unobservable_and_journals_its_last_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = LivenessState()
    journal = _Journal()
    monotonic_values = iter((10.0, 10_000.0))
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe.time.monotonic",
        lambda: next(monotonic_values),
    )

    assert _sample(api=_Api(responses=[]), state=state, record=None, journal=journal) is None
    assert journal.records == [
        {
            "stage": STREAM_POLL_JOURNAL_STAGE,
            "run_id": "01RUN",
            "observable": False,
            "status": 0,
            "reason": "stream-read-unobservable",
        }
    ]


def test_a_malformed_successful_page_is_unobservable_and_journals_its_status() -> None:
    api = _Api(
        responses=[
            FabroHttpResult(
                status=200,
                body=json.dumps({"data": "not-event-records"}),
                error=None,
                payload={"data": "not-event-records"},
                succeeded=True,
            )
        ]
    )
    journal = _Journal()

    assert _sample(api=api, state=LivenessState(), record=None, journal=journal) is None
    assert journal.records[-1] == {
        "stage": STREAM_POLL_JOURNAL_STAGE,
        "run_id": "01RUN",
        "observable": False,
        "status": 200,
        "reason": "stream-read-unobservable",
    }


def test_a_paginated_page_without_a_new_cursor_is_unobservable() -> None:
    api = _Api(
        responses=[
            _response(body=json.dumps({"data": [], "meta": {"has_more": True}})),
        ]
    )
    state = LivenessState(stream_seq=7)
    journal = _Journal()

    assert _sample(api=api, state=state, record=None, journal=journal) is None
    assert api.calls == [7]
    assert journal.records[-1] == {
        "stage": STREAM_POLL_JOURNAL_STAGE,
        "run_id": "01RUN",
        "observable": False,
        "status": 200,
        "reason": "stream-read-unobservable",
    }


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
        (STREAM_POLL_JOURNAL_STAGE, True),
        (STREAM_POLL_JOURNAL_STAGE, False),
    ]
