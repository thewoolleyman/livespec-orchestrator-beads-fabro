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


def release_observation(
    *,
    cache_path: Path,
    repo: Path,
    runner: FabroRunner,
    now: datetime,
) -> FabroReleaseObservation:
    """Fetch one publication observation and preserve it for later reuse."""
    result = runner.run(
        argv=["gh", "api", "--paginate", "--slurp", _RELEASES_ENDPOINT],
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
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


def _timestamp(*, value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
