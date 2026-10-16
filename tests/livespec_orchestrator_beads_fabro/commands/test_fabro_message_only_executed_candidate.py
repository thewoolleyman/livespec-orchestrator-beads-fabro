"""A message-only failure is classified from its text and attributed from what ran.

Scenario 65's outline grades `claude-acp` with "only the message text "You've
hit your usage limit" and no structured payload" as `anthropic`. That row is
the Petri-era shape: MEASURED on v0.378.0-nightly.0, the record's failure block
is `{reason, detail: {message, category}}` with no `causes`, no `signature` and
no provider `data` object, so the sentence is the only evidence of the ceiling
and nothing in the block says whose it was.

THE BLOCK IS RUN-LEVEL ON THAT ENGINE, which is what makes the node reading
load-bearing rather than incidental. The pinned engine hangs its failure off
`checkpoint.node_outcomes.<node>`, so the block's own position names the
attempt; the Petri record carries ONE `conclusion.failure` and keys its
per-stage results separately, under `stages`, as `<ordinal>-<node>@<visit>`.
So the failing node has to come from that stage map, and the label it selects
is keyed on the graph node id alone — `implement`, not `002-implement@1`.

THE LIST-SHAPED CONTROL IS THE HONEST HALF. The same engine has also been
measured answering `stages` as a LIST OF KEYS carrying no per-stage state at
all (`tests/.../test_fabro_port_petri_payloads.py`). Nothing in that record
says which stage failed, so no identity can be established from it and the
v107 cause-text attribution stands — which is the right answer for a record
that cannot be read, and is asserted so a later reader does not mistake the
degradation for a defect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach import inspect_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_fabro_reattach import Journal

_RUN_ID = "01M4Y7EJWTQWK5CWWS0NKDHY7T"
# The sentence BOTH vendors emit, as the Petri block preserves it: the whole
# structured payload is gone, so there is no vendor marker and no reset instant.
_SHARED_SENTENCE = "the agent answered `session/prompt` with an error: You've hit your usage limit"
_ANTHROPIC_CANDIDATE = "builtin-anthropic-9f2c1d0b4e5a6f78"


@dataclass(kw_only=True)
class _SubcommandRunner:
    """A runner keyed on the fabro subcommand rather than on call order."""

    replies: dict[str, CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return self.replies[argv[1]]


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-zvnpfo",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
    )


def _petri_inspect_stdout(*, stages: object) -> str:
    """A terminated Petri record: one run-level failure, per-stage results apart.

    The checkpoint carries `current_node` and no next node — the terminated
    shape — and records no `node_outcomes` at all, which is why the failing
    attempt can only be read out of `stages`.
    """
    return json.dumps(
        [
            {
                "run_id": _RUN_ID,
                "parent_id": None,
                "status": {"kind": "failed", "reason": "workflow_error"},
                "stages": stages,
                "checkpoint": {
                    "current_node": "needs_human",
                    "next_node_id": None,
                    "git_commit_sha": "9bcd4faa2e3c4d5f6071829304a5b6c7d8e9f012",
                    "timestamp": "2026-10-15T12:36:11.004213877Z",
                },
                "conclusion": {
                    "status": "failed",
                    "timestamp": "2026-10-15T12:36:11.004213877Z",
                    "failure": {
                        "reason": "workflow_error",
                        "detail": {
                            "message": _SHARED_SENTENCE,
                            "category": "transient_infra",
                        },
                    },
                },
            }
        ]
    )


_STAGE_MAP: dict[str, object] = {
    "001-start@1": {"handler": "script", "state": "succeeded"},
    "002-implement@1": {"handler": "acp", "state": "failed"},
}
_STAGE_LIST: list[str] = ["001-start@1", "002-implement@1"]

_PS_STDOUT = json.dumps(
    [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "failed"},
            "total_usd_micros": None,
            "labels": {
                "livespec.acp.implement.availability": "anthropic",
                "livespec.acp.implement.candidate": _ANTHROPIC_CANDIDATE,
            },
        }
    ]
)


def _observed(*, repo: Path, stages: object) -> object:
    runner = _SubcommandRunner(
        replies={
            "inspect": CommandResult(
                exit_code=0, stdout=_petri_inspect_stdout(stages=stages), stderr=""
            ),
            "ps": CommandResult(exit_code=0, stdout=_PS_STDOUT, stderr=""),
            # Every case here observes a FAILED run, which also spends the
            # terminal event-stream read that recovers a needs-human
            # terminal's emitted preservation sentinel.
            "events": CommandResult(exit_code=0, stdout="[]", stderr=""),
        }
    )
    return inspect_run(plan=_plan(repo=repo), runner=runner, journal=Journal(), run_id=_RUN_ID)


def test_a_message_only_ceiling_is_attributed_to_its_executed_candidate(*, tmp_path: Path) -> None:
    """The text classifies the ceiling; the stage map's node attributes it."""
    observed = _observed(repo=tmp_path, stages=_STAGE_MAP)

    assert observed is not None
    assert observed.failure is not None
    assert observed.failure.cause == _SHARED_SENTENCE
    assert observed.failure.signature is None
    assert observed.failure.category == "deterministic"
    assert observed.failure.provider_usage_limit is True
    assert observed.failure.provider_usage_limit_provider == "anthropic"
    assert observed.failure.provider_usage_limit_entitlement == _ANTHROPIC_CANDIDATE


def test_a_record_naming_no_failed_stage_keeps_the_v107_attribution(*, tmp_path: Path) -> None:
    """CONTROL: an unreadable failing attempt establishes no identity.

    The list-shaped `stages` carries no per-stage state, so which attempt
    failed is not a question this record can answer — and the conservative
    legacy attribution is the honest answer rather than a guess at the one
    node that happens to be an ACP node.
    """
    observed = _observed(repo=tmp_path, stages=_STAGE_LIST)

    assert observed is not None
    assert observed.failure is not None
    assert observed.failure.provider_usage_limit is True
    assert observed.failure.provider_usage_limit_provider == "codex"
    assert observed.failure.provider_usage_limit_entitlement is None
