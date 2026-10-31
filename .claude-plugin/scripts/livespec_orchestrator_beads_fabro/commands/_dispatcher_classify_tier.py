"""The classification-only dispatcher command for parked work items.

Plan-child disposition may only act on a recorded autonomy tier. A parked child
cannot rely on the dispatch wall to record one, because that wall would also
take the item. This command therefore binds the wall's shared classifier to one
named item and deliberately performs no admission, claim, or Fabro work.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    classify_item_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_outcome import (
    SpecChangeTierOutcome,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "add_classify_tier_arguments",
    "run_classify_tier_command",
]

_STAGE_CLASSIFY = "classify"


def add_classify_tier_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Add the narrow target selection accepted by `classify-tier`."""
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)


def run_classify_tier_command(*, args: argparse.Namespace) -> int:
    """Record or report one item's tier without dispatching it.

    The classifier is exactly the one the pre-dispatch wall uses. It owns the
    reuse read, so an existing classification causes neither a second ledger
    record nor a second model call; the rendered result makes that no-op visible
    to the operator who requested it.
    """
    repo = Path(args.repo)
    item = next(
        (candidate for candidate in load_items(repo=repo) if candidate.id == args.item), None
    )
    if item is None:
        _ = write_stderr(text=f"ERROR: work-item {args.item} is not in the tenant at {repo}\n")
        return EXIT_PRECONDITION_ERROR
    outcome = classify_item_spec_change_tier(
        item=item,
        repo=repo,
        path=store_config(repo=repo),
        stage=_STAGE_CLASSIFY,
    )
    _ = write_stdout(text=_classification_report(item_id=item.id, outcome=outcome))
    return 0


def _classification_report(*, item_id: str, outcome: SpecChangeTierOutcome) -> str:
    """Render the standing tier or the reason a classification was unavailable."""
    if outcome.recorded is None:
        return f"{item_id}: classification did not run ({outcome.cause})\n"
    action = "existing" if outcome.reused else "recorded"
    return f"{item_id}: {action} classification tier {outcome.recorded.tier}\n"
