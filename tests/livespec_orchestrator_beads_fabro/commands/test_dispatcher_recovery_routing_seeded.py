"""An unanchorable released item is seeded from its failed run's preserved work.

Scenario 185's second scenario. The `contracts.md` section
"Factory-configurable ACP fallback priority" → "Recovery from the failed run's
preserved work": "When resume is inapplicable because no valid proof anchor
exists, the head or Definition of Done changed, or the resume-count bound is
reached, the Dispatcher MUST autonomously use a plain dispatch seeded from
preserved work... The seed record MUST name the source run, remote, immutable
commit SHA, and preservation reference... The new sandbox MUST check out the
recorded SHA."

WHY THE REFUSAL IS "NO PULL REQUEST" RATHER THAN A MOVED HEAD. Any of the
fallback-permitting refusals would do, and this one is the cheapest to state
honestly: the dead run pushed its publish branch and died before opening a pull
request, so the forge names none. That is a real state and it is the FIRST arm
of the resume's own anchor ladder, so a build that routed on anything but the
refusal class would have to get this one wrong too.

WHY THE ORDER OF THE REMOTE CALLS IS THE SECOND ASSERTION. "It MUST verify
preservation before deleting the publish branch." The preserved commit is read
first, the reclaim's preserve-and-delete pair follows, and the launch is last —
so the branch is only cleared once there is a durable commit to seed from. A
build that reclaimed first would satisfy every record assertion here and would
have destroyed the publish branch on a seed it had not yet established.

WHY THE RECLAIM IS ASSERTED TO HAVE RUN AT ALL. "The stale publish-branch
reclaim runs for `fresh` and `seeded` items only." Its ABSENCE is what the
sibling resume case asserts, so a build that simply stopped reclaiming would
pass that file; this case is its control.

WHY THE PREPARE STEP IS READ AS WELL AS THE NAMESPACE. Two attributes on a
namespace are not a checkout. The overlay renders them into the sandbox's last
prepare step, and that rendering is where "checks out the recorded commit SHA"
either happens or silently does not — a namespace carrying a head whose ref
nobody fetches produces a run on whatever the clone happened to contain.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Import order is load-bearing; see `test_dispatcher_recovery_routing_resume.py`.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_wave as loop_wave,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    resume_checkout_for,
    resume_checkout_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-qgcpoc"
_BRANCH = f"feat/{_ITEM_ID}"
_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_DISPATCH = "a7395318d0c945589105940e7936139f"

# The head the dead run pushed to its publish branch before dying, and the
# commit its needs-human ending preserved. They are DIFFERENT shas on purpose:
# the seed must take the preserved tree, which the clause prefers over the
# observed published head, so a build reading the branch tip lands on the wrong
# one rather than on no one.
_DEAD_HEAD = "f3f139b28469c7efaae32dcb897d73518edbaadd"
_PRESERVED_COMMIT = "216c811200000000000000000000000000000002"
_PRESERVED_REF = f"refs/heads/needs-human/{_RUN}"

# The journal stages this file reads. Spelled as literals because its Red
# predates the module that exports them, and a Red's test bytes are fixed
# across its Red-to-Green pair.
_ROUTE_STAGE = "recovery-route"
_RECLAIM_STAGE = "publish-branch-reclaim"


class _Shell:
    """A scripted subprocess seam; an unscripted argv FAILS rather than answering.

    See the sibling resume module for why the state is class-level and why the
    refusal matters. `calls` keeps the joined argv of every command in order,
    which is what makes the preserve-then-delete ORDER readable against the
    preserved-commit read that must precede it.
    """

    answers: ClassVar[dict[str, CommandResult]] = {}
    calls: ClassVar[list[str]] = []

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
        joined = " ".join(argv)
        _Shell.calls.append(joined)
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


def test_the_shell_seam_refuses_a_command_no_case_scripted() -> None:
    """The instrument's own control; see the sibling module for the argument."""
    _Shell.answers = {}
    _Shell.calls = []

    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Shell().run(
            argv=["git", "ls-remote", "origin", "refs/heads/x"],
            cwd=Path("/repo"),
            timeout_seconds=1.0,
        )


