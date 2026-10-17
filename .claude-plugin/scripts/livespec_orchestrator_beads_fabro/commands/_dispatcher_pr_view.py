"""The ONE journaled forge read of a publish branch's pull request.

Split out of `_dispatcher_engine_merge` by cohesion once pull-request
CONFIRMATION and merge POLLING became separate modules: both are public entry
points and both need this read, so it is a properly-named public interface
rather than a private helper either of them owns. A cross-module private import
is the thing that must not happen here — pyright strict (`reportPrivateUsage`)
and the `private_calls` check both reject it.

`include_publication` is the only dimension the read has. The ordinary view
already carries `headRefOid`, so a publication comparison needs just the branch
NAME and the owning REPOSITORY added; the fields are asked for only when a
caller is going to compare them, so the ordinary green dispatch pays nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    parse_pr_view,
    pr_view_argv,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        JournalWriter,
    )

__all__: list[str] = [
    "GH_TIMEOUT_SECONDS",
    "view_pr",
]

GH_TIMEOUT_SECONDS = 300.0
# `headRefOid` already rides the ordinary view, so only the branch name and the
# owning repository have to be added for a publication comparison.
_PUBLICATION_FIELDS = ",headRefName,headRepository"


def view_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    include_publication: bool = False,
) -> PrView | None:
    argv = pr_view_argv(plan=plan)
    if include_publication:
        argv[-1] = f"{argv[-1]}{_PUBLICATION_FIELDS}"
    result = runner.run(
        argv=argv,
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-view", result=result)
    if result.exit_code != 0:
        return None
    return parse_pr_view(stdout=result.stdout)
