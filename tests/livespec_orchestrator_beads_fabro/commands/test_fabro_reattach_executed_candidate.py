"""The run observation attributes a ceiling from the factory's own labels.

Scenario 65's "A shared provider sentence is attributed to the candidate that
ran": a `claude-acp` attempt whose recorded failure carries only "You've hit
your usage limit" is `anthropic`, not `codex`. The attribution needs an input
the failure block does not carry, so this is the case that decides whether the
reading is WIRED or merely available.

WHY THE RUN ROW AND NOT THE INSPECT PAYLOAD. MEASURED on both engines, an
`inspect --json` record carries no `labels` key: the pinned build's response
holds `run_id`, `status` and `checkpoint` (the committed native fixtures at
`tests/fixtures/fabro_native_inspect/`), and the candidate build's holds
`checkpoint, conclusion, parent_id, run_id, run_spec, sandbox, stages,
start_record, status` (`plan/fabro-currency/research/
006-hp-candidate-first-measurements-2026-10-08.md`). The labels live on the
`ps --json` row, which the same note measures carrying them. So the
attribution costs a SECOND read, and these cases assert both halves of what
that read must be: aimed at the right run, and taken only when it can change
an answer.

THE SECOND RUN ROW IS THE LOAD-BEARING FIXTURE. A factory serves every
repository on the host — 1626 rows measured on `hp` — so a reader that took
the first row's labels, or merged every row's, would produce a perfectly
well-formed attribution belonging to somebody else's dispatch. Its labels are
deliberately the OTHER vendor's, so that misreading fails here instead of
passing with the right answer by luck.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach import inspect_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_fabro_reattach import Journal

_RUN_ID = "01M4J5M63APH75NJ1JF7ZCN9DY"
_OTHER_RUN_ID = "01M4EZ7CGACPQ4WQ7NTRXTTWCM"
_ACP_WRAPPER = "ACP protocol error"
# The sentence BOTH vendors emit, carrying no reset instant and no vendor
# marker, so the cause text offers nothing about whose allowance was spent.
_SHARED_SENTENCE = "the agent answered `session/prompt` with an error: You've hit your usage limit"
_ORDINARY_FAULT = "connection reset by peer"
_ANTHROPIC_CANDIDATE = "builtin-anthropic-9f2c1d0b4e5a6f78"


@dataclass(kw_only=True)
class ArgvRunner:
    """A runner keyed on the fabro SUBCOMMAND rather than on call order.

    Keying on the subcommand is what lets a case assert that the labels read
    did not happen at all: a reply list would make its absence look like an
    unconsumed element, which is also what a reordered pair looks like.
    """

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


def _inspect_stdout(*, cause: str) -> str:
    """The pinned engine's terminated `inspect` response, one failed node.

    The shape is the committed native fixture's: a checkpoint sitting AT the
    needs-human terminal with no next node, the failing node's own outcome
    block, and the terminal's own failure beside it — which is why the reader
    has to exclude the terminal rather than take the first failed entry.
    """
    return json.dumps(
        [
            {
                "run_id": _RUN_ID,
                "status": {"kind": "failed"},
                "checkpoint": {
                    "current_node": "needs_human",
                    "next_node_id": None,
                    "completed_nodes": ["setup", "dod_gate", "implement"],
                    "loop_failure_signatures": {"needs_human|deterministic|script failed": 1},
                    "node_outcomes": {
                        "implement": {
                            "status": "failed",
                            "failure": {
                                "category": "transient_infra",
                                "signature": "implement|transient_infra|acp turn failed",
                                "causes": [_ACP_WRAPPER, cause],
                            },
                        },
                        "needs_human": {
                            "status": "failed",
                            "failure": {
                                "category": "deterministic",
                                "signature": "needs_human|deterministic|script failed",
                                "causes": ["stage needs_human failed with no outgoing fail edge"],
                            },
                        },
                    },
                },
            }
        ]
    )


_PS_STDOUT = json.dumps(
    [
        {
            "run_id": _OTHER_RUN_ID,
            "status": {"kind": "failed"},
            "total_usd_micros": None,
            "labels": {
                "livespec.repository": "livespec-overseer",
                "livespec.acp.implement.availability": "codex",
                "livespec.acp.implement.candidate": "builtin-codex-1a2b3c4d5e6f7081",
            },
        },
        {
            "run_id": _RUN_ID,
            "status": {"kind": "failed"},
            "total_usd_micros": None,
            "labels": {
                "livespec.repository": "livespec-orchestrator-beads-fabro",
                "livespec.acp.implement.availability": "anthropic",
                "livespec.acp.implement.candidate": _ANTHROPIC_CANDIDATE,
            },
        },
    ]
)


def test_a_shared_sentence_is_attributed_to_the_claude_candidate_that_ran(
    *, tmp_path: Path
) -> None:
    """The failing node's recorded entitlement decides, not the sentence."""
    runner = ArgvRunner(
        replies={
            "inspect": CommandResult(
                exit_code=0, stdout=_inspect_stdout(cause=_SHARED_SENTENCE), stderr=""
            ),
            "ps": CommandResult(exit_code=0, stdout=_PS_STDOUT, stderr=""),
            "events": CommandResult(exit_code=0, stdout="[]", stderr=""),
        }
    )

    observed = inspect_run(
        plan=_plan(repo=tmp_path), runner=runner, journal=Journal(), run_id=_RUN_ID
    )

    assert observed is not None
    assert observed.failure is not None
    assert observed.failure.provider_usage_limit is True
    assert observed.failure.provider_usage_limit_provider == "anthropic"
    assert observed.failure.provider_usage_limit_entitlement == _ANTHROPIC_CANDIDATE
    assert [argv[1] for argv in runner.calls] == ["inspect", "ps", "events"]


