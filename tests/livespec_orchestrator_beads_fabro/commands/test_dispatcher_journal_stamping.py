"""The append layer stamps the invoker once and refuses a forged one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    DelegationGrant,
    InvokerIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile


def _identity(*, source: str = "flag") -> InvokerIdentity:
    return InvokerIdentity(invoker="human:cw", invoker_source=source)


def _records(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_every_written_record_carries_the_resolved_invoker(tmp_path: Path) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl", identity=_identity())

    journal.append(record={"stage": "loop-pick"})
    journal.append(record={"stage": "outcome"})

    written = _records(path=tmp_path / "journal.jsonl")
    assert [record["stage"] for record in written] == ["loop-pick", "outcome"]
    assert {record["invoker"] for record in written} == {"human:cw"}
    assert {record["invoker_source"] for record in written} == {"flag"}


def test_the_stamp_records_the_source_the_identity_resolved_from(tmp_path: Path) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl", identity=_identity(source="fallback"))

    journal.append(record={"stage": "loop-pick"})

    assert _records(path=tmp_path / "journal.jsonl")[0]["invoker_source"] == "fallback"


def test_a_journal_built_without_an_identity_still_stamps_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:default")

    JournalFile(path=tmp_path / "journal.jsonl").append(record={"stage": "loop-pick"})

    record = _records(path=tmp_path / "journal.jsonl")[0]
    assert record["invoker"] == "session:default"
    assert record["invoker_source"] == "env"


@pytest.mark.parametrize("forged", ["invoker", "invoker_source"])
def test_a_caller_supplied_stamp_field_is_refused(tmp_path: Path, forged: str) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl", identity=_identity())

    with pytest.raises(ValueError, match=forged):
        journal.append(record={"stage": "loop-pick", forged: "forged:identity"})

    assert not (tmp_path / "journal.jsonl").exists()


def test_the_refusal_names_every_forged_field(tmp_path: Path) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl", identity=_identity())

    with pytest.raises(ValueError, match="invoker, invoker_source"):
        journal.append(
            record={"stage": "x", "invoker": "forged", "invoker_source": "flag"},
        )


def test_a_verified_delegation_is_stamped_and_cannot_be_supplied(tmp_path: Path) -> None:
    identity = InvokerIdentity(
        invoker="delegate:coordinator",
        invoker_source="flag",
        delegation=DelegationGrant(ref="R1", grantor="human:pat", record="r"),
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl", identity=identity)

    journal.append(record={"stage": "valve"})
    with pytest.raises(ValueError, match="delegation"):
        journal.append(record={"stage": "valve", "delegation": {}})

    written = _records(path=tmp_path / "journal.jsonl")
    assert written[0]["delegation"] == {"ref": "R1", "grantor": "human:pat", "record": "r"}
