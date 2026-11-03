"""A provider error recorded as an ACP success keeps its provider cause.

Fabro can record an ACP prompt as succeeded even when the response ends in a
provider's structured error. When the later dead-implementer breaker sees the
unchanged tree, the Dispatcher must retain the provider refusal rather than
claiming that the work-item itself was defective.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroTarget,
)

_RUN = "01M592CTREYPGA1GZNPND1TXAY"
_MODEL = "gpt-6-sol"
_ADAPTER = 'CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-6-sol"}\' codex-acp'
_MESSAGE = "The 'gpt-6-sol' model is not supported when using Codex with a ChatGPT account."
_REFUSAL = json.dumps(
    {
        "type": "error",
        "status": 400,
        "error": {"type": "invalid_request_error", "message": _MESSAGE},
    }
)
_TERMINAL = f"{NEEDS_HUMAN_MARKER}: implementer made no changes; run terminated"
_DEAD_IMPLEMENTER = "LIVESPEC_DEAD_IMPLEMENTER: unchanged tree after implementer"


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


def _payload() -> list[dict[str, Any]]:
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": {
                "implement@1": {
                    "handler": "agent",
                    "state": "succeeded",
                    "response": f"Warning: unknown model metadata\n{_REFUSAL}",
                    "output": "",
                },
                "implementation_diff@1": {
                    "handler": "command",
                    "state": "failed",
                    "output": _DEAD_IMPLEMENTER,
                },
                "needs_human@1": {
                    "handler": "command",
                    "state": "failed",
                    "output": _TERMINAL,
                },
            },
            "checkpoint": {
                "current_node": "needs_human",
                "node_outcomes": {
                    "implement@1": {"status": "succeeded"},
                    "implementation_diff@1": {"status": "failed"},
                },
            },
            "conclusion": {
                "status": "failed",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {"message": f"{_DEAD_IMPLEMENTER}\n{_TERMINAL}"},
                },
            },
        }
    ]


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-piclal",
        branch="feat/bd-ib-piclal",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
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
            nodes={},
            inputs={},
            run_inputs=(f"implement_adapter={_ADAPTER}",),
            candidates={},
        ),
    )


def _inspect(*, tmp_path: Path) -> FabroInspectResult:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=_Runner(stdout=json.dumps(_payload())),
        cwd=tmp_path,
    ).inspect(run_id=_RUN, timeout_seconds=1)


def test_a_dead_implementer_after_a_succeeded_provider_error_surfaces_the_refusal(
    tmp_path: Path,
) -> None:
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=_inspect(tmp_path=tmp_path),
        exit_code=1,
        stderr="",
    )

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.dead_implementer_condition is None
    assert outcome.provider_refusal is not None
    assert outcome.provider_refusal.message == _MESSAGE
    assert outcome.provider_refusal.model == _MODEL
    assert outcome.provider_refusal.adapter == "codex-acp"
    assert outcome.provider_usage_limit is False
