"""The marker-removal section an incident's normal repayment dispatch carries.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle", scenario
"a successful incident merge reenters normal factory on the same item": the
repayment pull request removes the `EXPEDITED_INCIDENT_RESPONSE flag: <item-id>`
marker. Completion refuses closure while master still carries it, so a repayment
run never told to remove it merges a marker that blocks completion (measured
2026-11-09 on livespec-dev-tooling-e62ss6, PR #3883).

The section is authored by the Dispatcher from the item's incident chain and a
scan of the default branch, not read off the item's prose, which is why it is
handed to `render_goal` rather than assembled there. A scan that cannot be taken
is rendered as unread, never as an empty answer: "no path carries it" is a claim
the brief must not make on the strength of a failed read.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES
from livespec_orchestrator_beads_fabro._incident_repayment_scope import (
    incident_marker,
    repayment_brief,
    repayment_scope,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_incident_closure import (
    incident_standing_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "marker_paths_on_default_branch",
    "repayment_goal_for",
    "repayment_goal_section",
]

_HEADING = "Expedited incident repayment (remove the incident marker):"
_NO_MATCH = 1
_TIMEOUT_SECONDS = 60.0


def repayment_goal_section(
    *, attempt: IncidentAttempt, marker_paths: tuple[str, ...] | None
) -> str:
    """The brief section for one repayment attempt; `None` paths means the scan was unread."""
    brief = repayment_brief(scope=repayment_scope(attempt=attempt), marker_paths=marker_paths)
    return f"\n{_HEADING}\n{brief}"


def marker_paths_on_default_branch(
    *, runner: CommandRunner, repo: Path, marker: str, default_branch: str | None
) -> tuple[str, ...] | None:
    """The paths of the freshly fetched default branch carrying `marker`; None when unreadable."""
    if default_branch is None:
        return None
    ref = f"refs/remotes/origin/{default_branch}"
    fetched = runner.run(
        argv=[
            "git",
            "fetch",
            "--quiet",
            "--no-tags",
            "origin",
            f"+refs/heads/{default_branch}:{ref}",
        ],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    if fetched.exit_code != 0:
        return None
    result = runner.run(
        argv=["git", "grep", "-l", "-F", "-e", marker, ref, "--"],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    if result.exit_code == _NO_MATCH and not result.stdout and not result.stderr.strip():
        return ()
    if result.exit_code != 0:
        return None
    prefix = f"{ref}:"
    return tuple(line.removeprefix(prefix) for line in result.stdout.splitlines() if line)


def repayment_goal_for(*, repo: Path, item_id: str, runner: CommandRunner | None = None) -> str:
    """The section for a dispatch of `item_id`; empty unless it is an incident's repayment."""
    standing = incident_standing_for(config=store_config(repo=repo), item_id=item_id)
    if standing.kind != "incident" or standing.reading is None:
        return ""
    attempt = standing.reading.attempt
    if attempt.phase not in REPAYMENT_PHASES:
        return ""
    active = runner if runner is not None else ShellCommandRunner()
    paths = marker_paths_on_default_branch(
        runner=active,
        repo=repo,
        marker=incident_marker(item_id=item_id),
        default_branch=resolve_default_branch(repo=repo, runner=active),
    )
    return repayment_goal_section(attempt=attempt, marker_paths=paths)
