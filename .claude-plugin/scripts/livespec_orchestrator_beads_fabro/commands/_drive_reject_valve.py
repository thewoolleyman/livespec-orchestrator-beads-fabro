"""The `reject` human valve — the one valve that also rewrites the repository.

Split out of `_drive_valves` when that module reached the file-LLOC ceiling,
along the seam its own machinery already drew. Every other valve is a ledger
write and nothing else; `reject` alone shells out to `git revert` on the
`regroom` arm, carries the runner Protocol that indirection needs, and is the
only valve whose SUCCESS is journaled. All three exist for this action and
nothing else, so they travel with it rather than sitting in the router.

The router keeps `runner` in its own signature and forwards it here, which is
why `HumanValveRunner` is public: a caller injecting a fake command runner
reaches the valve through `run_human_valve_action`, never directly.
"""

from collections.abc import Callable
from pathlib import Path
from subprocess import run
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro._store_claim_tokens import write_claim_change
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    update_work_item_rework_pending,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    invalid_source_state,
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["journal_rework_return", "reject_item"]


class HumanValveCommandRun(Protocol):
    @property
    def returncode(self) -> int: ...

    @property
    def stderr(self) -> str: ...


HumanValveRunner = Callable[..., object]
_REWORK_REJECT_KIND = "rework"


def reject_item(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    reject_kind: str,
    runner: HumanValveRunner | None,
) -> dict[str, Any]:
    if item.status != "acceptance":
        return invalid_source_state(aid=aid, item=item, expected="acceptance")
    target_status = "active" if reject_kind == "rework" else "backlog"
    if reject_kind == "regroom":
        refusal = _revert_merged_change(repo=repo, item=item, aid=aid, runner=runner)
        if refusal is not None:
            return refusal
    changed = write_claim_change(
        path=config,
        work_item_id=item.id,
        writer="reject",
        intent=f"reject:{reject_kind}",
        status=target_status,
    )
    if changed.outcome != "applied":
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err=changed.outcome,
            msg=f"reject refused: {changed.outcome}.",
        )
    if reject_kind == _REWORK_REJECT_KIND:
        # The human rework entry stamps the SAME marker the AI-fail entry does:
        # the two rework entries must not diverge in selectability, so the valve
        # an operator is offered is not a dead end.
        update_work_item_rework_pending(path=config, item_id=item.id, value=True)
    return valve_success(
        aid=aid,
        wid=item.id,
        stage=f"human-valve-reject-{reject_kind}",
        status=target_status,
        assignee=None,
        msg=f"Rejected {item.id}: acceptance -> {target_status}.",
    )


def journal_rework_return(
    *, repo: Path, identity: InvokerIdentity, reject_kind: str, result: dict[str, Any]
) -> None:
    """Journal a SUCCESSFUL REWORK return through the single append layer.

    Lifted out of `reject_item` so the invocation's identity reaches the write
    without pushing that function past the argument ceiling, and it owns BOTH
    guards rather than splitting them with its caller. A `regroom` return is not
    journaled here, and a refusal payload carries no `journal` key — so that
    key's absence is the success discriminator.
    """
    record = result.get("journal")
    if reject_kind != _REWORK_REJECT_KIND or record is None:
        return
    JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl", identity=identity).append(
        record=cast("dict[str, object]", record)
    )


def _revert_merged_change(
    *, repo: Path, item: WorkItem, aid: str, runner: HumanValveRunner | None
) -> dict[str, Any] | None:
    merge_sha = item.audit.merge_sha if item.audit is not None else None
    if not merge_sha:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="missing-merge-evidence",
            msg="reject:regroom refused: no merged change recorded to revert.",
        )
    argv = ("git", "revert", "--no-edit", merge_sha)
    if runner is None:
        result = run(argv, check=False, cwd=repo, text=True, capture_output=True)  # noqa: S603
    else:
        result = cast("HumanValveCommandRun", runner(argv=argv, cwd=repo))
    if result.returncode == 0:
        return None
    return valve_refusal(
        aid=aid,
        wid=item.id,
        err="revert-failed",
        msg=f"reject:regroom refused: git revert {merge_sha} failed: {result.stderr}",
    )
