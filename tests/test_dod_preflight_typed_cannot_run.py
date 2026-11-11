"""A failed Definition-of-Done judge reports a machine-readable cannot-run cause.

The preflight consumes a live plugin registry and the repository's live work-item
tenant, so its end-to-end execution is host-captured. These assertions cover the
committed integration seam: the shared candidate-chain runner owns each failed
Claude or Codex invocation and returns the typed cause the preflight emits.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")


def test_failed_judge_commands_use_the_shared_candidate_chain() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "run_candidate_chain" in text
    assert "ShellCommandRunner" in text
    assert "candidate_resolver=candidates" in text


def test_failed_judge_commands_emit_the_typed_cannot_run_sentinel_last() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert 'print(f"DID-NOT-RUN {chain.cause}")' in text
    assert "raise SystemExit(2)" in text


def test_an_input_bound_cannot_run_is_recorded_without_turning_into_a_refusal() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "did_not_run_comment" in text
    assert "append_work_item_comment" in text
    assert "cause=chain.cause" in text
    assert "raise SystemExit(2)" in text
