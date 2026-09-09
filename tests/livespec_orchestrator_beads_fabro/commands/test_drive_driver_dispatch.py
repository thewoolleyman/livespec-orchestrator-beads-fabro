"""Tests for `driver-dispatch:<id>` — the journaled door for host-only work.

Every test drives the PUBLIC operator surface (`drive.run_action` /
`drive.main`) and then reads the ledger and the journal FILE back, rather than
inspecting the handler's return value alone. That is deliberate: the door's
whole point is that the transition is journaled durably, and a `journal` key in
a response payload is not a journal — the response is gone the moment the
invocation returns, which is exactly why the door rules in
`SPECIFICATION/contracts.md` refuse to count one.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands import drive
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACTS = _REPO_ROOT / "SPECIFICATION" / "contracts.md"
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _operator() -> InvokerIdentity:
    return InvokerIdentity(invoker="human:cw", invoker_source="flag")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-host",
        type="task",
        status="ready",
        title="Rebuild the host commit hook",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        factory_safety="mutates-host-machinery",
    )
    return replace(base, **overrides)


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    path = repo / _JOURNAL
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# The action id is accepted at all (SPECIFICATION/contracts.md)
# ---------------------------------------------------------------------------


def test_driver_dispatch_is_no_longer_an_unsupported_action_id(tmp_path: Path) -> None:
    """The verb the spec fully describes is reachable from the executor."""
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item())

    result = drive.run_action(
        repo=repo, action_id="driver-dispatch:bd-ib-host", identity=_operator()
    )

    assert "Unsupported action id" not in str(result["summary"])
    assert result["status"] == "green"


def test_driver_dispatch_appears_in_the_unsupported_action_enumeration(tmp_path: Path) -> None:
    """The enumeration an operator is shown must name every accepted verb."""
    repo = _repo(tmp_path)

    result = drive.run_action(repo=repo, action_id="not-an-action", identity=_operator())

    assert result["status"] == "failed"
    assert "driver-dispatch:<id>" in str(result["summary"])


# ---------------------------------------------------------------------------
# Eligibility, enforced in BOTH directions
# ---------------------------------------------------------------------------


def test_driver_dispatch_moves_a_host_only_ready_item_into_active(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item())

    result = drive.run_action(
        repo=repo, action_id="driver-dispatch:bd-ib-host", identity=_operator()
    )

    assert result["status"] == "green"
    assert result["target_status"] == "active"
    assert _fake().show_issue(issue_id="bd-ib-host")["status"] == "active"


def test_driver_dispatch_refuses_a_factory_safe_ready_item(tmp_path: Path) -> None:
    """The scope constraint is a SAFETY property: no claim mechanism exists.

    A factory-safe `ready` item is the Dispatcher's to claim, so admitting it
    here would open exactly the dispatcher/driver race the spec says widening
    this door would require a claim mechanism to survive.
    """
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item(factory_safety=None))

    result = drive.run_action(
        repo=repo, action_id="driver-dispatch:bd-ib-host", identity=_operator()
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "not-host-only"
    assert "factory_safety is non-null" in str(result["summary"])
    assert _fake().show_issue(issue_id="bd-ib-host")["status"] == "ready"
    assert _journal_records(repo=repo) == []


@pytest.mark.parametrize("status", ["backlog", "pending-approval", "active", "acceptance"])
def test_driver_dispatch_refuses_every_lane_but_ready(tmp_path: Path, status: str) -> None:
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item(status=status))

    result = drive.run_action(
        repo=repo, action_id="driver-dispatch:bd-ib-host", identity=_operator()
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
    assert f"expected ready source state for bd-ib-host; found {status}" in str(result["summary"])
    assert _fake().show_issue(issue_id="bd-ib-host")["status"] == status
    assert _journal_records(repo=repo) == []


def test_driver_dispatch_refuses_an_id_that_was_never_filed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = drive.run_action(
        repo=repo, action_id="driver-dispatch:bd-ib-missing", identity=_operator()
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "work-item-not-found"
    assert _journal_records(repo=repo) == []


# ---------------------------------------------------------------------------
# The DURABLE journal record — read back off disk, never off the payload
# ---------------------------------------------------------------------------


def test_driver_dispatch_writes_a_durable_journal_record_carrying_actor_and_session(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item())

    _ = drive.run_action(
        repo=repo,
        action_id="driver-dispatch:bd-ib-host",
        identity=_operator(),
        driver_session="tmux:host-only-worker",
    )

    [record] = _journal_records(repo=repo)
    assert record["stage"] == "human-valve-driver-dispatch"
    assert record["work_item_id"] == "bd-ib-host"
    assert record["driver_session"] == "tmux:host-only-worker"
    assert record["from_status"] == "ready"
    assert record["to_status"] == "active"
    assert record["factory_safety"] == "mutates-host-machinery"
    # Stamped by the append layer, which is the only place the attribution
    # contract lets the acting identity come from.
    assert record["invoker"] == "human:cw"
    assert record["invoker_source"] == "flag"
    assert record["at"] != ""


def test_driver_dispatch_journals_the_invoker_when_no_session_is_asserted(
    tmp_path: Path,
) -> None:
    """The session that presses the door is the session that drives the item."""
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item())

    _ = drive.run_action(repo=repo, action_id="driver-dispatch:bd-ib-host", identity=_operator())

    [record] = _journal_records(repo=repo)
    assert record["driver_session"] == "human:cw"


def test_driver_dispatch_treats_a_blank_session_assertion_as_no_assertion(
    tmp_path: Path,
) -> None:
    """A blank reference is not a reference; journaling one names nobody."""
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item())

    _ = drive.run_action(
        repo=repo,
        action_id="driver-dispatch:bd-ib-host",
        identity=_operator(),
        driver_session="   ",
    )

    [record] = _journal_records(repo=repo)
    assert record["driver_session"] == "human:cw"


def test_driver_dispatch_republishes_the_record_it_wrote(tmp_path: Path) -> None:
    """The payload's `journal` key must be the SAME object that reached disk."""
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item())

    result = drive.run_action(
        repo=repo,
        action_id="driver-dispatch:bd-ib-host",
        identity=_operator(),
        driver_session="tmux:host-only-worker",
    )

    [record] = _journal_records(repo=repo)
    payload = result["journal"]
    assert isinstance(payload, dict)
    assert {key: record[key] for key in payload} == payload


