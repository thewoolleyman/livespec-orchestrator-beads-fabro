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
