"""Turn an unreadable latest master-CI run lookup into its refusal outcome."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    MasterCiPipeline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_lookups import (
    UNKNOWN_RUN,
    has_stored_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_refusals import (
    CREDENTIAL_REMEDY,
    PIPELINE_REMEDY,
    MasterCiOutcome,
    unprovable_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)

__all__: list[str] = ["lookup_failure_outcome"]

_STDERR_EXCERPT = 200


def lookup_failure_outcome(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    result: CommandResult,
) -> MasterCiOutcome:
    """Return the credential or pipeline refusal for a failed list-runs command."""
    if not has_stored_credential(repo=repo, runner=runner):
        return unprovable_outcome(
            pipeline=pipeline,
            branch=branch,
            run_id=UNKNOWN_RUN,
            cause=f"no usable `gh` credential on this host; `gh` exited {result.exit_code}",
            remedy=CREDENTIAL_REMEDY,
        )
    excerpt = result.stderr.strip()[:_STDERR_EXCERPT] or "<empty stderr>"
    return unprovable_outcome(
        pipeline=pipeline,
        branch=branch,
        run_id=UNKNOWN_RUN,
        cause=(
            f"the resolved pipeline could not be found; credentialed `gh` exited "
            f"{result.exit_code}: {excerpt}"
        ),
        remedy=PIPELINE_REMEDY,
    )
