"""Plugin-currency gate for dispatcher builds at dispatch admission.

Ambient release-staleness is SURFACED, never enforced. Running the payload the
operator provisioned is legitimate per the self-update contract in
SPECIFICATION/contracts.md, so this gate has NO blocking authority on the sole
ground that a newer `refs/heads/release` head exists than the executing build.
Plugin builds bind at SESSION START while this
gate probes a MOVING ref at DISPATCH TIME, so a blocking comparison against that
head refused every live session's dispatches the moment a release was published
mid-session — the homelab incident of 2026-08-29, re-based here onto the ratified
v089 contract.

The ONE blocking currency form is the deliberate operator floor in
`_dispatcher_minimum_release_floor.py`.

A SECOND ambient finding, equally non-blocking, compares the executing build
against the build the dispatch target's install registry records
(`_dispatcher_registered_install_currency.py`). A build behind the RELEASE may
be an operator's deliberate choice; a build behind the REGISTERED INSTALL can
only be a session that bound its plugin root before the last update, so that
finding names a restart rather than a plugin update as its remedy.

Currency that cannot be OBSERVED is recorded as UNDETERMINED under its own
journal stage and proceeds. That stage is what keeps "we could not tell" from
being read back as "the build is current" — the contract requires the two to be
distinguishable, and a shared warning stage cannot express the difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_currency_probe import (
    build_matches_ref,
    executing_cache_build_id,
    git_checkout_head,
    latest_release_ref_argv,
    master_ref_argv,
    remote_ref_sha,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_minimum_release_floor import (
    MinimumReleaseVerdict,
    minimum_release_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_registered_install_currency import (
    REGISTERED_INSTALL_LAG_STAGE,
    registered_install_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_unreleased_master import (
    unreleased_dispatcher_commits_argv,
    unreleased_master_detail,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
    "CURRENCY_UNDETERMINED_STAGE",
    "MINIMUM_RELEASE_REFUSED_STAGE",
    "REGISTERED_INSTALL_LAG_STAGE",
    "STALENESS_WARNING_STAGE",
    "DispatcherStalenessDecision",
    "DispatcherStalenessMessage",
    "apply_dispatcher_staleness_gate",
    "dispatcher_staleness_decision",
    "latest_release_ref_argv",
    "master_ref_argv",
    "unreleased_dispatcher_commits_argv",
]

STALENESS_WARNING_STAGE = "dispatcher-staleness-warning"
# The journal stage for a currency verdict that could not be REACHED. Distinct
# from the plain warning stage on purpose: a reader tallying "no refusal" must
# still be able to tell an observed-current build from an unobservable one.
CURRENCY_UNDETERMINED_STAGE = "dispatcher-currency-undetermined"
# The one blocking stage this gate can still journal. Deliberately NOT the
# retired `dispatcher-staleness-refused` name, so nothing can read an ambient
# staleness refusal — which no longer exists — into a deliberate operator floor.
MINIMUM_RELEASE_REFUSED_STAGE = "dispatcher-minimum-release-refused"

_EXIT_PRECONDITION_ERROR = 3
_PLUGIN_UPDATE_REMEDY = (
    "claude plugin update livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
)


class _StalenessJournal(Protocol):
    """Append-only journal seam for the pre-admission staleness gate."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class DispatcherStalenessMessage:
    """One operator-facing gate message, carrying the journal stage it records under."""

    detail: str
    stage: str = STALENESS_WARNING_STAGE


@dataclass(frozen=True, kw_only=True)
class DispatcherStalenessDecision:
    """The gate result: at most one refusal plus zero or more warnings."""

    refusal: DispatcherStalenessMessage | None
    warnings: tuple[DispatcherStalenessMessage, ...]


def dispatcher_staleness_decision(
    *,
    plugin_root: Path,
    runner: CommandRunner,
    cwd: Path | None = None,
    install_record: Path | None = None,
    executing_payload: Path | None = None,
) -> DispatcherStalenessDecision:
    """Refuse ONLY below a committed floor; surface every other currency finding.

    Identity is established FIRST: a git-checkout plugin root is exempt, and a
    root that is neither a checkout nor a release-cache sha prefix has no
    provable identity — currency is recorded UNDETERMINED and dispatch proceeds
    WITHOUT any network probe (the bd-ib-n7ce4n deadlock case: a verdict that
    cannot be established must never block dispatch).

    `cwd` is where the committed `dispatcher.minimum_release` floor is read
    from — the dispatch target repo, not the plugin root — and it is the
    repository whose registered install `install_record` is consulted for.
    With no `install_record` the registered-install comparison is skipped: a
    caller that does not name the registry is not asking that question.

    `executing_payload` is the tree the minimum-release floor JUDGES, and it is
    not `plugin_root`: the floor asks "which release am I running", which only
    the retained payload answers stably, while `plugin_root` answers "which
    installation is present" for the checkout exemption, the ambient build id
    and the registered-install comparison. Forwarded unresolved; the floor owns
    the default.
    """
    if git_checkout_head(plugin_root=plugin_root, runner=runner) is not None:
        return DispatcherStalenessDecision(refusal=None, warnings=())
    target = cwd if cwd is not None else Path.cwd()
    decision = _release_currency_decision(
        plugin_root=plugin_root, runner=runner, cwd=target, executing_payload=executing_payload
    )
    if install_record is None or decision.refusal is not None:
        return decision
    return DispatcherStalenessDecision(
        refusal=None,
        warnings=decision.warnings
        + _registered_install_warnings(
            plugin_root=plugin_root, repo=target, install_record=install_record
        ),
    )


