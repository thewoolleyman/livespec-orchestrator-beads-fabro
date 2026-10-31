"""The classification-only dispatcher command for parked work items.

Plan-child disposition may only act on a recorded autonomy tier. A parked child
cannot rely on the dispatch wall to record one, because that wall would also
take the item. This command therefore binds the wall's shared classifier to one
named item and deliberately performs no admission, claim, or Fabro work.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    classify_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    RecordedSpecChangeTier,
    recorded_spec_change_tier,
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

    An item that already carries ANY classification record is reported as it
    stands, whatever specification it was taken against: the command appends
    only for an item with no record, so a stale one is left for the next cadence
    point to retake. The judgement is the one the pre-dispatch wall takes. Its
    ledger writes are held back until it has produced a classification, so a
    judgement that could not be obtained leaves the item's comments untouched
    and exits non-zero rather than recording a did-not-run alarm.
    """
    repo = Path(args.repo)
    item = next(
        (candidate for candidate in load_items(repo=repo) if candidate.id == args.item), None
    )
    if item is None:
        _ = write_stderr(text=f"ERROR: work-item {args.item} is not in the tenant at {repo}\n")
        return EXIT_PRECONDITION_ERROR
    path = store_config(repo=repo)
    bodies = item_comment_bodies(path=path, work_item_id=item.id)
    if bodies is None:
        _ = write_stderr(text=f"ERROR: {item.id}: ledger comments unreadable; nothing written\n")
        return EXIT_FAILURE
    standing = recorded_spec_change_tier(comments=bodies)
    if standing is not None:
        _ = write_stdout(text=_report(item_id=item.id, action="existing", recorded=standing))
        return 0
    held: list[str] = []

    def hold(*, body: str) -> None:
        held.append(body)

    outcome = classify_spec_change_tier(
        item=item, repo=repo, stage=_STAGE_CLASSIFY, comments=bodies, append=hold
    )
    if outcome.recorded is None:
        _ = write_stderr(
            text=f"ERROR: {item.id}: classification did not run ({outcome.cause}); no write\n"
        )
        return EXIT_FAILURE
    for body in held:
        append_work_item_comment(path=path, work_item_id=item.id, body=body)
    _ = write_stdout(text=_report(item_id=item.id, action="recorded", recorded=outcome.recorded))
    return 0


def _report(*, item_id: str, action: str, recorded: RecordedSpecChangeTier) -> str:
    """Render the classification that now stands against the item."""
    return f"{item_id}: {action} classification tier {recorded.tier}\n"
