"""Tests for stamping a live Fabro run onto its work-item and reading it back."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroRunSummary
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
)

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_run_stamp.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp"


def _module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _write_livespec_config(*, repo: Path) -> None:
    _ = repo.joinpath(".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {
              "prefix": "bd-ib",
              "tenant": "test-tenant",
              "fake": true
            }
          }
        }
        """,
        encoding="utf-8",
    )


def _seed_item(*, repo: Path, issue_id: str) -> FakeBeadsClient:
    client = make_beads_client(config=store_config(repo=repo))
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title="title",
            description="description",
            assignee=None,
            created_at="2026-08-30T00:00:00Z",
        )
    )
    return client


def _plan(*, repo: Path, work_item_id: str = "bd-ib-owner") -> Any:
    return build_plan(
        repo=repo,
        work_item_id=work_item_id,
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp-xubuntu.perch-rudd.ts.net:32276",
    )


def _row(*, run_id: str, work_item_id: str | None) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind="running",
        goal=None,
        work_item_id=work_item_id,
        total_usd_micros=None,
    )


def test_stamp_writes_both_dispatch_keys_and_journals_the_write(tmp_path: Path) -> None:
    module = _module()
    _write_livespec_config(repo=tmp_path)
    client = _seed_item(repo=tmp_path, issue_id="bd-ib-owner")
    journal = _Journal()

    attribution = module.stamp_dispatch_run(
        plan=_plan(repo=tmp_path),
        journal=journal,
        run_id="01M199TWET07",
    )

    metadata = client.show_issue(issue_id="bd-ib-owner")["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["dispatch_fabro_run_id"] == "01M199TWET07"
    assert metadata["dispatch_factory"] == {
        "name": "hp",
        "server": "https://hp-xubuntu.perch-rudd.ts.net:32276",
    }
    assert journal.records == [
        {
            "work_item_id": "bd-ib-owner",
            "stage": module.STAMP_JOURNAL_STAGE,
            "run_id": "01M199TWET07",
            "dispatch_factory": "hp",
            "dispatch_factory_server": "https://hp-xubuntu.perch-rudd.ts.net:32276",
            "stamped": True,
            "stamp_failure_detail": None,
        }
    ]
    assert attribution.work_item_id_for(run=_row(run_id="01M199TWET07", work_item_id=None)) == (
        "bd-ib-owner"
    )


def test_stamp_fails_open_and_says_so_when_the_repo_carries_no_livespec_config(
    *,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """An absent `.livespec.jsonc` is a diagnosed cause, not a bare silent no-write."""
    module = _module()
    journal = _Journal()

    attribution = module.stamp_dispatch_run(
        plan=_plan(repo=tmp_path),
        journal=journal,
        run_id="01NOCONFIG",
    )

    assert journal.records[0]["stamped"] is False
    detail = journal.records[0].get("stamp_failure_detail")
    assert isinstance(detail, str)
    assert ".livespec.jsonc" in detail
    warning = capsys.readouterr().err
    assert "bd-ib-owner" in warning
    assert "01NOCONFIG" in warning
    assert ".livespec.jsonc" in warning
    assert attribution.metadata_run_ids == {"01NOCONFIG": "bd-ib-owner"}


def test_stamp_fails_open_when_the_ledger_write_itself_refuses(
    *,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The run is the expensive thing; a beads hiccup must not end it — but it must speak."""
    module = _module()
    _write_livespec_config(repo=tmp_path)
    journal = _Journal()

    # No issue seeded, so the fake tenant refuses the update with a mapping error.
    _ = module.stamp_dispatch_run(
        plan=_plan(repo=tmp_path),
        journal=journal,
        run_id="01ABSENT",
    )

    assert journal.records[0]["stamped"] is False
    detail = journal.records[0].get("stamp_failure_detail")
    assert isinstance(detail, str)
    assert "record_dispatch_run" in detail
    assert "bd-ib-owner" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [
        BeadsCommandError(command="bd update", exit_code=1, stderr="refused"),
        BeadsConnectionError(detail="tenant unreachable"),
        BeadsMappingError(record_id="bd-ib-owner", detail="unmappable"),
    ],
    ids=["command", "connection", "mapping"],
)
def test_stamp_names_the_ledger_error_class_that_refused_the_write(
    *,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Each of the three swallowed beads errors reaches the journal AND stderr by name."""
    module = _module()
    _write_livespec_config(repo=tmp_path)
    journal = _Journal()

    def _refuse(**kwargs: object) -> None:
        _ = kwargs
        raise error

    monkeypatch.setattr(module, "record_dispatch_run", _refuse)

    _ = module.stamp_dispatch_run(
        plan=_plan(repo=tmp_path),
        journal=journal,
        run_id="01REFUSED",
    )

    detail = journal.records[0].get("stamp_failure_detail")
    assert isinstance(detail, str)
    assert type(error).__name__ in detail
    assert type(error).__name__ in capsys.readouterr().err


def test_stamped_attribution_is_a_no_op_before_any_run_is_discovered(tmp_path: Path) -> None:
    module = _module()
    journal = _Journal()
    before = RunAttribution()

    after = module.stamped_attribution(
        plan=_plan(repo=tmp_path),
        journal=journal,
        run=None,
        attribution=before,
    )

    assert after is before
    assert journal.records == []


def test_stamped_attribution_stamps_once_and_then_passes_through(tmp_path: Path) -> None:
    module = _module()
    _write_livespec_config(repo=tmp_path)
    _ = _seed_item(repo=tmp_path, issue_id="bd-ib-owner")
    journal = _Journal()
    run = _row(run_id="01ONCE", work_item_id="bd-ib-owner")

    first = module.stamped_attribution(
        plan=_plan(repo=tmp_path),
        journal=journal,
        run=run,
        attribution=RunAttribution(),
    )
    second = module.stamped_attribution(
        plan=_plan(repo=tmp_path),
        journal=journal,
        run=run,
        attribution=first,
    )

    assert second is first
    assert [record["stage"] for record in journal.records] == [module.STAMP_JOURNAL_STAGE]


def test_repo_attribution_reads_the_ledger_stamp_and_the_journal(tmp_path: Path) -> None:
    module = _module()
    _write_livespec_config(repo=tmp_path)
    _ = _seed_item(repo=tmp_path, issue_id="bd-ib-owner")
    module.stamp_dispatch_run(plan=_plan(repo=tmp_path), journal=_Journal(), run_id="01STAMPED")
    journal_file = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal_file.parent.mkdir(parents=True)
    _ = journal_file.write_text(
        json.dumps({"work_item_id": "bd-ib-earlier", "run_id": "01JOURNALED"}) + "\n",
        encoding="utf-8",
    )

    attribution = module.repo_run_attribution(repo=tmp_path)

    assert attribution.work_item_id_for(run=_row(run_id="01STAMPED", work_item_id=None)) == (
        "bd-ib-owner"
    )
    assert attribution.work_item_id_for(run=_row(run_id="01JOURNALED", work_item_id=None)) == (
        "bd-ib-earlier"
    )


def test_repo_attribution_degrades_to_the_regex_floor_with_no_records_at_all(
    tmp_path: Path,
) -> None:
    module = _module()

    attribution = module.repo_run_attribution(repo=tmp_path)

    assert attribution.work_item_id_for(run=_row(run_id="01X", work_item_id="bd-ib-goal")) == (
        "bd-ib-goal"
    )


def test_repo_attribution_keeps_the_journal_leg_when_the_ledger_is_unreachable(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _module()
    _write_livespec_config(repo=tmp_path)

    def _refuse(*, path: object) -> dict[str, str]:
        _ = path
        raise BeadsConnectionError(detail="tenant unreachable")

    monkeypatch.setattr(module, "dispatch_run_ids_for", _refuse)
    journal_file = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal_file.parent.mkdir(parents=True)
    _ = journal_file.write_text(
        json.dumps({"work_item_id": "bd-ib-earlier", "run_id": "01JOURNALED"}) + "\n",
        encoding="utf-8",
    )

    attribution = module.repo_run_attribution(repo=tmp_path)

    assert attribution.work_item_id_for(run=_row(run_id="01JOURNALED", work_item_id=None)) == (
        "bd-ib-earlier"
    )
