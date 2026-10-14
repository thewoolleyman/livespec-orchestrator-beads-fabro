"""The dispatch base every Dispatcher-launched run fetches into its sandbox clone.

WHY THE STEP EXISTS (work-item bd-ib-xlblgr, Scenario 61). Since the Dispatcher
began staging each run on a disposable `livespec/source/<id>` branch, the sandbox
clone is SINGLE-BRANCH: its `remote.origin.fetch` refspec names that staged branch
and nothing else. The committed prepare chain's opening `git fetch --unshallow`
fetches the CONFIGURED refspec, so it deepens the staged branch and brings in no
other ref. Nothing else in the rendered sequence fetched the governed repository's
default branch, and `implementation_diff`'s script is
`git diff --quiet origin/<default_branch>...HEAD`.

So that node exited 128 on `fatal: ambiguous argument 'origin/<default_branch>
...HEAD'`, `dead_implementer` then reported an unchanged tree, and the run failed
carrying a measurement failure dressed as a dead implementer. Measured 2026-10-14
on hp run 01M4Y28FVEBC6B2HH6J4QHRFKH (dolt-server item dolt-server-6fdarx):
`implement` succeeded after 13m37s with a 5-file, +245/-4 conclusion diff, and the
whole run was lost to the absent ref.

WHY THE REF WAS ABSENT EVERYWHERE, not only off this fleet's own repository. The
defect report left this as a lead, because every source-staged run that had passed
`implementation_diff` was a livespec-orchestrator-beads-fabro run. Measured
2026-10-14 inside the orchestrator's own sandbox for this very work-item:
`git rev-parse --verify origin/master` exited 128 and
`git config --get-all remote.origin.fetch` named only the staged branch. The ref is
therefore absent in EVERY repository; the orchestrator runs that passed did so
because their implementer SESSION fetched it, the implement prompt having asked for
`git log origin/<default_branch>..HEAD`. That is not something a prepare sequence
may rely on, which is why the fetch is rendered here rather than left to the agent.

WHY AN EXPLICIT DESTINATION REFSPEC, and not `git fetch origin <default_branch>`.
git updates a remote-tracking ref only for a refspec its own configuration names,
and a single-branch clone's configuration names only the staged branch. Measured
2026-10-14: in such a clone the bare form writes `FETCH_HEAD` and leaves
`refs/remotes/origin/<default_branch>` absent, exiting 0 with no warning — a fetch
that reports success while the ref the next node reads still does not exist. The
destination half of the refspec is therefore load-bearing rather than decoration.

WHY THE OVERLAY AND NOT `workflow.toml`. The committed run config is FORKED per
repository — `_dispatcher_paths.workflow_toml` resolves a dispatch target's own
`<repo>/.fabro/workflows/implement-work-item/workflow.toml` ahead of the bundled
one — so a prepare step written into one fork covers one consumer and silently
omits the rest. Only the overlay reaches every dispatch, which is the same reason
`_dispatcher_factory_provenance` and `_dispatcher_git_credential_helper` are
rendered there.

WHY IT MUST NOT FAIL SOFT. A prepare step that exits non-zero aborts the run before
any work is driven, and that is the direction this one belongs in: without the ref
the run spends its whole implement stage and then loses it at
`implementation_diff`, so a fetch that could not be taken is cheaper to report in
preparation than to discover afterwards. It carries no `|| true` for that reason.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    CONTRACT_INPUT_NAMES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    DEFAULT_BRANCH_FIELD,
)

__all__: list[str] = ["default_branch_fetch_prepare_steps_block"]

# The workflow-input name the governed repository's default branch crosses as,
# taken from the projection's own closed mapping rather than spelled here: the
# prepare-step scripts, the node prompts and the `--input` pairs all read ONE
# value, and a second spelling of its name is how this block would come to render
# for a field nothing projects.
_DEFAULT_BRANCH_INPUT = CONTRACT_INPUT_NAMES[DEFAULT_BRANCH_FIELD.attribute]


def default_branch_fetch_prepare_steps_block(*, prepare_inputs: Mapping[str, str] | None) -> str:
    """Render the dispatch-base fetch `[[run.prepare.steps]]` block.

    Empty string when no default branch is projected — a direct caller that wires
    no contract inputs at all, which renders exactly the overlay it did before this
    step existed. The branch is read through the projection's own input name rather
    than resolved here, because the contract is resolved ONCE per dispatch at
    plan-build time and every seam is a projection of that one object.

    The refspec is `shlex.quote`-ed because the step body is a shell command line
    and a branch name is repository-supplied text; the whole script is then
    `json.dumps`-ed to TOML-quote it, matching every sibling block in the overlay.
    The leading `+` makes the update non-fast-forward-tolerant, so a default branch
    that was force-pushed between two dispatches still lands rather than refusing
    the step.
    """
    default_branch = (prepare_inputs or {}).get(_DEFAULT_BRANCH_INPUT, "").strip()
    if not default_branch:
        return ""
    refspec = f"+refs/heads/{default_branch}:refs/remotes/origin/{default_branch}"
    script = f"git fetch --quiet origin {shlex.quote(refspec)}"
    lines = [
        "",
        "# --- Dispatcher-materialized dispatch-base fetch: bring the governed",
        "# --- repository's default branch into the SINGLE-BRANCH sandbox clone as",
        "# --- origin/<default_branch>, which the clone's own refspec never names and",
        "# --- which `git fetch --unshallow` therefore never brings in — the ref",
        "# --- `implementation_diff` and the check suite diff against (bd-ib-xlblgr) ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"
