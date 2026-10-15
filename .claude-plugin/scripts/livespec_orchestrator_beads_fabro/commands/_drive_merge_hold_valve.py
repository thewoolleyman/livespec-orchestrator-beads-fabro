"""The `set-merge-hold` human valve — the one policy edit that also writes the FORGE.

The other eleven valves write the ledger and stop there. The per-item merge hold
ratified in `SPECIFICATION/contracts.md` cannot: the hold's whole purpose is to
put a maintainer's chosen window between dispatch and merge, and a pull request
that is ALREADY armed for auto-merge would land inside that window no matter
what the ledger says. So
setting the hold disarms an armed pull request, releasing it arms one, and that
single forge write is the action's only effect beside the label.

Which merge method the release arms is the part that must not be casual. It is
read from the DISPATCH RECORD the run journaled, never re-resolved from
`.livespec.jsonc`: the resolve-once-project-everywhere clause journals the
frozen `ResolvedIntegrationContract` with the dispatch precisely so a question
asked afterwards is answered by what the orchestrator believed THEN — and a hold
exists to make "afterwards" long enough for the configuration to have changed.

The forge is READ before either direction writes anything, because both
write-nothing refusals depend on what it says: setting a hold on an
already-merged pull request has no merge left to hold, and releasing one cannot
arm a strategy no dispatch recorded.

WHAT A RELEASE MUST ESTABLISH BEFORE IT ARMS lives next door, in
`_drive_merge_hold_arm_guard`. v145 made this release the ONE arming that
happens outside a run, so it may not arm while a run of the item is live and may
arm only a head the latest `verified` or `carried_forward` record of that item's
latest run names. Those are two external measurements with their own failure
modes; this module keeps the valve's own shape — the label, the two directions,
the one forge write — and asks the guard for the answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from subprocess import run
from typing import Any, cast

from livespec_orchestrator_beads_fabro._store_merge_hold import update_work_item_merge_hold
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    MERGE_METHOD_FLAGS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_probe_cycle import (
    journal_records,
    probe_publish_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_status import PrView, parse_pr_view
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_arm_guard import (
    MergeHoldCommandRun,
    arm_refusal_for_release,
)
from livespec_orchestrator_beads_fabro.commands._drive_reject_valve import HumanValveRunner
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["journaled_merge_method_flag", "set_merge_hold"]

_HOLD_VALUE = "on"
_OPEN_STATE = "OPEN"
_MERGED_STATE = "MERGED"
_VALVE_STAGE = "human-valve-set-merge-hold"
_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")
# Where one dispatch record spells the merge strategy it resolved, as
# `_dispatcher_integration_projection.integration_contract_journal_record` writes
# it. Walked as a path rather than indexed step by step so the four "is this
# still a mapping?" guards are one loop instead of four nested branches.
_MERGE_MODE_RECORD_PATH = ("integration_contract", "fields", "merge_mode", "value")
# `headRefOid` rides this ONE view because the v145 arm guard compares the
# pull request's CURRENT head against the head a proof record names, and the
# view is already taken at the moment the valve decides. A probe of its own
# would be a second forge round trip that could answer differently for the same
# pull request in the same action, with nothing in the record saying which
# reading the arming was justified by.
_PR_VIEW_FIELDS = "number,state,autoMergeRequest,mergeCommit,headRefOid"


@dataclass(frozen=True, kw_only=True)
class _MergeHoldCall:
    """One invocation: where to write the ledger, and how to reach the forge."""

    repo: Path
    config: StoreConfig
    item: WorkItem
    aid: str
    runner: HumanValveRunner | None


def set_merge_hold(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    value: str,
    runner: HumanValveRunner | None,
) -> dict[str, Any]:
    """Set or release one item's merge hold, and disarm or arm its pull request."""
    call = _MergeHoldCall(repo=repo, config=config, item=item, aid=aid, runner=runner)
    view = _pr_view(call=call)
    return _hold(call=call, view=view) if value == _HOLD_VALUE else _release(call=call, view=view)


