"""A Petri-era needs-human ending is released on the ROUTING stage's failure.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-3jboeo`,
Scenario 127): a run that terminates "through any terminal, the workflow's
`needs_human` terminal included" is released when "the failing node's recorded
failure" classifies as an eligible cause.

THE FIXTURE IS THE MEASURED ENDING, trimmed from the `fabro inspect --json`
record of livespec-dev-tooling-ebtm6t run 01M5RAS2EAWGNDF0YK1Q9MC9AX (petri,
2026-10-25). On the Petri-era engine the run CONCLUSION carries the terminal
SCRIPT's own deliberate exit ("script exited with status 1" plus the
needs-human sentinels) and NO provider sentence; the session-limit refusal
lives ONLY in the failing node's stage output, as the adapter's JSON-RPC error.
The release used to grade the conclusion, so it returned nothing and the item
rested at `blocked / needs-human` with `provider_usage_limit: true` on the very
same outcome row -- the needs-human mapper re-read the routing stage while the
release, which runs first, did not.

The pinned-engine shape, where the provider sentence sits in the conclusion,
is covered by `test_dispatcher_provider_limit_terminal_outcome.py`; this file
is its Petri-era counterpart, and the unclassifiable control keeps the human
route for a routing stage that recorded an ordinary gate failure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroTarget,
)

_RUN = "01M5RAS2EAWGNDF0YK1Q9MC9AX"
_PRESERVED_REF = "refs/heads/needs-human/98d4e9e97e2a487e80a3fb73745fd7b3"
_TERMINAL_EXIT = (
    "script exited with status 1\n"
    f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_PRESERVED_REF}\n"
    "LIVESPEC_NEEDS_HUMAN: loop cannot auto-resolve this work-item; run terminated, "
    "work preserved by reference, decision routed to the ledger (blocked / needs-human)"
)
# The adapter's own JSON-RPC refusal, verbatim from the run's stage output.
_SESSION_LIMIT_OUTPUT = (
    "Error handling request {\n  jsonrpc: '2.0',\n  id: 3,\n  method: 'session/prompt',\n"
    "  params: {\n    sessionId: '87f76590-fd58-4e2f-a2a4-84fb6d1c9aaf',\n"
    "    prompt: [ [Object] ]\n  }\n} {\n  code: -32603,\n"
    '  message: "Internal error: You\'ve hit your session limit · resets 3:40am (UTC)",\n'
    "  data: { errorKind: 'rate_limit' }\n}"
)
_GATE_FAILURE_OUTPUT = (
    "just check: 2 targets failed: check-per-file-coverage, check-coverage\n"
    "error: Recipe `check` failed with exit code 1"
)

_AVAILABILITY_KEY = "anthropic-team"
_CANDIDATE_KEY = "claude-primary"
_IDENTITY = AcpCandidateIdentity(
    display_name="Claude ACP primary",
    candidate_key=_CANDIDATE_KEY,
    availability_key=_AVAILABILITY_KEY,
)
_DECLARED_QUOTA = {
    "source": "protocol.message",
    "cause": "quota",
    "scope": "availability-domain",
    "all_literals": ["hit your session limit"],
}


def _petri_payload(*, implement_output: str) -> list[dict[str, Any]]:
    """One Petri-era run whose implement node failed and was routed to needs_human."""
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "checkpoint": {
                "current_node": "needs_human",
                "git_commit_sha": "0" * 40,
                "timestamp": "2026-10-25T02:10:40Z",
            },
            "conclusion": {
                "status": "failed",
                "timestamp": "2026-10-25T02:10:44Z",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {"message": _TERMINAL_EXIT, "category": "deterministic"},
                },
            },
            "stages": {
                "implement@1": {
                    "handler": "agent",
                    "state": "failed",
                    "output": implement_output,
                },
                "needs_human@1": {
                    "handler": "command",
                    "state": "failed",
                    "output": _TERMINAL_EXIT,
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


def _inspect(*, tmp_path: Path, implement_output: str) -> FabroInspectResult:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=_Runner(stdout=json.dumps(_petri_payload(implement_output=implement_output))),
        cwd=tmp_path,
    ).inspect(run_id=_RUN, timeout_seconds=1)


def _write_repo(*, repo: Path) -> None:
    """A repository whose `implement` node declares the candidate that ran."""
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n\n'
        "[run.inputs]\nimplement_adapter = 'claude-code-acp'\n",
        encoding="utf-8",
    )
    (workflow / "workflow.fabro").write_text(
        'digraph ImplementWorkItem {\n    implement [\n        timeout="60s"\n    ]\n}\n',
        encoding="utf-8",
    )
    entry: dict[str, object] = {
        "command": "claude-code-acp",
        "display_name": _IDENTITY.display_name,
        "candidate_key": _CANDIDATE_KEY,
        "availability_key": _AVAILABILITY_KEY,
        "availability_signatures": [_DECLARED_QUOTA],
    }
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"acp_nodes": {"implement": entry}}
                }
            }
        ),
        encoding="utf-8",
    )


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="livespec-dev-tooling-ebtm6t",
        branch="feat/livespec-dev-tooling-ebtm6t",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="petri",
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
            nodes={}, inputs={}, run_inputs=(), candidates={"implement": _IDENTITY}
        ),
    )


def _outcome(*, tmp_path: Path, implement_output: str) -> DispatchOutcome | None:
    return fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=_inspect(tmp_path=tmp_path, implement_output=implement_output),
        exit_code=1,
        stderr="",
    )


def test_a_session_limit_recorded_only_on_the_routing_stage_is_released(
    tmp_path: Path,
) -> None:
    """The measured ebtm6t ending releases instead of resting blocked."""
    _write_repo(repo=tmp_path)

    outcome = _outcome(tmp_path=tmp_path, implement_output=_SESSION_LIMIT_OUTPUT)

    assert outcome is not None
    assert outcome.stage == "provider-limit-release"
    assert outcome.status != "blocked"
    release = outcome.provider_limit_release
    assert release is not None
    assert release.node_attempt == "implement"
    assert release.executed == _IDENTITY
    assert release.matched is not None
    assert release.matched.cause == "quota"
    assert release.matched.hold_key == _AVAILABILITY_KEY
    assert _PRESERVED_REF in release.recovery_source
    # The outcome carries the ROUTING stage's failure, so the provider fields
    # `record_provider_exhaustion_if_observed` keys on are present.
    assert outcome.provider_usage_limit is True
    assert outcome.provider_usage_limit_provider == "anthropic"
    assert outcome.fabro_failure_cause is not None
    assert "hit your session limit" in outcome.fabro_failure_cause


def test_a_routing_stage_gate_failure_still_rests_at_blocked_needs_human(
    tmp_path: Path,
) -> None:
    """The control: an ordinary gate failure on the routing stage keeps the human route."""
    _write_repo(repo=tmp_path)

    outcome = _outcome(tmp_path=tmp_path, implement_output=_GATE_FAILURE_OUTPUT)

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.stage == "fabro-run"
    assert outcome.provider_limit_release is None
