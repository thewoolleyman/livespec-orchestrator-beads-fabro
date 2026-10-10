"""Fabro release-publication currency for one selected factory target."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_diagnostics import (
    TRANSITION_DEADLINE,
    FabroCurrencyDecision,
    ancestry_refusal,
    no_base_refusal,
    release_observation_refusal,
    transition_admission,
    unidentifiable_build_refusal,
    window_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_forge import (
    FabroForgeFailure,
    FabroRelease,
    FabroReleaseObservation,
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
_CURRENCY_WINDOW = timedelta(days=30)


@dataclass(frozen=True, kw_only=True)
class _CurrencyEvidence:
    serving_commit: str
    observation: FabroReleaseObservation


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
    evidence = _currency_evidence(
        target=target,
        fabro_bin=fabro_bin,
        repo=repo,
        runner=runner,
        now=now,
        cache_path=cache_path,
    )
    if isinstance(evidence, FabroCurrencyDecision):
        return evidence
    serving_commit = evidence.serving_commit
    observation = evidence.observation
    ordered = sorted(
        observation.releases,
        key=lambda release: (release.published_at, release.tag),
        reverse=True,
    )
    base: FabroRelease | None = None
    for release in ordered:
        ancestry = release_tag_is_ancestor(
            tag=release.tag,
            serving_commit=serving_commit,
            repo=repo,
            runner=runner,
        )
        if isinstance(ancestry, FabroForgeFailure):
            return ancestry_refusal(
                target=target,
                serving_commit=serving_commit,
                release=release,
                newest=ordered[0],
                observed_at=observation.observed_at,
                failure=ancestry,
            )
        if ancestry:
            base = release
            break
    if base is None:
        return no_base_refusal(
            target=target,
            serving_commit=serving_commit,
            newest=ordered[0],
            observed_at=observation.observed_at,
        )
    if base.tag == "v0.254.0" and now < TRANSITION_DEADLINE:
        return transition_admission(
            target=target,
            serving_commit=serving_commit,
            base=base,
        )
    newest = ordered[0]
    if newest.published_at - base.published_at > _CURRENCY_WINDOW:
        return window_refusal(
            target=target,
            serving_commit=serving_commit,
            base=base,
            newest=newest,
            observed_at=observation.observed_at,
        )
    return FabroCurrencyDecision(admitted=True, message="")


def _currency_evidence(
    *,
    target: FactoryTarget,
    fabro_bin: str,
    repo: Path,
    runner: FabroRunner,
    now: datetime,
    cache_path: Path,
) -> _CurrencyEvidence | FabroCurrencyDecision:
    version = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(server_url=target.server, dev_token=target.dev_token),
        runner=runner,
        cwd=repo,
    ).client_version(timeout_seconds=_VERSION_TIMEOUT_SECONDS)
    match = _SERVING_COMMIT_RE.search(version.text)
    serving_commit = match.group(1) if match is not None else "unknown"
    observation = release_observation(
        cache_path=cache_path,
        repo=repo,
        runner=runner,
        now=now,
    )
    if isinstance(observation, FabroForgeFailure):
        return release_observation_refusal(
            target=target,
            serving_commit=serving_commit,
            failure=observation,
            now=now,
        )
    if match is None:
        return unidentifiable_build_refusal(
            target=target,
            version=version,
            observation=observation,
        )
    return _CurrencyEvidence(serving_commit=serving_commit, observation=observation)
