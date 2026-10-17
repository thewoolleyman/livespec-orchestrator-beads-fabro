"""Consumer-tier acceptance for SPECIFICATION/scenarios.md Scenario 186.

Binds "## Scenario 186 — A provider exhaustion observed on one credential
account does not refuse dispatch on another account of the same vendor". Its
six Given/When/Then blocks map 1:1 to the six cases below, and each is driven
through the surface the scenario names rather than through a helper:

- "A record names the credential identity the observing dispatch projected" —
  `post_run_dispositions`, the post-run disposition sequence a real dispatch
  runs, over a terminal outcome built by `fabro_run_terminal_outcome` from a
  Fabro payload, so the vendor is classified by production code.
- "A newer record for one identity does not retire another identity's record" —
  `live_provider_exhaustions`, "the records the Dispatcher reads".
- the four admission cases — `filter_eligible_candidates`, the mechanical
  eligibility filter both admission legs pass through, whose first per-row
  refusal is the provider-exhaustion gate.

WHAT MAKES THIS A SCENARIO BINDING AND NOT A UNIT TEST. Each admission case
runs against a real repository checkout and a real on-disk journal, and the
account the valve compares against is taken from the verdict's own journaled
session-headroom assessment rather than passed to the gate by hand — which is
the join the scenario is actually about: the record is labelled by one
dispatch's admission and read by another's.

THE INCIDENT, measured 2026-10-16. The account selection rotated the Anthropic
choice from `anthropic-1` to `anthropic-3` at 16:52Z. Four in-flight
`anthropic-1` runs met the session limit between 17:35Z and 17:41Z, and the
records their closes minted refused every `anthropic-3` dispatch until
17:50:19Z — one of them a `petri-factory-on-gmktec` dispatch refused at 17:38Z
naming `record_expires_at` 17:50:19Z. Every refusal was right about the vendor
and wrong about the allowance.

Everything is HERMETIC: repository and journal live under `tmp_path`, the
work-item store is the fake, no provider is reached and no adapter is launched.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import SessionHeadroomReading
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    session_headroom_assessment_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    live_provider_exhaustions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_io import (
    ABSENT_CREDENTIAL_IDENTITY,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroInspectResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_NOW = "2026-10-16T17:41:00Z"
_LIVE_EXPIRY = "2099-01-01T00:00:00Z"
_ITEM = "bd-ib-b53dhr"
# `anthropic-1`, whose allowance the four in-flight runs spent, and
# `anthropic-3`, which the selection had already rotated onto. Opaque digests
# of the kind `projected_credential_identity` returns: only inequality matters.
_EXHAUSTED_ACCOUNT = "1111111111111111"
_ROTATED_ACCOUNT = "2222222222222222"
_ACP_WRAPPER = "ACP protocol error"
_ANTHROPIC_CEILING = (
    "You've hit your usage limit. Visit claude.ai/settings/usage for details "
    "or try again at 2026-10-16T22:00:00Z"
)


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _item(*, status: str = "ready", assignee: str | None = None) -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status=status,
        title="Key the provider-exhaustion record on the credential account",
        description="## Definition of Done\n\n- The product satisfies one assertion.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=assignee,
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd-ib",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"adopted_assertion_count_ceiling": None},
                },
            }
        ),
        encoding="utf-8",
    )
    return repo


def _ceiling_outcome() -> DispatchOutcome:
    """A terminal provider-usage-limit outcome, classified by production code."""
    payload: list[object] = [
        {
            "status": {"kind": "failed"},
            "failure": {
                "causes": [_ACP_WRAPPER, _ANTHROPIC_CEILING],
                "category": "transient_infra",
            },
        }
    ]
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=build_plan(
            repo=Path("/nonexistent"),
            work_item_id=_ITEM,
            workflow_toml=Path("/nonexistent/wf.toml"),
            goal_file=Path("/nonexistent/goal.md"),
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=Path("/nonexistent/janitor-co"),
        ),
        run_id="01M52QRP5WZH",
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
        ),
        exit_code=1,
        stderr="",
    )
    assert outcome is not None
    assert outcome.provider_usage_limit_provider == "anthropic"
    return outcome


def _assessment_record(*, identity: str) -> dict[str, object]:
    """The admission session-headroom record the dispatch's own evaluation wrote."""
    return session_headroom_assessment_record(
        work_item_id=_ITEM,
        floor_percent=20,
        assessments=(_reading(identity=identity),),
    )


def _reading(*, identity: str) -> SessionHeadroomReading:
    return SessionHeadroomReading(
        credential_identity=identity,
        observed_at=_NOW,
        utilization_percent=95.0,
        remaining_percent=5.0,
    )


