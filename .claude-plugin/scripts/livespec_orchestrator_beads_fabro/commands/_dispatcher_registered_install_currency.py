"""Registered-install currency: is this SESSION executing the build its repository resolves?

A Claude Code session binds its plugin root ONCE, at session start, and keeps
it for the session's whole life. The install registry moves underneath it on
every `claude plugin update`, so a session older than the last update
dispatches through a build the operator has already replaced -- with no
warning of its own, and with a failure shape that reads as a factory outage.
Measured 2026-09-06: a three-day-old session dispatched livespec-overseer work
through a v0.124.1 cache build (the one installed build that templates the
sandbox prepare steps but predates the host-side substitution fix released in
v0.124.3) while that repository's registered install was already v0.129.1;
the run died at sandbox setup and was reported fleet-wide as a workflow-config
regression.

This is a DIFFERENT question from the release-staleness warning beside it.
That one asks whether the executing build lags the newest release, which an
operator may legitimately have declined to adopt. This one asks whether the
executing build lags what the operator DID adopt for this repository, which
only a stale session can produce -- so its remedy is a restart, never a
`claude plugin update` (bd-ib-97v4: an update cannot move a running session).

Like every ambient currency finding it is SURFACED, never enforced (the
ratified currency contract): the one blocking form remains the committed
`dispatcher.minimum_release` floor. A registry that cannot be read, a
repository with no registered install, and a build whose manifest does not
parse are each recorded UNDETERMINED, never as current.

Identity is read from each build's `plugin.json`, never from the cache
directory name, for the reasons `_needs_attention_release_adoption` records.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_install_registry import (
    plugin_install_records,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_core_roots import version_key
from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
    read_build_version,
)

__all__: list[str] = [
    "REGISTERED_INSTALL_LAG_STAGE",
    "RegisteredInstallVerdict",
    "default_install_record",
    "registered_install_verdict",
]

# The journal stage for an executing build older than the repository's
# registered install. Its own stage, distinct from the release-lag warning,
# because the two name different remedies: this one is cleared by restarting
# the session, the other by adopting a release.
REGISTERED_INSTALL_LAG_STAGE = "dispatcher-registered-install-lag"

# The plugin whose registered install is looked up -- this one, wherever the
# dispatcher happens to run. Never read from the governed repository's own
# manifest, which names that repository rather than this plugin.
_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"


@dataclass(frozen=True, kw_only=True)
class RegisteredInstallVerdict:
    """At most one detail is set; both `None` means the session executes a current build."""

    lag_detail: str | None
    undetermined_detail: str | None


def default_install_record() -> Path:  # pragma: no cover
    """The production install registry under the real HOME (integration-covered)."""
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def registered_install_verdict(
    *, plugin_root: Path, repo: Path, install_record: Path
) -> RegisteredInstallVerdict:
    """Compare the executing build against the build `repo` resolves from the registry.

    `plugin_root` is the root the running session executes from; `repo` is the
    dispatch target whose registry entry is consulted. Versions are compared as
    parsed manifest versions, so a build older than the registered one lags
    regardless of which cache-directory naming scheme either build uses.
    """
    registered = _registered_install_path(repo=repo, install_record=install_record)
    if registered is None:
        return _undetermined(
            reason=(
                f"no registered install of {_PLUGIN_NAME} for {repo} could be read "
                f"from {install_record}"
            )
        )
    registered_version = read_build_version(install_path=registered)
    executing_version = read_build_version(install_path=plugin_root)
    if registered_version is None or executing_version is None:
        return _undetermined(
            reason=(
                f"a build manifest did not parse (executing build at {plugin_root}, "
                f"registered build at {registered})"
            )
        )
    if version_key(name=executing_version) >= version_key(name=registered_version):
        return RegisteredInstallVerdict(lag_detail=None, undetermined_detail=None)
    return RegisteredInstallVerdict(
        lag_detail=(
            f"WARNING: this session executes dispatcher plugin build {executing_version} "
            f"from {plugin_root}, but {repo.name} resolves build {registered_version} from "
            f"{registered}: the session bound its plugin root at start and the registered "
            "install has moved since. Dispatch proceeds because ambient staleness is "
            "surfaced, not enforced. Restart the session, or invoke the registered build's "
            "scripts/bin entry point by explicit path; commit a `dispatcher.minimum_release` "
            "floor to refuse a known-broken build range outright."
        ),
        undetermined_detail=None,
    )


def _undetermined(*, reason: str) -> RegisteredInstallVerdict:
    return RegisteredInstallVerdict(lag_detail=None, undetermined_detail=reason)


def _registered_install_path(*, repo: Path, install_record: Path) -> Path | None:
    """The install path the registry records for `repo`, or None when none can be read.

    The registry traversal itself lives in `_dispatcher_plugin_install_registry`,
    which is the one reader of that file: this function is the narrower question
    asked of its records. A second traversal here would be a second set of
    tolerances for one harness-written file, and a shape one side dropped while
    the other kept it would make this currency finding and the host-wide
    sandbox-image enumeration disagree about which repositories exist.
    """
    target = repo.resolve()
    for record in plugin_install_records(install_record=install_record):
        if record.project_path.resolve() == target:
            return record.install_path
    return None
