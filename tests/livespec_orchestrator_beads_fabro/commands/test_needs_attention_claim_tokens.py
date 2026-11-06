"""Coverage for the claim-token-missing attention lane.

Once `dispatcher.claim_tokens` is committed true, every claim writer refuses a
non-closed item that names no current token and writes nothing, so the item is
silent on every other lane. These cases pin the row that makes it visible, the
key that arms it, and the handoff, which must never be the applying form of
the migration pass.
"""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _store_claim_token_migration
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_claim_token_migration import (
    migrate_claim_tokens,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._needs_attention_claim_tokens import (
    claim_token_missing_items,
)
from livespec_orchestrator_beads_fabro.commands.migrate_claim_tokens import CONFIRM_FLAG
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ROW_PREFIX = "hygiene:claim-token-missing:"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _tenant() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _write_config(project_root: Path, *, claim_tokens: bool | None) -> None:
    dispatcher = (
        ""
        if claim_tokens is None
        else f', "dispatcher": {{"claim_tokens": {str(claim_tokens).lower()}}}'
    )
    _ = (project_root / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": '
        '{"prefix": "bd", "bd_path": "bd", "fake": true}' + dispatcher + "}}",
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
            labels=["intake:triaged"],
            metadata={} if token is None else {CLAIM_TOKEN_METADATA_KEY: token},
        )
    )
    client.update_issue(issue_id=item_id, status=status)


def test_after_cutover_every_non_closed_item_naming_no_token_gets_one_row(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path, claim_tokens=True)
    _seed(item_id="bd-unnamed-b", status="backlog")
    _seed(item_id="bd-unnamed-a", status="active")
    _seed(item_id="bd-named", token=create_claim_token(client=_tenant()))
    _seed(item_id="bd-closed", status="closed")

    rows = claim_token_missing_items(project_root=tmp_path, repo="repo", config=_config())

    assert [(row.id, row.kind, row.urgency) for row in rows] == [
        (f"{_ROW_PREFIX}bd-unnamed-a", "hygiene", "high"),
        (f"{_ROW_PREFIX}bd-unnamed-b", "hygiene", "high"),
    ]
    first = rows[0]
    assert first.source_ref.repo == "repo"
    assert first.source_ref.work_item == "bd-unnamed-a"
    assert "bd-unnamed-a names no current claim token" in first.summary
    assert "claim-token-missing" in first.summary
    assert first.handoff.kind == "shell"
    assert "/bin/migrate_claim_tokens.py " in first.handoff.command
    assert first.handoff.command.endswith(f"--project-root {tmp_path}")
    assert CONFIRM_FLAG not in first.handoff.command


@pytest.mark.parametrize("claim_tokens", [False, None])
def test_before_cutover_the_lane_composes_nothing_and_reads_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    claim_tokens: bool | None,
) -> None:
    _write_config(tmp_path, claim_tokens=claim_tokens)
    _seed(item_id="bd-unnamed")
    reads: list[str] = []
    monkeypatch.setattr(
        _store_claim_token_migration,
        "make_beads_client",
        lambda **_kwargs: reads.append("read"),
    )

    assert claim_token_missing_items(project_root=tmp_path, repo="repo", config=_config()) == []
    assert reads == []


def test_build_attention_surfaces_the_row_until_the_migration_pass_names_a_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(needs_attention, "spec_next", lambda **_kwargs: None)
    monkeypatch.setattr(needs_attention, "currency_staleness_items", lambda **_kwargs: [])
    _write_config(tmp_path, claim_tokens=True)
    _seed(item_id="bd-unnamed", status="backlog")

    def _rows() -> list[str]:
        attention = build_attention(project_root=tmp_path, repo_name="repo", include_hygiene=False)
        return [item.id for item in attention if item.id.startswith(_ROW_PREFIX)]

    assert _rows() == [f"{_ROW_PREFIX}bd-unnamed"]

    assert migrate_claim_tokens(client=_tenant(), apply=True).complete is True

    assert _rows() == []