def _observation(*, identity: str | None) -> dict[str, object]:
    return {
        "stage": "provider-exhaustion-observed",
        "work_item_id": "bd-ib-p4clqz",
        "provider": "anthropic",
        "credential_identity": identity,
        "governing_condition": "provider_usage_limit",
        "record_expires_at": _LIVE_EXPIRY,
    }


def _verdict(*, identity: str) -> AcpPreflightVerdict:
    """A viable verdict carrying the account its own headroom reading named."""
    return AcpPreflightVerdict(
        fallback_enabled=True,
        success_critical=("implement",),
        headroom_assessments=(_reading(identity=identity),),
        session_headroom_floor_percent=20,
    )


def _admission(
    *, repo: Path, journal: JournalFile, identity: str
) -> tuple[list[WorkItem], list[DispatchOutcome]]:
    return filter_eligible_candidates(
        repo=repo,
        preflight=_verdict(identity=identity),
        candidates=[_item()],
        journal=journal,
    )


def test_scenario186_a_record_names_the_account_the_observing_dispatch_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a dispatch whose admission projected credential identity "A"."""
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    append_work_item(path=_config(repo_root=repo), item=_item(status="active", assignee="fabro"))
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record=_assessment_record(identity=_EXHAUSTED_ACCOUNT))

    post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=repo,
        item=_item(status="active", assignee="fabro"),
        outcome=_ceiling_outcome(),
        journal=journal,
        wall_clock_seconds=42.0,
        dispatch_context_size=100,
        token_supplier=lambda: "token",
    )

    minted = [
        record
        for record in _records(path=journal.path)
        if record["stage"] == "provider-exhaustion-observed"
    ]
    assert [record["provider"] for record in minted] == ["anthropic"]
    assert [record["credential_identity"] for record in minted] == [_EXHAUSTED_ACCOUNT]


def test_scenario186_a_newer_record_for_one_account_does_not_retire_anothers(
    tmp_path: Path,
) -> None:
    """When the Dispatcher reads the live provider-exhaustion records."""
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record=_observation(identity=_EXHAUSTED_ACCOUNT))
    journal.append(record=_observation(identity=_ROTATED_ACCOUNT))

    live = live_provider_exhaustions(journal_path=journal.path, now_iso=_NOW)

    assert [record.credential_identity for record in live] == [
        _ROTATED_ACCOUNT,
        _EXHAUSTED_ACCOUNT,
    ]


def test_scenario186_a_dispatch_on_another_account_is_admitted_while_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Then the record does not refuse the item."""
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    append_work_item(path=_config(repo_root=repo), item=_item())
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record=_observation(identity=_EXHAUSTED_ACCOUNT))

    admitted, refused = _admission(repo=repo, journal=journal, identity=_ROTATED_ACCOUNT)

    assert refused == []
    assert [item.id for item in admitted] == [_ITEM]


def test_scenario186_a_dispatch_on_the_same_account_is_refused_while_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Then the item is refused naming the record and its expiry."""
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    append_work_item(path=_config(repo_root=repo), item=_item())
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record=_observation(identity=_EXHAUSTED_ACCOUNT))

    admitted, refused = _admission(repo=repo, journal=journal, identity=_EXHAUSTED_ACCOUNT)

    assert admitted == []
    assert [outcome.stage for outcome in refused] == ["provider-exhaustion"]
    assert f"credential_identity={_EXHAUSTED_ACCOUNT}" in refused[0].detail
    assert f"record_expires_at={_LIVE_EXPIRY}" in refused[0].detail


def test_scenario186_a_record_without_an_account_keeps_vendor_wide_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Then the item is refused naming the record and its expiry."""
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    append_work_item(path=_config(repo_root=repo), item=_item())
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record=_observation(identity=None))

    admitted, refused = _admission(repo=repo, journal=journal, identity=_ROTATED_ACCOUNT)

    assert admitted == []
    assert [outcome.stage for outcome in refused] == ["provider-exhaustion"]
    assert "credential_identity=None" in refused[0].detail
    assert f"record_expires_at={_LIVE_EXPIRY}" in refused[0].detail


def test_scenario186_an_unreadable_account_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Then the record refuses the item."""
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    append_work_item(path=_config(repo_root=repo), item=_item())
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record=_observation(identity=_EXHAUSTED_ACCOUNT))

    admitted, refused = _admission(repo=repo, journal=journal, identity=ABSENT_CREDENTIAL_IDENTITY)

    assert admitted == []
    assert [outcome.stage for outcome in refused] == ["provider-exhaustion"]
    assert f"credential_identity={_EXHAUSTED_ACCOUNT}" in refused[0].detail


def _records(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