def test_an_ordinary_failure_spends_no_second_read_for_labels(*, tmp_path: Path) -> None:
    """CONTROL: the labels read happens only where it can change an answer.

    `ps -a --json` lists every run the factory holds, so spending it on every
    observation would put a large read on the ordinary failure path — and a
    run whose failure reports no ceiling has no provider to attribute.

    `events` IS spent here, and that is not a weakening of this control: the
    terminal event-stream read is gated on a CONFIRMED FAILED run rather than
    on a ceiling, because a terminal's emitted preservation sentinel has to be
    recovered whatever the fault was. What this case pins is the absence of
    `ps`, which is why the whole sequence is asserted rather than its length.
    """
    runner = ArgvRunner(
        replies={
            "inspect": CommandResult(
                exit_code=0, stdout=_inspect_stdout(cause=_ORDINARY_FAULT), stderr=""
            ),
            "events": CommandResult(exit_code=0, stdout="[]", stderr=""),
        }
    )

    observed = inspect_run(
        plan=_plan(repo=tmp_path), runner=runner, journal=Journal(), run_id=_RUN_ID
    )

    assert observed is not None
    assert observed.failure is not None
    assert observed.failure.provider_usage_limit is False
    assert observed.failure.provider_usage_limit_provider is None
    assert [argv[1] for argv in runner.calls] == ["inspect", "events"]


def test_an_unreadable_labels_read_keeps_the_v107_cause_text_attribution(*, tmp_path: Path) -> None:
    """A labels read that answers nothing establishes no identity.

    The run row is the only place the entitlement is recorded, so a refused or
    unparseable `ps` leaves the conservative legacy attribution standing rather
    than inventing a vendor — and the observation itself still returns, because
    a failed second read says nothing about the terminal the first one proved.
    """
    runner = ArgvRunner(
        replies={
            "inspect": CommandResult(
                exit_code=0, stdout=_inspect_stdout(cause=_SHARED_SENTENCE), stderr=""
            ),
            "ps": CommandResult(exit_code=1, stdout="", stderr="connection refused"),
            "events": CommandResult(exit_code=0, stdout="[]", stderr=""),
        }
    )

    observed = inspect_run(
        plan=_plan(repo=tmp_path), runner=runner, journal=Journal(), run_id=_RUN_ID
    )

    assert observed is not None
    assert observed.failure is not None
    assert observed.failure.provider_usage_limit is True
    assert observed.failure.provider_usage_limit_provider == "codex"
    assert observed.failure.provider_usage_limit_entitlement is None


def test_the_labels_read_is_journaled_as_its_own_stage(*, tmp_path: Path) -> None:
    """The second read is visible, because its silence changes an attribution.

    A labels read that could not be taken degrades to the v107 posture, which
    is indistinguishable at the outcome from a dispatch that never had an
    identity to read — so the read itself is journaled rather than inferred.
    """
    journal = Journal()
    runner = ArgvRunner(
        replies={
            "inspect": CommandResult(
                exit_code=0, stdout=_inspect_stdout(cause=_SHARED_SENTENCE), stderr=""
            ),
            "ps": CommandResult(exit_code=0, stdout=_PS_STDOUT, stderr=""),
            "events": CommandResult(exit_code=0, stdout="[]", stderr=""),
        }
    )

    _ = inspect_run(plan=_plan(repo=tmp_path), runner=runner, journal=journal, run_id=_RUN_ID)

    stages = [row.get("stage") for row in journal.records]
    assert "fabro-run-labels" in stages
