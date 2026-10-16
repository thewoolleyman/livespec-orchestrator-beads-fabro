"""The hold a ceiling records covers the EXECUTED candidate's domain only.

Scenario 65's "A shared provider sentence is attributed to the candidate that
ran" closes on "And the hold recorded for it covers the executed candidate's
availability domain only". This module grades that second half, which the
attribution cases cannot: a provider value is only correct in so far as the
record written under it holds the right dispatches and admits the rest.

EVERY VALUE HERE COMES FROM PRODUCTION CODE. The only input supplied is the
vendor's own sentence and the labels one dispatch stamped; the classification,
the attribution, the terminal outcome, the journal record and the coverage
verdict are all taken through the functions a live dispatch uses. A test that
hand-wrote `provider="anthropic"` into the record would assert the coverage
rule while skipping the misattribution the rule exists to survive.

THE NEGATIVE CASE IS THE DISCRIMINATING ONE, and it sits on the SAME journal
as the positive. "Covers only the executed candidate's availability domain" is
a claim with two edges: before the attribution this record was written under
`codex`, which held every Codex dispatch on an allowance nothing had spent and
left the exhausted Anthropic one to be spent again. So a hold that refuses
everything satisfies the positive edge exactly as well as a correct one does.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach import inspect_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    covering_provider_exhaustion,
    record_provider_exhaustion_if_observed,
)

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_RUN_ID = "01M4J5M63APH75NJ1JF7ZCN9DY"
_NOW = "2026-10-15T12:00:00Z"
_ACP_WRAPPER = "ACP protocol error"
# The sentence BOTH vendors emit: no reset instant, no vendor marker, nothing
# the cause text can turn into an attribution.
_SHARED_SENTENCE = "the agent answered `session/prompt` with an error: You've hit your usage limit"
_ANTHROPIC_CANDIDATE = "builtin-anthropic-9f2c1d0b4e5a6f78"
_CODEX_CANDIDATE = "builtin-codex-1a2b3c4d5e6f7081"


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


@dataclass(kw_only=True)
class _FileJournal:
    """The append-only journal the exhaustion reader later walks as a file."""

    path: Path

    def append(self, *, record: dict[str, object]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            _ = handle.write(f"{json.dumps(record)}\n")


_INSPECT_STDOUT = json.dumps(
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
                            "causes": [_ACP_WRAPPER, _SHARED_SENTENCE],
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
            "run_id": _RUN_ID,
            "status": {"kind": "failed"},
            "total_usd_micros": None,
            "labels": {
                "livespec.acp.implement.availability": "anthropic",
                "livespec.acp.implement.candidate": _ANTHROPIC_CANDIDATE,
                "livespec.acp.disposition.availability": "codex",
                "livespec.acp.disposition.candidate": _CODEX_CANDIDATE,
            },
        }
    ]
)


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


def _rendered(*, availability: str, candidate: str) -> Any:
    """One built-in candidate a dispatch's resolved node would render.

    `builtin=True` is the caller's fact everywhere in production — it is read
    off the rendered-bytes table — and it is what makes a legacy provider
    record able to cover the candidate at all.
    """
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    coverage = importlib.import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    return coverage.RenderedCandidate(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
            identity=schema.AcpCandidateIdentity(
                display_name="candidate",
                candidate_key=candidate,
                availability_key=availability,
            ),
        ),
        builtin=True,
    )


def _recorded_hold(*, repo: Path) -> Path:
    """Drive one ceiling from its sentence to its appended hold record."""
    runner = _SubcommandRunner(
        replies={
            "inspect": CommandResult(exit_code=0, stdout=_INSPECT_STDOUT, stderr=""),
            "ps": CommandResult(exit_code=0, stdout=_PS_STDOUT, stderr=""),
            # Every case here observes a FAILED run, which also spends the
            # terminal event-stream read that recovers a needs-human
            # terminal's emitted preservation sentinel.
            "events": CommandResult(exit_code=0, stdout="[]", stderr=""),
        }
    )
    plan = _plan(repo=repo)
    journal_path = repo / "fabro-dispatch-journal.jsonl"
    journal = _FileJournal(path=journal_path)
    inspect = inspect_run(plan=plan, runner=runner, journal=journal, run_id=_RUN_ID)
    assert inspect is not None
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=_RUN_ID,
        inspect=inspect,
        exit_code=1,
        stderr=NEEDS_HUMAN_MARKER,
    )
    assert outcome is not None
    assert outcome.provider_usage_limit is True
    record_provider_exhaustion_if_observed(outcome=outcome, journal=journal, now_iso=_NOW)
    return journal_path


def test_the_hold_is_recorded_under_the_executed_candidates_availability_domain(
    *, tmp_path: Path
) -> None:
    """The appended record names the vendor whose allowance was actually spent."""
    journal_path = _recorded_hold(repo=tmp_path)

    observed = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if '"provider-exhaustion-observed"' in line
    ]

    assert [record["provider"] for record in observed] == ["anthropic"]
    assert [record["governing_condition"] for record in observed] == ["provider_usage_limit"]


def test_the_hold_refuses_the_executed_domain_and_admits_the_other(*, tmp_path: Path) -> None:
    """One journal, two verdicts: the spent domain is held, the intact one is not.

    The negative is what tells a correctly scoped hold from one that refuses
    everything, and the positive beside it is what tells a scoped hold from a
    gauge that has simply been blinded.
    """
    journal_path = _recorded_hold(repo=tmp_path)

    held = covering_provider_exhaustion(
        journal_path=journal_path,
        now_iso=_NOW,
        candidates=(_rendered(availability="anthropic", candidate=_ANTHROPIC_CANDIDATE),),
    )
    admitted = covering_provider_exhaustion(
        journal_path=journal_path,
        now_iso=_NOW,
        candidates=(_rendered(availability="codex", candidate=_CODEX_CANDIDATE),),
    )

    assert held is not None
    assert held.provider == "anthropic"
    assert admitted is None
