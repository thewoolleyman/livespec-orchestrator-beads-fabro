"""The host-side Definition-of-Done chain follows the configured ACP order."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_dod_gate_candidates as candidate_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_dod_judgement_run as judgement_module,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_candidates import (
    dod_gate_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    CAUSE_NO_ELIGIBLE_MODEL,
    run_dod_gate_prompt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult


def _configured_repo(*, tmp_path: Path) -> Path:
    """A fixture chain, so no test reads the committed ACP-node table."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {
          "agent": "codex-acp",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "fallbacks": [{
            "agent": "claude-acp",
            "model": "claude-opus-5",
            "effort": "high"
          }]
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


@dataclass(kw_only=True)
class _Runner:
    """A runner that makes a second call visible rather than silently accepting it."""

    results: list[CommandResult]
    argvs: list[list[str]] = field(default_factory=list)
    environs: list[dict[str, str]] = field(default_factory=list)
    stdin_text: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, start_new_session)
        self.argvs.append(argv)
        self.environs.append(
            {key: value for key, value in (env or {}).items() if value is not None}
        )
        assert stdin is not None
        _ = os.lseek(stdin, 0, os.SEEK_SET)
        self.stdin_text.append(os.read(stdin, 1_000_000).decode("utf-8"))
        assert self.results
        return self.results.pop(0)


def _only_candidate(*, candidate: AcpCandidate):
    """A configured-chain seam that returns one candidate for the fixture repo."""

    def resolve(*, cwd: Path) -> tuple[AcpCandidate, ...]:
        _ = cwd
        return (candidate,)

    return resolve


def _codex_argv(*, model: str, cwd: Path, settings: list[str] | None = None) -> list[str]:
    """The isolated Codex command, after any catalog-derived settings."""
    return [
        "codex",
        "exec",
        "-m",
        model,
        *(settings or []),
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        "features.skills=false",
        "-c",
        "features.multi_agent=false",
        "--add-dir",
        str(cwd),
        "-s",
        "read-only",
        "--skip-git-repo-check",
    ]


def test_an_unparseable_primary_falls_back_to_the_next_configured_candidate(
    tmp_path: Path,
) -> None:
    runner = _Runner(
        results=[
            CommandResult(exit_code=0, stdout="not a verdict", stderr=""),
            CommandResult(exit_code=0, stdout="accepted", stderr=""),
        ]
    )

    repo = _configured_repo(tmp_path=tmp_path)
    reply, cause = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=repo,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply == "accepted"
    assert cause == ""
    assert runner.argvs[0] == _codex_argv(
        model="gpt-5.6-terra",
        cwd=repo,
        settings=["-c", 'model_reasoning_effort="high"'],
    )
    assert runner.argvs[1][runner.argvs[1].index("--model") :] == [
        "--model",
        "claude-opus-5",
        "--add-dir",
        str(repo),
        "--setting-sources",
        "",
        "--managed-settings",
        "{}",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]
    assert runner.stdin_text == ["one prompt", "one prompt"]


def test_a_primary_verdict_stops_the_chain_before_the_anthropic_fallback(tmp_path: Path) -> None:
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="accepted", stderr="")])

    repo = _configured_repo(tmp_path=tmp_path)
    reply, cause = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=repo,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply == "accepted"
    assert cause == ""
    assert runner.argvs == [
        _codex_argv(
            model="gpt-5.6-terra",
            cwd=repo,
            settings=["-c", 'model_reasoning_effort="high"'],
        )
    ]


def test_missing_dod_gate_has_no_host_candidate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}',
        encoding="utf-8",
    )

    assert dod_gate_candidates(cwd=repo) is None


def test_an_unresolvable_dod_gate_has_no_host_candidate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {"dod_gate": {"agent": "missing-acp", "model": "missing"}}
    }
  }
}
""",
        encoding="utf-8",
    )

    assert dod_gate_candidates(cwd=repo) is None


def test_an_unreadable_config_has_no_host_candidate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text("{not JSON", encoding="utf-8")

    assert dod_gate_candidates(cwd=repo) is None


def test_an_unreadable_catalog_has_no_host_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable_catalog(*, block: object) -> str:
        _ = block
        return "bad"

    monkeypatch.setattr(candidate_module, "resolve_acp_catalogs", unreadable_catalog)

    assert dod_gate_candidates(cwd=_configured_repo(tmp_path=tmp_path)) is None


def test_no_resolved_candidate_uses_the_did_not_run_cause(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}',
        encoding="utf-8",
    )
    runner = _Runner(results=[])

    reply, cause = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=repo,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply is None
    assert cause == CAUSE_NO_ELIGIBLE_MODEL
    assert runner.argvs == []


def test_a_codex_candidate_without_effort_does_not_add_a_reasoning_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = AcpCandidate(
        adapter=AcpAdapter(command="codex-acp", env={"CODEX_CONFIG": '{"model": "gpt"}'}),
        agent_id="codex-acp",
    )
    monkeypatch.setattr(
        judgement_module, "dod_gate_candidates", _only_candidate(candidate=candidate)
    )
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="accepted", stderr="")])
    reply, _ = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=tmp_path,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply == "accepted"
    assert runner.argvs == [_codex_argv(model="gpt", cwd=tmp_path)]


def test_a_codex_candidate_without_host_auth_still_receives_a_private_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent interactive auth file is not an invocation failure."""
    candidate = AcpCandidate(
        adapter=AcpAdapter(command="codex-acp", env={"CODEX_CONFIG": '{"model": "gpt"}'}),
        agent_id="codex-acp",
    )
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home-without-codex-auth"))
    monkeypatch.setattr(
        judgement_module, "dod_gate_candidates", _only_candidate(candidate=candidate)
    )
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="accepted", stderr="")])

    reply, _ = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=tmp_path,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply == "accepted"
    assert runner.argvs == [_codex_argv(model="gpt", cwd=tmp_path)]


