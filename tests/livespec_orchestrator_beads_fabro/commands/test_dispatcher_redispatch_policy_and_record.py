"""The committed repetition limit and the recovery comment records round-trip honestly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_policy import (
    redispatch_no_progress_limit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    RedispatchRecovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_recovery_record import (
    CONSUMED_MARKER,
    RECOVERY_MARKER,
    consumed_attempt_ids,
    parse_recovery_comments,
    render_consumed_comment,
    render_recovery_comment,
)


def _config(root: Path, *, dispatcher: object) -> Path:
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    return root


def test_a_committed_positive_integer_is_the_limit(tmp_path: Path) -> None:
    """The one accepted shape is a positive integer."""
    repo = _config(tmp_path, dispatcher={"redispatch_no_progress_limit": 3})
    assert redispatch_no_progress_limit(repo=repo) == 3


@pytest.mark.parametrize("value", [0, -1, True, "3", 2.5])
def test_an_invalid_value_is_a_diagnostic_never_a_count(tmp_path: Path, value: object) -> None:
    """Zero, negatives, booleans and non-integers never become an implicit count."""
    repo = _config(tmp_path, dispatcher={"redispatch_no_progress_limit": value})
    result = redispatch_no_progress_limit(repo=repo)
    assert isinstance(result, str)
    assert "must be a positive integer" in result


def test_an_absent_key_file_or_block_is_a_diagnostic(tmp_path: Path) -> None:
    """Nothing committed means nothing to count against."""
    empty = tmp_path / "empty"
    empty.mkdir()
    missing = redispatch_no_progress_limit(repo=empty)
    assert isinstance(missing, str)
    assert "is not committed" in missing
    unset = redispatch_no_progress_limit(repo=_config(tmp_path, dispatcher={}))
    assert isinstance(unset, str)
    assert "is not committed" in unset


def test_an_unreadable_config_is_a_diagnostic(tmp_path: Path) -> None:
    """A file that does not parse is reported, not read as unset."""
    _ = (tmp_path / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")
    result = redispatch_no_progress_limit(repo=tmp_path)
    assert isinstance(result, str)
    assert "could not be read" in result


def _recovery() -> RedispatchRecovery:
    return RedispatchRecovery(
        attempt_id="rec-1",
        prior_run_ids=("a", "b"),
        diagnosis="the fixture is stale",
        operation="dispatch --item x",
        execution_evidence="receipt",
    )


def test_a_recovery_comment_round_trips_in_recorded_order() -> None:
    """The typed fields survive the ledger comment unchanged."""
    other = RedispatchRecovery(
        attempt_id="rec-2",
        prior_run_ids=(),
        diagnosis="d",
        operation="o",
        execution_evidence="e",
    )
    bodies = [
        render_recovery_comment(recovery=_recovery()),
        "prose",
        render_recovery_comment(recovery=other),
    ]
    assert parse_recovery_comments(bodies=bodies) == (_recovery(), other)


def test_a_consumption_comment_spends_exactly_its_id() -> None:
    """Spent ids are read from consumption comments alone."""
    bodies = [
        render_consumed_comment(attempt_id="rec-1"),
        render_recovery_comment(recovery=_recovery()),
    ]
    assert consumed_attempt_ids(bodies=bodies) == frozenset({"rec-1"})


@pytest.mark.parametrize(
    "body",
    [
        "no marker\n{}",
        f"{RECOVERY_MARKER}\nnot json",
        f"{RECOVERY_MARKER}\n[1]",
        f'{RECOVERY_MARKER}\n{{"attempt_id": 1}}',
        f'{RECOVERY_MARKER}\n{{"attempt_id": "a", "prior_run_ids": "x"}}',
        f'{RECOVERY_MARKER}\n{{"attempt_id": "a", "prior_run_ids": [1]}}',
        f'{RECOVERY_MARKER}\n{{"attempt_id": "a", "prior_run_ids": [], "diagnosis": 1}}',
    ],
)
def test_malformed_recovery_bodies_are_dropped_not_half_read(body: str) -> None:
    """Prose posing as a typed attempt never parses."""
    assert parse_recovery_comments(bodies=[body]) == ()


def test_a_malformed_consumption_spends_nothing() -> None:
    """Only a well-formed consumption with a string id spends an attempt."""
    bodies = [f'{CONSUMED_MARKER}\n{{"attempt_id": 3}}', f"{CONSUMED_MARKER}\nbroken"]
    assert consumed_attempt_ids(bodies=bodies) == frozenset()
