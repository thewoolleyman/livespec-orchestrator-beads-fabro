"""Preserving a publish branch's head before the branch is cleared.

The mechanics half of the publish-branch reclaim. What is asserted here is the
ORDER and the FAILURE ARMS, because those are what make an irreversible remote
operation safe: the head is copied onto a ref of its own and confirmed by origin
BEFORE the branch is deleted, and any step that failed leaves the branch standing
rather than proceeding.

"THE PRESERVE FAILED" IS ASSERTED TO MEAN THE HEAD IS NOT PRESERVED, which is a
different claim from "the create call returned non-zero". The forge refuses a
create for a ref that already stands, and the preservation ref is named after the
head it carries, so the SECOND reclaim of a head already preserved — the shape a
failed delete leaves behind, and therefore the shape every retry of that arm takes
— meets that refusal on a ref that holds exactly what it should. A build reading
the exit code alone reports `preserve-failed` there, which strands the recovery
permanently and names a failure that did not happen. So the refusal is settled by
ASKING ORIGIN what the ref carries, and only an unconfirmed ref holds the reclaim.

NEITHER OPERATION MAY BE SPELLED AS A `git push`, and that is asserted against the
argv list rather than trusted. The Dispatcher runs from the host's PRIMARY
CHECKOUT, whose commit-refuse pre-push hook refuses EVERY push with exit 1, so a
push here cannot succeed in use however well it reads — the first build of these
mechanics pushed twice and passed its proof only because a factory sandbox clone
lacks the primary-checkout condition the hook keys on. The scripted runner below
therefore fails every push, which is the host as it really is.

NO SPELLING OF REF REWRITE IS PERMITTED EITHER, and that is checked against the
argv list too: the ratified stages clause of `SPECIFICATION/contracts.md` grants a
lease-guarded force push to the `pr` node ALONE, so a recovery bought with a ref
rewrite here — a forced git push, or the forge's reference-UPDATE interface, which
is the same capability over this transport — would take back what the graph
deliberately withheld from `publish_draft`.
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
# The forge's own way of rewriting a ref: a PATCH of the reference, optionally
# forced. Matched on the joined argv rather than on token membership, because both
# are values of a preceding flag rather than flags themselves.
_REWRITE_SPELLINGS = ("PATCH", "force=true", "force=True")
# Spelled out here rather than imported from the module under test, so a change to
# the production argv fails these assertions instead of agreeing with them. The
# read endpoint is the SINGULAR `git/ref/...`, which resolves one exact ref; the
# plural `matching-refs` form is a PREFIX match and the preservation ref ends in
# the very sha under question, so a prefix answer could never settle it.
_REFS_ENDPOINT = "/repos/{owner}/{repo}/git/refs"
_REF_ENDPOINT = "/repos/{owner}/{repo}/git/ref"
# Another dead head of the same item: what origin reports when the preservation
# ref exists but carries something other than the head being preserved.
_OTHER_HEAD = "1122334455667788990011223344556677889900"
# The pre-push hook every primary checkout carries, reproduced verbatim from the
# hand run of 2026-10-05T06:12Z that measured it.
_PRIMARY_CHECKOUT_PUSH_REFUSAL = CommandResult(
    exit_code=1,
    stdout="",
    stderr="livespec: refusing commit/push at primary checkout; use a worktree\n",
)


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


def _runner_on_a_primary_checkout(**answers: CommandResult) -> _Runner:
    """A runner on the host these mechanics really run on: every push refused.

    The push refusal is scripted on EVERY runner in this file rather than in one
    dedicated test, so a leg that quietly returned to `git push` fails every
    assertion here instead of only the one that remembered to look.
    """
    return _Runner(answers={"push": _PRIMARY_CHECKOUT_PUSH_REFUSAL, **answers})


def _create_argv(*, preserved: str) -> list[str]:
    """The forge create of the preservation ref, as production spells it."""
    return [
        "gh",
        "api",
        "--method",
        "POST",
        _REFS_ENDPOINT,
        "--raw-field",
        f"ref={preserved}",
        "--raw-field",
        f"sha={_DEAD_HEAD}",
    ]


def _read_argv(*, preserved: str) -> list[str]:
    """The forge read that confirms what origin carries at the preservation ref."""
    segment = preserved.removeprefix("refs/")
    return ["gh", "api", f"{_REF_ENDPOINT}/{segment}", "--jq", ".object.sha"]


def _delete_argv() -> list[str]:
    """The forge delete of the publish branch, as production spells it."""
    return ["gh", "api", "--method", "DELETE", f"{_REFS_ENDPOINT}/heads/{_BRANCH}"]


def _rewrites(*, runner: _Runner) -> list[list[str]]:
    """Every argv reaching for a ref REWRITE, in either transport's spelling."""
    return [
        argv
        for argv in runner.argvs
        if set(argv) & set(_FORCE_SPELLINGS)
        or any(spelling in " ".join(argv) for spelling in _REWRITE_SPELLINGS)
    ]


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


