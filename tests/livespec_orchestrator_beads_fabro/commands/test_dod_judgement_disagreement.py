"""Definition-of-Done disagreement reconciliation is durable and idempotent."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_dod_judgement_disagreement.py"
)
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_disagreement"
_SUBJECT = "a" * 64
_RUBRIC = "b" * 64


def test_opposite_verdicts_on_one_digest_pair_create_one_named_disagreement() -> None:
    """Scenario 240: repeated reads do not duplicate one disagreement receipt."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    comments = (
        module.verdict_record(
            taking="repository-preflight",
            outcome="admitted",
            subject_digest=_SUBJECT,
            rubric_digest=_RUBRIC,
            timestamp="2026-10-24T19:00:00Z",
        ),
        module.verdict_record(
            taking="dod-gate",
            outcome="rests-at-needs-human",
            subject_digest=_SUBJECT,
            rubric_digest=_RUBRIC,
            timestamp="2026-10-24T19:01:00Z",
            run_id="run-240",
            findings=("the node refused",),
        ),
    )

    first = module.disagreements(comments=comments)
    receipt = module.disagreement_record(disagreement=first[0])
    second = module.disagreements(comments=(*comments, receipt))

    assert len(first) == 1
    assert first[0].subject_digest == _SUBJECT
    assert first[0].rubric_digest == _RUBRIC
    assert first[0].takings == ("repository-preflight", "dod-gate run-240")
    assert first[0].outcomes == ("admitted", "rests-at-needs-human")
    assert second == ()
