"""Exact, immutable incident-carrier provenance evidence."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_a_trusted_incident_receipt_matches_only_its_exact_pr_head_and_landing() -> None:
    module_path = Path(
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_incident_provenance.py"
    )
    assert module_path.is_file()
    subject = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._incident_provenance"
    )
    receipt = subject.IncidentReceipt(
        repository="owner/repository",
        item_id="incident-1",
        phase="repair",
        pr_number=73,
        head_sha="a" * 40,
        landed_commits=("b" * 40,),
        repayment_required=True,
    )
    assert subject.matches_receipt(
        receipt=receipt,
        repository="owner/repository",
        pr_number=73,
        head_sha="a" * 40,
        landed_commits=("b" * 40,),
    )
    assert not subject.matches_receipt(
        receipt=receipt,
        repository="owner/repository",
        pr_number=74,
        head_sha="a" * 40,
        landed_commits=("b" * 40,),
    )
    assert not subject.matches_receipt(
        receipt=receipt,
        repository="owner/repository",
        pr_number=73,
        head_sha="c" * 40,
        landed_commits=("b" * 40,),
    )
    assert not subject.matches_receipt(
        receipt=receipt,
        repository="owner/repository",
        pr_number=73,
        head_sha="a" * 40,
        landed_commits=("c" * 40,),
    )


def test_only_repair_or_revert_receipts_can_bypass_factory_authorship() -> None:
    subject = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._incident_provenance"
    )
    assert hasattr(subject, "permits_incident_exception")
    repair = subject.IncidentReceipt(
        repository="owner/repository",
        item_id="incident-1",
        phase="repair",
        pr_number=73,
        head_sha="a" * 40,
        landed_commits=("b" * 40,),
        repayment_required=True,
    )
    repayment = subject.IncidentReceipt(
        repository="owner/repository",
        item_id="incident-1",
        phase="repayment-active",
        pr_number=74,
        head_sha="c" * 40,
        landed_commits=("d" * 40,),
        repayment_required=True,
    )
    carrier = dict(
        repository="owner/repository",
        pr_number=73,
        head_sha="a" * 40,
        landed_commits=("b" * 40,),
    )
    assert subject.permits_incident_exception(receipt=repair, **carrier)
    assert not subject.permits_incident_exception(
        receipt=repayment,
        repository="owner/repository",
        pr_number=74,
        head_sha="c" * 40,
        landed_commits=("d" * 40,),
    )


def test_history_receipts_bind_every_pr_bound_attempt_and_owe_repayment_until_the_chain_closes() -> (
    None
):
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt

    subject = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._incident_provenance"
    )

    def attempt(*, generation: int, phase: str, pr_number: int) -> IncidentAttempt:
        return IncidentAttempt(
            repository="owner/repository",
            item_id="incident-1",
            attempt_id=f"attempt-{generation}",
            phase=phase,
            operation_id=f"operation-{generation}",
            generation=generation,
            owner="operator:alice",
            base="a" * 40,
            head="b" * 40,
            pr_number=pr_number,
            landed_commits=() if pr_number == 0 else ("c" * 40,),
            landed_trees=() if pr_number == 0 else ("d" * 40,),
            original_paths=("app.py",),
            deferred_work=("normal-factory-proof",),
            repayment_required=True,
        )

    assert subject.receipts_from_history(history=()) == ()
    owed = subject.receipts_from_history(
        history=(
            attempt(generation=1, phase="repair", pr_number=0),
            attempt(generation=2, phase="repair", pr_number=73),
            attempt(generation=3, phase="repayment-active", pr_number=80),
        )
    )
    assert [
        (receipt.phase, receipt.pr_number, receipt.repayment_outstanding) for receipt in owed
    ] == [
        ("repair", 73, True),
        ("repayment-active", 80, True),
    ]
    repaid = subject.receipts_from_history(
        history=(
            attempt(generation=1, phase="repair", pr_number=73),
            attempt(generation=2, phase="closed", pr_number=80),
        )
    )
    assert [receipt.repayment_outstanding for receipt in repaid] == [False, False]
    carrier = dict(
        receipts=owed,
        repository="owner/repository",
        pr_number=80,
        head_sha="b" * 40,
        landed_commits=("c" * 40,),
    )
    assert subject.matching_incident_receipt(**carrier) is None
    assert subject.matching_repayment_carrier(**carrier) == owed[1]
    assert subject.matching_repayment_carrier(**(carrier | dict(pr_number=73))) is None
    assert subject.matching_incident_receipt(**(carrier | dict(pr_number=73))) == owed[0]
    assert (
        subject.matching_incident_receipt(**(carrier | dict(pr_number=73, repository="x/y")))
        is None
    )
