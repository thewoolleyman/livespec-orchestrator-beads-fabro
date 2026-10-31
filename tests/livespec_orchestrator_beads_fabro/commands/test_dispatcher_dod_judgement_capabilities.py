"""The host Definition-of-Done judgement states the governed repository's capability set.

A host candidate has no tools, so it cannot resolve the sandbox capability set
the rubric's capability section asks for. The set therefore travels inline,
taken from the governed repository's committed `dispatcher.sandbox_capabilities`
mirror. With no mirror the set is UNKNOWN, so the judge is told
`sandbox-capabilities: unpublished` rather than a guessed baseline, because a
guessed `terminal`-only set would grade every browser or tmux assertion as
unprovable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
    run_dod_judgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 174 — The judgement runs before admission"


@dataclass
class _Runner:
    """A CommandRunner double that keeps the prompt each candidate was handed."""

    stdin_text: list[str] = field(default_factory=list)

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
        # The judgement always hands its prompt over on stdin.
        assert stdin is not None
        _ = os.lseek(stdin, 0, os.SEEK_SET)
        self.stdin_text.append(os.read(stdin, 1_000_000).decode("utf-8"))
        return CommandResult(exit_code=0, stdout='{"outcome": "passed"}\n', stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-ff5ohb",
        type="bug",
        status="ready",
        title="Judge with the configured capability set",
        description=(
            "## Definition of Done\n\n- The judgement runs before admission.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-31T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path, capabilities: str | None) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nThe judgement runs before admission.\n", encoding="utf-8"
    )
    mirror = "" if capabilities is None else f'"sandbox_capabilities": {capabilities},\n      '
    _ = (repo / ".livespec.jsonc").write_text(
        '{\n  "livespec-orchestrator-beads-fabro": {\n    "dispatcher": {\n      '
        f"{mirror}"
        '"acp_nodes": {\n        "dod_gate": {\n          "agent": "claude-acp",\n'
        '          "model": "claude-opus-5",\n          "effort": "high"\n        }\n'
        "      }\n    }\n  }\n}\n",
        encoding="utf-8",
    )
    return repo


def _prompt(*, tmp_path: Path, capabilities: str | None) -> str:
    runner = _Runner()
    _ = run_dod_judgement(
        item=_item(),
        cwd=_repo(tmp_path=tmp_path, capabilities=capabilities),
        runner=runner,
        rubric=dod_gate_prompt_path().read_text(encoding="utf-8"),
    )
    return runner.stdin_text[0].casefold()


def test_the_judge_is_told_the_repository_s_whole_configured_capability_set(
    tmp_path: Path,
) -> None:
    prompt = _prompt(
        tmp_path=tmp_path, capabilities='["terminal", "headless_browser", "tmux", "herdr"]'
    )

    assert "sandbox capabilities: terminal, headless_browser, tmux, herdr" in prompt
    # The rubric's own capability section tells the judge to read the image's
    # published file; a tool-less judge cannot, so that direction must be gone.
    assert "/etc/livespec/sandbox-capabilities" not in prompt


def test_with_no_configured_mirror_the_judge_is_told_the_set_is_unpublished(
    tmp_path: Path,
) -> None:
    prompt = _prompt(tmp_path=tmp_path, capabilities=None)

    assert "sandbox-capabilities: unpublished" in prompt
    assert "sandbox capabilities: terminal" not in prompt
