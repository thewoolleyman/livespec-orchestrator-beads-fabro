"""Tests for the host-local cache of one upstream Fabro release observation.

EVERY NEGATIVE CASE ASSERTS `None` RATHER THAN A RAISE, and that is the claim
worth having: `None` means "no cached reading", which sends the caller to the
forge. The failure mode this excludes is a cache that reported a PARTIAL record
as a complete one — a reading whose releases list lost an entry still proves
currency against whatever survived, and nothing in the result says so.

THE ROUND TRIP IS ASSERTED AS AN EQUALITY on the whole observation rather than
field by field, because a writer and reader that agreed on the instant and
disagreed on the releases would pass a per-field check of either one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    FabroRelease,
    FabroReleaseObservation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_release_cache import (
    RELEASE_OBSERVATION_SCHEMA,
    read_release_observation,
    release_observation_path,
    write_release_observation,
)

_OBSERVED_AT = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
_PUBLISHED_AT = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)


def _observation() -> FabroReleaseObservation:
    return FabroReleaseObservation(
        releases=(
            FabroRelease(tag="v0.378.0-nightly.0", published_at=_PUBLISHED_AT),
            FabroRelease(tag="v0.254.0", published_at=_PUBLISHED_AT),
        ),
        observed_at=_OBSERVED_AT,
    )


def _write_raw(*, path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def test_the_cache_path_sits_under_the_per_user_state_root_not_beside_a_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The observation is a fact about UPSTREAM, shared by every governed repo.

    A per-repository copy would re-spend the paginated read once per tenant on one
    host, which is the cost the cache exists to avoid.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    path = release_observation_path()

    assert path.parent.parent == tmp_path / "state"
    assert path.name == "fabro-release-observation.json"


def test_an_observation_survives_a_write_and_read_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "state" / "observation.json"

    write_release_observation(path=path, observation=_observation())

    assert read_release_observation(path=path) == _observation()


def test_the_write_leaves_no_staging_file_behind(tmp_path: Path) -> None:
    """Atomic, because two dispatch paths on one host can refresh concurrently.

    A surviving half-written sibling would be read back as an unparseable record
    on every later dispatch until something overwrote it.
    """
    path = tmp_path / "state" / "observation.json"

    write_release_observation(path=path, observation=_observation())

    assert not (path.parent / f"{path.name}.tmp").exists()


def test_a_write_to_an_unwritable_state_root_is_swallowed(tmp_path: Path) -> None:
    """The caller already holds the fresh reading, so this costs one re-read.

    Raising would convert a host-local filesystem fault into a refused dispatch.
    """
    blocker = tmp_path / "blocker"
    _ = blocker.write_text("not a directory", encoding="utf-8")

    write_release_observation(
        path=blocker / "nested" / "observation.json", observation=_observation()
    )

    assert blocker.read_text(encoding="utf-8") == "not a directory"


def test_an_absent_cache_file_reads_as_no_observation(tmp_path: Path) -> None:
    assert read_release_observation(path=tmp_path / "missing.json") is None


def test_an_unparseable_cache_file_reads_as_no_observation(tmp_path: Path) -> None:
    path = tmp_path / "observation.json"
    _ = path.write_text("{not json", encoding="utf-8")

    assert read_release_observation(path=path) is None


def test_a_payload_that_is_not_an_object_reads_as_no_observation(tmp_path: Path) -> None:
    path = tmp_path / "observation.json"
    _write_raw(path=path, payload=["v0.254.0"])

    assert read_release_observation(path=path) is None


def test_a_record_under_another_schema_reads_as_absent_rather_than_being_coerced(
    tmp_path: Path,
) -> None:
    """A future shape read through this parser would produce a plausible answer.

    Its fields would no longer mean what they did, and nothing in the resulting
    observation would say so.
    """
    path = tmp_path / "observation.json"
    _write_raw(
        path=path,
        payload={
            "schema": "livespec-fabro-release-observation/v99",
            "observed_at": _OBSERVED_AT.isoformat(),
            "releases": [],
        },
    )

    assert read_release_observation(path=path) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"schema": RELEASE_OBSERVATION_SCHEMA, "releases": []},
        {"schema": RELEASE_OBSERVATION_SCHEMA, "observed_at": 7, "releases": []},
        {"schema": RELEASE_OBSERVATION_SCHEMA, "observed_at": "not-an-instant", "releases": []},
        {
            "schema": RELEASE_OBSERVATION_SCHEMA,
            "observed_at": "2026-10-11T09:00:00",
            "releases": [],
        },
        {"schema": RELEASE_OBSERVATION_SCHEMA, "observed_at": "2026-10-11T09:00:00+00:00"},
        {
            "schema": RELEASE_OBSERVATION_SCHEMA,
            "observed_at": "2026-10-11T09:00:00+00:00",
            "releases": {"tag": "v1"},
        },
    ],
    ids=[
        "no-observed-at",
        "observed-at-not-a-string",
        "observed-at-unparseable",
        "observed-at-naive",
        "no-releases-key",
        "releases-not-a-list",
    ],
)
def test_a_record_missing_or_mistyping_an_envelope_field_reads_as_absent(
    tmp_path: Path, payload: object
) -> None:
    path = tmp_path / "observation.json"
    _write_raw(path=path, payload=payload)

    assert read_release_observation(path=path) is None


@pytest.mark.parametrize(
    "entry",
    [
        "v0.254.0",
        {"published_at": "2026-10-10T01:00:00+00:00"},
        {"tag": "v0.254.0"},
        {"tag": 7, "published_at": "2026-10-10T01:00:00+00:00"},
        {"tag": "v0.254.0", "published_at": "2026-10-10T01:00:00"},
    ],
    ids=["not-an-object", "no-tag", "no-published-at", "tag-not-a-string", "naive-instant"],
)
def test_one_unreadable_release_entry_fails_the_whole_record(tmp_path: Path, entry: object) -> None:
    """The WHOLE record, not just that entry.

    Dropping the bad entry would return a SHORT release list that still reads as a
    complete observation — and a short list is how a genuinely-ancestral tag
    disappears and a current build gets refused for having no base.
    """
    path = tmp_path / "observation.json"
    _write_raw(
        path=path,
        payload={
            "schema": RELEASE_OBSERVATION_SCHEMA,
            "observed_at": _OBSERVED_AT.isoformat(),
            "releases": [entry],
        },
    )

    assert read_release_observation(path=path) is None


def test_an_observation_holding_no_releases_round_trips_as_itself(tmp_path: Path) -> None:
    """An empty surface is a READABLE record, distinct from an unreadable one.

    The predicate refuses on it, which it can only do if the cache hands it back
    rather than reporting the file as absent.
    """
    path = tmp_path / "observation.json"
    empty = FabroReleaseObservation(releases=(), observed_at=_OBSERVED_AT)

    write_release_observation(path=path, observation=empty)

    assert read_release_observation(path=path) == empty
