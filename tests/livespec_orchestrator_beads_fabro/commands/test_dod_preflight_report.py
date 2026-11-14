"""The repository preflight prints the contract its launchers read.

`dev-tooling/dod-preflight.sh` promises exit 0 and a last line of PASS, exit 1 and a
failure JSON line, and exit 2 when the judgement could not run. `fleet-launch/
dispatch-dual.sh` logs `tail -1` of the output on exit 1 and greps the output for a
`{"outcome": "failed"` line on exit 2, so the report the package renders for a
decision is graded here on the lines it prints.
"""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dod_preflight_judgement"
_AGENT = '{"agent":"claude-acp","model":"claude-opus-5"}'


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
    exit_code: int = 0
    calls: int = 0

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
        _ = (argv, cwd, timeout_seconds, env, start_new_session)
        assert stdin is not None
        _ = os.read(stdin, 1_000_000)
        self.calls += 1
        return CommandResult(exit_code=self.exit_code, stdout=self.reply, stderr="")


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


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True)
    (repo / ".livespec.jsonc").write_text(
        f'{{"livespec-orchestrator-beads-fabro":{{"dispatcher":{{"acp_nodes":{{"dod_gate":{_AGENT}}}}}}}}}',
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


def _report(
    *, tmp_path: Path, runner: _Runner, store: _CommentStore
) -> tuple[tuple[str, ...], int]:
    judgement = importlib.import_module(_MODULE)
    report = getattr(judgement, "repository_preflight_report", None)
    assert report is not None
    decision = judgement.repository_preflight_reading(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        store=store,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=_unobserved,
    )
    return report(decision=decision)


def test_a_refusal_prints_a_failure_json_line_last_and_exits_one(tmp_path: Path) -> None:
    reply = json.dumps({"outcome": "failed", "failure_reason": "no proof mode: name one"})

    lines, status = _report(tmp_path=tmp_path, runner=_Runner(reply=reply), store=_CommentStore())

    assert status == 1
    assert json.loads(lines[-1]) == {
        "outcome": "failed",
        "failure_reason": "no proof mode: name one",
    }
    assert lines[-1].startswith('{"outcome": "failed"')


def test_a_reused_refusal_names_the_reuse_and_still_ends_on_the_failure_line(
    tmp_path: Path,
) -> None:
    reply = json.dumps({"outcome": "failed", "failure_reason": "no proof mode: name one"})
    store = _CommentStore()
    _report(tmp_path=tmp_path, runner=_Runner(reply=reply), store=store)
    runner = _Runner(reply=reply)

    lines, status = _report(tmp_path=tmp_path, runner=runner, store=store)

    assert runner.calls == 0
    assert status == 1
    assert lines[0] == f"REUSED {JUDGEMENT_HELD}"
    assert json.loads(lines[-1])["failure_reason"] == "no proof mode: name one"


def test_a_pass_exits_zero_and_names_a_reuse_only_when_it_reused(tmp_path: Path) -> None:
    reply = json.dumps({"outcome": "passed"})
    store = _CommentStore()

    first, first_status = _report(tmp_path=tmp_path, runner=_Runner(reply=reply), store=store)
    second, second_status = _report(tmp_path=tmp_path, runner=_Runner(reply=reply), store=store)

    assert (first, first_status) == ((), 0)
    assert (second, second_status) == ((f"REUSED {JUDGEMENT_ADMITTED}",), 0)


def test_a_judgement_that_could_not_run_prints_its_cause_and_exits_two(tmp_path: Path) -> None:
    lines, status = _report(
        tmp_path=tmp_path,
        runner=_Runner(reply="not a verdict", exit_code=1),
        store=_CommentStore(),
    )

    assert status == 2
    assert len(lines) == 1
    assert lines[0].startswith("DID-NOT-RUN ")
    assert len(lines[0]) > len("DID-NOT-RUN ")
    assert JUDGEMENT_UNAVAILABLE == "did-not-run"
