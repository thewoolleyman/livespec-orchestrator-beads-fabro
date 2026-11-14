"""A failed Definition-of-Done judge reports a machine-readable cannot-run cause.

The preflight consumes a live plugin registry and the repository's live work-item
tenant, so its end-to-end execution is host-captured. These assertions cover the
committed integration seam: the shared candidate-chain runner owns each failed
Claude or Codex invocation and returns the typed cause the preflight emits.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")
_COMMANDS = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")


def test_failed_judge_commands_use_the_shared_candidate_chain() -> None:
    script = _SCRIPT.read_text(encoding="utf-8")
    run = (_COMMANDS / "_dispatcher_dod_judgement_run.py").read_text(encoding="utf-8")

    assert "run_candidate_chain" in run
    assert "ShellCommandRunner" in script
    assert "repository_preflight_reading(" in script


def test_failed_judge_commands_emit_the_typed_cannot_run_sentinel_last() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    judgement = (_COMMANDS / "_dod_preflight_judgement.py").read_text(encoding="utf-8")

    assert "repository_preflight_report(decision=decision)" in text
    assert "raise SystemExit(status)" in text
    assert 'f"DID-NOT-RUN {cause}"' in judgement
    assert "), 2" in judgement


def test_an_input_bound_cannot_run_is_recorded_without_turning_into_a_refusal() -> None:
    script = _SCRIPT.read_text(encoding="utf-8")
    gate = (_COMMANDS / "_dispatcher_dod_judgement_gate.py").read_text(encoding="utf-8")

    assert "did_not_run_comment" in gate
    assert "cause=cause" in gate
    judgement = (_COMMANDS / "_dod_preflight_judgement.py").read_text(encoding="utf-8")

    assert "if decision.outcome == JUDGEMENT_UNAVAILABLE:" in judgement
    assert "repository_preflight_report(decision=decision)" in script
