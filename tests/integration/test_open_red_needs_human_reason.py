"""A timed-out stage's needs-human ending NAMES the open Red commit it left behind.

Binds the SECOND Definition-of-Done assertion of work-item `bd-ib-qhv7qs`
against `SPECIFICATION/scenarios.md` "Scenario 103 — A needs-human outcome
terminates the run and routes the decision to the ledger": the dispatch result
for that ending names the timed-out stage AND the open Red commit as the
reason, and the item rests `blocked` with that reason RECORDED rather than
`active` with no reason.

WHY THE REASON HAS TO COME FROM THE TERMINAL AND THE STAGE FROM THE ENGINE, and
why neither can supply the other. A turn that TIMED OUT wrote nothing: it never
reached the structured needs-human ending, so the per-stage reason file the
graph reads is absent and the only account of the half-authored tree is the tree
itself, which only the terminal node can see. The STAGE, conversely, is nowhere
in the sandbox — it is the engine's own `node_outcomes` map, which only the
Dispatcher reads. So the two halves are asserted TOGETHER on one payload: each
alone is satisfied by a build that loses the other, and the operator reads them
in one result.

THE CONTROLS ARE WHAT MAKE THE POSITIVE CASE EVIDENCE. A terminal that appended
the open-Red clause unconditionally would pass the positive case and lie on
every other ending, so the SAME fixture is run with a COMPLETED Red-Green pair
at the branch head (the third Definition-of-Done assertion's own control) and
with a stage-written reason file present — which must win, because a stage that
DID reach the structured ending has diagnosed its own fault and the tree shape
is then the less specific account.

AND THE RECORD IS READ BACK OFF THE TENANT, not off the renderer. The dispatch
result and the stderr line are both transient — the result is read once and the
stream scrolls away — while `bd comments` is the only thing on this tenant that
outlives the run. "Recorded" therefore means the comment, so the comment is
what this module reads, through `read_work_item_comments` and indexed on
`text`: `bd show --json` carries no comment bodies at all, so verifying the
write through it reports every successful append as lost.

WHAT IS STOOD IN, AND WHAT IS NOT. Nothing stands in for the terminal: its own
script is extracted from the committed graph and unescaped, then run by `sh` in
a throwaway repository with a real bare `origin` and real commits, so the
open-Red reading is MEASURED against a tree that genuinely carries one. The
terminal mapper, the causal-stage verdict, the detail render, the durable record
writer and the blocked ledger write are production code over the real
store/client seam.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
    record_needs_human_cause,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import WorkItem

_WORKFLOW_DOT = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_TERMINAL = "needs_human"
_ITEM = "bd-ib-qhv7qs"
_RUN = "01M4HA8YVAAH21T5ZR1TVBDQYP"
_STAGE = "review_fix"
_SIGNATURE = f"{_STAGE}|deterministic|acp turn failed"
_OPERATOR_NAME = "Chad Woolley"
_OPERATOR_EMAIL = "thewoolleyman@gmail.com"

# The two needles the reason owes an operator: WHICH commit is open, and WHAT
# about it blocks the loop. The second is asserted separately because the sha
# alone appears in any git output and says nothing about the tree's shape.
_OPEN_RED_CLAUSE = "open Red commit"
_HALF_PAIR_CLAUSE = "half authored"

# The measured cause of the second incident, in the engine's own wording. The
# chain is outermost-first, so the fixed `ACP protocol error` wrapper leads.
_CAUSE = (
    "ACP turn timed out after 131 tool call(s) and 1799992ms without the agent " "ending its turn"
)

# The trailer keys the commit-refuse hook writes. An OPEN Red carries the first
# and not the second; a completed pair carries both, which is exactly why the
# presence of Red trailers alone is not the discriminator.
_RED_TRAILER = "TDD-Red-Test-File-Checksum: sha256:0f0f"
_GREEN_TRAILER = "TDD-Green-Verified-At: 2026-10-13T00:00:00Z"

_OPEN_RED_MESSAGE = f"fix(factory): the staged test\n\n{_RED_TRAILER}\n"
_COMPLETED_PAIR_MESSAGE = f"fix(factory): the staged test\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n"


@pytest.fixture
def tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _preservation_script() -> str:
    """The terminal node's own script, unescaped from the committed DOT attribute."""
    text = _WORKFLOW_DOT.read_text(encoding="utf-8")
    match = re.search(rf"^\s*{_TERMINAL}\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    assert match is not None
    script = re.search(r'script="(?P<script>(?:[^"\\]|\\.)*)"', match.group("body"))
    assert script is not None
    return re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", script.group("script"))


def _git(repo: Path, *argv: str) -> str:
    completed = subprocess.run(
        ["git", *argv], cwd=str(repo), check=True, text=True, capture_output=True
    )
    return completed.stdout.strip()


def _sandbox(*, root: Path, head_message: str) -> tuple[Path, str]:
    """A sandbox-shaped checkout whose HEAD carries `head_message`, plus a bare origin.

    The in-progress edit is what the terminal preserves, and it is left
    UNCOMMITTED on purpose: that is the shape a timed-out turn leaves behind,
    and it is what makes the HEAD message — rather than the worktree — the
    thing the open-Red reading has to key on.
    """
    origin = root / "origin.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", str(origin)],
        check=True,
        text=True,
        capture_output=True,
    )
    work = root / "work"
    work.mkdir(parents=True)
    _ = _git(work, "init", "--quiet")
    _ = _git(work, "config", "user.email", _OPERATOR_EMAIL)
    _ = _git(work, "config", "user.name", _OPERATOR_NAME)
    _ = _git(work, "config", "commit.gpgsign", "false")
    _ = (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _ = _git(work, "add", "seed.txt")
    _ = _git(work, "commit", "--quiet", "-m", "seed")
    (work / "tests").mkdir()
    _ = (work / "tests" / "test_slice.py").write_text(
        "def test_slice() -> None:\n    pass\n", encoding="utf-8"
    )
    _ = _git(work, "add", "tests/test_slice.py")
    subprocess.run(
        ["git", "commit", "--quiet", "-F", "-"],
        cwd=str(work),
        check=True,
        text=True,
        capture_output=True,
        input=head_message,
    )
    _ = _git(work, "remote", "add", "origin", str(origin))
    _ = (work / "impl.py").write_text(
        "the edit the timed-out turn never amended\n", encoding="utf-8"
    )
    return work, _git(work, "rev-parse", "--short", "HEAD")


def _terminal_stderr(*, work: Path) -> str:
    """The terminal's real stderr, with the engine's stdin run-id source stood in for."""
    env = {key: value for key, value in os.environ.items() if key != "FABRO_RUN_ID"}
    env["LIVESPEC_GIT_AUTHOR_NAME"] = _OPERATOR_NAME
    env["LIVESPEC_GIT_AUTHOR_EMAIL"] = _OPERATOR_EMAIL
    completed = subprocess.run(
        ["sh", "-c", _preservation_script()],
        cwd=str(work),
        env=env,
        check=False,
        text=True,
        capture_output=True,
        input=f"{_RUN}\n",
    )
    assert completed.returncode == 1, completed.stderr
    return completed.stderr


def _payload() -> list[object]:
    """`fabro inspect --json` for the measured run, in its measured terminated shape."""
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed"},
            "checkpoints": [
                {
                    "checkpoint": {
                        "current_node": _TERMINAL,
                        "next_node_id": None,
                        "completed_nodes": ["implement", "janitor", _STAGE],
                        "loop_failure_signatures": {_SIGNATURE: 2},
                        "node_outcomes": {
                            _STAGE: {
                                "status": "failed",
                                "failure": {
                                    "category": "deterministic",
                                    "signature": _SIGNATURE,
                                    "causes": ["ACP protocol error", _CAUSE],
                                },
                            }
                        },
                    }
                }
            ],
        }
    ]


