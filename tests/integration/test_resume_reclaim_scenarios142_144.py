"""Integration journeys for published-run recovery (Scenarios 142--144).

These tests deliberately drive the command/launch boundaries instead of the
smaller decision helpers.  A resume uses the real command, journal and argument
handoff, while the reclaim journey uses a real bare origin.  The local ``gh``
double implements only the forge reference calls that the production code makes;
the ref it creates and the branch it deletes are then read back from origin.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_resume_command as resume
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_launch as launch
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import Admission
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    publish_branch_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    ProofRecord,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    preserved_publish_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    RecoveryRouting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    RESUMED_AT_PR,
    SOURCE_FACTORY_RUN,
    ResumeAnchor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import RESUME_STAGE
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    PR_STATE_CLOSED,
    PR_STATE_MERGED,
    PR_STATE_OPEN,
    LiveRun,
    ResumeObservation,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IOSuccess

_ITEM_ID = "bd-ib-recovery-integration"
_EARLIER_RUN = "01M5EARLIERRUN000000000000"
_PULL_REQUEST = 3142
_HEAD = "a" * 40
_MOVED_HEAD = "b" * 40
_WORKFLOW = "implement-work-item"
_EXIT_PRECONDITION = 3


def _item(*, status: str = "ready") -> WorkItem:
    """One item whose criteria are present in the published proof record."""
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="A published run that needs recovery",
        description="## Definition of Done\n\n- The published run resumes.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-24T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _record() -> ProofRecord:
    """The verified record the published draft pull request exposes."""
    return ProofRecord(
        verdict=VERDICT_VERIFIED,
        run_id=_EARLIER_RUN,
        timestamp="2026-10-24T00:00:00Z",
        url=f"https://forge.example/pull/{_PULL_REQUEST}#issuecomment-1",
        body=f"Publish-branch head: {_HEAD}\n\n- The published run resumes.\n",
    )


def _anchor() -> ResumeAnchor:
    return ResumeAnchor(
        record=_record(),
        run_id=_EARLIER_RUN,
        head=_HEAD,
        resumed_at=RESUMED_AT_PR,
        source=SOURCE_FACTORY_RUN,
    )


def _observation(**overrides: object) -> ResumeObservation:
    """A fully observed, resumable pull request, with one refusal arm changed."""
    values: dict[str, object] = {
        "work_item_id": _ITEM_ID,
        "status": "ready",
        "anchor_head": _HEAD,
        "forge_observed": True,
        "pull_request": _PULL_REQUEST,
        "pull_request_state": PR_STATE_OPEN,
        "pull_request_head": _HEAD,
        "records_observed": True,
        "liveness_observed": True,
    }
    values.update(overrides)
    return ResumeObservation(**values)


def _gather(*, observation: ResumeObservation) -> ResumeGather:
    return ResumeGather(
        observation=observation,
        anchor=_anchor(),
        branch=publish_branch_for(work_item_id=_ITEM_ID),
        earlier_run_ids=(_EARLIER_RUN,),
        workflow_name=_WORKFLOW,
    )


def _resume_args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        item=_ITEM_ID,
        journal=str(journal.path),
        janitor=None,
        fabro_bin="fabro",
        factory=None,
        workflow=None,
        workflow_name=None,
        as_json=False,
    )


def _journal_rows(*, journal: JournalFile) -> list[dict[str, object]]:
    if not journal.path.exists():
        return []
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


def _wire_resume(
    *,
    monkeypatch: pytest.MonkeyPatch,
    item: WorkItem,
    journal: JournalFile,
    observation: ResumeObservation,
    launched: list[argparse.Namespace],
) -> None:
    """Leave command sequencing real while isolating the factory launch seam."""
    monkeypatch.setattr(resume, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(resume, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(resume, "prepare", lambda **_kwargs: ([item], journal))
    monkeypatch.setattr(
        resume,
        "apply_factory_size_dispatch_entry",
        lambda **_kwargs: IOSuccess(()),
    )
    monkeypatch.setattr(resume, "gather_resume", lambda **_kwargs: _gather(observation=observation))
    monkeypatch.setattr(resume, "pre_dispatch_wall_exit", lambda **_kwargs: None)
    monkeypatch.setattr(
        resume,
        "admit_and_select",
        lambda **_kwargs: Admission(admitted=[item], deferred=[], refused=[]),
    )
    monkeypatch.setattr(
        resume,
        "args_with_dispatch_factory_target",
        lambda **kwargs: kwargs["args"],
    )

    def _dispatch(**kwargs: object) -> DispatchOutcome:
        args = kwargs["args"]
        assert isinstance(args, argparse.Namespace)
        launched.append(args)
        return DispatchOutcome(
            work_item_id=_ITEM_ID,
            status="green",
            stage="done",
            pr_number=_PULL_REQUEST,
            merge_sha="merge",
            detail="resumed",
        )

    monkeypatch.setattr(resume, "dispatch_one", _dispatch)
    monkeypatch.setattr(resume, "dispatch_tail_exit", lambda **_kwargs: 0)


def test_resume_starts_at_the_first_unfinished_stage_of_a_published_draft_pr(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 142: the record anchors a dead run at ``pr`` without replaying work."""
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    launched: list[argparse.Namespace] = []
    _wire_resume(
        monkeypatch=monkeypatch,
        item=_item(),
        journal=journal,
        observation=_observation(),
        launched=launched,
    )

    exit_code = resume.run_resume_command(args=_resume_args(repo=tmp_path, journal=journal))

    assert exit_code == 0
    assert len(launched) == 1
    assert launched[0].resume_entry_node == RESUMED_AT_PR
    assert launched[0].resume_head == _HEAD
    assert launched[0].workflow_name == _WORKFLOW
    records = _journal_rows(journal=journal)
    assert len(records) == 1
    assert {
        key: records[0][key]
        for key in (
            "stage",
            "work_item_id",
            "earlier_run_ids",
            "pull_request",
            "head",
            "resumed_at",
            "resumed_at_source",
        )
    } == {
        "stage": RESUME_STAGE,
        "work_item_id": _ITEM_ID,
        "earlier_run_ids": [_EARLIER_RUN],
        "pull_request": _PULL_REQUEST,
        "head": _HEAD,
        "resumed_at": RESUMED_AT_PR,
        "resumed_at_source": SOURCE_FACTORY_RUN,
    }


