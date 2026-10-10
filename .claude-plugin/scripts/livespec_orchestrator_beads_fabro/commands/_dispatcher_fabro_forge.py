"""GitHub release and ancestry evidence for Fabro currency admission."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from urllib.parse import quote

from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "FabroForgeFailure",
    "FabroRelease",
    "FabroReleaseObservation",
    "fabro_release_cache_path",
    "release_observation",
    "release_tag_is_ancestor",
]

_RELEASES_ENDPOINT = "repos/fabro-sh/fabro/releases?per_page=100"
_COMPARE_ENDPOINT = "repos/fabro-sh/fabro/compare/{tag}...{commit}"
_FORGE_TIMEOUT_SECONDS = 60.0
_MAX_OBSERVATION_AGE = timedelta(days=7)


@dataclass(frozen=True, kw_only=True)
class FabroRelease:
    tag: str
    published_at: datetime


@dataclass(frozen=True, kw_only=True)
class FabroReleaseObservation:
    observed_at: datetime
    releases: tuple[FabroRelease, ...]


@dataclass(frozen=True, kw_only=True)
class FabroForgeFailure:
    detail: str
    stale_observation: FabroReleaseObservation | None


def fabro_release_cache_path(*, repo: Path) -> Path:
    """Return this checkout's release-observation file outside the governed tree."""
    cache_home = Path(os.getenv("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    repo_digest = hashlib.sha256(str(repo.resolve()).encode("utf-8")).hexdigest()[:32]
    return (
        cache_home
        / "livespec-orchestrator-beads-fabro"
        / "fabro-release-observation"
        / f"{repo_digest}.json"
    )


def release_observation(
    *,
    cache_path: Path,
    repo: Path,
    runner: FabroRunner,
    now: datetime,
) -> FabroReleaseObservation | FabroForgeFailure:
    """Refresh publication evidence, retaining a stale timestamp for refusal."""
    stale = _read_cache(path=cache_path) if cache_path.is_file() else None
    if stale is not None and now - stale.observed_at <= _MAX_OBSERVATION_AGE:
        return stale
    result = runner.run(
        argv=["gh", "api", "--paginate", "--slurp", _RELEASES_ENDPOINT],
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return FabroForgeFailure(
            detail=result.stderr.strip(),
            stale_observation=stale,
        )
    releases = _release_pages(text=result.stdout)
    if isinstance(releases, str):
        return FabroForgeFailure(
            detail=f"GitHub Releases returned unusable metadata: {releases}",
            stale_observation=stale,
        )
    observation = FabroReleaseObservation(observed_at=now, releases=releases)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _ = cache_path.write_text(
        json.dumps(
            {
                "observed_at": _timestamp(value=now),
                "releases": [
                    {
                        "tag_name": release.tag,
                        "published_at": _timestamp(value=release.published_at),
                    }
                    for release in releases
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return observation


def release_tag_is_ancestor(
    *,
    tag: str,
    serving_commit: str,
    repo: Path,
    runner: FabroRunner,
) -> bool | FabroForgeFailure:
    endpoint = _COMPARE_ENDPOINT.format(
        tag=quote(tag, safe=""),
        commit=quote(serving_commit, safe=""),
    )
    result = runner.run(
        argv=["gh", "api", endpoint],
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return FabroForgeFailure(
            detail=(
                f"GitHub compare failed with exit {result.exit_code}: " f"{result.stderr.strip()}"
            ),
            stale_observation=None,
        )
    try:
        payload = cast("dict[str, object]", json.loads(result.stdout))
        status = cast(str, payload["status"])
        return {
            "ahead": True,
            "identical": True,
            "behind": False,
            "diverged": False,
        }[status]
    except (KeyError, TypeError, ValueError) as error:
        return FabroForgeFailure(
            detail=f"GitHub compare returned malformed metadata: {error}",
            stale_observation=None,
        )


def _parse_timestamp(*, text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _read_cache(*, path: Path) -> FabroReleaseObservation | None:
    try:
        payload = cast(
            "dict[str, object]",
            json.loads(path.read_text(encoding="utf-8")),
        )
        records = cast("list[dict[str, object]]", payload["releases"])
        releases = tuple(
            FabroRelease(
                tag=cast(str, record["tag_name"]),
                published_at=_parse_timestamp(text=cast(str, record["published_at"])),
            )
            for record in records
        )
        _ = max(releases, key=lambda release: (release.published_at, release.tag))
        observed_at = _parse_timestamp(text=cast(str, payload["observed_at"]))
    except (
        AttributeError,
        IndexError,
        KeyError,
        OSError,
        OverflowError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ):
        return None
    return FabroReleaseObservation(
        observed_at=observed_at,
        releases=releases,
    )


def _release_pages(*, text: str) -> tuple[FabroRelease, ...] | str:
    try:
        pages: object = json.loads(text)
    except json.JSONDecodeError as error:
        return f"invalid JSON ({error})"
    if not isinstance(pages, list):
        return "top-level response is not a list of pages"
    records: list[object] = []
    for page_index, page in enumerate(cast("list[object]", pages)):
        if not isinstance(page, list):
            return f"page {page_index} is not a list"
        records.extend(cast("list[object]", page))
    return _release_records(records=records)


def _release_records(*, records: list[object]) -> tuple[FabroRelease, ...] | str:
    try:
        releases = tuple(
            _release_record(record=record)
            for record in records
            if cast("dict[str, object]", record).get("draft") is not True
        )
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError) as error:
        return f"malformed published release record ({error})"
    return tuple(releases) if releases else "response contains no published releases"


def _release_record(*, record: object) -> FabroRelease:
    release_record = cast("dict[str, object]", record)
    tag = cast(str, release_record["tag_name"])
    _ = tag.encode("utf-8")
    _ = tag[0]
    return FabroRelease(
        tag=tag,
        published_at=_parse_timestamp(text=cast(str, release_record["published_at"])),
    )


def _timestamp(*, value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
