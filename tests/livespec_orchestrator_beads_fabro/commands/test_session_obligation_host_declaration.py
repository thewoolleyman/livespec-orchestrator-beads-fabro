"""Reading one host's coverage declaration, and the two ways it can fail to read.

Scenario 161's "Missing all recovery coverage is not prevention" needs three
answers kept apart on a real host: a host that declares no owner, a host whose
declaration this build cannot resolve, and a host that declares one. The pure
ladder in `_session_obligation_coverage` already distinguishes the grades; what
is measured here is that the READ hands it the right reading, because a reader
that reported an unparseable declaration as "no owner" would turn a broken
instrument into a finding about the host.

The store-root case belongs here rather than beside the records suite because
it is the same mistake in a different place: a declaration filed under the
obligation store root is censused by `outstanding_obligations` as an unreadable
obligation, so every completion gate would report the host's own coverage
declaration as outstanding work.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    COVERAGE_UNMONITORED,
    COVERAGE_UNOBSERVABLE,
    COVERAGE_VERIFIED,
    DIAGNOSTIC_COVERAGE_UNREADABLE,
    DIAGNOSTIC_OWNER_ABSENT,
    DIAGNOSTIC_ROUTE_UNSUPPORTED,
    coverage_verdict,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_host import (
    coverage_declaration_path,
    host_coverage_reading,
    obligation_store_root,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    outstanding_obligations,
)

_SOUND_DECLARATION: dict[str, object] = {
    "max_observation_interval_seconds": 15.0,
    "proof_artifact": "livespec-overseer-consumer@0.1.0",
    "recovery_route": "overseer-supervised-service",
    "runtime": "codex",
    "runtime_version": "0.60.0",
    "service_generation": "7",
    "service_identity": "livespec-overseer-consumer.service",
    "takeover_budget_seconds": 20.0,
    "terminal_backend": "herdr",
    "terminal_instance": "w1:pF",
    "terminal_version": "0.9.3",
}


def _declare(*, primary: Path, payload: object) -> Path:
    path = coverage_declaration_path(primary=primary)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_an_undeclared_host_reads_as_an_absent_owner(tmp_path: Path) -> None:
    reading = host_coverage_reading(path=coverage_declaration_path(primary=tmp_path))

    graded = coverage_verdict(reading=reading)

    assert reading.declaration is None
    assert reading.diagnostic is None
    assert (graded.state, graded.diagnostic) == (COVERAGE_UNMONITORED, DIAGNOSTIC_OWNER_ABSENT)


def test_a_sound_declaration_grades_as_verified_coverage(tmp_path: Path) -> None:
    _ = _declare(primary=tmp_path, payload=_SOUND_DECLARATION)

    reading = host_coverage_reading(path=coverage_declaration_path(primary=tmp_path))

    graded = coverage_verdict(reading=reading)
    assert graded.state == COVERAGE_VERIFIED
    assert reading.declaration is not None
    assert reading.declaration.terminal_instance == "w1:pF"


def test_a_well_shaped_declaration_is_graded_by_the_pure_ladder(tmp_path: Path) -> None:
    """Content faults stay with the grade; the reader never pre-empts them."""
    _ = _declare(
        primary=tmp_path,
        payload={**_SOUND_DECLARATION, "recovery_route": "an-ad-hoc-nudge"},
    )

    graded = coverage_verdict(
        reading=host_coverage_reading(path=coverage_declaration_path(primary=tmp_path))
    )

    assert (graded.state, graded.diagnostic) == (
        COVERAGE_UNMONITORED,
        DIAGNOSTIC_ROUTE_UNSUPPORTED,
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(["not", "an", "object"], id="not-an-object"),
        pytest.param({**_SOUND_DECLARATION, "runtime": 7}, id="identity-at-the-wrong-type"),
        pytest.param(
            {name: value for name, value in _SOUND_DECLARATION.items() if name != "proof_artifact"},
            id="identity-absent",
        ),
        pytest.param(
            {**_SOUND_DECLARATION, "takeover_budget_seconds": "20"},
            id="budget-at-the-wrong-type",
        ),
        pytest.param(
            {**_SOUND_DECLARATION, "takeover_budget_seconds": True},
            id="budget-as-a-boolean",
        ),
    ],
)
def test_a_declaration_this_build_cannot_resolve_is_unobservable(
    tmp_path: Path, payload: object
) -> None:
    _ = _declare(primary=tmp_path, payload=payload)

    reading = host_coverage_reading(path=coverage_declaration_path(primary=tmp_path))

    graded = coverage_verdict(reading=reading)
    assert reading.declaration is None
    assert (graded.state, graded.diagnostic) == (
        COVERAGE_UNOBSERVABLE,
        DIAGNOSTIC_COVERAGE_UNREADABLE,
    )


def test_bytes_that_are_not_json_are_unobservable(tmp_path: Path) -> None:
    path = coverage_declaration_path(primary=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("{not json", encoding="utf-8")

    graded = coverage_verdict(reading=host_coverage_reading(path=path))

    assert (graded.state, graded.diagnostic) == (
        COVERAGE_UNOBSERVABLE,
        DIAGNOSTIC_COVERAGE_UNREADABLE,
    )


def test_a_declaration_path_that_cannot_be_read_is_unobservable(tmp_path: Path) -> None:
    """A directory at the declaration path is a read failure, never an absence."""
    path = coverage_declaration_path(primary=tmp_path)
    path.mkdir(parents=True)

    graded = coverage_verdict(reading=host_coverage_reading(path=path))

    assert (graded.state, graded.diagnostic) == (
        COVERAGE_UNOBSERVABLE,
        DIAGNOSTIC_COVERAGE_UNREADABLE,
    )


def test_the_declaration_is_not_censused_as_an_outstanding_obligation(tmp_path: Path) -> None:
    declaration = _declare(primary=tmp_path, payload=_SOUND_DECLARATION)
    store = obligation_store_root(primary=tmp_path)
    store.mkdir(parents=True, exist_ok=True)

    census = outstanding_obligations(obligation_store_root=store)

    assert declaration.parent != store
    assert (census.records, census.diagnostics) == ((), ())
