"""A failed Definition-of-Done judge reports a machine-readable cannot-run cause.

The preflight consumes a live plugin registry and the repository's live work-item
tenant, so its end-to-end execution is host-captured. These assertions cover the
committed integration seam: failed Claude and Codex judge commands classify their
combined output through the same provider-limit signature classifier that turns a
recorded run failure into a provider-limit outcome, then emit a typed final line.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")


def test_failed_judge_commands_use_the_recorded_failure_provider_limit_classifier() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert text.count("fabro_usage_limit_provider") == 2
    assert text.count("causes=(output,)") == 1
    assert text.count('judge_failure_cause "$judgement_input.judge"') == 2


def test_failed_judge_commands_emit_the_typed_cannot_run_sentinel_last() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert text.count('"DID-NOT-RUN $cause $agent $model"') == 2
    assert text.count('else "judge-command-failed"') == 1
    assert text.count('"provider-limit"') == 1
