"""Actionable decisions emitted by the Fabro currency predicate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_forge import (
    FabroForgeFailure,
    FabroRelease,
    FabroReleaseObservation,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroVersionResult

__all__: list[str] = [
    "TRANSITION_DEADLINE",
    "TRANSITION_DEADLINE_TEXT",
    "FabroCurrencyDecision",
    "ancestry_refusal",
    "no_base_refusal",
    "release_observation_refusal",
    "transition_admission",
    "unidentifiable_build_refusal",
    "window_refusal",
]

TRANSITION_DEADLINE_TEXT = "2026-11-14T00:00:00Z"
TRANSITION_DEADLINE = datetime.fromisoformat(TRANSITION_DEADLINE_TEXT.replace("Z", "+00:00"))


@dataclass(frozen=True, kw_only=True)
class FabroCurrencyDecision:
    """Whether one selected target may receive a dispatch."""

    admitted: bool
    message: str


def transition_admission(
    *, target: FactoryTarget, serving_commit: str, base: FabroRelease
) -> FabroCurrencyDecision:
    return FabroCurrencyDecision(
        admitted=True,
        message=(
            f"NOTICE: Fabro currency admission admits factory {target.name} under the "
            f"bd-ib-6tcjfx transition: serving integration commit {serving_commit} "
            f"resolves to the out-of-window {base.tag} base published "
            f"{_timestamp(value=base.published_at)}; this non-renewable exception expires "
            f"at {TRANSITION_DEADLINE_TEXT}.\n"
        ),
    )


def release_observation_refusal(
    *,
    target: FactoryTarget,
    serving_commit: str,
    failure: FabroForgeFailure,
    now: datetime,
) -> FabroCurrencyDecision:
    if failure.stale_observation is None:
        return FabroCurrencyDecision(
            admitted=False,
            message=(
                f"ERROR: Fabro currency admission refused factory {target.name}: serving "
                f"integration commit {serving_commit}; no cached release metadata "
                f"observation exists, and refresh failed at {_timestamp(value=now)} "
                f"({failure.detail}); newest observed release and observation time are "
                "unavailable. Restore the fabro-sh/fabro GitHub Releases observation and "
                "retry dispatch.\n"
            ),
        )
    stale = failure.stale_observation
    newest = _newest(releases=stale.releases)
    return FabroCurrencyDecision(
        admitted=False,
        message=(
            f"ERROR: Fabro currency admission refused factory {target.name}: serving "
            f"integration commit {serving_commit}; cached release metadata observed "
            f"{_timestamp(value=stale.observed_at)} is older than seven days, and refresh "
            f"failed at {_timestamp(value=now)} ({failure.detail}); newest observed release "
            f"{newest.tag} was published {_timestamp(value=newest.published_at)}. Restore "
            "the fabro-sh/fabro GitHub Releases observation and retry dispatch.\n"
        ),
    )


def unidentifiable_build_refusal(
    *,
    target: FactoryTarget,
    version: FabroVersionResult,
    observation: FabroReleaseObservation,
) -> FabroCurrencyDecision:
    newest = _newest(releases=observation.releases)
    return FabroCurrencyDecision(
        admitted=False,
        message=(
            f"ERROR: Fabro currency admission refused factory {target.name}: serving "
            f"integration commit is unknown because {_version_failure(version=version)}; "
            f"newest observed release {newest.tag} was published "
            f"{_timestamp(value=newest.published_at)}; release metadata was observed "
            f"{_timestamp(value=observation.observed_at)}. Restore factory "
            f"{target.name}'s Fabro binary so `fabro --version` reports its serving "
            "integration commit, then retry dispatch.\n"
        ),
    )


def ancestry_refusal(
    *,
    target: FactoryTarget,
    serving_commit: str,
    release: FabroRelease,
    newest: FabroRelease,
    observed_at: datetime,
    failure: FabroForgeFailure,
) -> FabroCurrencyDecision:
    return FabroCurrencyDecision(
        admitted=False,
        message=(
            f"ERROR: Fabro currency admission refused factory {target.name}: serving "
            f"integration commit {serving_commit}; could not determine whether published "
            f"release {release.tag} is an ancestor of the serving commit ({failure.detail}); "
            f"newest observed release {newest.tag} was published "
            f"{_timestamp(value=newest.published_at)}; release metadata was observed "
            f"{_timestamp(value=observed_at)}. Restore fabro-sh/fabro compare evidence and "
            "retry dispatch.\n"
        ),
    )


def no_base_refusal(
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


def window_refusal(
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


def _version_failure(*, version: FabroVersionResult) -> str:
    if version.command.exit_code != 0:
        return (
            f"fabro --version failed with exit {version.command.exit_code} "
            f"({version.command.stderr.strip()})"
        )
    return "fabro --version output did not identify the serving integration commit"


def _timestamp(*, value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _newest(*, releases: tuple[FabroRelease, ...]) -> FabroRelease:
    return max(releases, key=lambda release: (release.published_at, release.tag))
