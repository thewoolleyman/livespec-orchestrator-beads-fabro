"""Command lifetimes use event timestamps, identities and finite node budgets."""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_liveness import (
    command_in_timeout,
)


def _start(**changes: object) -> dict[str, object]:
    return {
        "event": "command.started",
        "node_id": "janitor",
        "stage_id": "janitor@1",
        "ts": 100.0,
        "properties": {"timeout_ms": 1_000_000},
        **changes,
    }


def _complete(**changes: object) -> dict[str, object]:
    return _start(**{"event": "command.completed", "ts": 200.0, **changes})


@given(seconds=st.integers(min_value=1, max_value=100_000))
def test_command_budget_ends_at_exact_deadline(*, seconds: int) -> None:
    events = json.dumps([_start(properties={"timeout_ms": seconds * 1000})])
    assert command_in_timeout(events_json=events, now_epoch=100 + seconds - 0.001)
    assert not command_in_timeout(events_json=events, now_epoch=100 + seconds)


@pytest.mark.parametrize("events", ["", "garbage", "[]", "42"])
def test_no_readable_command_is_no_protection(*, events: str) -> None:
    assert not command_in_timeout(events_json=events, now_epoch=300)


@pytest.mark.parametrize(
    "changes",
    [
        {"event": "agent.tool.started"},
        {"node_id": None},
        {"node_id": ""},
        {"ts": None},
        {"ts": float("nan")},
        {"ts": float("inf")},
        {"properties": None},
        {"properties": {}},
        *[
            {"properties": {"timeout_ms": value}}
            for value in [None, True, "1000", 0, -1, float("nan"), float("inf")]
        ],
    ],
)
def test_malformed_start_does_not_grant_immunity(*, changes: dict[str, object]) -> None:
    assert not command_in_timeout(events_json=json.dumps([_start(**changes)]), now_epoch=300)


@pytest.mark.parametrize(
    "records",
    [
        [_start(), _complete()],
        [_complete(), _start()],
        [_complete()],
        [_complete(ts=100.0), _start()],
        [_start(), _start(ts=200.0, properties={})],
    ],
)
def test_closed_or_unbudgeted_command_cannot_protect(*, records: list[dict[str, object]]) -> None:
    assert not command_in_timeout(events_json=json.dumps(records), now_epoch=300)


@pytest.mark.parametrize(
    "records",
    [
        [_start(stage_id=None)],
        [_start(stage_id=5)],
        [_start(), _complete(stage_id="janitor@0")],
        [_start(), _complete(node_id="other")],
        [_start(ts=300.0), _complete()],
        [_start(ts=100.0), _start(ts=1200.0)],
    ],
)
def test_other_visits_and_old_records_cannot_close_the_open_command(
    *,
    records: list[dict[str, object]],
) -> None:
    assert command_in_timeout(events_json=json.dumps(records), now_epoch=300)


def test_event_container_formats_share_the_same_command_lifetime() -> None:
    record = _start()
    for stream in (json.dumps({"events": [record]}), json.dumps(record) + "\n"):
        assert command_in_timeout(events_json=stream, now_epoch=300)


def test_reentered_command_gets_its_own_budget() -> None:
    records = [_start(), _complete(), _start(ts=1200)]
    assert command_in_timeout(events_json=json.dumps(records), now_epoch=1300)