@dataclass(frozen=True, kw_only=True)
class _ResumeRefusal:
    """One measured refusal, constructed independently from the command's result."""

    name: str
    observation: Callable[[], ResumeObservation]


_REFUSALS = (
    _ResumeRefusal(name="not-ready", observation=lambda: _observation(status="blocked")),
    _ResumeRefusal(
        name="forge-unobservable", observation=lambda: _observation(forge_observed=False)
    ),
    _ResumeRefusal(name="no-pull-request", observation=lambda: _observation(pull_request=None)),
    _ResumeRefusal(
        name="records-unobservable", observation=lambda: _observation(records_observed=False)
    ),
    _ResumeRefusal(name="no-anchor", observation=lambda: _observation(anchor_head=None)),
    _ResumeRefusal(
        name="head-unobservable", observation=lambda: _observation(pull_request_head=None)
    ),
    _ResumeRefusal(
        name="head-moved", observation=lambda: _observation(pull_request_head=_MOVED_HEAD)
    ),
    _ResumeRefusal(
        name="definition-of-done-changed",
        observation=lambda: _observation(changed_assertions=("A later criterion.",)),
    ),
    _ResumeRefusal(
        name="factory-unobservable", observation=lambda: _observation(liveness_observed=False)
    ),
    _ResumeRefusal(
        name="earlier-run-live",
        observation=lambda: _observation(live_runs=(LiveRun(run_id="live", status="running"),)),
    ),
    _ResumeRefusal(
        name="dispatch-lock-live", observation=lambda: _observation(lock_age_seconds=60.0)
    ),
    _ResumeRefusal(
        name="pull-request-closed",
        observation=lambda: _observation(pull_request_state=PR_STATE_CLOSED),
    ),
    _ResumeRefusal(
        name="pull-request-merged",
        observation=lambda: _observation(pull_request_state=PR_STATE_MERGED),
    ),
    _ResumeRefusal(
        name="resume-chain-exhausted",
        observation=lambda: _observation(earlier_resumes=("one", "two")),
    ),
)


