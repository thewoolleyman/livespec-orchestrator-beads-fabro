"""Preserving a publish branch's head before the branch is cleared.

The mechanics half of the publish-branch reclaim. What is asserted here is the
ORDER and the FAILURE ARMS, because those are what make an irreversible remote
operation safe: the head is copied onto a ref of its own and confirmed by origin
BEFORE the branch is deleted, and any step that failed leaves the branch standing
rather than proceeding.

BOTH PRESERVE LEGS ARE ASSERTED, and the second is the load-bearing one. The fetch
brings the dead run's head into this clone; only the push makes it durable
somewhere a later reader can reach. A build that checked the fetch alone would
delete the branch whose copy never left the host, and the journal record it left
would be indistinguishable from a healthy reclaim.

NO SPELLING OF FORCE PUSH IS PERMITTED, and that is checked against the argv list
rather than trusted: the ratified stages clause of `SPECIFICATION/contracts.md`
grants a lease-guarded force push to the `pr` node ALONE, so a recovery bought
with a ref rewrite here would take back the capability the graph deliberately
withheld from `publish_draft`.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_publish_branch_preserve.py"
)

_ITEM_ID = "bd-ib-qm4luz"
_BRANCH = f"feat/{_ITEM_ID}"
_DEAD_HEAD = "9f1c2d3e4f506172839a0b1c2d3e4f5061728394"
_FORCE_SPELLINGS = ("--force", "--force-with-lease", "-f")


def _preserve_module() -> Any:
    """Import the preserve module, asserting the file exists first."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


@dataclass(kw_only=True)
class _Runner:
    """A scripted subprocess seam: one answer per argv substring, exit 0 otherwise."""

    answers: dict[str, CommandResult] = field(default_factory=dict)
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        joined = " ".join(argv)
        for needle, result in self.answers.items():
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


def _surviving(*, module: Any) -> Any:
    return module.SurvivingPublishBranch(branch=_BRANCH, head=_DEAD_HEAD)


def test_the_preserved_ref_carries_the_head_so_a_repeat_is_not_a_rewrite() -> None:
    """The ref name includes the head, which makes every preserve a CREATE.

    Two dead heads for one item therefore preserve to two refs, and re-running the
    same reclaim pushes the same sha to the same ref — which origin accepts as
    already up to date rather than as a ref rewrite.
    """
    module = _preserve_module()

    first = module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD)
    second = module.preserved_publish_ref(work_item_id=_ITEM_ID, head="0" * 40)

    assert first == f"{module.PRESERVED_PUBLISH_REF_PREFIX}/{_ITEM_ID}/{_DEAD_HEAD}"
    assert first != second
    # Not under `refs/heads/`: a preserved head must never be a branch, or a
    # branch-hygiene sweep would treat the preservation as the thing to clean up.
    assert not module.PRESERVED_PUBLISH_REF_PREFIX.startswith("refs/heads/")


def test_the_head_is_copied_and_confirmed_by_origin_before_the_branch_is_deleted(
    tmp_path: Path,
) -> None:
    """The ordering that makes the delete safe, read off the real argv sequence."""
    module = _preserve_module()
    runner = _Runner()

    outcome = module.preserve_and_clear(
        runner=runner, repo=tmp_path, work_item_id=_ITEM_ID, surviving=_surviving(module=module)
    )

    preserved = module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD)
    assert outcome == module.Reclaimed(preserved_ref=preserved)
    assert runner.argvs == [
        ["git", "fetch", "origin", f"+refs/heads/{_BRANCH}:{preserved}"],
        ["git", "push", "origin", f"{preserved}:{preserved}"],
        ["git", "push", "origin", "--delete", f"refs/heads/{_BRANCH}"],
    ]
    assert [argv for argv in runner.argvs if set(argv) & set(_FORCE_SPELLINGS)] == []


def test_either_failed_preserve_leg_leaves_the_branch_standing(tmp_path: Path) -> None:
    """A copy that is not durable must not be followed by a delete.

    The push leg is the one that matters: a fetch-only check would pass while the
    head existed on this host alone, and the branch would be gone.
    """
    module = _preserve_module()
    failed = CommandResult(exit_code=1, stdout="", stderr="")
    preserved = module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD)

    for answers in ({"fetch": failed}, {f"push origin {preserved}": failed}):
        runner = _Runner(answers=answers)

        outcome = module.preserve_and_clear(
            runner=runner,
            repo=tmp_path,
            work_item_id=_ITEM_ID,
            surviving=_surviving(module=module),
        )

        assert isinstance(outcome, module.PreserveFailure)
        assert outcome.reason == module.HELD_PRESERVE_FAILED
        assert _DEAD_HEAD in outcome.detail
        assert [argv for argv in runner.argvs if "--delete" in argv] == []


def test_a_failed_delete_reports_the_preserved_head_and_its_own_reason(
    tmp_path: Path,
) -> None:
    """The two failures are different facts, and the caller records whichever it got.

    A failed delete means the head IS preserved and only the branch remains, which
    is a different thing for an operator to act on than a preserve that copied
    nothing — so the reason, not just the detail, distinguishes them.
    """
    module = _preserve_module()
    runner = _Runner(answers={"--delete": CommandResult(exit_code=1, stdout="", stderr="")})

    outcome = module.preserve_and_clear(
        runner=runner, repo=tmp_path, work_item_id=_ITEM_ID, surviving=_surviving(module=module)
    )

    assert isinstance(outcome, module.PreserveFailure)
    assert outcome.reason == module.HELD_DELETE_FAILED
    assert outcome.reason != module.HELD_PRESERVE_FAILED
    assert module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD) in outcome.detail
