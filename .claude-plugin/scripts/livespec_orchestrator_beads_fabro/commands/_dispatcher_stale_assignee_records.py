"""What a stale-assignee clearance LEAVES: its journal row and its ledger comment.

PURE. A *stale assignee* is a work-item resting at `ready` whose assignee is
still `fabro`. Clearing it removes that assignee and changes nothing else, so
the two durable records are the whole account of what happened, and both are
rendered here from one set of facts rather than from two readings that could
disagree.

THE STAGE NAME IS THE CONTRACT'S. "It MUST journal one `stale-assignee-clear`
record naming the item, the run id, the factory and the run state", and that
record "keeps the item released for recovery after its assignee is gone", so
`_dispatcher_recovery_release` reads this literal by import. It is a stage of
its own, never a field on another recovery's row: the clearance's effects are
"keyed by item, run and the `stale-assignee-clear` kind, so they are distinct
from any recovery effect earlier written for the same item and run".

THE COMMENT NAMES THE RUN AND THE FACTORY IN FULL. The dispatch journal lives
under the `tmp/` tree of whichever checkout ran the pass; the ledger comment is
the only account an operator reading the item later can still find. A comment
can be neither edited nor deleted, so it carries no template opener, no shell
quoting and no credential.
"""

from __future__ import annotations

__all__: list[str] = [
    "STALE_ASSIGNEE_CLEAR_STAGE",
    "STALE_ASSIGNEE_COMMENT_MARKER",
    "stale_assignee_comment_body",
    "stale_assignee_journal_record",
]

STALE_ASSIGNEE_CLEAR_STAGE = "stale-assignee-clear"

# A stable first line, because the replay reads the comment back to decide
# whether its own comment already landed.
STALE_ASSIGNEE_COMMENT_MARKER = "livespec-stale-assignee-clear"


def stale_assignee_journal_record(
    *,
    work_item_id: str,
    run_id: str,
    factory_name: str,
    factory_server_url: str | None,
    run_state: str,
) -> dict[str, object]:
    """The one journal row a clearance leaves."""
    return {
        "stage": STALE_ASSIGNEE_CLEAR_STAGE,
        "work_item_id": work_item_id,
        "run_id": run_id,
        "factory": factory_name,
        "factory_server": factory_server_url,
        "run_state": run_state,
    }


def stale_assignee_comment_body(
    *,
    work_item_id: str,
    run_id: str,
    factory_name: str,
    factory_server_url: str | None,
    run_state: str,
) -> str:
    """The durable account of one stale-assignee clearance."""
    server = (
        factory_server_url
        if factory_server_url is not None
        else "no server recorded on the claim stamp"
    )
    return "\n".join(
        (
            STALE_ASSIGNEE_COMMENT_MARKER,
            "",
            f"Work-item {work_item_id} is `ready`; its stale `fabro` assignee was cleared.",
            f"Run {run_id} on factory {factory_name} ({server}) was reported {run_state}.",
            "No live dispatch owned the item on its stamped host.",
            "The item's status, labels and run stamp are unchanged, and its next dispatch",
            "is graded by recovery routing as an item released for recovery.",
        )
    )
