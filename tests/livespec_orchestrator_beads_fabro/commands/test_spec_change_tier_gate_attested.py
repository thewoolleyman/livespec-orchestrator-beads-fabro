"""A standing human attestation beats the model in the classification gate.

The `release-spec-tier` valve attests that an existing clause states a held
item's behaviour. The autonomy-tier bullet of `SPECIFICATION/contracts.md` says
the attestation is used "without requiring model agreement", that "a change
elsewhere in the specification does not void it", and that "a change to the
attested input or to the cited clause voids it".

EVERY CASE READS THE JUDGE CALL COUNT, because the release is a claim that no
model was consulted and a return value cannot carry that: a gate that asked the
model again and happened to be told `stated` returns the identical outcome.

THE VOIDING CASE IS THE SAME ITEM ON THE SAME LEDGER as the surviving ones, so the
only difference between "still released" and "classified afresh" is the cited
clause's text.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    classify_item_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_outcome import (
    SpecChangeTierOutcome,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_DISPATCH,
    STAGE_FILING,
    STAGE_RELEASE,
)
from livespec_orchestrator_beads_fabro.commands._spec_tier_attestation import attestation_comment
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import clauses_named
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-attested-gate"
_HEADING = "## A governing clause"
_OTHER = "## Another clause"
_UNSTATED = (
    '{"kind": "unstated", "stated_by": [], "generalization_target": '
    f'"{_HEADING}", "rationale": "the ratified text does not state it"}}'
)


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


def _spec_text(*, body: str = "The clause body.", other: str = "Other body.") -> str:
    return f"# Contracts\n\n{_HEADING}\n\n{body}\n\n{_OTHER}\n\n{other}\n"


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"acp_nodes": {"dod_gate": {"agent": "claude-acp",'
        ' "model": "claude-opus-5"}}}}}',
        encoding="utf-8",
    )
    _ = (spec / "contracts.md").write_text(_spec_text(), encoding="utf-8")
    return repo


def _revise(*, repo: Path, version: int, text: str) -> None:
    spec = repo / "SPECIFICATION"
    (spec / "history" / f"v{version:03d}").mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(text, encoding="utf-8")


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="feature",
        status="backlog",
        title="Hold an unstated feature for its proposal",
        description="New observable behaviour.",
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


def _install_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: tuple[str, ...]
) -> Path:
    ledger = tmp_path / "judge-calls"
    script = tmp_path / "fake-judge"
    arms = "\n".join(
        f"{index})\n  cat <<'REPLY'\n{reply}\nREPLY\n  ;;"
        for index, reply in enumerate(replies, start=1)
    )
    _ = script.write_text(
        "#!/bin/sh\n"
        f"echo call >> {ledger}\n"
        f"calls=$(wc -l < {ledger} | tr -d ' ')\n"
        f"case $calls in\n{arms}\n*)\n  exit 1\n  ;;\nesac\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))
    return ledger


def _calls(*, ledger: Path) -> int:
    return len(ledger.read_text(encoding="utf-8").splitlines()) if ledger.is_file() else 0


def _comment_count(*, repo: Path) -> int:
    return len(read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM))


def _classify(*, repo: Path, stage: str) -> SpecChangeTierOutcome:
    return classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=stage
    )


def _attest(*, repo: Path, version: str) -> None:
    clause = clauses_named(spec_tree={"contracts.md": _spec_text()}, headings=[_HEADING])[0]
    append_work_item_comment(
        path=_config(repo=repo),
        work_item_id=_ITEM,
        body=attestation_comment(
            item=_item(), actor="human:chad", clause=clause, spec_version=version
        ),
    )


def test_an_attestation_releases_a_held_feature_and_survives_what_it_must_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _UNSTATED, "feature", _UNSTATED),
    )
    append_work_item(path=_config(repo=repo), item=_item())
    held = _classify(repo=repo, stage=STAGE_FILING)
    assert held.is_spec_change is True
    assert _calls(ledger=ledger) == 2

    _attest(repo=repo, version="1")
    released = _classify(repo=repo, stage=STAGE_RELEASE)

    assert released.is_spec_change is False
    assert released.recorded.tier == "none"
    assert released.recorded.verdict_kind == "stated"
    assert _calls(ledger=ledger) == 2
    standing = _comment_count(repo=repo)

    again = _classify(repo=repo, stage=STAGE_DISPATCH)
    assert again.reused is True
    assert _comment_count(repo=repo) == standing

    _revise(repo=repo, version=2, text=_spec_text(other="Other body, amended."))
    elsewhere = _classify(repo=repo, stage=STAGE_DISPATCH)
    assert elsewhere.is_spec_change is False
    assert _calls(ledger=ledger) == 2

    _revise(repo=repo, version=3, text=_spec_text(body="The clause body, rewritten."))
    voided = _classify(repo=repo, stage=STAGE_DISPATCH)
    assert voided.is_spec_change is True
    assert _calls(ledger=ledger) == 4
