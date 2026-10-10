"""GitHub release and ancestry evidence for Fabro currency admission."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from urllib.parse import quote

from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "FabroForgeFailure",
    "FabroRelease",
    "FabroReleaseObservation",
    "release_observation",
    "release_tag_is_ancestor",
]

_RELEASES_ENDPOINT = "repos/fabro-sh/fabro/releases?per_page=100"
_COMPARE_ENDPOINT = "repos/fabro-sh/fabro/compare/{tag}...{commit}"
_FORGE_TIMEOUT_SECONDS = 60.0


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
    stale_observed_at: datetime


def release_observation(
    *,
    cache_path: Path,
    repo: Path,
    runner: FabroRunner,
    now: datetime,
) -> FabroReleaseObservation | FabroForgeFailure:
    """Refresh publication evidence, retaining a stale timestamp for refusal."""
    stale = _read_cache(path=cache_path) if cache_path.is_file() else None
    result = runner.run(
        argv=["gh", "api", "--paginate", "--slurp", _RELEASES_ENDPOINT],
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return FabroForgeFailure(
            detail=result.stderr.strip(),
            stale_observed_at=cast(FabroReleaseObservation, stale).observed_at,
        )
    pages = cast("list[list[dict[str, object]]]", json.loads(result.stdout))
    releases = tuple(
        FabroRelease(
            tag=cast(str, record["tag_name"]),
            published_at=_parse_timestamp(text=cast(str, record["published_at"])),
        )
        for page in pages
        for record in page
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
) -> bool:
    endpoint = _COMPARE_ENDPOINT.format(
        tag=quote(tag, safe=""),
        commit=quote(serving_commit, safe=""),
    )
    result = runner.run(
        argv=["gh", "api", endpoint],
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    payload = cast("dict[str, object]", json.loads(result.stdout))
    return payload["status"] in {"ahead", "identical"}


def _parse_timestamp(*, text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _read_cache(*, path: Path) -> FabroReleaseObservation:
    payload = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
    records = cast("list[dict[str, object]]", payload["releases"])
    return FabroReleaseObservation(
        observed_at=_parse_timestamp(text=cast(str, payload["observed_at"])),
        releases=tuple(
            FabroRelease(
                tag=cast(str, record["tag_name"]),
                published_at=_parse_timestamp(text=cast(str, record["published_at"])),
            )
            for record in records
        ),
    )


def _timestamp(*, value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
