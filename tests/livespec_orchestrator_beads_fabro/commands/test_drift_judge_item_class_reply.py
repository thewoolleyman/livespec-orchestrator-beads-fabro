"""The shared judge chain accepts a classification's bare-word reply.

The spec-stated classification is one BARE WORD (`feature`, `bug`, `chore` or
`non_functional`), while the judgement is a JSON object. The shared candidate
chain advances to its next candidate on any reply its `is_verdict` check does
not recognise, so a chain built only for the JSON shape discards every
classification answer as unparseable and the classification can never run: the
cadence points then record a did-not-run cause for every item in the tenant.

THE JUDGE IS STOOD IN AT THE EXECUTABLE, as the Definition-of-Done judgement's
own tests stand theirs in, so the argv, the standard-input prompt and the
chain's reply check are all exercised.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    classify_item_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import STAGE_FILING
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-reply"


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {"prefix": "bd-ib"},
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    _ = (spec / "contracts.md").write_text(
        "# Contracts\n\n## A governing clause\n\nThe clause body.\n", encoding="utf-8"
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="feature",
        status="backlog",
        title="Fix a typo in a message",
        description="A wording fix.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: str) -> None:
    script = tmp_path / "fake-judge"
    _ = script.write_text(f"#!/bin/sh\necho {reply}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def test_a_bare_word_classification_reply_is_a_recorded_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply="bug")
    append_work_item(path=_config(repo=repo), item=_item())

    outcome = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )

    assert outcome.cause is None
    assert outcome.recorded is not None
    assert outcome.recorded.classification == "bug"
    assert outcome.recorded.is_spec_change is False