def _plan(*, root: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=root,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=root / "workflow.toml",
        goal_file=root / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp.example:32276",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=root / ".janitor",
        janitor_core_checkout=root / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _outcome(*, root: Path, stderr: str) -> DispatchOutcome:
    payload = _payload()
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(root=root),
        run_id=_RUN,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
        ),
        exit_code=1,
        stderr=stderr,
    )
    assert outcome is not None
    return outcome


def _write_repo(*, root: Path) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-orch-beads-fabro",
      "prefix": "bd-ib",
      "server_user": "livespec-orch-beads-fabro",
      "database": "livespec-orch-beads-fabro",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )


def _seed(*, root: Path) -> WorkItem:
    item = WorkItem(
        id=_ITEM,
        type="bug",
        status="active",
        blocked_reason=None,
        title="A timed-out fix stage leaves the item active with no reason",
        description="## Definition of Done\n\n- the ending names the open Red commit.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=store_config(repo=root), item=item)
    return item


def test_the_terminal_reason_names_the_open_red_commit_at_the_branch_head(
    tmp_path: Path,
) -> None:
    """The measured shape: Red trailers at HEAD, no Green, nothing else written."""
    work, sha = _sandbox(root=tmp_path, head_message=_OPEN_RED_MESSAGE)

    stderr = _terminal_stderr(work=work)

    assert f"{_OPEN_RED_CLAUSE} {sha}" in stderr
    assert _HALF_PAIR_CLAUSE in stderr
    assert "loop cannot auto-resolve this work-item" not in stderr


def test_a_completed_red_green_pair_at_the_branch_head_claims_no_open_red(
    tmp_path: Path,
) -> None:
    """The control: Red trailers alone are not the discriminator — the Green is."""
    work, _ = _sandbox(root=tmp_path, head_message=_COMPLETED_PAIR_MESSAGE)

    stderr = _terminal_stderr(work=work)

    assert _OPEN_RED_CLAUSE not in stderr
    assert _HALF_PAIR_CLAUSE not in stderr
    assert "loop cannot auto-resolve this work-item" in stderr


def test_a_stage_written_reason_outranks_the_open_red_clause(tmp_path: Path) -> None:
    """A stage that DID reach the structured ending has the more specific account."""
    work, _ = _sandbox(root=tmp_path, head_message=_OPEN_RED_MESSAGE)
    reason_path = Path(_git(work, "rev-parse", "--git-path", "livespec-needs-human-reason"))
    resolved = reason_path if reason_path.is_absolute() else work / reason_path
    _ = resolved.write_text("Definition of Done amendment for bd-ib-qhv7qs\n", encoding="utf-8")

    stderr = _terminal_stderr(work=work)

    assert "Definition of Done amendment for bd-ib-qhv7qs" in stderr
    assert _OPEN_RED_CLAUSE not in stderr


def test_the_dispatch_result_names_both_the_timed_out_stage_and_the_open_red(
    tmp_path: Path,
) -> None:
    """One payload, both halves: the engine's failed node and the terminal's reason."""
    work, sha = _sandbox(root=tmp_path / "sandbox", head_message=_OPEN_RED_MESSAGE)

    outcome = _outcome(root=tmp_path, stderr=_terminal_stderr(work=work))

    assert outcome.status == "blocked"
    assert f"stage {_STAGE}" in outcome.detail
    assert f"{_OPEN_RED_CLAUSE} {sha}" in outcome.detail
    assert outcome.needs_human_reason is not None
    assert f"{_OPEN_RED_CLAUSE} {sha}" in outcome.needs_human_reason
    assert _HALF_PAIR_CLAUSE in outcome.needs_human_reason
    # The ending is the structured one, so the preserved ref is named rather
    # than a `fabro attach` against a run that no longer exists.
    assert f"refs/heads/needs-human/{_RUN}" in outcome.detail
    assert "fabro attach" not in outcome.detail


def test_the_item_rests_blocked_with_the_stage_and_the_open_red_recorded(
    tmp_path: Path, tenant: None
) -> None:
    """The durable half: the comment outlives the run, and the row leaves `active`."""
    del tenant
    work, sha = _sandbox(root=tmp_path / "sandbox", head_message=_OPEN_RED_MESSAGE)
    _write_repo(root=tmp_path)
    item = _seed(root=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    outcome = _outcome(root=tmp_path, stderr=_terminal_stderr(work=work))

    record_needs_human_cause(repo=tmp_path, item=item, outcome=outcome, journal=journal)
    escalate_needs_human_block(repo=tmp_path, item=item, outcome=outcome, journal=journal)

    bodies = [
        comment.text
        for comment in read_work_item_comments(path=store_config(repo=tmp_path), work_item_id=_ITEM)
        if comment.text.startswith(NEEDS_HUMAN_CAUSE_MARKER)
    ]
    assert len(bodies) == 1
    assert f"failed stage: {_STAGE}" in bodies[0]
    assert f"{_OPEN_RED_CLAUSE} {sha}" in bodies[0]
    assert _HALF_PAIR_CLAUSE in bodies[0]
    rested = [row for row in read_work_items(path=store_config(repo=tmp_path)) if row.id == _ITEM]
    assert [(row.status, row.blocked_reason) for row in rested] == [("blocked", "needs-human")]