def journaled_merge_method_flag(*, repo: Path, work_item_id: str) -> str | None:
    """The `gh pr merge` method flag the dispatch that opened this item's PR journaled.

    `None` means the journal names no usable strategy for this item — either no
    dispatch record carries one, or the one it carries has no forge flag. It is
    NOT an invitation to fall back on the repository's current configuration:
    that fallback is the very thing the ratified release forbids.

    Newest-wins over the append-only journal, the convention every other
    per-item journal read here uses — a later record for one item cannot
    describe an earlier dispatch of it.
    """
    records = journal_records(journal_path=repo.joinpath(*_JOURNAL_SUBPATH))
    mode = _newest_journaled_merge_mode(records=records, work_item_id=work_item_id)
    return None if mode is None else MERGE_METHOD_FLAGS.get(mode)


def _hold(*, call: _MergeHoldCall, view: PrView | None) -> dict[str, Any]:
    if view is not None and view.state == _MERGED_STATE:
        return valve_refusal(
            aid=call.aid,
            wid=call.item.id,
            err="already-merged",
            msg=(
                f"set-merge-hold:on refused: pull request #{view.number} for {call.item.id} "
                f"has already merged{_merge_note(view=view)}, so there is no merge left to hold."
            ),
        )
    update_work_item_merge_hold(path=call.config, item_id=call.item.id, value=True)
    if view is None or not view.auto_merge_armed:
        return _hold_success(call=call, note="no auto-merge request stood to be disarmed")
    disarmed = _run(call=call, argv=_disarm_argv(number=view.number))
    if disarmed.returncode != 0:
        return valve_refusal(
            aid=call.aid,
            wid=call.item.id,
            err="disarm-failed",
            msg=(
                f"set-merge-hold:on wrote the hold on {call.item.id} but disarming auto-merge "
                f"on pull request #{view.number} failed: {disarmed.stderr}"
            ),
        )
    return _hold_success(call=call, note=f"auto-merge disarmed on pull request #{view.number}")


def _release(*, call: _MergeHoldCall, view: PrView | None) -> dict[str, Any]:
    if view is None or view.state != _OPEN_STATE:
        update_work_item_merge_hold(path=call.config, item_id=call.item.id, value=False)
        return _release_success(call=call, note="no open pull request, so no auto-merge was armed")
    # THE GUARD RUNS FIRST, before the strategy is resolved and before the label
    # is removed. It answers whether this release may arm AT ALL, and a release
    # that may not is a different answer from one that cannot resolve a strategy
    # -- reporting the strategy fault on a pull request a live run is about to
    # rewrite would send an operator after the wrong thing.
    refusal = arm_refusal_for_release(
        repo=call.repo,
        work_item_id=call.item.id,
        pr_number=view.number,
        pr_head=view.head,
        runner=call.runner,
    )
    if refusal is not None:
        return valve_refusal(aid=call.aid, wid=call.item.id, err=refusal.error, msg=refusal.message)
    method = journaled_merge_method_flag(repo=call.repo, work_item_id=call.item.id)
    if method is None:
        return valve_refusal(
            aid=call.aid,
            wid=call.item.id,
            err="unresolved-merge-method",
            msg=(
                f"set-merge-hold:off refused: no dispatch journaled a usable merge method for "
                f"{call.item.id}. The release MUST arm the strategy recorded by the dispatch "
                f"that opened pull request #{view.number} rather than re-derive one from "
                "configuration, so the hold stands."
            ),
        )
    # The label goes first. A hold released in the ledger but not yet armed is
    # recoverable by re-running the identical action; a pull request armed while
    # the ledger still reads held is a merge nobody can see coming.
    update_work_item_merge_hold(path=call.config, item_id=call.item.id, value=False)
    armed = _run(call=call, argv=_arm_argv(number=view.number, method=method))
    if armed.returncode != 0:
        return valve_refusal(
            aid=call.aid,
            wid=call.item.id,
            err="arm-failed",
            msg=(
                f"set-merge-hold:off removed the hold on {call.item.id} but arming auto-merge "
                f"on pull request #{view.number} failed: {armed.stderr}; re-run the action to "
                "retry the arm."
            ),
        )
    return _release_success(
        call=call,
        note=f"auto-merge armed on pull request #{view.number} with {method}",
    )


