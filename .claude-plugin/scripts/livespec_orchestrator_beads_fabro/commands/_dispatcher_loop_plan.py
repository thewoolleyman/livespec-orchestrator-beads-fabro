"""Per-item `DispatchPlan` construction for the dispatch loop.

Split out of `_dispatcher_loop` by cohesion: everything here answers "what
does THIS item's run look like" — where its per-dispatch scratch files live,
which janitor checkout it gets, which factory it goes to, its effective
review-fix policy, and the subprocess ceiling derived from its resolved node
timeouts. `_dispatcher_loop` is left with the other concern, driving the
dispatch and routing each pre-run refusal to its own journal stage.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._store_merge_hold import merge_hold_from_labels
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    resolve_fabro_sandbox_image,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_environment import (
    factory_environment_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    livespec_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    build_plan,
    janitor_checkout_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_merge_on_review_cap,
    effective_review_fix_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_MERGE_ON_REVIEW_CAP,
    DEFAULT_REVIEW_FIX_CAP,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import (
    DEFAULT_RUN_WALL_BUDGET,
    RunWallBudget,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    sandbox_image_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_window import (
    stall_window_from_timeouts,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    NodeTimeouts,
    derive_fabro_timeout_seconds,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "dispatch_plan_for_item",
    "goal_file_path",
    "overlay_file_path",
    "workflow_payload_dir",
]


def _readable_text(*, path: Path) -> str:
    """A committed payload's text, or the empty string when it cannot be read.

    Unreadability is not a third answer HERE: this text is consulted only for
    which input names the workflow declares, so a payload nobody could read
    declares none and the dispatch sends no contract inputs. The refusal an
    unreadable workflow config earns belongs to the materialization stage, which
    names the file.
    """
    text = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    return "" if isinstance(text, AttemptFailure) else text


def goal_file_path(*, work_item_id: str) -> Path:
    """The per-dispatch rendered run goal (`--goal-file`)."""
    return Path(tempfile.gettempdir()) / f"fabro-goal-{work_item_id}.md"


def overlay_file_path(*, work_item_id: str) -> Path:
    """The per-dispatch uncommitted run-config overlay (mode 600)."""
    return Path(tempfile.gettempdir()) / f"fabro-run-config-{work_item_id}.toml"


def workflow_payload_dir(*, work_item_id: str) -> Path:
    """The per-dispatch workflow payload (rendered graph plus its prompts)."""
    return Path(tempfile.gettempdir()) / f"fabro-workflow-{work_item_id}"


def dispatch_plan_for_item(  # noqa: PLR0913 — kw-only plan resolver; each field is an independent caller input.
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    janitor: tuple[str, ...] | None,
    raw_labels: tuple[str, ...],
    timeouts: NodeTimeouts,
    run_wall_budget: RunWallBudget = DEFAULT_RUN_WALL_BUDGET,
    runner: CommandRunner,
    committed_workflow: Path,
    acp_nodes: AcpNodeResolution | None = None,
) -> DispatchPlan:
    """Resolve one item's dispatch plan from its args, labels and timeouts.

    The `runner` is here for ONE call: the ratified two-route default-branch
    probe, taken once, at plan build, because the plan's integration contract
    carries that branch and every seam downstream reads it from there rather
    than re-probing. `committed_workflow` is read only for the input NAMES the
    dispatched payload declares.
    """
    factory_target = cast("FactoryTarget", args.fabro_factory_target)
    return build_plan(
        repo=repo,
        work_item_id=item.id,
        workflow_toml=overlay_file_path(work_item_id=item.id),
        goal_file=goal_file_path(work_item_id=item.id),
        fabro_bin=args.fabro_bin,
        fabro_factory_name=factory_target.name,
        fabro_factory_server=factory_target.server,
        fabro_factory_dev_token=factory_target.dev_token,
        fabro_factory_environment=factory_environment_id(factory=factory_target),
        # WHERE this dispatch's sandbox image comes from, decided ONCE here and
        # projected to both consumers off the plan: the launch overlay renders
        # from it and the dispatch record names it. An unreadable
        # `.livespec.jsonc` falls back to "no configured override", visibly and
        # here rather than inside the reader. `unsafe_perform_io` is required:
        # `IOResult.value_or` returns `IO[value]`, not the value.
        sandbox_image=sandbox_image_source(
            factory_environment=factory_environment_id(factory=factory_target),
            configured_image=unsafe_perform_io(
                resolve_fabro_sandbox_image(cwd=repo).value_or(None)
            ),
        ),
        janitor=janitor,
        janitor_checkout=janitor_checkout_path(repo=repo, work_item_id=item.id),
        config_text=livespec_config_text(repo=repo),
        default_branch=resolve_default_branch(repo=repo, runner=runner),
        committed_workflow_text=_readable_text(path=committed_workflow),
        # An unreadable `.livespec.jsonc` falls back to the documented
        # defaults, visibly and here rather than inside the reader.
        # `unsafe_perform_io` is required: `IOResult.value_or` returns
        # `IO[value]`, not the value.
        review_fix_cap=unsafe_perform_io(
            effective_review_fix_cap(item=item, cwd=repo, raw_labels=raw_labels).value_or(
                DEFAULT_REVIEW_FIX_CAP
            )
        ),
        merge_on_review_cap=unsafe_perform_io(
            effective_merge_on_review_cap(item=item, cwd=repo, raw_labels=raw_labels).value_or(
                DEFAULT_MERGE_ON_REVIEW_CAP
            )
        ),
        # The merge hold reads straight off the same raw labels, with no
        # `.livespec.jsonc` leg and no `IOResult` around it, because it has NO
        # repository-level default to fall through to and no value space of its
        # own: the `merge-hold:` label's PRESENCE is the effective hold. An
        # `effective_merge_hold` beside the cap overrides would invent a
        # precedence the ratified contract deliberately does not have.
        merge_hold=merge_hold_from_labels(labels=raw_labels),
        # The `fabro run` subprocess ceiling FOLLOWS the resolved graph rather
        # than a constant, so lengthening a node cannot outrun the poller and
        # shortening one is not masked.
        fabro_timeout_seconds=derive_fabro_timeout_seconds(timeouts=timeouts),
        # The host-side stall watchdog's window is a PROJECTION of that same
        # resolution — `dispatcher.stall_timeout_seconds` through the node
        # timeouts' own layers — so the window the watchdog grades against, the
        # `stall_timeout` written into the rendered graph, and the subprocess
        # ceiling derived above all come from ONE read of the file.
        stall_window=stall_window_from_timeouts(timeouts=timeouts),
        # And the WHOLE resolution beside that projection, because the host
        # watchdog grades a quiet stretch inside a COMMAND node against THAT
        # node's timeout rather than the stall window — the same one read of
        # the file, so the bound the watchdog applies is the value the
        # rendered graph gave the node.
        node_timeouts=timeouts,
        # And the WHOLE-RUN WALL BUDGET from the same read, which the
        # pre-dispatch admission already graded against those node timeouts.
        # Projected off the materialized payload rather than re-resolved, so
        # the figure the watchdog cancels against is the figure the refusal
        # passed and the dispatch record names.
        run_wall_budget=run_wall_budget,
        # Already resolved and journaled by the caller, so the run renders the
        # adapters the dispatch record names rather than a re-derivation.
        acp_nodes=acp_nodes,
    )
