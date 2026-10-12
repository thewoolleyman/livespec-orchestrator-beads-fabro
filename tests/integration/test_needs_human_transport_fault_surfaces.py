"""A backgrounded-tool fault reads as a TRANSPORT fault on every surface.

Epic `bd-ib-ctagnf`'s opening research note "Failure analysis and mechanism
candidates", sections "The measured backgrounded-tool fault" and "The pr stage
dies without publishing", measured the fault this module binds. The harness moves a
shell call that reaches its default foreground budget to a BACKGROUND TASK; the
engine (by the design of `bd-ib-bindom`, which must not be weakened) refuses to
let the agent continue beside a detached process and ends the turn; the node
reports the generic stage label `ACP turn failed`, the graph routes the run to
the `needs_human` terminal, and the operator is sent looking for a question
nobody asked. A transport fault is NOT evidence that an agent asked anything.

THE SURFACES ARE ASSERTED TOGETHER BECAUSE EACH ALONE IS SATISFIED BY A BUILD
THAT LOSES THE OTHERS. The clause requires the fault to be legible where each
party actually looks: the `drive` result an operator reads, the dispatch
journal a later reconciliation reads, the `resolve-blocked` valve lane a
console renders, and the item's own DURABLE ledger record. One case carrying
one cause string through all of them is what makes that a claim about
composition rather than four claims about four renderers.

TWO OF THOSE WERE STOOD IN BY SOMETHING THAT COULD NOT FAIL, and the repair is
the reason this module is worth re-reading. The drive assertion was made
against a stand-in supplying EMPTY stderr, so it examined one channel of a
two-channel payload — and the contradiction lived in the other one, where a
detail saying no agent asked anything sat beside a line saying the run was
parked at a human gate. The stderr is now the real one, threaded in from the
dispositions that emit it.

And the "ledger account" was `needs_human_question_summary`, which
RE-INSPECTS FABRO ON DEMAND. That is a rendering, not a record: its answer
lasts exactly as long as the run does, so it reports nothing once the factory
prunes the run, becomes unreachable, or the run is reaped — which is precisely
when an operator is reading the item instead of the run. The durable comment is
asserted as its own fourth surface, read back off the tenant, and the rendering
is kept beside it because the lane is still the right place to SEE this ending.

WHAT IS STOOD IN, AND WHAT IS NOT. Exactly one seam leaves the process: the
`fabro` CLI, at the runner seam the port publishes for it. `run_dispatch`, the
terminal mapper, the JSON emitter the Dispatcher's `--json` mode prints, the
`drive` transport that parses it, the post-run dispositions, the real on-disk
journal, the needs-human question reader and the valve lane are all production
code over the real store/client seam.

THE ASSERTIONS DO NOT KEY ON THE COMMAND SUBSTRING ALONE, which is the trap
this module has to avoid. The engine's cause string QUOTES the backgrounded
command inside its own prose, so a renderer that merely echoed the raw cause
would satisfy "names the backgrounded command" while classifying nothing. Each
surface is therefore asserted on the CLASSIFICATION plus the command named AS a
command.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro._store_dispatch_factory import record_dispatch_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import emit_outcomes
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._drive_impl_dispatch import (
    CommandRun,
    run_impl_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_needs_human_question import (
    needs_human_question_summary,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-qm4luz"
_RUN = "01M44F9E56XCEWZNMVJX4M14Z6"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_TENANT = "livespec-orch-beads-fabro"
_PR_SIGNATURE = "pr|deterministic|acp turn failed"

# The measured cause, sanitized in its tool-call identifier only. Note that the
# COMMAND is quoted inside it: that is why no assertion below is satisfied by
# the command substring on its own.
_COMMAND = "git push -u origin HEAD:refs/heads/feat/bd-ib-qm4luz 2>&1 | tail -100"
_TASK = "b9hp9md1u"
_CAUSE = (
    f"ACP tool call toolu_01SANITIZEDTOOLCALL ({_COMMAND}) continued in background "
    f"as task {_TASK}; Fabro terminated the turn before the agent could start "
    "conflicting work"
)
# What a renderer can only produce by CLASSIFYING the cause.
_FAULT_LABEL = "transport fault (backgrounded-tool)"
_NAMED_COMMAND = f"the backgrounded command was `{_COMMAND}`"
_NAMED_TASK = f"background task {_TASK}"
_NO_QUESTION = "no agent asked anything"

_RUN_STDOUT = f"Run: {_RUN}\n"
_RUN_STDERR = (
    f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/{_RUN}\n"
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run terminated, "
    "work preserved by reference, decision routed to the ledger (blocked / needs-human)\n"
)


def _inspect_payload() -> list[object]:
    """`fabro inspect --json` for the measured run, in its measured shape.

    The cause chain is outermost-first, so the fixed `ACP protocol error`
    wrapper leads and the real fault is the INNERMOST element; the loop
    signature for the terminal node itself rides beside the `pr` one, because
    the terminal is a dead-end script that exits 1 by design.
    """
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed"},
            "checkpoints": [
                {
                    "checkpoint": {
                        "next_node_id": "needs_human",
                        "loop_failure_signatures": {
                            "needs_human|deterministic|script failed": 1,
                            _PR_SIGNATURE: 2,
                        },
                        "node_outcomes": {
                            "pr": {
                                "failure": {
                                    "category": "deterministic",
                                    "signature": _PR_SIGNATURE,
                                    "causes": ["ACP protocol error", _CAUSE],
                                }
                            }
                        },
                    }
                }
            ],
            "nodes": [
                {
                    "id": "needs_human",
                    "output": {"stderr": _RUN_STDERR},
                }
            ],
        }
    ]


@dataclass(kw_only=True)
class _FabroRunner:
    """The ONE seam that leaves the process: the `fabro` CLI."""

    calls: list[list[str]]

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.calls.append(argv)
        if argv[1] == "run":
            return CommandResult(exit_code=1, stdout=_RUN_STDOUT, stderr=_RUN_STDERR)
        return CommandResult(exit_code=0, stdout=json.dumps(_inspect_payload()), stderr="")


def _write_repo(*, root: Path) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": _TENANT,
                        "prefix": "bd-ib",
                        "server_user": _TENANT,
                        "database": _TENANT,
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "default_factory": _FACTORY,
                        "factories": {_FACTORY: {"server": _SERVER}},
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def _seed(*, root: Path) -> WorkItem:
    item = WorkItem(
        id=_ITEM,
        type="bug",
        status="active",
        blocked_reason=None,
        title="The pr stage dies on a backgrounded push",
        description="## Definition of Done\n\n- the publish leg runs without an agent turn.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=store_config(repo=root), item=item)
    return item


def _plan(*, root: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=root,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=root / "workflow.toml",
        goal_file=root / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name=_FACTORY,
        fabro_factory_server=_SERVER,
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=root / ".janitor",
        janitor_core_checkout=root / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


@pytest.fixture
def tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _terminal_outcome(
    *,
    root: Path,
    journal: JournalFile,
    slept: list[float],
) -> DispatchOutcome:
    """The engine's own terminal for the measured run, end to end.

    `slept` records every merge-poll wait the engine asked for, so the caller
    can assert the terminal returned BEFORE the merge-confirmation boundary —
    which is what makes "this run never reached a pull request" an observation
    rather than a consequence of the stand-in answering nothing.
    """
    return run_dispatch(
        plan=_plan(root=root),
        runner=_FabroRunner(calls=[]),
        journal=journal,
        sleep=slept.append,
        poll=PollPolicy(attempts=1, interval_seconds=0.0),
    )


def _drive_report(
    *,
    root: Path,
    outcome: DispatchOutcome,
    dispatcher_stderr: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[str, dict[str, Any], str]:
    """The drive result's status, the dispatch record, and the stderr it carried.

    The bytes the drive transport parses are the ones the Dispatcher's own
    `--json` mode prints for this outcome, so neither renderer is stood in.

    THE STDERR IS THE REAL ONE, threaded in from the dispositions that actually
    emitted it, and that matters because `drive` carries BOTH channels into one
    result. An empty stand-in here would assert only that the `detail` reads
    correctly while leaving the other half of the same payload unexamined —
    which is exactly where the contradiction lived: a detail saying no agent
    asked anything beside a stderr line saying the run was parked at a human
    gate. A proof that cannot see both channels cannot see that at all.
    """
    emit_outcomes(outcomes=[outcome], as_json=True)
    emitted = capsys.readouterr().out

    def _runner(*, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        del cwd
        return CommandRun(argv=argv, returncode=4, stdout=emitted, stderr=dispatcher_stderr)

    result = run_impl_dispatch(
        repo=root,
        work_item_ref=_ITEM,
        runner=_runner,
        dispatcher_bin=root / "dispatcher.py",
        acp_nodes=(),
        workflow_name=None,
        identity=None,
    )
    reported = cast("list[dict[str, Any]]", result["dispatcher"]["stdout_json"])
    return (
        cast("str", result["status"]),
        reported[0],
        cast("str", result["dispatcher"]["stderr"]),
    )


def _run_dispositions(
    *,
    root: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[dict[str, Any]], str]:
    """The real post-run dispositions: their `outcome` records AND their stderr.

    Both halves come from ONE execution, which is what makes the two surfaces
    below a claim about composition. The stderr is the Dispatcher's own, written
    by the escalation this sequence calls, and it is returned rather than
    discarded so the drive assertion can be made against the bytes a real
    dispatch would hand it.
    """
    _ = post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=root,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=100,
        token_supplier=lambda: "token",
    )
    emitted_stderr = capsys.readouterr().err
    lines = journal.path.read_text(encoding="utf-8").splitlines()
    records = [cast("dict[str, Any]", json.loads(line)) for line in lines if line]
    return (
        [
            cast("dict[str, Any]", record["outcome"])
            for record in records
            if record.get("stage") == "outcome"
        ],
        emitted_stderr,
    )


def _durable_record(*, root: Path) -> str:
    """The causal record as it RESTS on the item, read back off the tenant.

    This is the surface the clause names, and it is deliberately not the
    attention rendering asserted below it: the rendering re-inspects Fabro on
    demand, so it answers only while the run record survives, whereas this
    comment is what an operator finds after the run is pruned or reaped. The
    read goes through `read_work_item_comments`, which indexes the beads-native
    `text` key — `bd show --json` carries no comment bodies at all, so a check
    that reached for the item record instead would report this write as lost.
    """
    bodies = [
        comment.text
        for comment in read_work_item_comments(path=store_config(repo=root), work_item_id=_ITEM)
        if NEEDS_HUMAN_CAUSE_MARKER in comment.text
    ]
    assert len(bodies) == 1
    return bodies[0]


def _ledger_account(*, root: Path) -> str:
    """The item's own ledger account: its `resolve-blocked` valve lane.

    The run is stamped onto the item through the production writer, so the lane
    resolves the factory the way it does in production rather than being handed
    one.
    """
    record_dispatch_run(
        path=store_config(repo=root),
        work_item_id=_ITEM,
        run_id=_RUN,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )
    return needs_human_question_summary(
        project_root=root,
        item_id=_ITEM,
        default_summary=f"Resolve human-needed block for work-item {_ITEM}",
        runner=_FabroRunner(calls=[]),
    )


def test_a_backgrounded_tool_fault_is_a_transport_fault_on_every_surface(
    tmp_path: Path,
    tenant: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Read the module docstring for why the four surfaces are one case."""
    del tenant
    _write_repo(root=tmp_path)
    item = _seed(root=tmp_path)
    journal = JournalFile(path=tmp_path / "dispatch-journal.jsonl")
    slept: list[float] = []

    outcome = _terminal_outcome(root=tmp_path, journal=journal, slept=slept)

    assert (outcome.status, outcome.stage, outcome.fabro_run_id) == ("blocked", "fabro-run", _RUN)
    assert outcome.fabro_failure_cause == _CAUSE
    assert outcome.fabro_failure_category == "deterministic"
    # The terminal returned before the merge-confirmation boundary, so nothing
    # below is an artefact of a stand-in that declined to answer a pull-request
    # query it was never asked.
    assert slept == []

    # The dispositions run FIRST, because they are what emits the dispatcher's
    # stderr and what writes the durable record — so surfaces 1, 2 and 4 below
    # are all read from the artefacts of one execution rather than from three.
    journaled, dispatcher_stderr = _run_dispositions(
        root=tmp_path, item=item, outcome=outcome, journal=journal, capsys=capsys
    )

    _assert_drive_surface(
        root=tmp_path, outcome=outcome, dispatcher_stderr=dispatcher_stderr, capsys=capsys
    )
    _assert_journal_surface(journaled=journaled)
    _assert_attention_surface(root=tmp_path)
    _assert_durable_surface(root=tmp_path)


