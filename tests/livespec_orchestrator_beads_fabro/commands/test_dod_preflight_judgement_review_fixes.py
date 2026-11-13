"""The repository preflight keeps the legacy dod_gate bridge and never re-takes a heading it took."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_UNAVAILABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dod_preflight_judgement"


@dataclass
class _CommentStore:
    bodies: list[str] = field(default_factory=list)

    def comments(self) -> tuple[str, ...]:
        return tuple(self.bodies)

    def append(self, *, body: str) -> None:
        self.bodies.append(body)


@dataclass
class _Runner:
    reply: str
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, start_new_session)
        assert stdin is not None
        _ = os.read(stdin, 1_000_000)
        self.argvs.append(argv)
        return CommandResult(exit_code=0, stdout=self.reply, stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-hofndb",
        type="bug",
        status="ready",
        title="Record repository preflight verdicts",
        description="## Definition of Done\n\n- Record the verdict.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path, dod_gate: str) -> Path:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True)
    (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"acp_nodes":'
        f'{{"dod_gate":{dod_gate}}}}}}}}}',
        encoding="utf-8",
    )
    return repo


def _payload(*, tmp_path: Path) -> Path:
    prompts = tmp_path / "payload" / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "dod-gate.md").write_text(
        dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    return prompts.parents[3]


def _unobserved(**_: object) -> None:
    return None


def test_a_legacy_string_dod_gate_still_reaches_the_claude_judge(tmp_path: Path) -> None:
    judgement = importlib.import_module(_MODULE)
    runner = _Runner(reply='{"outcome":"passed"}')

    decision = judgement.repository_preflight_reading(
        item=_item(),
        repo=_repo(tmp_path=tmp_path, dod_gate='"claude-agent-acp"'),
        store=_CommentStore(),
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=_unobserved,
    )

    assert decision.outcome == JUDGEMENT_ADMITTED
    assert len(runner.argvs) == 1


def test_an_unrecognised_legacy_string_dod_gate_runs_no_judge(tmp_path: Path) -> None:
    judgement = importlib.import_module(_MODULE)
    runner = _Runner(reply='{"outcome":"passed"}')

    decision = judgement.repository_preflight_reading(
        item=_item(),
        repo=_repo(tmp_path=tmp_path, dod_gate='"some-other-adapter"'),
        store=_CommentStore(),
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=_unobserved,
    )

    assert decision.outcome == JUDGEMENT_UNAVAILABLE
    assert runner.argvs == []


def test_a_governing_heading_the_script_could_not_observe_is_not_taken_again(
    tmp_path: Path,
) -> None:
    judgement = importlib.import_module(_MODULE)
    runner = _Runner(reply='{"outcome":"passed"}')

    decision = judgement.repository_preflight_reading(
        item=_item(),
        repo=_repo(tmp_path=tmp_path, dod_gate='{"agent":"claude-acp","model":"claude-opus-5"}'),
        store=_CommentStore(),
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
        governing_observed=False,
    )

    assert decision.outcome == JUDGEMENT_ADMITTED
    assert len(runner.argvs) == 1
