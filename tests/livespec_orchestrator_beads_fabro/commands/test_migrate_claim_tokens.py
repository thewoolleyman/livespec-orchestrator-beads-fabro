"""Tests for the migrate-claim-tokens maintenance command.

The command is the operator's door onto the sanctioned migration pass: it
surveys unless the operator attests that every claim writer is stopped, and
its exit code is the cutover precondition. The hermetic fake backend stands in
for the tenant; what the pass itself decides is covered in
`test_store_claim_token_migration.py`.
"""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import CLAIM_TOKEN_METADATA_KEY
from livespec_orchestrator_beads_fabro.commands.migrate_claim_tokens import CONFIRM_FLAG, main
from livespec_orchestrator_beads_fabro.types import StoreConfig


def _tenant() -> FakeBeadsClient:
    client = make_beads_client(
        config=StoreConfig(
            tenant="livespec-impl-beads",
            prefix="livespec-impl-beads",
            server_user="livespec-impl-beads",
            database="livespec-impl-beads",
            bd_path="bd",
            fake=True,
        )
    )
    assert isinstance(client, FakeBeadsClient)
    return client


@pytest.fixture(autouse=True)
def _in_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


def _seed(*, item_id: str, status: str = "ready", token: str | None = None) -> None:
    client = _tenant()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="task",
            title=f"{item_id} title",
            description="A work item.",
            assignee=None,
            created_at="2026-11-05T00:00:00Z",
            metadata={} if token is None else {CLAIM_TOKEN_METADATA_KEY: token},
        )
    )
    client.update_issue(issue_id=item_id, status=status)


def _named(*, item_id: str) -> str | None:
    return _tenant().show_issue(issue_id=item_id)["metadata"].get(CLAIM_TOKEN_METADATA_KEY)


def test_without_the_attestation_the_command_surveys_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(item_id="bd-ib-one")
    _seed(item_id="bd-ib-done", status="closed")

    rc = main(argv=[])
    out = capsys.readouterr().out

    assert rc == 1
    assert "migrate-claim-tokens: survey only, nothing written" in out
    assert "naming no open token (not written): 1\n  bd-ib-one\n" in out
    assert "bd-ib-done" not in out
    assert f"then run again with {CONFIRM_FLAG}" in out
    assert _named(item_id="bd-ib-one") is None
    assert _tenant().no_history_issue_ids() == ()


def test_with_the_attestation_the_command_names_tokens_and_a_second_run_changes_nothing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _seed(item_id="bd-ib-one")
    _seed(item_id="bd-ib-two", status="active")

    rc = main(argv=[CONFIRM_FLAG, "--project-root", str(tmp_path)])
    out = capsys.readouterr().out

    first = {item_id: _named(item_id=item_id) for item_id in ("bd-ib-one", "bd-ib-two")}
    assert rc == 0
    assert "migrate-claim-tokens: applied" in out
    assert "named a fresh open token: 2\n" in out
    assert f"  bd-ib-one -> {first['bd-ib-one']}\n" in out
    assert f"  bd-ib-two -> {first['bd-ib-two']}\n" in out
    assert "result: complete - every non-closed item names an open claim token" in out
    assert None not in first.values()

    rc = main(argv=[CONFIRM_FLAG])
    out = capsys.readouterr().out

    assert rc == 0
    assert "named a fresh open token: 0\n" in out
    assert "already naming an open token (unchanged): 2\n" in out
    assert {item_id: _named(item_id=item_id) for item_id in first} == first

    assert main(argv=[]) == 0
    assert "result: complete" in capsys.readouterr().out


def test_an_applied_run_that_holds_an_item_exits_non_zero_and_says_to_run_again(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(item_id="bd-ib-ghost", token="fake-wisp-absent")  # noqa: S106 - a token id

    rc = main(argv=[CONFIRM_FLAG])
    out = capsys.readouterr().out

    assert rc == 1
    assert "held: 1\n  bd-ib-ghost: claim-token-unobservable\n" in out
    assert "result: incomplete - run the pass again to settle the held items" in out