def test_a_codex_candidate_carries_its_adapter_settings_but_judges_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = AcpCandidate(
        adapter=AcpAdapter(
            command="codex-acp",
            env={
                "CODEX_CONFIG": (
                    '{"approval_policy": "never", "model": "gpt", '
                    '"model_provider": "azure", "model_reasoning_effort": "high", '
                    '"sandbox_mode": "danger-full-access", "tools": {"web": true}}'
                ),
                "CODEX_ENDPOINT": "https://codex.invalid",
            },
        ),
        agent_id="codex-acp",
    )
    monkeypatch.setattr(
        judgement_module, "dod_gate_candidates", _only_candidate(candidate=candidate)
    )
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="accepted", stderr="")])
    reply, _ = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=tmp_path,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply == "accepted"
    assert runner.argvs == [
        _codex_argv(
            model="gpt",
            cwd=tmp_path,
            settings=[
                "-c",
                'model_provider="azure"',
                "-c",
                'model_reasoning_effort="high"',
            ],
        )
    ]
    assert runner.environs[0]["CODEX_ENDPOINT"] == "https://codex.invalid"


def test_a_claude_candidate_carries_its_adapter_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = AcpCandidate(
        adapter=AcpAdapter(
            command="claude-acp",
            env={
                "ANTHROPIC_MODEL": "claude-opus-5",
                "ANTHROPIC_BASE_URL": "https://anthropic.invalid",
                "CLAUDE_CODE_EFFORT_LEVEL": "high",
            },
        ),
        agent_id="claude-acp",
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "selected-token")
    monkeypatch.setattr(
        judgement_module, "dod_gate_candidates", _only_candidate(candidate=candidate)
    )
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="accepted", stderr="")])
    reply, _ = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=tmp_path,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply == "accepted"
    assert runner.argvs[0][1:] == [
        "-p",
        "--allowedTools",
        "Read,Grep,Glob",
        "--model",
        "claude-opus-5",
        "--add-dir",
        str(tmp_path),
        "--setting-sources",
        "",
        "--managed-settings",
        "{}",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]
    assert runner.environs[0]["ANTHROPIC_BASE_URL"] == "https://anthropic.invalid"
    assert runner.environs[0]["CLAUDE_CODE_EFFORT_LEVEL"] == "high"
    assert runner.environs[0]["CLAUDE_CODE_OAUTH_TOKEN"] == "selected-token"


def test_another_catalog_adapter_runs_its_declared_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = AcpCandidate(
        adapter=AcpAdapter(command="other-acp", args=("--judge",)),
        agent_id="other-acp",
    )
    monkeypatch.setattr(
        judgement_module, "dod_gate_candidates", _only_candidate(candidate=candidate)
    )
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="accepted", stderr="")])
    reply, _ = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=tmp_path,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply == "accepted"
    assert runner.argvs == [["other-acp", "--judge"]]


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not JSON"),
        pytest.param("[]"),
        pytest.param('{"model": 5, "model_reasoning_effort": 3}'),
    ],
)
def test_invalid_codex_settings_do_not_invent_a_model_or_effort(
    raw: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = AcpCandidate(
        adapter=AcpAdapter(command="codex-acp", env={"CODEX_CONFIG": raw}),
        agent_id="codex-acp",
    )
    monkeypatch.setattr(
        judgement_module, "dod_gate_candidates", _only_candidate(candidate=candidate)
    )
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="accepted", stderr="")])
    reply, _ = run_dod_gate_prompt(
        prompt="one prompt",
        cwd=tmp_path,
        runner=runner,
        is_verdict=lambda text: text == "accepted",
    )

    assert reply == "accepted"
    assert runner.argvs == [_codex_argv(model="", cwd=tmp_path)]


def test_the_red_runner_also_models_a_command_without_standard_input() -> None:
    path = Path(__file__).with_name("test_dispatcher_dod_judgement_run.py")
    specification = spec_from_file_location("red_runner_seam", path)
    assert specification is not None
    assert specification.loader is not None
    red_test = module_from_spec(specification)
    sys.modules[specification.name] = red_test
    specification.loader.exec_module(red_test)
    result = CommandResult(exit_code=0, stdout="", stderr="")
    runner = red_test._Runner(result=result)  # noqa: SLF001 - its branch is the test subject.

    returned = runner.run(
        argv=["judge"],
        cwd=Path(),
        timeout_seconds=1.0,
    )

    assert returned == result
    assert runner.stdin_text == []
