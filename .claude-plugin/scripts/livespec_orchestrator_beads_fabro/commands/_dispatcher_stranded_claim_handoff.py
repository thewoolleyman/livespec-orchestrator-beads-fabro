"""Reading what became of a handed-off merge wait's pull request.

A merge wait whose poll budget ended on an armed, passing pull request leaves the
item `active` under its claim and journals one `merge-wait-handed-off` row
(`_dispatcher_merge_wait_handoff`). This is the OBSERVATION half of completing it:
which pull request the newest dispatch handed off, and what the forge now says
about it. The pass that acts on the answer lives in
`_dispatcher_stranded_claim_handoff_recovery`; the ladder that routes on it in
`_dispatcher_stranded_claim_grade`.

THE ROW MUST BELONG TO THE CLAIM IN HAND, and it takes two tests to be sure. It
must sit in the NEWEST dispatch's journal segment, since an earlier dispatch that
handed off and was then released and re-dispatched says nothing about the dispatch
now standing; and it must name the claim's own run id, since a segment can carry
the rows of a run that was replaced within it. A claim whose journal could not be
read is not handed off: "the newest dispatch journaled a handoff" is a claim about
what was read.

EVERY ARM THAT COULD NOT MEASURE IS `unobservable` AND NEVER A VERDICT. A pull
request that cannot be read, a required-check list that cannot be read, and a
state the forge reports that this reading does not recognise all hold the claim,
because completing a claim on a guess is the one wrong answer that cannot be
walked back: a rest asks a human to act, and a reconcile runs the janitor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_wait_handoff import (
    MERGE_WAIT_HANDED_OFF_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import view_pr
from livespec_orchestrator_beads_fabro.commands._dispatcher_required_checks import (
    required_check_names,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import (
    REWORK_ADMIT_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    HANDOFF_ENDED,
    HANDOFF_MERGED,
    HANDOFF_PENDING,
    HANDOFF_REQUIRED_CHECK_FAILED,
    HANDOFF_UNOBSERVABLE,
)

__all__: list[str] = [
    "HANDED_OFF_HOLD_DETAIL",
    "HandoffReading",
    "handed_off_hold_detail",
    "handed_off_pull_request",
    "handed_off_rework_pull_request",
    "observe_handoff",
]

# What a held entry for a handed-off claim names, so a person reading the held
# list can tell a claim awaiting its own CI from one nobody is looking after.
HANDED_OFF_HOLD_DETAIL = "merge-wait-handed-off"

_STAGE_KEY = "stage"
_WORK_ITEM_KEY = "work_item_id"
_RUN_ID_KEY = "run_id"
_PR_NUMBER_KEY = "pr_number"
# The row that opens each dispatch's segment of the journal.
_DISPATCH_OPENING_STAGE = "dispatch-id"


@dataclass(frozen=True, kw_only=True)
class HandoffReading:
    """What the forge said about one handed-off pull request, with the view's facts.

    `plan` rides along because the disposition builds its outcome through the
    dispatch path's own builders, which take a plan, and a second plan resolved
    there could name a different publish branch than the one read here.
    """

    kind: str
    plan: DispatchPlan
    pr_number: int
    pr_head: str | None = None
    pr_base: str | None = None
    merge_sha: str | None = None
    failed_checks: tuple[str, ...] = ()


def handed_off_hold_detail(*, reading: HandoffReading) -> str:
    """What a held handed-off claim names, and why it is still held."""
    if reading.kind == HANDOFF_UNOBSERVABLE:
        return (
            f"{HANDED_OFF_HOLD_DETAIL}: the forge's answer for pull request "
            f"#{reading.pr_number} could not be read"
        )
    return (
        f"{HANDED_OFF_HOLD_DETAIL}: pull request #{reading.pr_number} is armed and its "
        "required checks are passing or still running"
    )


def handed_off_pull_request(
    *,
    records: tuple[Mapping[str, object], ...] | None,
    work_item_id: str,
    run_id: str,
) -> int | None:
    """The pull request number this claim's newest dispatch handed off, or `None`."""
    if records is None:
        return None
    own = [record for record in records if record.get(_WORK_ITEM_KEY) == work_item_id]
    openings = [
        index
        for index, record in enumerate(own)
        if record.get(_STAGE_KEY) == _DISPATCH_OPENING_STAGE
    ]
    if not openings:
        return None
    for record in reversed(own[openings[-1] + 1 :]):
        number = record.get(_PR_NUMBER_KEY)
        if (
            record.get(_STAGE_KEY) == MERGE_WAIT_HANDED_OFF_STAGE
            and record.get(_RUN_ID_KEY) == run_id
            and isinstance(number, int)
            and not isinstance(number, bool)
        ):
            return number
    return None


def handed_off_rework_pull_request(
    *,
    records: tuple[Mapping[str, object], ...] | None,
    work_item_id: str,
    run_id: str,
) -> int | None:
    """The pull request a REWORK dispatch of this claim handed off, or `None`.

    A handed-off rework is told from a parked one by the journal alone: the rework
    admission row marks where the rework began, and only a handoff row of a dispatch
    opened AFTER the newest such row is the rework's own. The earlier dispatch's
    handoff (the original run, whose merge was accepted and then failed acceptance)
    sits before that row and says nothing about the rework, and a rework that has
    been admitted but not opened, or that opened and died before publishing, has no
    handoff row after it. An item whose journal holds no rework admission is not a
    rework that started at all. A journal that could not be read answers `None`.
    """
    if records is None:
        return None
    own = [record for record in records if record.get(_WORK_ITEM_KEY) == work_item_id]
    admissions = [
        index for index, record in enumerate(own) if record.get(_STAGE_KEY) == REWORK_ADMIT_STAGE
    ]
    if not admissions:
        return None
    return handed_off_pull_request(
        records=tuple(own[admissions[-1] + 1 :]), work_item_id=work_item_id, run_id=run_id
    )


def observe_handoff(
    *,
    plan: DispatchPlan,
    pr_number: int,
    runner: CommandRunner,
    journal: JournalWriter,
) -> HandoffReading:
    """Ask the forge what became of the handed-off pull request."""
    view = view_pr(plan=plan, runner=runner, journal=journal).view
    if view is None:
        return HandoffReading(kind=HANDOFF_UNOBSERVABLE, plan=plan, pr_number=pr_number)
    number = view.number
    if view.state == "MERGED":
        return HandoffReading(
            kind=HANDOFF_MERGED,
            plan=plan,
            pr_number=number,
            pr_head=view.head,
            merge_sha=view.merge_sha,
        )
    if view.state == "CLOSED" or (view.state == "OPEN" and not view.auto_merge_armed):
        return HandoffReading(
            kind=HANDOFF_ENDED,
            plan=plan,
            pr_number=number,
            pr_head=view.head,
            pr_base=view.base,
        )
    required = (
        required_check_names(plan=plan, number=number, runner=runner, journal=journal)
        if view.state == "OPEN"
        else None
    )
    if required is None:
        return HandoffReading(
            kind=HANDOFF_UNOBSERVABLE, plan=plan, pr_number=number, pr_head=view.head
        )
    failed = tuple(name for name in view.terminal_check_failures if name in required)
    return HandoffReading(
        kind=HANDOFF_REQUIRED_CHECK_FAILED if failed else HANDOFF_PENDING,
        plan=plan,
        pr_number=number,
        pr_head=view.head,
        merge_sha=view.merge_sha,
        failed_checks=failed,
    )
