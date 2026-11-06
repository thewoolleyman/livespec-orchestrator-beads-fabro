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
