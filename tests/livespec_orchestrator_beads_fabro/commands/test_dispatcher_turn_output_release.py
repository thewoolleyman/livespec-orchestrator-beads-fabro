"""A provider refusal booked as a successful turn is released, not left for a human.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "A provider refusal booked as a successful turn is a failed
attempt" (Scenario 209). An agent node attempt the engine recorded as succeeded
whose output ends with a measured refusal is a FAILED attempt of its candidate.
It is the failing node attempt for the provider-limit release "ONLY when it is
the unrecovered failure responsible for the run's terminal disposition": the run
reached the needs_human terminal through that attempt's own outcome and no later
attempt of any node failed. When a later failure determined the terminal instead,
that failure keeps its own route, and the reclassified attempt still mints its
candidate hold.

THE FIXTURE IS THE MEASURED INCIDENT. Run 01M5C0FBAE8FVZK15XN9WHVM6H of
`bd-ib-davaxq` recorded `review@1` as succeeded with an output ending in the
capacity refusal, with the refusal following the preceding period with no space,
and routed to needs_human through the unmatched review outcome edge. The
candidate is declared in `.livespec.jsonc` with the `turn.final_output` form so
that the operator-declared route is exercised through the same resolution a
dispatch takes; the built-in form is covered by the matching module.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    parse_availability_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
    classified_release,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records import (
    provider_limit_release_record,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail
from livespec_orchestrator_beads_fabro.types import WorkItem

# Reached through the module object so the file collects before the disposition
# exists: a top-level import of an absent name would die at collection and prove
# only that the name is absent.
_DISPOSITION = importlib.import_module(
    "livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_disposition"
)

_RUN = "01M5C0FBAE8FVZK15XN9WHVM6H"
_NOW = "2026-10-20T06:41:00Z"
_REFUSAL = "Selected model is at capacity. Please try a different model."
_INCIDENT_OUTPUT = (
    "I'm reviewing the branch and its latest captured proof against the six stated "
    "acceptance assertions. I'll make no changes.Selected model is at capacity. "
    "Please try a different model."
)
_PRESERVED = f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/{_RUN}"
_TERMINAL_OUTPUT = f"{_PRESERVED}\n{NEEDS_HUMAN_MARKER}: run terminated\n"
_IDENTITY = AcpCandidateIdentity(
    display_name="Codex ACP fallback",
    candidate_key="codex-review",
    availability_key="codex-team",
)
_DECLARED_CAPACITY = {
    "source": "turn.final_output",
    "cause": "provider_capacity",
    "scope": "candidate",
    "final_text": _REFUSAL,
}


def _stage(*, state: str, handler: str, output: str) -> dict[str, object]:
    return {"handler": handler, "state": state, "response": "", "output": output}


def _payload(*, stages: dict[str, object]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": stages,
            "checkpoint": {
                "timestamp": "2026-10-20T06:40:00.000Z",
                "current_node": "needs_human",
                "git_commit_sha": "c4bfd246fdd84f46ea13e1a4100c1adb4189cd6a",
            },
            "conclusion": {
                "status": "failed",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {
                        "message": f"script exited with status 1\n{_TERMINAL_OUTPUT}",
                        "category": "deterministic",
                    },
                },
            },
        }
    ]


@dataclass(kw_only=True)
class _Runner:
    stdout: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _inspect(*, tmp_path: Path, stages: dict[str, object]) -> FabroInspectResult:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=_Runner(stdout=json.dumps(_payload(stages=stages))),
        cwd=tmp_path,
    ).inspect(run_id=_RUN, timeout_seconds=1)


def _write_repo(*, repo: Path) -> None:
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n\n'
        "[run.inputs]\nreview_adapter = 'codex-acp'\n",
        encoding="utf-8",
    )
    (workflow / "workflow.fabro").write_text(
        'digraph ImplementWorkItem {\n    review [\n        timeout="60s"\n    ]\n}\n',
        encoding="utf-8",
    )
    entry = {
        "command": "codex-acp",
        "display_name": _IDENTITY.display_name,
        "candidate_key": _IDENTITY.candidate_key,
        "availability_key": _IDENTITY.availability_key,
        "availability_signatures": [_DECLARED_CAPACITY],
    }
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes": {"review": entry}}}}
        ),
        encoding="utf-8",
    )


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-davaxq",
        branch="feat/bd-ib-davaxq",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="gmktec",
        fabro_factory_server=None,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
        acp_nodes=AcpNodeResolution(
            nodes={}, inputs={}, run_inputs=(), candidates={"review": _IDENTITY}
        ),
    )


def _terminal(*, tmp_path: Path, stages: dict[str, object]) -> DispatchOutcome | None:
    _write_repo(repo=tmp_path)
    return fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=_inspect(tmp_path=tmp_path, stages=stages),
        exit_code=1,
        stderr="",
    )


def _needs_human_stages(*, review_output: str, review_handler: str = "agent") -> dict[str, object]:
    return {
        "implement@1": _stage(state="succeeded", handler="agent", output="Implemented."),
        "review@1": _stage(state="succeeded", handler=review_handler, output=review_output),
        "needs_human@1": _stage(state="failed", handler="command", output=_TERMINAL_OUTPUT),
    }


def _rendered() -> RenderedCandidate:
    parsed = parse_availability_signatures(value=[_DECLARED_CAPACITY], key="probe")
    assert not isinstance(parsed, str), parsed
    return RenderedCandidate(
        candidate=AcpCandidate(
            adapter=AcpAdapter(command="codex-acp", args=(), env={}),
            identity=_IDENTITY,
            signatures=parsed,
        ),
        builtin=False,
    )


def _release(*, output: str | None) -> ProviderLimitRelease | None:
    return classified_release(
        failure=FabroFailureDetail(
            cause=None,
            category=None,
            signature="review|succeeded",
            succeeded_turn_output=output,
        ),
        rendered=_rendered(),
        node_attempt="review",
        factory="gmktec",
        run_id=_RUN,
        recovery_source=f"the tree was preserved on refs/heads/needs-human/{_RUN}",
    )


def test_a_reclassified_review_turn_yields_a_release_naming_the_final_output_source() -> None:
    release = _release(output=_INCIDENT_OUTPUT)
    assert isinstance(release, ProviderLimitRelease)
    assert release.source == "turn.final_output"
    assert release.matched is not None
    assert release.matched.cause == "provider_capacity"
    assert release.matched.scope == "candidate"
    assert release.matched.candidate_key == "codex-review"
    assert release.executed == _IDENTITY
    assert release.legacy_provider is None
    assert release.release_key == f"gmktec:{_RUN}:review"
    record = provider_limit_release_record(release=release, work_item_id="bd-ib-davaxq")
    assert record["source"] == "turn.final_output"
    assert record["cause"] == "provider_capacity"


def test_a_succeeded_turn_that_is_not_a_refusal_yields_no_release() -> None:
    assert _release(output="Looks good.\npreferred_label: approve") is None
    assert _release(output=None) is None


def test_a_needs_human_run_through_a_reclassified_review_turn_is_released(
    tmp_path: Path,
) -> None:
    outcome = _terminal(
        tmp_path=tmp_path, stages=_needs_human_stages(review_output=_INCIDENT_OUTPUT)
    )

    assert outcome is not None
    assert outcome.stage == "provider-limit-release"
    assert outcome.status != "blocked"
    release = outcome.provider_limit_release
    assert release is not None
    assert release.source == "turn.final_output"
    assert release.node_attempt == "review"
    assert release.release_key == f"gmktec:{_RUN}:review"
    assert f"refs/heads/needs-human/{_RUN}" in release.recovery_source


def test_a_review_turn_that_continues_past_the_refusal_keeps_the_human_route(
    tmp_path: Path,
) -> None:
    output = f"{_REFUSAL} The review verdict follows.\npreferred_label: reject"
    outcome = _terminal(tmp_path=tmp_path, stages=_needs_human_stages(review_output=output))

    assert outcome is not None
    assert outcome.stage != "provider-limit-release"
    assert outcome.provider_limit_release is None
    assert not outcome.reclassified_turns


def test_a_command_node_is_not_an_agent_turn_and_is_never_reclassified(tmp_path: Path) -> None:
    stages = _needs_human_stages(review_output=_INCIDENT_OUTPUT, review_handler="command")
    outcome = _terminal(tmp_path=tmp_path, stages=stages)

    assert outcome is not None
    assert outcome.provider_limit_release is None
    assert not outcome.reclassified_turns


def test_a_later_test_failure_keeps_its_route_and_the_reclassified_turn_keeps_its_hold(
    tmp_path: Path,
) -> None:
    stages: dict[str, object] = {
        "review@1": _stage(state="succeeded", handler="agent", output=_INCIDENT_OUTPUT),
        "janitor@1": _stage(state="failed", handler="command", output="FAILED tests/test_x.py"),
        "needs_human@1": _stage(state="failed", handler="command", output=_TERMINAL_OUTPUT),
    }
    outcome = _terminal(tmp_path=tmp_path, stages=stages)

    assert outcome is not None
    assert outcome.stage != "provider-limit-release"
    assert outcome.provider_limit_release is None
    turns = outcome.reclassified_turns
    assert turns is not None
    assert len(turns) == 1
    assert turns[0].node_attempt == "review"
    assert turns[0].matched.cause == "provider_capacity"
    assert turns[0].matched.candidate_key == "codex-review"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-davaxq",
        type="task",
        status="active",
        title="A slice whose review turn was refused",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The slice is verified green.",
    )


def _hold_records(*, journal: JournalFile) -> list[dict[str, object]]:
    lines = journal.path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    return [record for record in records if record.get("stage") == "acp-availability-observed"]


def test_a_reclassified_turn_that_did_not_end_the_run_still_records_its_candidate_hold(
    tmp_path: Path,
) -> None:
    stages: dict[str, object] = {
        "review@1": _stage(state="succeeded", handler="agent", output=_INCIDENT_OUTPUT),
        "janitor@1": _stage(state="failed", handler="command", output="FAILED tests/test_x.py"),
        "needs_human@1": _stage(state="failed", handler="command", output=_TERMINAL_OUTPUT),
    }
    outcome = _terminal(tmp_path=tmp_path, stages=stages)
    assert outcome is not None
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.path.write_text("", encoding="utf-8")

    for _ in range(2):
        _DISPOSITION.dispose_reclassified_turn_holds(
            repo=tmp_path, item=_item(), outcome=outcome, journal=journal, now_iso=_NOW
        )

    holds = _hold_records(journal=journal)
    assert len(holds) == 1
    assert holds[0]["scope"] == "candidate"
    assert holds[0]["hold_key"] == "codex-team"
    assert holds[0]["candidate_key"] == "codex-review"
    assert holds[0]["cause"] == "provider_capacity"
    assert holds[0]["expires_at"] == "2026-10-20T06:56:00Z"


def test_an_outcome_with_no_reclassified_turn_records_no_hold(tmp_path: Path) -> None:
    outcome = replace(
        DispatchOutcome(
            work_item_id="bd-ib-davaxq",
            status="failed",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="",
        ),
        reclassified_turns=None,
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.path.write_text("", encoding="utf-8")

    _DISPOSITION.dispose_reclassified_turn_holds(
        repo=tmp_path, item=_item(), outcome=outcome, journal=journal, now_iso=_NOW
    )

    assert _hold_records(journal=journal) == []
