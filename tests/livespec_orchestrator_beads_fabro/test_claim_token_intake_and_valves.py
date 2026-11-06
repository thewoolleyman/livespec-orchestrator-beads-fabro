"""Claim-token adoption at intake and the human lifecycle valves."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.unsafe import unsafe_perform_io


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="claim-token-intake",
        prefix="claim-token-intake",
        server_user="claim-token-intake",
        database="claim-token-intake",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _enable_claim_tokens(*, repo: Path) -> None:
    (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"claim_tokens":true}}}',
        encoding="utf-8",
    )


def _seed(*, config: StoreConfig, issue_id: str, status: str = "backlog") -> str:
    client = make_beads_client(config=config)
    token = create_claim_token(client=client)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title=issue_id,
            description="",
            priority=2,
            assignee=None,
            created_at="2026-11-06T00:00:00Z",
            labels=[],
            metadata={CLAIM_TOKEN_METADATA_KEY: token},
            spec_id=None,
            parent_id=None,
        )
    )
    client.update_issue(issue_id=issue_id, status=status)
    return token


def _backlog_checklist() -> DefinitionOfReadyChecklist:
    return DefinitionOfReadyChecklist(
        single_coherent_done=False,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )


def test_intake_wins_the_current_token_before_its_status_write(tmp_path: Path) -> None:
    """Intake's routing write closes its current token and names a successor."""
    reset_fake_singleton()
    repo = tmp_path / "repo"
    repo.mkdir()
    _enable_claim_tokens(repo=repo)
    config = _config(repo_root=repo)
    token = _seed(config=config, issue_id="bd-claim-intake")

    result = apply_intake_dor(
        path=config,
        item_id="bd-claim-intake",
        checklist=_backlog_checklist(),
    )

    assert unsafe_perform_io(result.unwrap()) == "backlog"
    client = make_beads_client(config=config)
    assert client.show_issue(issue_id=token)["status"] == "closed"
    successor = client.show_issue(issue_id="bd-claim-intake")["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert successor != token
    reset_fake_singleton()
