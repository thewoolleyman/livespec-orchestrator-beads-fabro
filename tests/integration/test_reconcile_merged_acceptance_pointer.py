"""`reconcile-merged` for an item RESTING IN ACCEPTANCE writes its missing pointer.

`SPECIFICATION/contracts.md`'s reconcile-merged clause (v115) says that for an
item resting in `acceptance` the valve "MUST NOT re-run the post-merge janitor or
re-merge anything: it MUST re-run only the acceptance pass ..., apply that pass's
ordinary disposition, and write a missing Proof of Done pointer". That is the
route by which `bd-ib-mxqrr4` — merged, verified, parked since 2026-10-01 with no
pointer because its record was stamped with the dispatch id — reaches a pointer at
all.

EVERYTHING BUT TWO SOCKETS IS PRODUCTION CODE. The real
`dispatcher.main(argv=["reconcile-merged", ...])` supervisor runs over the real
store/client seam against the in-memory `FakeBeadsClient`, writes a real on-disk
journal, and resolves the merging dispatch's identifiers out of that journal
through the real reader. Only the two seams that leave the process are stood in:
the valve's own shell `CommandRunner`, and the acceptance pass's, which answers
the pull request's comments read.

THE JANITOR'S ABSENCE IS READ OFF THE SEAM, NOT INFERRED. The clause's first
requirement is a NEGATIVE one, and an exit code cannot evidence it — a janitor
that ran and passed exits 0 too. So the valve's runner is handed exactly the two
commands this arm is allowed to issue and its full call list is asserted: a
provisioning command would appear there, and would also exhaust the queue.

THE CONTROL IS A RECORD FROM ANOTHER DISPATCH OF THE SAME ITEM. Without it, "the
pointer was written" is equally consistent with a valve that writes a pointer off
whatever verified record the pull request happens to carry — which would cite a
record describing another tree. Both legs run the same invocation over the same
fixture and differ only in the identifier the record is stamped with.
"""

from __future__ import annotations

import json
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    AcceptancePassResult,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-reconcilepointer"
_PR_NUMBER = 2538
_MERGE_SHA = "52783f67"
# The merging dispatch's two identifiers. Only the DISPATCH id is journaled here,
# because that is the state the reconcile valve actually meets: it builds its own
# outcome from a resolved merged pull request, so no Fabro run id reaches it.
_DISPATCH_ID = "f195238b76b942698485a780611fe1ef"
_OTHER_DISPATCH_ID = "aaaa1111bbbb2222cccc3333dddd4444"
_ASSERTION = "The reader attributes a record stamped with the dispatch id."
_RECORD_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-5940752598"
_RECORD_TIMESTAMP = "2026-10-01T21:15:01Z"
# Shares no significant term with the assertion, so a PASS cannot have come from
# the merged-diff vocabulary matcher.
_MERGED_DIFF = "diff --git a/x b/x\n+rearranged an unrelated helper\n"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    """Resolve the store onto the in-memory fake, fresh per case.

    `$HOME` is scrubbed with it: the janitor checkout path resolves under
    `Path.home()/.worktrees`, and a case whose whole claim is that no janitor ran
    must not be able to touch the real one if that claim ever breaks.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _ValveRunner:
    """The valve's own shell seam: a queue, and the full call list it consumed."""

    queue: list[CommandResult]
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
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _ForgeRunner:
    """The acceptance pass's seam: the pull request's comments, and the merged diff."""

    comments: str

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
        if "comments" in argv:
            return CommandResult(exit_code=0, stdout=self.comments, stderr="")
        return CommandResult(exit_code=0, stdout=_MERGED_DIFF, stderr="")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _definition_of_done() -> str:
    return textwrap.dedent(f"""\
        Repair the attribution.

        ## Definition of Done

        - {_ASSERTION}

        References: ## Effective acceptance criteria
        """)


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="acceptance",
        title="A merged, verified slice parked with no pointer",
        description=_definition_of_done(),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        # The parked default: the pass disposes of nothing, so the pointer write
        # is isolated from a close that would also rewrite the record.
        acceptance_policy="ai-then-human",
    )


