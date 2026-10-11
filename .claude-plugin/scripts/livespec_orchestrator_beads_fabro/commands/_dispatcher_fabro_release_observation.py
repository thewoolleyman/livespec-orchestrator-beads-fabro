"""One upstream release reading per dispatch: serve the cache, or refresh it.

The cache-versus-refresh decision of the Fabro-currency-admission clause of
`SPECIFICATION/contracts.md`, which permits caching upstream release metadata for
at most seven calendar days. `_dispatcher_fabro_release_cache` reads and writes
the record; this module decides WHETHER the record may be served, takes the fresh
reading when it may not, and says what failed when neither can be had.

THE AGE TEST SITS BESIDE THE REFRESH IT DECIDES, which is why it is here rather
than in the cache module: a cache that graded its own staleness would answer a
question whose only consumer is the refresh, and a refresh that re-derived the
age could disagree with it.

A STALE RECORD IS CARRIED FORWARD WHEN THE REFRESH FAILS, never discarded. The
clause requires the refusal to NAME the stale observation, so the reading has to
hold both the record and the reason it is not good enough; discarding it would
leave the refusal unable to say how old the evidence it declined actually was.
That is also why it is not served: an expired reading proves nothing about
currency, and the one thing this module must never do is let age be mistaken for
evidence.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    FABRO_UPSTREAM_REPO,
    OBSERVATION_MAX_AGE_DAYS,
    FabroReleaseObservation,
    calendar_days_between,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_sources import (
    ObservationReading,
    parse_releases,
    releases_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_release_cache import (
    read_release_observation,
    release_observation_path,
    write_release_observation,
)

__all__: list[str] = [
    "release_observation_reading",
]

_RELEASES_TIMEOUT_SECONDS = 120.0


def release_observation_reading(
    *, repo: Path, runner: CommandRunner, now: datetime
) -> ObservationReading:
    """The release observation this dispatch evaluates currency against.

    A cached record inside the seven-calendar-day bound is served as it stands. A
    record outside it, or none at all, sends the read to the forge; a successful
    read is cached and returned, and a failed one returns whatever record existed
    beside the reason it could not be replaced.
    """
    path = release_observation_path()
    cached = read_release_observation(path=path)
    if cached is not None and not _is_stale(observation=cached, now=now):
        return ObservationReading(observation=cached, failure=None)
    fresh = _fresh_observation(repo=repo, runner=runner, now=now)
    if fresh is not None:
        write_release_observation(path=path, observation=fresh)
        return ObservationReading(observation=fresh, failure=None)
    return ObservationReading(observation=cached, failure=_failure(cached=cached, now=now))


def _is_stale(*, observation: FabroReleaseObservation, now: datetime) -> bool:
    return (
        calendar_days_between(earlier=observation.observed_at, later=now) > OBSERVATION_MAX_AGE_DAYS
    )


def _fresh_observation(
    *, repo: Path, runner: CommandRunner, now: datetime
) -> FabroReleaseObservation | None:
    result = runner.run(argv=releases_argv(), cwd=repo, timeout_seconds=_RELEASES_TIMEOUT_SECONDS)
    if result.exit_code != 0:
        return None
    releases = parse_releases(stdout=result.stdout)
    if releases is None:
        return None
    return FabroReleaseObservation(releases=releases, observed_at=now)


def _failure(*, cached: FabroReleaseObservation | None, now: datetime) -> str:
    """Why currency cannot be evaluated, said in the terms of what was available.

    The two clauses are deliberately different sentences rather than one with a
    conditional tail: a stale record and no record at all have different remedies
    — the first says the refresh path is broken while evidence exists, the second
    says no evidence has ever been taken on this host — and a single message would
    make the operator guess which they have.
    """
    if cached is None:
        return (
            f"no {FABRO_UPSTREAM_REPO} release observation could be taken: the forge read"
            " failed and this host holds no cached observation"
        )
    age = calendar_days_between(earlier=cached.observed_at, later=now)
    return (
        f"the cached {FABRO_UPSTREAM_REPO} release observation is {age} calendar days old"
        f" (the bound is {OBSERVATION_MAX_AGE_DAYS}) and refreshing it failed, so it cannot"
        " prove currency"
    )
