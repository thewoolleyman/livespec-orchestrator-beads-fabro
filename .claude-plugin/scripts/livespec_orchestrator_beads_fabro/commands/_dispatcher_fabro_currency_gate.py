"""Fabro release-publication currency for one selected factory target."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_forge import (
    FabroForgeFailure,
    FabroRelease,
    release_observation,
    release_tag_is_ancestor,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "FabroCurrencyDecision",
    "fabro_currency_admission",
]

_SERVING_COMMIT_RE = re.compile(r"\(([0-9a-fA-F]{7,40})(?:\s|\))")
_VERSION_TIMEOUT_SECONDS = 20.0
_TRANSITION_DEADLINE_TEXT = "2026-11-14T00:00:00Z"
_TRANSITION_DEADLINE = datetime.fromisoformat(_TRANSITION_DEADLINE_TEXT.replace("Z", "+00:00"))


@dataclass(frozen=True, kw_only=True)
class FabroCurrencyDecision:
    """Whether one selected target may receive a dispatch."""

    admitted: bool
    message: str


def fabro_currency_admission(
    *,
    target: FactoryTarget,
    fabro_bin: str,
    repo: Path,
    runner: FabroRunner,
    now: datetime,
    cache_path: Path,
) -> FabroCurrencyDecision:
    """Resolve and reject one target whose exact published base is too old."""
    version = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(server_url=target.server, dev_token=target.dev_token),
        runner=runner,
        cwd=repo,
    ).client_version(timeout_seconds=_VERSION_TIMEOUT_SECONDS)
    match = cast("re.Match[str]", _SERVING_COMMIT_RE.search(version.text))
    serving_commit = match.group(1)
    observation = release_observation(
        cache_path=cache_path,
        repo=repo,
        runner=runner,
        now=now,
    )
    if isinstance(observation, FabroForgeFailure):
        return _stale_observation_refusal(
            target=target,
            serving_commit=serving_commit,
            failure=observation,
            now=now,
        )
    ordered = sorted(
        observation.releases,
        key=lambda release: (release.published_at, release.tag),
        reverse=True,
    )
    base: FabroRelease | None = None
    for release in ordered:
        if release_tag_is_ancestor(
            tag=release.tag,
            serving_commit=serving_commit,
            repo=repo,
            runner=runner,
        ):
            base = release
            break
    if base is None:
        return _no_base_refusal(
            target=target,
            serving_commit=serving_commit,
            newest=ordered[0],
            observed_at=observation.observed_at,
        )
    if base.tag == "v0.254.0" and now < _TRANSITION_DEADLINE:
        return _transition_admission(
            target=target,
            serving_commit=serving_commit,
            base=base,
        )
    return _window_refusal(
        target=target,
        serving_commit=serving_commit,
        base=base,
        newest=ordered[0],
        observed_at=observation.observed_at,
    )


def _transition_admission(
    *,
    target: FactoryTarget,
    serving_commit: str,
    base: FabroRelease,
) -> FabroCurrencyDecision:
    return FabroCurrencyDecision(
        admitted=True,
        message=(
            f"NOTICE: Fabro currency admission admits factory {target.name} under the "
            f"bd-ib-6tcjfx transition: serving integration commit {serving_commit} "
            f"resolves to the out-of-window {base.tag} base published "
            f"{_timestamp(value=base.published_at)}; this non-renewable exception expires "
            f"at {_TRANSITION_DEADLINE_TEXT}.\n"
        ),
    )


def _stale_observation_refusal(
    *,
    target: FactoryTarget,
    serving_commit: str,
    failure: FabroForgeFailure,
    now: datetime,
) -> FabroCurrencyDecision:
    return FabroCurrencyDecision(
        admitted=False,
        message=(
            f"ERROR: Fabro currency admission refused factory {target.name}: serving "
            f"integration commit {serving_commit}; cached release metadata observed "
            f"{_timestamp(value=failure.stale_observed_at)} is older than seven days, and "
            f"refresh failed at {_timestamp(value=now)} ({failure.detail}). Restore the "
            "fabro-sh/fabro GitHub Releases observation and retry dispatch.\n"
        ),
    )


def _no_base_refusal(
    *,
    target: FactoryTarget,
    serving_commit: str,
    newest: FabroRelease,
    observed_at: datetime,
) -> FabroCurrencyDecision:
    return FabroCurrencyDecision(
        admitted=False,
        message=(
            f"ERROR: Fabro currency admission refused factory {target.name}: serving "
            f"integration commit {serving_commit} has no published fabro-sh/fabro "
            f"release-tag ancestor; newest observed release {newest.tag} was published "
            f"{_timestamp(value=newest.published_at)}; release metadata was observed "
            f"{_timestamp(value=observed_at)}. Rebuild factory-integration on an exact "
            f"published release, re-pin factory {target.name}, and retry dispatch.\n"
        ),
    )


def _window_refusal(
    *,
    target: FactoryTarget,
    serving_commit: str,
    base: FabroRelease,
    newest: FabroRelease,
    observed_at: datetime,
) -> FabroCurrencyDecision:
    return FabroCurrencyDecision(
        admitted=False,
        message=(
            f"ERROR: Fabro currency admission refused factory {target.name}: serving "
            f"integration commit {serving_commit} resolves to base {base.tag} published "
            f"{_timestamp(value=base.published_at)}; newest observed release {newest.tag} "
            f"was published {_timestamp(value=newest.published_at)}; release metadata was "
            f"observed {_timestamp(value=observed_at)}; the base is more than "
            "30 calendar days behind the newest release. Rebuild factory-integration on an "
            f"eligible published fabro-sh/fabro release, re-pin factory {target.name}, and "
            "retry dispatch.\n"
        ),
    )


def _timestamp(*, value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