# ---------------------------------------------------------------------------
# `--driver-session` transport scoping
# ---------------------------------------------------------------------------


def test_driver_session_is_refused_for_an_action_that_cannot_deliver_it(
    tmp_path: Path,
) -> None:
    """Accepted-and-discarded is the one outcome a scoped input must not have."""
    repo = _repo(tmp_path)
    append_work_item(path=_config(), item=_item())

    result = drive.run_action(
        repo=repo,
        action_id="approve:bd-ib-host",
        identity=_operator(),
        driver_session="tmux:host-only-worker",
    )

    assert result["status"] == "failed"
    assert "accepted only by 'driver-dispatch:<id>'" in str(result["summary"])
    assert _fake().show_issue(issue_id="bd-ib-host")["status"] == "ready"


def test_main_carries_the_driver_session_flag_into_the_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    seen: list[str | None] = []

    def fake_run_action(*, driver_session: str | None = None, **_: object) -> dict[str, object]:
        seen.append(driver_session)
        return {"action_id": "driver-dispatch:bd-ib-host", "status": "green", "summary": "ok"}

    monkeypatch.setattr(drive, "run_action", fake_run_action)

    exit_code = drive.main(
        argv=[
            "--repo",
            str(repo),
            "--action",
            "driver-dispatch:bd-ib-host",
            "--driver-session",
            "tmux:host-only-worker",
            "--invoker",
            "human:cw",
        ]
    )

    assert exit_code == 0
    assert seen == ["tmux:host-only-worker"]
    assert "driver-dispatch" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Specification coverage — the advertised-but-unspecified failure class
# ---------------------------------------------------------------------------


def test_driver_dispatch_ships_with_non_zero_specification_coverage(tmp_path: Path) -> None:
    """A first-class operator verb may not ship advertised-but-unspecified.

    The control matters as much as the assertion: the same scan run for a name
    the specification does NOT carry returns zero, so a green result here means
    "the spec covers this verb" rather than "the scan could not have found
    anything".
    """
    spec = _CONTRACTS.read_text(encoding="utf-8")

    assert "#### `driver-dispatch:<id>`" in spec
    assert spec.count("driver-dispatch") > 0
    assert spec.count("driver-dispatch-never-specified") == 0
    # And the executor advertises exactly what the spec describes.
    repo = _repo(tmp_path)
    summary = str(drive.run_action(repo=repo, action_id="nope", identity=_operator())["summary"])
    assert "driver-dispatch:<id>" in summary