def test_the_head_is_preserved_and_the_branch_cleared_where_every_push_is_refused(
    tmp_path: Path,
) -> None:
    """The ordering that makes the delete safe, on the host that refuses pushes.

    The full argv sequence is asserted rather than a count, because the ordering
    is the safety property and a reversed pair would issue both calls. Every push
    is scripted to fail, so a sequence that reached for one could not complete.
    """
    module = _preserve_module()
    runner = _runner_on_a_primary_checkout()

    outcome = module.preserve_and_clear(
        runner=runner, repo=tmp_path, work_item_id=_ITEM_ID, surviving=_surviving(module=module)
    )

    preserved = module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD)
    assert outcome == module.Reclaimed(preserved_ref=preserved)
    assert runner.argvs == [_create_argv(preserved=preserved), _delete_argv()]
    assert _rewrites(runner=runner) == []


def test_a_preserve_the_forge_refused_leaves_the_branch_standing(tmp_path: Path) -> None:
    """A head that was not copied must not be followed by a delete.

    The whole reference endpoint fails here, so the create does not land AND
    origin cannot be asked what the preservation ref carries — which is what makes
    the preserve genuinely unachieved rather than merely unconfirmed. This is the
    one arm where a hold costs a stalled recovery while proceeding costs the
    published head itself, so the delete must not be reached.
    """
    module = _preserve_module()
    runner = _runner_on_a_primary_checkout(
        **{"/git/ref": CommandResult(exit_code=1, stdout="", stderr="not found")}
    )

    outcome = module.preserve_and_clear(
        runner=runner,
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        surviving=_surviving(module=module),
    )

    assert isinstance(outcome, module.PreserveFailure)
    assert outcome.reason == module.HELD_PRESERVE_FAILED
    assert _DEAD_HEAD in outcome.detail
    assert [argv for argv in runner.argvs if "DELETE" in argv] == []


def test_a_refused_create_on_a_ref_origin_already_carries_is_not_a_failure(
    tmp_path: Path,
) -> None:
    """The retry of a failed delete, which the exit code alone gets backwards.

    The preservation ref is named after the head it carries, so a second reclaim of
    the same head asks the forge to create a ref that already stands — and the
    forge refuses that. The head IS preserved in this state, so reporting
    `preserve-failed` would strand the recovery on exactly the arm that most needs
    to retry: the failed delete leaves the branch standing and the ref in place,
    and every subsequent reclaim meets this refusal.

    What settles it is ORIGIN, not the exit code: the read is issued and reports
    the head, so the clear proceeds and the reclaim completes.
    """
    module = _preserve_module()
    preserved = module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD)
    runner = _runner_on_a_primary_checkout(
        **{
            "--method POST": CommandResult(
                exit_code=1, stdout="", stderr="Reference already exists (HTTP 422)"
            ),
            "git/ref/": CommandResult(exit_code=0, stdout=f"{_DEAD_HEAD}\n", stderr=""),
        }
    )

    outcome = module.preserve_and_clear(
        runner=runner, repo=tmp_path, work_item_id=_ITEM_ID, surviving=_surviving(module=module)
    )

    assert outcome == module.Reclaimed(preserved_ref=preserved)
    assert runner.argvs == [
        _create_argv(preserved=preserved),
        _read_argv(preserved=preserved),
        _delete_argv(),
    ]
    assert _rewrites(runner=runner) == []


def test_a_refused_create_whose_ref_carries_another_head_holds_the_reclaim(
    tmp_path: Path,
) -> None:
    """Origin answering is not origin CONFIRMING, and the difference authorizes a delete.

    A refused create whose ref resolves to some OTHER object means this head was
    never preserved, however healthy the read looks. The detail names both shas,
    because an operator reading the journal has to know which one survived before
    deciding what to do with the branch that still stands.
    """
    module = _preserve_module()
    preserved = module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD)
    runner = _runner_on_a_primary_checkout(
        **{
            "--method POST": CommandResult(exit_code=1, stdout="", stderr="unprocessable"),
            "git/ref/": CommandResult(exit_code=0, stdout=f"{_OTHER_HEAD}\n", stderr=""),
        }
    )

    outcome = module.preserve_and_clear(
        runner=runner, repo=tmp_path, work_item_id=_ITEM_ID, surviving=_surviving(module=module)
    )

    assert isinstance(outcome, module.PreserveFailure)
    assert outcome.reason == module.HELD_PRESERVE_FAILED
    assert _DEAD_HEAD in outcome.detail
    assert _OTHER_HEAD in outcome.detail
    assert _read_argv(preserved=preserved) in runner.argvs
    assert [argv for argv in runner.argvs if "DELETE" in argv] == []


def test_a_failed_delete_reports_the_preserved_head_and_its_own_reason(
    tmp_path: Path,
) -> None:
    """The two failures are different facts, and the caller records whichever it got.

    A failed delete means the head IS preserved and only the branch remains, which
    is a different thing for an operator to act on than a preserve that copied
    nothing — so the reason, not just the detail, distinguishes them.
    """
    module = _preserve_module()
    runner = _runner_on_a_primary_checkout(
        **{"--method DELETE": CommandResult(exit_code=1, stdout="", stderr="")}
    )

    outcome = module.preserve_and_clear(
        runner=runner, repo=tmp_path, work_item_id=_ITEM_ID, surviving=_surviving(module=module)
    )

    assert isinstance(outcome, module.PreserveFailure)
    assert outcome.reason == module.HELD_DELETE_FAILED
    assert outcome.reason != module.HELD_PRESERVE_FAILED
    assert module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD) in outcome.detail