def _hold_success(*, call: _MergeHoldCall, note: str) -> dict[str, Any]:
    return _valve_success(call=call, msg=f"Held {call.item.id}: merge hold set; {note}")


def _release_success(*, call: _MergeHoldCall, note: str) -> dict[str, Any]:
    return _valve_success(call=call, msg=f"Released {call.item.id}: merge hold removed; {note}")


def _valve_success(*, call: _MergeHoldCall, msg: str) -> dict[str, Any]:
    return valve_success(
        aid=call.aid,
        wid=call.item.id,
        stage=_VALVE_STAGE,
        status=call.item.status,
        assignee=call.item.assignee,
        msg=f"{msg}; status unchanged.",
    )


def _merge_note(*, view: PrView) -> str:
    return "" if view.merge_sha is None else f" as {view.merge_sha}"


def _pr_view(*, call: _MergeHoldCall) -> PrView | None:
    """The item's publish-branch pull request, or `None` when there is none to read.

    An unreadable view and an absent pull request are deliberately the same
    answer. Neither one is a pull request this valve can arm or disarm, and the
    ledger half of the action is defined for an item that has never been
    dispatched at all.
    """
    branch = probe_publish_branch(work_item_id=call.item.id)
    viewed = _run(call=call, argv=_pr_view_argv(branch=branch))
    if viewed.returncode != 0:
        return None
    return parse_pr_view(stdout=viewed.stdout)


def _pr_view_argv(*, branch: str) -> tuple[str, ...]:
    return ("gh", "pr", "view", branch, "--json", _PR_VIEW_FIELDS)


def _arm_argv(*, number: int, method: str) -> tuple[str, ...]:
    """Arm auto-merge with the JOURNALED method.

    Deliberately not `_dispatcher_fabro_argv.pr_arm_argv`, which projects its
    method flag from a dispatch plan's freshly-resolved contract. There is no
    plan here and there must not be one — same argv shape, different and
    load-bearing source for the one flag.
    """
    return ("gh", "pr", "merge", str(number), method, "--auto", "--delete-branch")


def _disarm_argv(*, number: int) -> tuple[str, ...]:
    return ("gh", "pr", "merge", str(number), "--disable-auto")


def _run(*, call: _MergeHoldCall, argv: tuple[str, ...]) -> MergeHoldCommandRun:
    if call.runner is None:
        return run(argv, check=False, cwd=call.repo, text=True, capture_output=True)  # noqa: S603
    return cast("MergeHoldCommandRun", call.runner(argv=argv, cwd=call.repo))


def _newest_journaled_merge_mode(
    *, records: tuple[Mapping[str, object], ...], work_item_id: str
) -> str | None:
    newest: str | None = None
    for record in records:
        if record.get("work_item_id") != work_item_id:
            continue
        mode = _merge_mode_of(record=record)
        if mode is not None:
            newest = mode
    return newest


def _merge_mode_of(*, record: Mapping[str, object]) -> str | None:
    node: object = record
    for key in _MERGE_MODE_RECORD_PATH:
        node = _child(node=node, key=key)
    return node if isinstance(node, str) else None


def _child(*, node: object, key: str) -> object:
    """One step down a journal record's nested shape; `None` when the step is absent.

    A record whose shape does not reach the value is exactly as informative as
    one that carries no merge mode at all, so both answer `None` rather than
    raising: the journal is written by whichever build dispatched, and an older
    or truncated record is an ordinary thing to meet, not a bug.
    """
    if not isinstance(node, dict):
        return None
    return cast("dict[str, object]", node).get(key)
