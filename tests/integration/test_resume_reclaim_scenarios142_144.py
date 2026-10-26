"""Integration journeys for published-run recovery (Scenarios 142--144).

These tests deliberately drive the command/launch boundaries instead of the
smaller decision helpers.  A resume uses its real preparation and observation
path against a journaled factory run, a publish branch on a real bare origin, and
the command-facing forge/factory doubles.  The reclaim journey likewise uses a
real bare origin; the ref it creates and the branch it deletes are read back
from that origin.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection as selection
from livespec_orchestrator_beads_fabro.commands import _dispatcher_resume_command as resume
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_launch as launch
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import Admission
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_pid_liveness import (
    process_started_at_epoch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    publish_branch_for,
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
    RESUMED_AT_PR_REFRESH,
    SOURCE_FACTORY_RUN,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import RESUME_STAGE
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    PR_STATE_CLOSED,
    PR_STATE_MERGED,
    PR_STATE_OPEN,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IOSuccess

_ITEM_ID = "bd-ib-recovery-integration"
_EARLIER_RUN = "01M5EARLIERRUN000000000000"
_PULL_REQUEST = 3142
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
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


def _wire_resume(
    *,
    monkeypatch: pytest.MonkeyPatch,
    item: WorkItem,
    launched: list[argparse.Namespace],
) -> None:
    """Keep launch outside this journey while retaining prepare and observation."""
    monkeypatch.setattr(resume, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(resume, "arm_otel_egress", lambda **_kwargs: None)
    # `prepare` remains production code. These are its tenant/environment seams;
    # the fixture still supplies the workflow path and journal it resolves.
    monkeypatch.setattr(selection, "load_items", lambda **_kwargs: [item])
    monkeypatch.setattr(selection, "apply_dispatcher_staleness_gate", lambda **_kwargs: None)
    monkeypatch.setattr(
        resume,
        "apply_factory_size_dispatch_entry",
        lambda **_kwargs: IOSuccess(()),
    )
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
    """Scenario 142: a journaled dead run resumes at its checkpointed first gap."""
    fixture = _published_resume_fixture(tmp_path=tmp_path)
    monkeypatch.setenv("PATH", str(fixture.forge.parent) + os.pathsep + os.environ["PATH"])
    launched: list[argparse.Namespace] = []
    _wire_resume(
        monkeypatch=monkeypatch,
        item=_item(),
        launched=launched,
    )

    exit_code = resume.run_resume_command(
        args=_resume_args(repo=fixture.repo, journal=fixture.journal)
    )

    assert exit_code == 0
    assert len(launched) == 1
    assert launched[0].resume_entry_node == RESUMED_AT_PR_REFRESH
    assert launched[0].resume_head == fixture.head
    assert launched[0].workflow_name == _WORKFLOW
    records = [
        record
        for record in _journal_rows(journal=fixture.journal)
        if record.get("stage") == RESUME_STAGE
    ]
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
        "earlier_run_ids": [_EARLIER_RUN, "dead-dispatch"],
        "pull_request": _PULL_REQUEST,
        "head": fixture.head,
        "resumed_at": RESUMED_AT_PR_REFRESH,
        "resumed_at_source": SOURCE_FACTORY_RUN,
    }


@dataclass(frozen=True, kw_only=True)
class _ResumeRefusal:
    """One refusal induced through the command's observed external inputs."""

    name: str
    configure: Callable[[_PublishedResumeFixture], WorkItem]