def _git(*, cwd: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _branch_and_published_pr(*, tmp_path: Path) -> tuple[Path, Path, Path]:
    """A real branch plus the immutable forge fixture a refusal must not change."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(cwd=repo, args=["init", "--initial-branch=master"])
    _git(cwd=repo, args=["config", "user.name", "Integration Test"])
    _git(cwd=repo, args=["config", "user.email", "integration@example.invalid"])
    _ = (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(cwd=repo, args=["add", "README.md"])
    _git(cwd=repo, args=["commit", "-m", "fixture"])
    branch = publish_branch_for(work_item_id=_ITEM_ID)
    _git(cwd=repo, args=["checkout", "-b", branch])
    _ = (repo / "published.txt").write_text("draft\n", encoding="utf-8")
    _git(cwd=repo, args=["add", "published.txt"])
    _git(cwd=repo, args=["commit", "-m", "published draft"])
    pull_request = repo / "published-pr.json"
    _ = pull_request.write_text(
        json.dumps({"number": _PULL_REQUEST, "state": PR_STATE_OPEN, "head": _HEAD}),
        encoding="utf-8",
    )
    return repo, pull_request, Path(_git(cwd=repo, args=["rev-parse", "HEAD"]))


@pytest.mark.parametrize("refusal", _REFUSALS, ids=lambda refusal: refusal.name)
def test_every_resume_refusal_exits_before_a_run_and_leaves_the_publication_unchanged(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    refusal: _ResumeRefusal,
) -> None:
    """Scenario 143: every ladder arm is before launch, branch and pull request mutation."""
    repo, pull_request, branch_head = _branch_and_published_pr(tmp_path=tmp_path)
    original_pull_request = pull_request.read_bytes()
    journal = JournalFile(path=repo / "journal.jsonl")
    launched: list[argparse.Namespace] = []
    _wire_resume(
        monkeypatch=monkeypatch,
        item=_item(status=refusal.observation().status),
        journal=journal,
        observation=refusal.observation(),
        launched=launched,
    )

    exit_code = resume.run_resume_command(args=_resume_args(repo=repo, journal=journal))

    assert exit_code == _EXIT_PRECONDITION
    assert launched == []
    assert _git(cwd=repo, args=["rev-parse", "HEAD"]) == str(branch_head)
    assert pull_request.read_bytes() == original_pull_request
    assert _journal_rows(journal=journal) == []


def _origin(*, tmp_path: Path) -> tuple[Path, Path, str, str]:
    """A real origin holding exactly the dead run's surviving publish branch."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(origin)], check=True, capture_output=True, text=True
    )
    repo = tmp_path / "dispatch"
    subprocess.run(
        ["git", "clone", str(origin), str(repo)], check=True, capture_output=True, text=True
    )
    _git(cwd=repo, args=["config", "user.name", "Integration Test"])
    _git(cwd=repo, args=["config", "user.email", "integration@example.invalid"])
    _ = (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(cwd=repo, args=["add", "README.md"])
    _git(cwd=repo, args=["commit", "-m", "base"])
    _git(cwd=repo, args=["push", "origin", "HEAD:master"])
    branch = publish_branch_for(work_item_id=_ITEM_ID)
    _git(cwd=repo, args=["checkout", "-b", branch])
    _ = (repo / "published.txt").write_text("dead run\n", encoding="utf-8")
    _git(cwd=repo, args=["add", "published.txt"])
    _git(cwd=repo, args=["commit", "-m", "published by dead run"])
    _git(cwd=repo, args=["push", "origin", f"HEAD:{branch}"])
    return repo, origin, branch, _git(cwd=repo, args=["rev-parse", "HEAD"])


def _write_gh_double(*, directory: Path) -> Path:
    """A forge-ref endpoint backed by the current clone's real bare origin."""
    executable = directory / "gh"
    _ = executable.write_text(
        "#!/bin/sh\n"
        "origin=$(git remote get-url origin)\n"
        'case "$1 $2" in\n'
        "  'api --method')\n"
        "    method=$3\n"
        "    endpoint=$4\n"
        "    shift 4\n"
        '    case "$method" in\n'
        "      POST)\n"
        '        for field in "$@"; do\n'
        '          case "$field" in ref=*) ref=${field#ref=};; sha=*) sha=${field#sha=};; esac\n'
        "        done\n"
        '        git --git-dir="$origin" update-ref "$ref" "$sha"\n'
        "        ;;\n"
        "      DELETE)\n"
        "        ref=refs/${endpoint##*/git/refs/}\n"
        '        git --git-dir="$origin" update-ref -d "$ref"\n'
        "        ;;\n"
        "    esac\n"
        "    ;;\n"
        "  'api /repos/'*)\n"
        "    endpoint=$2\n"
        "    ref=refs/${endpoint##*/git/ref/}\n"
        '    git --git-dir="$origin" rev-parse "$ref"\n'
        "    ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    fabro = directory / "fabro"
    _ = fabro.write_text("#!/bin/sh\nprintf '%s\\n' '[]'\n", encoding="utf-8")
    fabro.chmod(0o755)
    return executable


def test_dispatch_reclaims_a_dead_run_publish_branch_on_a_real_origin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 144: an admitted re-dispatch preserves, deletes, then launches."""
    repo, origin, branch, head = _origin(tmp_path=tmp_path)
    gh_dir = tmp_path / "bin"
    gh_dir.mkdir()
    _ = _write_gh_double(directory=gh_dir)
    monkeypatch.setenv("PATH", str(gh_dir) + os.pathsep + os.environ["PATH"])
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record={"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": "dead"})
    item = _item()
    launched: list[str] = []
    monkeypatch.setattr(
        launch,
        "admit_and_select",
        lambda **_kwargs: Admission(admitted=[item], deferred=[], refused=[]),
    )
    monkeypatch.setattr(
        launch, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(launch, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"])
    monkeypatch.setattr(launch, "journal_recovery_route", lambda **_kwargs: None)
    monkeypatch.setattr(
        launch,
        "dispatch_one",
        lambda **_kwargs: (
            launched.append(_ITEM_ID)
            or DispatchOutcome(
                work_item_id=_ITEM_ID,
                status="green",
                stage="done",
                pr_number=None,
                merge_sha=None,
                detail="launched",
            )
        ),
    )
    args = argparse.Namespace(factory=None, workflow_name=None, fabro_bin="fabro")
    routing = RecoveryRouting(routes=(RecoveryRoute(work_item_id=_ITEM_ID, route=ROUTE_FRESH),))

    outcome = launch.admit_and_dispatch_target(
        args=args,
        repo=repo,
        items=[item],
        target=item,
        journal=journal,
        janitor=None,
        marked=False,
        routing=routing,
    )

    preserved = preserved_publish_ref(work_item_id=_ITEM_ID, head=head)
    assert outcome.status == "green"
    assert launched == [_ITEM_ID]
    assert _git(cwd=repo, args=["--git-dir", str(origin), "rev-parse", preserved]) == head
    deleted = subprocess.run(
        ["git", "--git-dir", str(origin), "show-ref", "--verify", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert deleted.returncode != 0
    reclaim_rows = [
        record
        for record in _journal_rows(journal=journal)
        if record.get("stage") == "publish-branch-reclaim"
    ]
    assert len(reclaim_rows) == 1
    assert {
        key: reclaim_rows[0][key]
        for key in (
            "stage",
            "work_item_id",
            "branch",
            "head",
            "preserved_ref",
        )
    } == {
        "stage": "publish-branch-reclaim",
        "work_item_id": _ITEM_ID,
        "branch": branch,
        "head": head,
        "preserved_ref": preserved,
    }