def _repo(*, tmp_path: Path, journaled_dispatch_id: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        (
            '{"livespec-orchestrator-beads-fabro": {'
            '"connection": {"prefix": "bd-ib"}, '
            '"compat": {"pinned": "master"}'
            "}}"
        ),
        encoding="utf-8",
    )
    # The ORIGINAL dispatch's journal, as it survives on the host between the
    # dispatch and the reconcile: the `dispatch-id` record is the only place the
    # identifier the sandbox stamped onto its records can still be read.
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        json.dumps(
            {
                "stage": "dispatch-id",
                "work_item_id": _ITEM_ID,
                "dispatch_id": journaled_dispatch_id,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return repo


def _comments_payload(*, run_id: str) -> str:
    body = textwrap.dedent(f"""\
        Proof of Done — verified — run {run_id} — {_RECORD_TIMESTAMP}

        ## Assertion 1 — {_ASSERTION}

        Proof mode: `factory_captured`

        Reproduced: yes.
        """)
    return json.dumps({"comments": [{"url": _RECORD_URL, "body": body}]})


def _pr_view_json() -> str:
    return json.dumps(
        {
            "number": _PR_NUMBER,
            "state": "MERGED",
            "autoMergeRequest": {},
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": _MERGE_SHA},
            "statusCheckRollup": [],
        }
    )


def _real_pass_over(*, comments: str) -> object:
    """The REAL acceptance pass with only its command seam stood in."""
    runner = _ForgeRunner(comments=comments)

    def _call(
        *,
        repo: Path,
        item: WorkItem,
        outcome: DispatchOutcome,
        raw_labels: Sequence[str] = (),
        journal_path: Path | None = None,
    ) -> AcceptancePassResult:
        return run_acceptance_pass(
            repo=repo,
            item=item,
            outcome=outcome,
            runner=runner,
            raw_labels=raw_labels,
            journal_path=journal_path,
        )

    return _call


def _merged_queue() -> list[CommandResult]:
    """The plan build's default-branch probe, then the merged-PR view.

    A THIRD command would raise an IndexError out of the runner, which is the
    queue doing half of the no-janitor assertion's work.
    """
    return [
        CommandResult(exit_code=0, stdout="origin/master", stderr=""),
        CommandResult(exit_code=0, stdout=_pr_view_json(), stderr=""),
    ]


def _unmerged_queue() -> list[CommandResult]:
    """The same probe, then a branch view that fails and a merged search with no hit."""
    return [
        CommandResult(exit_code=0, stdout="origin/master", stderr=""),
        CommandResult(exit_code=1, stdout="", stderr="no pull requests found"),
        CommandResult(exit_code=0, stdout="[]", stderr=""),
    ]


def _reconcile(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record_run_id: str,
    journaled_dispatch_id: str = _DISPATCH_ID,
    queue: list[CommandResult] | None = None,
) -> tuple[int, Path, _ValveRunner]:
    repo = _repo(tmp_path=tmp_path, journaled_dispatch_id=journaled_dispatch_id)
    append_work_item(path=_config(), item=_item())
    runner = _ValveRunner(queue=_merged_queue() if queue is None else queue)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner",
        lambda: runner,
    )
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        _real_pass_over(comments=_comments_payload(run_id=record_run_id)),
        raising=False,
    )

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", _ITEM_ID, "--json"])
    return exit_code, repo, runner


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_an_acceptance_resting_item_gets_its_pointer_and_no_janitor_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The pointer lands after a BYTE-IDENTICAL Definition of Done section."""
    exit_code, repo, runner = _reconcile(
        monkeypatch=monkeypatch, tmp_path=tmp_path, record_run_id=_DISPATCH_ID
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload[0]["status"] == "green"
    # The negative requirement, read off the seam: exactly the default-branch
    # probe and the merged-PR view. No checkout, no provisioning, no check suite.
    assert [argv[:2] for argv in runner.argvs] == [["git", "symbolic-ref"], ["gh", "pr"]]
    description = _stored().description
    head, _, pointer = description.partition("## Proof of Done")
    assert pointer != ""
    # Byte-for-byte: everything before the pointer heading is the filed
    # description, trailing separator aside. An `in`-containment check would pass
    # just as well for a build that rewrote the section while appending.
    assert head.rstrip("\n") == _definition_of_done().rstrip("\n")
    assert pointer.splitlines()[1:] == [
        "",
        f"- Pull request: #{_PR_NUMBER}",
        f"- Verified record: {_RECORD_URL}",
        f"- Run: {_DISPATCH_ID}",
        f"- Timestamp: {_RECORD_TIMESTAMP}",
        "- Verdict: verified",
    ]
    # The section carries the POINTER, never the proof.
    assert "Reproduced:" not in description
    records = _journal_records(repo=repo)
    written = next(one for one in records if one.get("stage") == "proof-pointer")
    assert written["run_id"] == _DISPATCH_ID
    assert written["record_comment"] == _RECORD_URL
    # The pass PASSED off the record, and the parked policy left the item resting.
    assert next(one for one in records if one.get("stage") == "acceptance-ai-pass")["verdict"] == (
        "PASS"
    )
    assert _stored().status == "acceptance"


def test_a_record_from_another_dispatch_of_the_same_item_writes_no_pointer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The control: the same invocation, a record belonging to a different dispatch.

    The pull request carries a `verified` record that lists the assertion as
    reproduced — a build attributing whatever verified record it finds would write
    a pointer here and would grade the assertion PASS. The record is simply not
    this merge's, so the assertion is UNOBSERVED and no pointer is written.
    """
    exit_code, repo, _ = _reconcile(
        monkeypatch=monkeypatch, tmp_path=tmp_path, record_run_id=_OTHER_DISPATCH_ID
    )

    assert exit_code == 0
    description = _stored().description
    assert "## Proof of Done" not in description
    assert description == _definition_of_done()
    records = _journal_records(repo=repo)
    skipped = next(one for one in records if one.get("stage") == "proof-pointer-skipped")
    assert skipped["reason"] == "no verified Proof of Done record for the merging run"
    ai_pass = next(one for one in records if one.get("stage") == "acceptance-ai-pass")
    assert ai_pass["verdict"] == "NEEDS_ATTENTION"
    assert ai_pass["absent_evidence"] == [f"proof of done record for {_ASSERTION!r}"]
    assert _stored().status == "acceptance"


def test_an_acceptance_resting_item_with_no_merged_pull_request_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No merge resolves, so the arm refuses instead of accepting against nothing.

    The admission gate let this item through on its STATUS, which says nothing
    about whether a merge exists. Were the arm to proceed anyway it would hand the
    acceptance pass an outcome asserting a merge it never resolved — the one thing
    the whole valve exists to establish from the forge rather than from the ledger.
    """
    exit_code, repo, _ = _reconcile(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        record_run_id=_DISPATCH_ID,
        queue=_unmerged_queue(),
    )

    stderr = capsys.readouterr().err
    assert exit_code == 3
    assert stderr == f"ERROR: no merged PR found for work-item {_ITEM_ID}\n"
    # Nothing was accepted and nothing was written: no pointer, no verdict, and the
    # item rests exactly where the admission gate found it.
    stages = [one.get("stage") for one in _journal_records(repo=repo)]
    assert "acceptance-ai-pass" not in stages
    assert "proof-pointer" not in stages
    assert "## Proof of Done" not in _stored().description
    assert _stored().status == "acceptance"