def _git(*, cwd: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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


@dataclass(frozen=True, kw_only=True)
class _PublishedResumeFixture:
    repo: Path
    origin: Path
    branch: str
    head: str
    journal: JournalFile
    forge: Path
    factory: Path

    def write_forge(self, payload: dict[str, object]) -> None:
        self.forge.write_text(json.dumps(payload), encoding="utf-8")

    def read_forge(self) -> dict[str, object]:
        return json.loads(self.forge.read_text(encoding="utf-8"))

    def write_factory(self, payload: dict[str, object]) -> None:
        self.factory.write_text(json.dumps(payload), encoding="utf-8")


def _proof_comment(*, head: str) -> dict[str, str]:
    return {
        "url": f"https://forge.example/pull/{_PULL_REQUEST}#issuecomment-1",
        "body": (
            f"Proof of Done — verified — run {_EARLIER_RUN} — 2026-10-24T00:00:00Z\n\n"
            f"Publish-branch head: {head}\n\n"
            "## Assertion 1\n\n- The published run resumes.\n\nReproduced: yes.\n"
        ),
    }


def _write_resume_command_doubles(*, directory: Path) -> None:
    """Install only the CLI endpoints production resume observation calls."""
    source = """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

root = Path(__file__).parent
name = Path(sys.argv[0]).name
payload = json.loads((root / ("forge.json" if name == "gh" else "factory.json")).read_text())
args = sys.argv[1:]
if name == "gh":
    if args[:2] == ["pr", "list"]:
        if payload.get("list_exit", 0):
            raise SystemExit(payload["list_exit"])
        print(json.dumps(payload["pull_requests"]))
    elif args[:2] == ["pr", "view"]:
        if payload.get("view_exit", 0):
            raise SystemExit(payload["view_exit"])
        print(json.dumps({"comments": payload["comments"]}))
    else:
        raise SystemExit(2)
elif args[:1] == ["ps"]:
    if payload.get("ps_exit", 0):
        raise SystemExit(payload["ps_exit"])
    print(json.dumps(payload["runs"]))
elif args[:1] == ["inspect"]:
    if payload.get("inspect_exit", 0):
        raise SystemExit(payload["inspect_exit"])
    print(json.dumps(payload["inspect"]))
else:
    raise SystemExit(2)
"""
    for name in ("gh", "fabro"):
        executable = directory / name
        executable.write_text(source, encoding="utf-8")
        executable.chmod(0o755)


def _published_resume_fixture(*, tmp_path: Path) -> _PublishedResumeFixture:
    """One real published branch and the files observed by production CLI reads."""
    repo, origin, branch, head = _origin(tmp_path=tmp_path)
    workflow = repo / ".fabro" / "workflows" / _WORKFLOW / "workflow.toml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("[workflow]\n", encoding="utf-8")
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "run_id": _EARLIER_RUN,
            "dispatch_id": "dead-dispatch",
            "workflow_name": _WORKFLOW,
        }
    )
    bin_dir = tmp_path / "resume-bin"
    bin_dir.mkdir()
    _write_resume_command_doubles(directory=bin_dir)
    forge = bin_dir / "forge.json"
    factory = bin_dir / "factory.json"
    fixture = _PublishedResumeFixture(
        repo=repo,
        origin=origin,
        branch=branch,
        head=head,
        journal=journal,
        forge=forge,
        factory=factory,
    )
    fixture.write_forge(
        {
            "pull_requests": [
                {"number": _PULL_REQUEST, "state": PR_STATE_OPEN, "headRefOid": head}
            ],
            "comments": [_proof_comment(head=head)],
        }
    )
    fixture.write_factory(
        {
            "runs": [{"run_id": _EARLIER_RUN, "status": "failed", "work_item_id": _ITEM_ID}],
            "inspect": [{"run_id": _EARLIER_RUN, "checkpoint": {"next_node_id": "pr"}}],
        }
    )
    return fixture


def _with_forge(fixture: _PublishedResumeFixture, **changes: object) -> None:
    payload = fixture.read_forge()
    payload.update(changes)
    fixture.write_forge(payload)


def _not_ready(_fixture: _PublishedResumeFixture) -> WorkItem:
    return _item(status="blocked")


def _forge_unobservable(fixture: _PublishedResumeFixture) -> WorkItem:
    _with_forge(fixture, list_exit=1)
    return _item()


def _no_pull_request(fixture: _PublishedResumeFixture) -> WorkItem:
    _with_forge(fixture, pull_requests=[])
    return _item()


def _records_unobservable(fixture: _PublishedResumeFixture) -> WorkItem:
    _with_forge(fixture, view_exit=1)
    return _item()


def _no_anchor(fixture: _PublishedResumeFixture) -> WorkItem:
    _with_forge(fixture, comments=[])
    return _item()


def _head_unobservable(fixture: _PublishedResumeFixture) -> WorkItem:
    _with_forge(
        fixture,
        pull_requests=[{"number": _PULL_REQUEST, "state": PR_STATE_OPEN}],
    )
    return _item()


def _head_moved(fixture: _PublishedResumeFixture) -> WorkItem:
    _with_forge(
        fixture,
        pull_requests=[
            {"number": _PULL_REQUEST, "state": PR_STATE_OPEN, "headRefOid": _MOVED_HEAD}
        ],
    )
    return _item()


def _definition_changed(_fixture: _PublishedResumeFixture) -> WorkItem:
    return replace(_item(), description="## Definition of Done\n\n- A later criterion.\n")


def _factory_unobservable(fixture: _PublishedResumeFixture) -> WorkItem:
    fixture.write_factory({"ps_exit": 1, "runs": [], "inspect": []})
    return _item()


