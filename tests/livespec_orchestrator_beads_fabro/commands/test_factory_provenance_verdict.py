"""The provenance verdict's grounds and refusals are named in what it renders."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._factory_provenance_verdict import (
    FACTORY_OVERRIDE_LABEL,
    ProvenanceVerdict,
    exit_code,
    permits_merge,
    render_verdict,
)
from livespec_orchestrator_beads_fabro.commands._incident_provenance import IncidentReceipt

_PRODUCT = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/thing.py"


def _receipt(*, phase: str, repayment_outstanding: bool = True) -> IncidentReceipt:
    return IncidentReceipt(
        repository="owner/repository",
        item_id="incident-1",
        phase=phase,
        pr_number=73,
        head_sha="b" * 40,
        landed_commits=("c" * 40,),
        repayment_required=True,
        repayment_outstanding=repayment_outstanding,
    )


def _verdict(
    *,
    outcome: str,
    factory_authored: bool = False,
    override_labeled: bool = False,
    incident_receipt: IncidentReceipt | None = None,
    repayment_carrier: IncidentReceipt | None = None,
) -> ProvenanceVerdict:
    return ProvenanceVerdict(
        outcome=outcome,  # type: ignore[arg-type]
        author_login="thewoolleyman",
        product_paths=(_PRODUCT,),
        judged_path_count=1,
        factory_authored=factory_authored,
        override_labeled=override_labeled,
        incident_receipt=incident_receipt,
        repayment_carrier=repayment_carrier,
    )


def test_a_pass_names_the_receipt_and_whether_its_repayment_is_still_owed() -> None:
    owed = render_verdict(
        verdict=_verdict(outcome="pass", incident_receipt=_receipt(phase="repair"))
    )
    repaid = render_verdict(
        verdict=_verdict(
            outcome="pass",
            incident_receipt=_receipt(phase="reverting", repayment_outstanding=False),
        )
    )
    assert "retained exact incident receipt of incident-1 (repair" in owed
    assert "normal repayment outstanding" in owed
    assert "(reverting" in repaid
    assert "recorded as repaid" in repaid


def test_a_pass_on_the_label_names_the_label() -> None:
    message = render_verdict(verdict=_verdict(outcome="pass", override_labeled=True))
    assert f"carries the `{FACTORY_OVERRIDE_LABEL}` label" in message


def test_a_refused_repayment_carrier_is_told_the_label_is_insufficient() -> None:
    verdict = _verdict(
        outcome="fail",
        override_labeled=True,
        repayment_carrier=_receipt(phase="repayment-active"),
    )
    message = render_verdict(verdict=verdict)
    assert "retained normal repayment carrier of incident incident-1 (repayment-active)" in message
    assert "requires normal factory provenance" in message
    assert "insufficient authorization" in message
    assert permits_merge(verdict=verdict) is False
    assert exit_code(verdict=verdict) == 1


def test_an_ordinary_refusal_names_both_missing_grounds() -> None:
    message = render_verdict(verdict=_verdict(outcome="fail"))
    assert f"carries no `{FACTORY_OVERRIDE_LABEL}` label" in message
    assert "matches no retained exact incident receipt" in message
    assert "Routes out:" in message