def _assert_drive_surface(
    *,
    root: Path,
    outcome: DispatchOutcome,
    dispatcher_stderr: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SURFACE 1 — the `drive` result, on BOTH of the channels it carries."""
    status, record, carried_stderr = _drive_report(
        root=root, outcome=outcome, dispatcher_stderr=dispatcher_stderr, capsys=capsys
    )
    drive_detail = cast("str", record["detail"])
    assert status == "blocked"
    assert _FAULT_LABEL in drive_detail
    assert _NAMED_COMMAND in drive_detail
    assert _NAMED_TASK in drive_detail
    assert _NO_QUESTION in drive_detail
    assert record["fabro_failure_cause"] == _CAUSE
    # The stderr the SAME result carries must not contradict the detail beside
    # it. The gate wording is the specific thing asserted absent, because it is
    # the half that named an action and so the half an operator acted on. The
    # non-empty check comes first: every assertion below it is vacuously true
    # of an empty string, which is exactly what the old stand-in supplied.
    assert carried_stderr != ""
    assert "parked at a Fabro human gate" not in carried_stderr
    assert "no answer is owed" in carried_stderr
    assert f"resolve-blocked:{_ITEM}:ready" in carried_stderr


def _assert_journal_surface(*, journaled: list[dict[str, Any]]) -> None:
    """SURFACE 2 — the dispatch journal a later reconciliation reads."""
    assert len(journaled) == 1
    journal_detail = cast("str", journaled[0]["detail"])
    assert _FAULT_LABEL in journal_detail
    assert _NAMED_COMMAND in journal_detail
    assert journaled[0]["fabro_failure_signature"] == _PR_SIGNATURE
    assert journaled[0]["needs_human_kind"] == "stage-failure"
    assert journaled[0]["needs_human_stages"] == ["pr"]


def _assert_attention_surface(*, root: Path) -> None:
    """SURFACE 3 — the attention rendering, retained beside the durable record."""
    summary = _ledger_account(root=root)
    assert _FAULT_LABEL in summary
    assert _NAMED_COMMAND in summary
    assert f"resolve-blocked:{_ITEM}:ready" in summary


def _assert_durable_surface(*, root: Path) -> None:
    """SURFACE 4 — the item's own DURABLE record, the one that outlives the run.

    This is the surface the clause names. Each line is asserted by its LABEL
    rather than by containment of the value alone, because the quoted cause
    already contains the command and the signature already contains the stage —
    so a record that merely echoed the cause would satisfy a bare `in` check
    for both while classifying and attributing nothing.
    """
    durable = _durable_record(root=root)
    assert "failed stage: pr" in durable
    assert "transport fault: backgrounded-tool" in durable
    assert f"backgrounded command: {_COMMAND}" in durable
    assert f"backgrounded task: {_TASK}" in durable
    assert f"failure signature: {_PR_SIGNATURE}" in durable
    assert "no answer is owed" in durable
    assert f"resolve-blocked:{_ITEM}:ready" in durable
