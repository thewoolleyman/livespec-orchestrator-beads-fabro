"""What a host record's SUBJECT is, and what its pull request already says about it.

Split out of `_dispatcher_host_record_post` along the cohesion seam between
characterising the subject and publishing against it. That module resolves the
target, renders, bounds and posts; this one answers three prior questions, all of
them reads rather than decisions about what to publish:

- Which item is this, if it was ever filed?
- Which assertions does its own Definition of Done declare as host-captured, and
  under which proof mode?
- What do the records ALREADY on its pull request say about a replay of them?

The split happened because the posting module crossed this tree's file-size
ceiling once the attachment path landed in it, and this is where the seam actually
is: nothing here knows the verdict will be posted, and nothing in the posting half
re-reads the ledger.

WHY `replay_refusal` TAKES `repo` AND `verdict` LOOSE rather than the
`HostRecordPost` it came from. The post value is defined in the posting module, so
accepting one here would make this module import that one while that one imports
this — a cycle. Taking the two fields it actually reads keeps the dependency in one
direction, and makes plain that this function is about the pull request's existing
records rather than about the invocation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import REPLAY_VERDICTS
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    ASSERTION_HEADING_PREFIX,
    GOVERNING_SCENARIO_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_RECORDED,
    ProofRecord,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "NO_CAPTURE_REFUSAL",
    "SELF_REPLAY_REFUSAL",
    "ReplayCapture",
    "captured_governing_scenarios",
    "declared_host_modes",
    "ledger_item",
    "replay_capture",
]

SELF_REPLAY_REFUSAL = "the computed identity equals the identity that recorded the capture"
NO_CAPTURE_REFUSAL = "no host_recorded record on the pull request for this replay to replay"

_UNREADABLE_PULL_REQUEST_REFUSAL = (
    "ERROR: post-host-record refused: pull request #{pr_number} comments could not be"
    " read, so the capturing identity this replay must differ from is unknown. A replay"
    " is not published against an unread pull request.\n"
)
_NO_CAPTURE_REFUSAL_TEXT = (
    "ERROR: post-host-record refused: {reason} (pull request #{pr_number}). Publish the"
    " {capture} capture first.\n"
)
_SELF_REPLAY_REFUSAL_TEXT = (
    "ERROR: post-host-record refused: {reason} ({identity}), so this post would not be"
    " evidence. The {capture} record it replays is {url}. A DIFFERENT session identity"
    " must replay those steps.\n"
)


@dataclass(frozen=True, kw_only=True)
class ReplayCapture:
    """The capture a replay may render from, or the refusal that prevents it."""

    record: ProofRecord | None
    refusal: str | None


def ledger_item(*, repo: Path, work_item_id: str) -> WorkItem | None:
    """The named item from the repository's ledger, or `None` when it was never filed.

    `load_items` is the Dispatcher's own ledger read, reused rather than re-rolled so
    the primitive sees the same tenant, through the same backend selection, as the
    acceptance pass whose verdict its post re-runs.
    """
    return next((one for one in load_items(repo=repo) if one.id == work_item_id), None)


def declared_host_modes(*, item: WorkItem) -> dict[str, str]:
    """Each host-captured assertion the item declares, mapped to its proof mode.

    A MAPPING rather than a set because the mode is what the record publishes, and
    computing it here is what stops a caller declaring one: the record can only ever
    carry the mode the item's own Definition of Done assigned.
    """
    criteria = effective_criteria(item=item)
    host = set(criteria.host_captured_assertions)
    return {
        text: mode
        for text, mode in zip(criteria.assertions, criteria.proof_modes, strict=True)
        if text in host
    }


def replay_capture(
    *, repo: Path, verdict: str, pr_number: int, identity: str, runner: CommandRunner
) -> ReplayCapture:
    """The prior capture a replay must use, or the refusal that prevents a replay.

    A capture earns none: it is the first leg, there is nothing for it to collide with,
    and requiring one would make the first host record of every item unpublishable.
    """
    if verdict not in REPLAY_VERDICTS:
        return ReplayCapture(record=None, refusal=None)
    records = read_pull_request_records(repo=repo, pr_number=pr_number, runner=runner)
    if records is None:
        return ReplayCapture(
            record=None,
            refusal=_UNREADABLE_PULL_REQUEST_REFUSAL.format(pr_number=pr_number),
        )
    capture = latest_proof_record(records=records, verdict=VERDICT_HOST_RECORDED)
    if capture is None:
        return ReplayCapture(
            record=None,
            refusal=_NO_CAPTURE_REFUSAL_TEXT.format(
                reason=NO_CAPTURE_REFUSAL, pr_number=pr_number, capture=VERDICT_HOST_RECORDED
            ),
        )
    if capture.run_id != identity:
        return ReplayCapture(record=capture, refusal=None)
    return ReplayCapture(
        record=capture,
        refusal=_SELF_REPLAY_REFUSAL_TEXT.format(
            reason=SELF_REPLAY_REFUSAL,
            identity=identity,
            capture=VERDICT_HOST_RECORDED,
            url=capture.url,
        ),
    )


def captured_governing_scenarios(
    *, capture: ProofRecord, assertions: Sequence[str]
) -> dict[str, str]:
    """Each named assertion's scenario in the exact capture the replay is verifying."""
    return {
        assertion: scenario
        for assertion in assertions
        if (scenario := _captured_scenario(body=capture.body, assertion=assertion)) is not None
    }


def _captured_scenario(*, body: str, assertion: str) -> str | None:
    """One assertion's rendered scenario, or `None` when the capture names none."""
    heading = f"## {ASSERTION_HEADING_PREFIX} "
    prefix = f"{GOVERNING_SCENARIO_LABEL}: "
    in_assertion = False
    for line in body.splitlines():
        if line.startswith("## "):
            in_assertion = line.startswith(heading) and line.endswith(f" — {assertion}")
        elif in_assertion and line.startswith(prefix):
            return line[len(prefix) :]
    return None
