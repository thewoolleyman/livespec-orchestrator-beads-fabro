"""The judgement decision renders as its own module.

It was split out of the gate, which sits at the file size ceiling, and keeps the
behaviour it had there: a held outcome rests the item, and the first remedy is
the first finding's remedy.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _dispatcher_dod_judgement_gate as gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    first_remedy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_decision import (
    DodJudgementDecision,
)


def test_a_held_decision_holds_and_names_the_first_findings_remedy() -> None:
    findings = ("first finding. Remedy: fix it", "second")
    decision = DodJudgementDecision(
        work_item_id="bd-ib-x", outcome=JUDGEMENT_HELD, findings=findings
    )

    assert decision.holds is True
    assert decision.first_remedy == first_remedy(findings=findings)


def test_an_unavailable_decision_does_not_hold() -> None:
    decision = DodJudgementDecision(work_item_id="bd-ib-x", outcome=JUDGEMENT_UNAVAILABLE)

    assert decision.holds is False
    assert decision.reused is False


def test_the_gate_still_exports_the_one_decision_class() -> None:
    assert gate.DodJudgementDecision is DodJudgementDecision
