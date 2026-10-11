"""The host-local cache of one upstream Fabro release observation.

The clause permits caching upstream release metadata for at most seven calendar
days, and this is the whole of that permission: one JSON record under the
per-user state root, holding the releases a reading saw and the instant it was
taken. The AGE test lives in `_dispatcher_fabro_currency_sources`, beside the
refresh it decides; this module only reads and writes.

WHY A CACHE AT ALL. Upstream publishes nightly tags, so the releases surface is
long and the read is paginated; spending it on every dispatch would put a
multi-page forge round trip on the admission path of every item in a drain wave.
Seven days is the ratified ceiling, not a tuning knob.

EVERY READ FAILS SOFT ONTO `None`, AND THAT IS NOT A FAIL-OPEN. `None` here
means "no cached reading", which sends the caller to the forge rather than past
the gate: an absent cache and an unparseable one have the same remedy, which is
to take a fresh reading. The thing that must never be inferred from an
unreadable cache is CURRENCY, and no arm here can report that.

THE WRITE IS ATOMIC — a temporary sibling then `replace` — because two dispatch
paths on one host can refresh concurrently, and a half-written record would be
read back as an unparseable one on every later dispatch until something
overwrote it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    FabroRelease,
    FabroReleaseObservation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import state_root
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "RELEASE_OBSERVATION_SCHEMA",
    "read_release_observation",
    "release_observation_path",
    "write_release_observation",
]

# The record's own schema marker. A record carrying any other value is read as
# absent rather than coerced: a future shape read through this parser would
# produce a plausible observation out of fields that no longer mean what they
# did.
RELEASE_OBSERVATION_SCHEMA = "livespec-fabro-release-observation/v1"

_FILENAME = "fabro-release-observation.json"
_PACKAGE_DIRECTORY = "livespec-orchestrator-beads-fabro"


def release_observation_path() -> Path:
    """Where the cached observation lives, repo-independent by construction.

    Under `state_root()` rather than beside a repository's journal because the
    observation is a fact about UPSTREAM, shared by every governed repository on
    the host; a per-repo copy would re-spend the read once per tenant.
    """
    return state_root() / _PACKAGE_DIRECTORY / _FILENAME


def read_release_observation(*, path: Path) -> FabroReleaseObservation | None:
    """The cached observation, or `None` when there is no readable one."""
    text = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(text, AttemptFailure):
        return None
    payload = attempt(action=lambda: json.loads(text), exceptions=(ValueError,))
    if not isinstance(payload, Mapping):
        return None
    return _observation(payload=cast("Mapping[str, object]", payload))


def write_release_observation(*, path: Path, observation: FabroReleaseObservation) -> None:
    """Persist `observation`, atomically, creating the state directory as needed.

    A write failure is SWALLOWED rather than raised: the caller already holds the
    fresh reading it was about to cache, so a state root it cannot write to costs
    the next dispatch a re-read and nothing else. Raising here would convert a
    host-local filesystem fault into a refused dispatch.
    """
    payload = {
        "schema": RELEASE_OBSERVATION_SCHEMA,
        "observed_at": observation.observed_at.isoformat(),
        "releases": [
            {"tag": release.tag, "published_at": release.published_at.isoformat()}
            for release in observation.releases
        ],
    }
    staging = path.with_name(f"{path.name}.tmp")
    _ = attempt(
        action=lambda: _write(staging=staging, path=path, payload=payload),
        exceptions=(OSError,),
    )


def _write(*, staging: Path, path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = staging.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    _ = staging.replace(path)


def _observation(*, payload: Mapping[str, object]) -> FabroReleaseObservation | None:
    if payload.get("schema") != RELEASE_OBSERVATION_SCHEMA:
        return None
    observed_at = _instant(value=payload.get("observed_at"))
    raw_releases = payload.get("releases")
    if observed_at is None or not isinstance(raw_releases, list):
        return None
    releases: list[FabroRelease] = []
    for entry in cast("list[object]", raw_releases):
        release = _release(entry=entry)
        if release is None:
            return None
        releases.append(release)
    return FabroReleaseObservation(releases=tuple(releases), observed_at=observed_at)


def _release(*, entry: object) -> FabroRelease | None:
    if not isinstance(entry, Mapping):
        return None
    fields = cast("Mapping[str, object]", entry)
    tag = fields.get("tag")
    published_at = _instant(value=fields.get("published_at"))
    if not isinstance(tag, str) or published_at is None:
        return None
    return FabroRelease(tag=tag, published_at=published_at)


def _instant(*, value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = attempt(action=lambda: datetime.fromisoformat(value), exceptions=(ValueError,))
    if isinstance(parsed, AttemptFailure):
        return None
    return None if parsed.tzinfo is None else parsed
