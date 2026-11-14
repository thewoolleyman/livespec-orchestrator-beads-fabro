"""The claim survey reads every candidate's claim stamp in ONE `bd show`, not one per claim.

`_survey_one` read each surveyed row's stamp with its own `bd show <id>`, so a dispatch's
preamble, which surveys every active claim in the fleet, spawned one `bd` process per
claim (measured 2026-11-14: 13 stranded-claim judgements in one window, about 5 CPU-seconds
of `bd show` and `comments add` on items unrelated to the dispatch). The client already has
a multi-id `show`; the survey takes the stamps through it, once, and keeps the per-claim
read only for a claim the batch could not name. Every recovery write still re-reads its own
row and is fenced on it, so a stamp read at the start of the pass cannot authorize a write.
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

_IDS = ("bd-ib-stampbatch1", "bd-ib-stampbatch2", "bd-ib-stampbatch3")


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


def test_the_survey_reads_every_claim_stamp_in_one_multi_id_show(
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
    batches: list[list[str]] = []
    original = _beads_client_fake.FakeBeadsClient.show_issues

    def counting(
        self: _beads_client_fake.FakeBeadsClient, *, issue_ids: list[str]
    ) -> list[dict[str, object]]:
        batches.append(sorted(issue_ids))
        return original(self, issue_ids=issue_ids)

    monkeypatch.setattr(_beads_client_fake.FakeBeadsClient, "show_issues", counting)
    monkeypatch.setattr(
        _beads_client_fake.FakeBeadsClient,
        "show_issue",
        lambda _self, **_kwargs: pytest.fail("a claim stamp was read one `bd show` at a time"),
    )

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
    assert batches == [sorted(_IDS)]
