"""History-reader edges of the spec-tier relinking valve."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _drive_relink_spec_tier_valve as valve
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action

_TOPIC = "filed-under-a-different-stem"


def _raise_os_error(path: Path, *, encoding: str | None = None, errors: str | None = None) -> str:
    _ = (path, encoding, errors)
    raise OSError


def _proposal(*, spec: Path, version: str, decision: str | None, topic: str = _TOPIC) -> Path:
    changes = spec / "history" / version / "proposed_changes"
    changes.mkdir(parents=True, exist_ok=True)
    _ = (changes / f"{topic}.md").write_text("proposal\n", encoding="utf-8")
    revision = changes / f"{topic}-revision.md"
    if decision is not None:
        _ = revision.write_text(f"---\ndecision: {decision}\n---\n", encoding="utf-8")
    return revision


def test_history_topics_distinguish_an_archived_topic_from_a_rejected_one(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "SPECIFICATION"

    assert valve.proposal_topic_state(spec_root=spec, topic=_TOPIC) == "unknown"
    (spec / "history").mkdir(parents=True)
    assert valve.proposal_topic_state(spec_root=spec, topic=_TOPIC) == "unknown"
    _ = (spec / "history" / "not-a-version").mkdir()
    accepted = _proposal(spec=spec, version="v001", decision="accept")

    assert accepted.is_file()
    assert valve.proposal_topic_state(spec_root=spec, topic=_TOPIC) == "archived"
    _ = _proposal(spec=spec, version="v002", decision="reject")
    assert valve.proposal_topic_state(spec_root=spec, topic=_TOPIC) == "rejected"


def test_history_reader_tolerates_incomplete_revision_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = tmp_path / "SPECIFICATION"
    _ = _proposal(spec=spec, version="v001", decision=None)
    malformed = _proposal(spec=spec, version="v002", decision=None, topic="malformed")
    closed = _proposal(spec=spec, version="v003", decision=None, topic="closed")
    open_record = _proposal(spec=spec, version="v004", decision=None, topic="open")
    unreadable = _proposal(spec=spec, version="v005", decision=None, topic="unreadable")
    _ = malformed.write_text("not front matter\n", encoding="utf-8")
    _ = closed.write_text("---\nfield: value\n---\n", encoding="utf-8")
    _ = open_record.write_text("---\nfield: value\n", encoding="utf-8")
    _ = unreadable.write_text("---\ndecision: accept\n---\n", encoding="utf-8")

    assert valve.proposal_topic_state(spec_root=spec, topic=_TOPIC) == "archived"
    assert valve.proposal_topic_state(spec_root=spec, topic="malformed") == "archived"
    assert valve.proposal_topic_state(spec_root=spec, topic="closed") == "archived"
    assert valve.proposal_topic_state(spec_root=spec, topic="open") == "archived"
    monkeypatch.setattr(Path, "read_text", _raise_os_error)
    assert valve.proposal_topic_state(spec_root=spec, topic="unreadable") == "archived"


def test_a_rejected_archived_topic_is_refused_without_a_ledger_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    fixture = runpy.run_path(str(Path(__file__).with_name("test_drive_relink_spec_tier_valve.py")))
    repo = fixture["_repo"](tmp_path=tmp_path, topic=None)
    _ = _proposal(
        spec=repo / "SPECIFICATION",
        version="v001",
        decision="reject",
    )
    fixture["_item"]()

    result = run_human_valve_action(
        repo=repo,
        action_id=f"relink-spec-tier:bd-ib-relink:{_TOPIC}",
        identity=InvokerIdentity(invoker="human:chad", invoker_source="flag"),
    )

    assert result["domain_error"] == "rejected-topic"


def test_the_primary_relink_fixture_can_leave_its_proposal_unfiled(tmp_path: Path) -> None:
    fixture = runpy.run_path(str(Path(__file__).with_name("test_drive_relink_spec_tier_valve.py")))

    repo = fixture["_repo"](tmp_path=tmp_path, topic=None)

    assert not (repo / "SPECIFICATION" / "proposed_changes" / f"{_TOPIC}.md").exists()
