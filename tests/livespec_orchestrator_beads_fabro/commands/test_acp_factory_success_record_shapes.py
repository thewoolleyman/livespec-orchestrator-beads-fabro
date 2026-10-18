"""The degraded factory-record shapes the confirmation arm must tolerate.

Sits beside `test_acp_factory_success_retirement.py`, which owns the retirement
claim itself. These are the row and record shapes a LIVE factory holds that the
positive fixture cannot reach, and they came out of a coverage measurement taken
after that module's Red was authored -- a Red's test bytes are fixed across its
Red-to-Green pair, so they belong in their own file rather than appended there.

EACH CASE ASSERTS WHAT WAS *NOT* SPENT, not only that nothing was derived. "No
confirmation" and "no per-run read" are different claims, and only the second
distinguishes a row the listing bound correctly passed over from one that was
inspected and found to say nothing -- which is the difference between an
affordable scan over the 1626 rows a factory serving this fleet listed and one
that pays a round trip per historical run.

NEITHER SHAPE IS SURFACED AS UNOBSERVABLE, and that is the claim worth holding.
A confirmation that cannot be derived retires nothing, which leaves every hold
standing -- the conservative direction -- so it is not a failure to measure
anything a decision rests on. The occurrence-unreadable surface stays scoped to
a FAILED row, where an undatable attempt WOULD otherwise mint a hold born
expired.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T12:00:00Z"
_RUN_ID = "01M4TNBBBBBBBBBBBBBBBBBBBB"
_PEER_REPOSITORY = "livespec-console-beads-fabro"

# Started five minutes ago, so the confirmation arm's window reaches this row
# and the per-run read IS spent on it.
_STARTED_AT = "2026-10-16T11:55:00Z"
_WALL_TIME_MS = 60_000

_LABELS: dict[str, str] = {
    "livespec.repository": _PEER_REPOSITORY,
    "livespec.acp.implement.availability": "codex",
    "livespec.acp.implement.candidate": "primary",
}

_FACTORIES_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {"hp": {"server": "https://hp.example.ts.net:32276"}}
    }
  }
}
"""


class _Reader:
    """A factory run reader recording exactly which per-run reads were spent."""

    def __init__(self, *, rows: tuple[Any, ...], payload: object | None) -> None:
        self._rows = rows
        self._payload = payload
        self.inspected: list[str] = []

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self._rows if factory == "hp" else ()

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        self.inspected.append(f"{factory}:{run_id}")
        return self._payload


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _repo(*, tmp_path: Path) -> Path:
    (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    return tmp_path


def _rows(*, row: dict[str, Any]) -> tuple[Any, ...]:
    return _module(name="_fabro_port_records").fabro_run_summaries_from_payload(payload=[row])


def _row(*, status: str, start_time: str | None) -> dict[str, Any]:
    """One measured `fabro ps -a --json` row, optionally sparse of its start."""
    record: dict[str, Any] = {
        "run_id": _RUN_ID,
        "status": {"kind": status},
        "goal": "Work-item: bd-peer-1\n",
        "repo_origin_url": f"https://github.com/thewoolleyman/{_PEER_REPOSITORY}",
        "labels": dict(_LABELS),
        "wall_time_ms": _WALL_TIME_MS,
    }
    if start_time is not None:
        record["start_time"] = start_time
    return record


def _evidence(*, repo: Path, reader: _Reader) -> Any:
    return _module(name="_acp_factory_hold_evidence").factory_hold_evidence(
        repo=repo, reader=reader, now_iso=_NOW
    )


@pytest.mark.parametrize("status", ["succeeded", "running"])
def test_a_non_failed_row_carrying_no_start_instant_costs_no_per_run_read(
    tmp_path: Path, status: str
) -> None:
    """`omitempty` sparseness on the one figure the confirmation arm needs.

    A run the engine recorded no `start_time` for cannot be placed relative to
    any observation, so no confirmation it carries could retire anything -- and
    the per-run read is therefore not worth spending. Both non-failed kinds are
    exercised because a RUNNING row is the one that proves the arm no longer
    short-circuits on status alone.
    """
    reader = _Reader(rows=_rows(row=_row(status=status, start_time=None)), payload=None)

    evidence = _evidence(repo=_repo(tmp_path=tmp_path), reader=reader)

    assert evidence.successes == ()
    assert evidence.observations == ()
    assert reader.inspected == []
    # Not a failure to MEASURE: nothing a decision rests on went unread.
    assert evidence.unobservable == ()
    assert evidence.unconfirmed_keys == frozenset()


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="empty-record-list"),
        pytest.param([{"run_id": _RUN_ID, "status": {"kind": "succeeded"}}], id="no-checkpoint"),
    ],
)
def test_a_record_the_port_cannot_grade_establishes_no_confirmation(
    tmp_path: Path, payload: object
) -> None:
    """A per-run read that SUCCEEDED and graded nothing retires nothing.

    Both reads SUCCEEDED -- each returned a well-formed JSON document -- and
    neither grades a node attempt: the first is the empty list a pruned run
    answers with, where `fabro inspect --json` normally returns one element,
    and the second carries no checkpoint and no `stages` map for the port to
    project. A confirmation invented from either would clear a live hold on the
    evidence of a record nobody could grade.

    Note what these are NOT: an unreadable read, which answers `None` and is
    surfaced as `run-record-unreadable` one branch earlier. That distinction is
    why both cases assert `unobservable` is empty.
    """
    reader = _Reader(
        rows=_rows(row=_row(status="succeeded", start_time=_STARTED_AT)), payload=payload
    )

    evidence = _evidence(repo=_repo(tmp_path=tmp_path), reader=reader)

    assert evidence.successes == ()
    # The read WAS spent, against the factory that listed the row: this row is
    # inside the confirmation window, which is what makes the two assertions
    # above a statement about the record rather than about the listing bound.
    assert reader.inspected == [f"hp:{_RUN_ID}"]
    assert evidence.unobservable == ()
