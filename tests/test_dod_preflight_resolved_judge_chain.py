"""The launch preflight delegates host judges to the committed ACP chain.

The complete preflight needs the host's installed plugin registry and live
tenant, so its execution is captured on the launch host.  These assertions pin
the committed integration seam: the shell script restores the operator CLI
directory, resolves its candidates through the package, and delegates the
actual invocation to the package seam, whose ordered chain is the one used by the
governing-heading and reflector judgements.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")
_COMMANDS = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")


def _judge_program() -> str:
    return (
        _SCRIPT.read_text(encoding="utf-8").split("<<'JUDGE_PY'\n", 1)[1].rsplit("\nJUDGE_PY", 1)[0]
    )


def test_the_preflight_uses_the_resolved_candidate_chain_and_operator_cli_directory() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert 'PATH="$HOME/.local/bin:$PATH"' in text
    assert "decision = repository_preflight_reading(" in text
    assert "dod_gate_candidates" not in text
    assert "run_candidate_chain" not in text


def test_the_legacy_claude_agent_acp_bridge_lives_in_the_package_seam_and_not_the_script() -> None:
    script = _SCRIPT.read_text(encoding="utf-8")
    seam = (_COMMANDS / "_dod_preflight_judgement.py").read_text(encoding="utf-8")

    assert "candidate_resolver=candidates" not in script
    assert "parse_adapter_string" not in script
    assert "candidate_resolver=preflight_dod_gate_candidates" in seam


def test_the_judge_program_imports_its_shell_runner_from_dispatcher_io() -> None:
    program = _judge_program()

    assert (
        "from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner"
        in program
    )
    assert (
        "from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import ShellCommandRunner"
        not in program
    )


def test_the_preflight_enforces_the_definition_of_done_input_bound() -> None:
    run = (_COMMANDS / "_dispatcher_dod_judgement_run.py").read_text(encoding="utf-8")

    assert "bound_input=True" in run