def _release_currency_decision(
    *,
    plugin_root: Path,
    runner: CommandRunner,
    cwd: Path,
    executing_payload: Path | None,
) -> DispatcherStalenessDecision:
    """The floor verdict when one is committed, else the ambient release comparison."""
    floor = minimum_release_verdict(
        plugin_root=plugin_root, cwd=cwd, executing_payload=executing_payload
    )
    if floor is not None:
        decided = _floor_decision(floor=floor)
        if decided is not None:
            return decided
    return _ambient_currency_decision(plugin_root=plugin_root, runner=runner)


def _registered_install_warnings(
    *,
    plugin_root: Path,
    repo: Path,
    install_record: Path,
) -> tuple[DispatcherStalenessMessage, ...]:
    """Surface a session executing a build older than the repo's registered install."""
    verdict = registered_install_verdict(
        plugin_root=plugin_root, repo=repo, install_record=install_record
    )
    if verdict.undetermined_detail is not None:
        return _undetermined(reason=verdict.undetermined_detail).warnings
    if verdict.lag_detail is not None:
        return (
            DispatcherStalenessMessage(
                detail=verdict.lag_detail, stage=REGISTERED_INSTALL_LAG_STAGE
            ),
        )
    return ()


def apply_dispatcher_staleness_gate(
    *,
    plugin_root: Path,
    journal: _StalenessJournal,
    runner: CommandRunner | None = None,
    cwd: Path | None = None,
    install_record: Path | None = None,
    executing_payload: Path | None = None,
) -> int | None:
    """Emit the currency decision; return an exit code only when dispatch must stop.

    The precondition exit code is reachable ONLY through a committed
    `dispatcher.minimum_release` floor. Ambient release-staleness returns `None`
    here however far behind the executing build is, and so does a build behind
    the repository's registered install.
    """
    decision = dispatcher_staleness_decision(
        plugin_root=plugin_root,
        runner=runner if runner is not None else ShellCommandRunner(),
        cwd=cwd,
        install_record=install_record,
        executing_payload=executing_payload,
    )
    for warning in decision.warnings:
        _ = write_stderr(text=f"{warning.detail}\n")
        journal.append(
            record={
                "stage": warning.stage,
                "detail": warning.detail,
                "blocking": False,
            }
        )
    if decision.refusal is None:
        return None
    _ = write_stderr(text=f"{decision.refusal.detail}\n")
    journal.append(
        record={
            "stage": decision.refusal.stage,
            "detail": decision.refusal.detail,
            "blocking": True,
        }
    )
    return _EXIT_PRECONDITION_ERROR


def _floor_decision(*, floor: MinimumReleaseVerdict) -> DispatcherStalenessDecision | None:
    """Map the floor's verdict into a gate decision; `None` when the floor cleared."""
    if floor.refusal_detail is not None:
        return DispatcherStalenessDecision(
            refusal=DispatcherStalenessMessage(
                detail=floor.refusal_detail,
                stage=MINIMUM_RELEASE_REFUSED_STAGE,
            ),
            warnings=(),
        )
    if floor.undetermined_detail is not None:
        return _undetermined(reason=floor.undetermined_detail)
    return None


def _ambient_currency_decision(
    *,
    plugin_root: Path,
    runner: CommandRunner,
) -> DispatcherStalenessDecision:
    """Surface how the executing build compares to release — never refuse on it."""
    build_id = executing_cache_build_id(plugin_root=plugin_root)
    if build_id is None:
        return _undetermined(
            reason=(
                "the gate could not establish the executing build identity (plugin root "
                f"{plugin_root.name!r} is neither a git checkout nor a release-cache build id)"
            )
        )
    release_sha = remote_ref_sha(runner=runner, argv=latest_release_ref_argv())
    if release_sha is None:
        return _undetermined(reason="the gate could not inspect latest release")
    master_sha = remote_ref_sha(runner=runner, argv=master_ref_argv())
    unreleased = unreleased_master_detail(
        runner=runner,
        release_sha=release_sha,
        master_sha=master_sha,
    )
    return DispatcherStalenessDecision(
        refusal=None,
        warnings=(
            _lag_warnings(build_id=build_id, release_sha=release_sha, master_sha=master_sha)
            + (() if unreleased is None else (DispatcherStalenessMessage(detail=unreleased),))
        ),
    )


def _undetermined(*, reason: str) -> DispatcherStalenessDecision:
    return DispatcherStalenessDecision(
        refusal=None,
        warnings=(
            DispatcherStalenessMessage(
                detail=(
                    f"WARNING: dispatcher plugin currency could not be determined: {reason}. "
                    "Dispatch proceeds."
                ),
                stage=CURRENCY_UNDETERMINED_STAGE,
            ),
        ),
    )


def _lag_warnings(
    *,
    build_id: str,
    release_sha: str,
    master_sha: str | None,
) -> tuple[DispatcherStalenessMessage, ...]:
    """The ambient-staleness surfacing that replaced the retired blocking refusal."""
    if build_matches_ref(build_id=build_id, ref_sha=release_sha) or (
        master_sha is not None and build_matches_ref(build_id=build_id, ref_sha=master_sha)
    ):
        return ()
    return (
        DispatcherStalenessMessage(
            detail=(
                f"WARNING: dispatcher plugin build {build_id} lags latest release "
                f"{release_sha[:12]}; dispatch proceeds because ambient staleness is "
                f"surfaced, not enforced. Run `{_PLUGIN_UPDATE_REMEDY}` and restart to adopt it."
            )
        ),
    )
