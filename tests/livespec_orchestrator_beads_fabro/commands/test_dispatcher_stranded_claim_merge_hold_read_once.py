"""The claim survey reads the merge-hold labels once per pass, not once per claim.

`surveyable` asked `read_current_merge_hold` of every candidate row, and that read is
the whole-ledger `bd list --status all --limit 0` followed by a parse of every record,
only to find the `merge-hold:` labels. A dispatch's preamble surveys every active
claim in the fleet, so the dump ran once per claim (measured 2026-11-14: about 14
bd CPU-seconds, 2.3 more in its sh wrapper and 6.5 parsing in-process, per dispatch).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _beads_client_fake
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    survey_stranded_claims,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_IDS = ("bd-ib-holdonce1", "bd-ib-holdonce2", "bd-ib-holdonce3")


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="active",
        title="An active claim",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_the_survey_reads_the_whole_ledger_for_merge_holds_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    journal_path = repo / "tmp" / "journal.jsonl"
    journal_path.parent.mkdir(parents=True)
    _ = journal_path.write_text(json.dumps({"stage": "dispatch-id"}) + "\n", encoding="utf-8")
    items = tuple(_item(item_id=item_id) for item_id in _IDS)
    for item in items:
        append_work_item(path=_config(), item=item)
    listings: list[None] = []
    original = _beads_client_fake.FakeBeadsClient.list_issues

    def counting(self: _beads_client_fake.FakeBeadsClient) -> list[dict[str, object]]:
        listings.append(None)
        return original(self)

    monkeypatch.setattr(_beads_client_fake.FakeBeadsClient, "list_issues", counting)

    survey = survey_stranded_claims(
        inputs=StrandedClaimInputs(
            repo=repo,
            items=items,
            journal=JournalFile(path=journal_path),
            runner=pytest.fail,
            inventories=(
                FactoryInventory(
                    name="hp",
                    server_url="https://hp.example:32276",
                    fabro_bin="fabro",
                    surveyed=True,
                    status_kinds={},
                ),
            ),
            this_host="owning-host",
            now_iso="2026-11-14T09:00:00Z",
            dry_run=True,
        )
    )

    assert len(survey.held) == len(_IDS)
    assert len(listings) == 1
