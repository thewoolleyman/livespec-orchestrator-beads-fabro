"""Tests for the cache-versus-refresh decision behind one release reading.

THREE OUTCOMES, AND THEY ARE NOT INTERCHANGEABLE: a cached record served as it
stands, a fresh record taken and cached, and a reading that holds a STALE record
beside the reason it could not be replaced. The third is the one with teeth — it
must carry the record forward so the refusal can name it, while never SERVING it,
because an expired reading proves nothing about currency.

EACH CASE READS THE FORGE CALL COUNT, not only the returned reading. "Served from
the cache" is a claim about a read that did NOT happen, and a reading that
refreshed every time returns exactly the same value here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    OBSERVATION_MAX_AGE_DAYS,
    FabroRelease,
    FabroReleaseObservation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_release_cache import (
    read_release_observation,
    release_observation_path,
    write_release_observation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_release_observation import (
    release_observation_reading,
)

_REPO = Path("/repo")
_NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
_FRESH_TAG = "v0.378.0-nightly.0"
_CACHED_TAG = "v0.370.0"


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.calls.append(tuple(argv))
        return self.result


def _forge_answer(*, tag: str = _FRESH_TAG) -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=json.dumps({"tag": tag, "published_at": "2026-10-10T01:00:00Z"}) + "\n",
        stderr="",
    )


def _forge_failure() -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr="HTTP 503")


def _seed_cache(*, age_days: int) -> FabroReleaseObservation:
    observation = FabroReleaseObservation(
        releases=(FabroRelease(tag=_CACHED_TAG, published_at=_NOW - timedelta(days=age_days + 1)),),
        observed_at=_NOW - timedelta(days=age_days),
    )
    write_release_observation(path=release_observation_path(), observation=observation)
    return observation


@pytest.fixture(autouse=True)
def _hermetic_state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def test_a_cached_record_inside_the_bound_is_served_without_a_forge_read() -> None:
    cached = _seed_cache(age_days=OBSERVATION_MAX_AGE_DAYS)
    runner = _Runner(result=_forge_answer())

    reading = release_observation_reading(repo=_REPO, runner=runner, now=_NOW)

    assert reading.observation == cached
    assert reading.failure is None
    assert runner.calls == []


def test_an_absent_cache_takes_a_fresh_reading_and_persists_it() -> None:
    runner = _Runner(result=_forge_answer())

    reading = release_observation_reading(repo=_REPO, runner=runner, now=_NOW)

    assert reading.observation is not None
    assert [release.tag for release in reading.observation.releases] == [_FRESH_TAG]
    assert reading.observation.observed_at == _NOW
    assert reading.failure is None
    assert len(runner.calls) == 1
    # Persisted, which is the whole reason the cache exists: the NEXT dispatch
    # must not re-spend this paginated read.
    assert read_release_observation(path=release_observation_path()) == reading.observation


def test_a_cached_record_past_the_bound_is_replaced_by_a_successful_refresh() -> None:
    _ = _seed_cache(age_days=OBSERVATION_MAX_AGE_DAYS + 1)
    runner = _Runner(result=_forge_answer())

    reading = release_observation_reading(repo=_REPO, runner=runner, now=_NOW)

    assert reading.observation is not None
    assert [release.tag for release in reading.observation.releases] == [_FRESH_TAG]
    assert reading.failure is None
    assert len(runner.calls) == 1


def test_a_stale_record_whose_refresh_fails_is_carried_forward_with_its_age_named() -> None:
    """Carried FORWARD, never served: the refusal has to be able to name it.

    Discarding it would leave the refusal unable to say how old the evidence it
    declined actually was, which is exactly what the clause requires of it.
    """
    stale = _seed_cache(age_days=OBSERVATION_MAX_AGE_DAYS + 3)
    runner = _Runner(result=_forge_failure())

    reading = release_observation_reading(repo=_REPO, runner=runner, now=_NOW)

    assert reading.observation == stale
    assert reading.failure is not None
    assert f"{OBSERVATION_MAX_AGE_DAYS + 3} calendar days old" in reading.failure
    assert f"the bound is {OBSERVATION_MAX_AGE_DAYS}" in reading.failure
    assert "refreshing it failed" in reading.failure


def test_no_cache_and_a_failed_refresh_reports_that_no_observation_exists_at_all() -> None:
    """A DIFFERENT sentence from the stale one, because the remedy differs.

    One says the refresh path is broken while evidence exists; the other says no
    evidence has ever been taken on this host.
    """
    runner = _Runner(result=_forge_failure())

    reading = release_observation_reading(repo=_REPO, runner=runner, now=_NOW)

    assert reading.observation is None
    assert reading.failure is not None
    assert "holds no cached observation" in reading.failure


def test_an_unparseable_forge_answer_is_a_failed_refresh_rather_than_an_empty_reading() -> None:
    """Exit 0 with a payload this parser does not understand is NOT evidence.

    An empty observation would read as "upstream has published nothing", which
    admits every base there is.
    """
    runner = _Runner(result=CommandResult(exit_code=0, stdout="not json\n", stderr=""))

    reading = release_observation_reading(repo=_REPO, runner=runner, now=_NOW)

    assert reading.observation is None
    assert reading.failure is not None