def _arm(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A world where the resume has no anchor and the preserved commit is durable.

    The forge names NO pull request for the publish branch, which is the resume's
    first anchor refusal and a fallback-permitting one. Origin DOES carry the
    needs-human ref the dying run pushed, at a commit distinct from the branch
    tip. The factory board answers and holds nothing alive. And the reclaim's own
    two forge calls are scripted, so it can run to completion — which is what
    lets its position in the sequence be measured rather than inferred.
    """
    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ls-remote origin refs/heads/needs-human/": CommandResult(
            exit_code=0, stdout=f"{_PRESERVED_COMMIT}\t{_PRESERVED_REF}\n", stderr=""
        ),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
        f"ls-remote origin refs/heads/{_BRANCH}": CommandResult(
            exit_code=0, stdout=f"{_DEAD_HEAD}\trefs/heads/{_BRANCH}\n", stderr=""
        ),
        "gh api --method POST": CommandResult(exit_code=0, stdout="", stderr=""),
        "gh api --method DELETE": CommandResult(exit_code=0, stdout="", stderr=""),
    }
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A released item whose resume has no anchor",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    """A journal whose newest dispatch of the item ended in a first-stall release."""
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    records: Sequence[dict[str, object]] = (
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH,
            "workflow_name": "implement-work-item",
        },
        {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH,
            "run_id": _RUN,
            "factory": "hp",
            "executing_stage": "proof_capture",
            "published_head": _DEAD_HEAD,
        },
        {"stage": "stall-cancel-release", "work_item_id": _ITEM_ID, "status": "ready"},
    )
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _rows(*, journal: JournalFile, stage: str) -> tuple[dict[str, Any], ...]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(record for record in written if record.get("stage") == stage)


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        item=None,
        items=None,
        budget=1,
        parallel=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


@dataclass(kw_only=True)
class _Wave:
    journal: JournalFile
    launched: argparse.Namespace


def _drive_wave(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Wave:
    """One wave over the single released candidate, with routing and reclaim live."""
    journal = _journal(tmp_path=tmp_path)
    items = [_work_item()]
    captured: list[argparse.Namespace] = []

    _arm(monkeypatch=monkeypatch)
    monkeypatch.setattr(loop_wave, "await_usable_credential", lambda **_kwargs: None)
    monkeypatch.setattr(loop_wave, "resolve_acp_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(
        loop_wave,
        "admit_and_select",
        lambda **_kwargs: admission.Admission(admitted=list(items), deferred=[], refused=[]),
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"]
    )

    def _launch(**kwargs: Any) -> DispatchOutcome:
        captured.append(kwargs["args"])
        _Shell.calls.append("launched the run")
        return DispatchOutcome(
            work_item_id=_ITEM_ID,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="merged",
        )

    monkeypatch.setattr(loop_wave, "dispatch_one", _launch)
    _ = loop_wave.dispatch_loop_wave(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        items=items,
        selected_candidates=items,
        journal=journal,
        janitor=None,
        rework=ReworkPass(scope_ids=frozenset()),
    )
    return _Wave(journal=journal, launched=captured[0])


def _first_index(*, needle: str) -> int:
    """Where one command first appears in the pass's command log."""
    return next(index for index, call in enumerate(_Shell.calls) if needle in call)


def test_an_unanchorable_released_item_is_seeded_from_its_preserved_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole second scenario of 185, read off one wave.

    The seed names all four things the clause requires, the sandbox is placed on
    the RECORDED commit by fetching the preservation reference that carries it,
    and the publish branch is cleared only after that commit was established.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert [
        {
            key: record[key]
            for key in (
                "stage",
                "work_item_id",
                "route",
                "source_run_id",
                "remote",
                "commit_sha",
                "preservation_ref",
            )
        }
        for record in _rows(journal=wave.journal, stage=_ROUTE_STAGE)
    ] == [
        {
            "stage": _ROUTE_STAGE,
            "work_item_id": _ITEM_ID,
            "route": "seeded",
            "source_run_id": _RUN,
            "remote": "origin",
            "commit_sha": _PRESERVED_COMMIT,
            "preservation_ref": _PRESERVED_REF,
        }
    ]
    # The run starts at `start` — a seed is not a resume — on the recorded commit.
    assert getattr(wave.launched, "resume_entry_node", None) is None
    assert getattr(wave.launched, "resume_head", None) == _PRESERVED_COMMIT
    # And the sandbox's own prepare step fetches the ref that carries it and
    # checks the commit out, which is where "checks out the recorded SHA" lands.
    block = resume_checkout_prepare_steps_block(
        checkout=resume_checkout_for(args=wave.launched, branch=_BRANCH)
    )
    assert f"git fetch --no-tags origin {_PRESERVED_REF}" in block
    assert f"git checkout --detach {_PRESERVED_COMMIT}" in block
    # The reclaim ran for this seeded item — unlike a resume — and only after the
    # preserved commit had been established.
    assert [record["branch"] for record in _rows(journal=wave.journal, stage=_RECLAIM_STAGE)] == [
        _BRANCH
    ]
    assert (
        _first_index(needle="ls-remote origin refs/heads/needs-human/")
        < _first_index(needle="gh api --method POST")
        < _first_index(needle="gh api --method DELETE")
        < _first_index(needle="launched the run")
    )