def _earlier_run_live(fixture: _PublishedResumeFixture) -> WorkItem:
    fixture.write_factory(
        {
            "runs": [{"run_id": _EARLIER_RUN, "status": "running", "work_item_id": _ITEM_ID}],
            "inspect": [{"run_id": _EARLIER_RUN, "checkpoint": {"next_node_id": "pr"}}],
        }
    )
    return _item()


def _dispatch_lock_live(fixture: _PublishedResumeFixture) -> WorkItem:
    started = process_started_at_epoch(pid=os.getpid())
    assert started is not None
    path = dispatch_lock_path(repo=fixture.repo, work_item_id=_ITEM_ID)
    path.parent.mkdir()
    path.write_text(
        json.dumps({"work_item_id": _ITEM_ID, "pid": os.getpid(), "started_at_epoch": started}),
        encoding="utf-8",
    )
    return _item()


def _pr_state(state: str) -> Callable[[_PublishedResumeFixture], WorkItem]:
    def configure(fixture: _PublishedResumeFixture) -> WorkItem:
        _with_forge(
            fixture,
            pull_requests=[{"number": _PULL_REQUEST, "state": state, "headRefOid": fixture.head}],
        )
        return _item()

    return configure


def _resume_chain_exhausted(fixture: _PublishedResumeFixture) -> WorkItem:
    for identifier in ("one", "two"):
        fixture.journal.append(
            record={
                "stage": RESUME_STAGE,
                "work_item_id": _ITEM_ID,
                "earlier_run_ids": [identifier],
                "pull_request": _PULL_REQUEST,
            }
        )
        fixture.journal.append(
            record={"stage": "launched", "work_item_id": _ITEM_ID, "run_id": identifier}
        )
    return _item()


_REFUSALS = (
    _ResumeRefusal(name="not-ready", configure=_not_ready),
    _ResumeRefusal(name="forge-unobservable", configure=_forge_unobservable),
    _ResumeRefusal(name="no-pull-request", configure=_no_pull_request),
    _ResumeRefusal(name="records-unobservable", configure=_records_unobservable),
    _ResumeRefusal(name="no-anchor", configure=_no_anchor),
    _ResumeRefusal(name="head-unobservable", configure=_head_unobservable),
    _ResumeRefusal(name="head-moved", configure=_head_moved),
    _ResumeRefusal(name="definition-of-done-changed", configure=_definition_changed),
    _ResumeRefusal(name="factory-unobservable", configure=_factory_unobservable),
    _ResumeRefusal(name="earlier-run-live", configure=_earlier_run_live),
    _ResumeRefusal(name="dispatch-lock-live", configure=_dispatch_lock_live),
    _ResumeRefusal(name="pull-request-closed", configure=_pr_state(PR_STATE_CLOSED)),
    _ResumeRefusal(name="pull-request-merged", configure=_pr_state(PR_STATE_MERGED)),
    _ResumeRefusal(name="resume-chain-exhausted", configure=_resume_chain_exhausted),
)


@pytest.mark.parametrize("refusal", _REFUSALS, ids=lambda refusal: refusal.name)
def test_every_resume_refusal_exits_before_a_run_and_leaves_the_publication_unchanged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: _ResumeRefusal
) -> None:
    """Scenario 143: every observed refusal is before launch or publication mutation."""
    fixture = _published_resume_fixture(tmp_path=tmp_path)
    monkeypatch.setenv("PATH", str(fixture.forge.parent) + os.pathsep + os.environ["PATH"])
    item = refusal.configure(fixture)
    published_ref = f"refs/heads/{fixture.branch}"
    original_ref = _git(
        cwd=fixture.repo, args=["--git-dir", str(fixture.origin), "rev-parse", published_ref]
    )
    original_forge = fixture.forge.read_bytes()
    original_journal = fixture.journal.path.read_bytes()
    launched: list[argparse.Namespace] = []
    _wire_resume(monkeypatch=monkeypatch, item=item, launched=launched)

    exit_code = resume.run_resume_command(
        args=_resume_args(repo=fixture.repo, journal=fixture.journal)
    )

    assert exit_code == _EXIT_PRECONDITION
    assert launched == []
    assert (
        _git(cwd=fixture.repo, args=["--git-dir", str(fixture.origin), "rev-parse", published_ref])
        == original_ref
    )
    assert fixture.forge.read_bytes() == original_forge
    assert fixture.journal.path.read_bytes() == original_journal


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
