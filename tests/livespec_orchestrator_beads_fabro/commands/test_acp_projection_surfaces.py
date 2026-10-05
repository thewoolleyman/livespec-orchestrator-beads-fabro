"""The operator-facing surfaces of the ACP projection: facts, posture, valve.

Binds the three consumer clauses of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority":

- the two attention rows, `hygiene:model-fallback-projection:<repo>:<run>:<node>`
  at `high` urgency with a server-qualified `shell` inspection handoff, and
  the aggregate `hygiene:model-fallback:<repo>:<node>` whose summary comes
  from "the newest unresolved observation";
- the loop posture -- "an unattended loop MUST stop further picking for that
  repository", while "a human-attended `--item` dispatch MAY proceed only
  after the high-urgency warning is surfaced before claim and does not clear
  the fact";
- the clearance valve, "attributed, reason-required, append-only ... naming
  that exact fact id", which "retires the fact only and MUST NOT mint,
  retire, or reinterpret a hold".

THE CONTROL THAT MATTERS MOST IS THE ATTENDED / UNATTENDED ASYMMETRY, and
it is asserted in BOTH directions over one journal: an implementation that
stopped both, or stopped neither, would pass every other assertion here.

THE SECOND IS THAT CLEARANCE TOUCHES NO HOLD. The journal in that test
carries a live typed availability hold as well as the projection fact, so
a valve that retired by stage-name overlap would be caught rather than
merely unasserted.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _acp_projection_clear,
    _dispatcher_loop_command,
    _dispatcher_pre_dispatch_wall,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import hold_observation_record
from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    AcpProjectionFailureTarget,
    projection_failure_fact_id,
    projection_failure_record,
    unresolved_projection_failures,
)
from livespec_orchestrator_beads_fabro.commands._acp_projection_posture import (
    PROJECTION_ATTENDED_STAGE,
    PROJECTION_STOP_STAGE,
    acp_projection_posture,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_model_fallback import (
    model_fallback_items,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main as dispatcher_main

_OCCURRED = "2026-09-12T12:00:00Z"
_WITHIN_EXPIRY = "2026-09-12T12:10:00Z"
_RUN_ID = "01M3R750MNDHENDYKY5MBKRYXJ"
_HP_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_REPO_NAME = "livespec-orchestrator-beads-fabro"

_FACT_ID = projection_failure_fact_id(repo=_REPO_NAME, run_id=_RUN_ID, node="implement")


def _failure_line(*, node: str = "implement", reason: str = "timed-out") -> dict[str, Any]:
    return projection_failure_record(
        target=AcpProjectionFailureTarget(
            repo=_REPO_NAME,
            run_id=_RUN_ID,
            node=node,
            factory_name="hp",
            factory_server_url=_HP_SERVER,
        ),
        reason=reason,
        exit_code=124,
    )


def _warning_line(
    *, node: str = "implement", occurred_at: str = _OCCURRED, key: str
) -> dict[str, Any]:
    return {
        "stage": "acp-model-fallback-observed",
        "schema_version": 1,
        "warning_id": f"acpwarn-{key}",
        "node": node,
        "occurred_at": occurred_at,
        "candidate_display_name": f"display {key}",
        "candidate_key": key,
        "availability_key": "codex",
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "event_id": f"ev-{key}",
        "candidate_index": 1,
        "work_item_id": "bd-ib-xtgwpz",
    }


def _hold_line() -> dict[str, Any]:
    built = hold_observation_record(
        failure=AcpAvailabilityFailure(
            cause="quota",
            scope="availability-domain",
            hold_key="codex",
            availability_key="codex",
            candidate_key=None,
            source="protocol.message",
        ),
        evidence_kind="acp-failover-event",
        evidence_id="ev-hold",
        occurred_at=_OCCURRED,
        work_item_id="bd-ib-xtgwpz",
        node="implement",
    )
    assert isinstance(built, dict)
    return dict(built)


def _journal(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


def _ids(*, items: list[Any]) -> list[str]:
    return [item.id for item in items]


def test_a_projection_failure_renders_one_high_urgency_server_qualified_row(
    tmp_path: Path,
) -> None:
    """The fact's id, kind, urgency, source reference, summary and handoff."""
    _ = _journal(tmp_path=tmp_path, records=(_failure_line(),))
    rows = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)
    assert _ids(items=rows) == [_FACT_ID]
    row = rows[0]
    assert (row.kind, row.urgency) == ("hygiene", "high")
    assert row.source_ref.repo == _REPO_NAME
    assert row.source_ref.path == "tmp/fabro-dispatch-journal.jsonl"
    assert row.handoff.kind == "shell"
    # The SAME server-qualified read reconciliation performs.
    assert row.handoff.command.endswith(f"events {_RUN_ID} --json --server {_HP_SERVER}")
    assert _RUN_ID in row.summary
    assert "implement" in row.summary
    assert "hp" in row.summary
    assert "timed-out" in row.summary


def test_the_fact_renders_byte_identically_over_an_unchanged_journal(
    tmp_path: Path,
) -> None:
    """Deterministic: the row carries no clock and no host-dependent text."""
    _ = _journal(tmp_path=tmp_path, records=(_failure_line(), _failure_line()))
    first = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)
    second = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)
    assert [row.summary for row in first] == [row.summary for row in second]


def test_the_warning_row_aggregates_per_node_from_the_newest_observation(
    tmp_path: Path,
) -> None:
    """One row per node, and the NEWEST live observation supplies its summary."""
    _ = _journal(
        tmp_path=tmp_path,
        records=(
            _warning_line(key="older"),
            _warning_line(key="newest", occurred_at="2026-09-12T12:05:00Z"),
            _warning_line(node="pr", key="publish"),
        ),
    )
    rows = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)
    assert _ids(items=rows) == [
        f"hygiene:model-fallback:{_REPO_NAME}:implement",
        f"hygiene:model-fallback:{_REPO_NAME}:pr",
    ]
    implement = rows[0]
    assert implement.kind == "hygiene"
    assert implement.urgency in {"high", "medium", "low"}
    assert implement.source_ref.work_item == "bd-ib-xtgwpz"
    assert "display newest" in implement.summary
    assert "2 unresolved observations" in implement.summary
    assert implement.handoff.kind == "shell"
    assert "acp-model-fallback" in implement.handoff.command
    assert "implement" in implement.handoff.command


def test_a_warning_with_no_work_item_still_renders_a_row(tmp_path: Path) -> None:
    """Provenance is optional; the row is not."""
    line = _warning_line(key="anon")
    line["work_item_id"] = ""
    _ = _journal(tmp_path=tmp_path, records=(line,))
    rows = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)
    assert rows[0].source_ref.work_item is None
    assert "1 unresolved" not in rows[0].summary


def test_a_repository_with_no_projection_records_composes_no_rows(tmp_path: Path) -> None:
    """The lane is additive: an untouched repository contributes nothing."""
    assert model_fallback_items(project_root=tmp_path, repo=_REPO_NAME) == []


def test_an_unreadable_config_degrades_the_handoff_binary_not_the_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row's value is the run and server it names, so it survives."""

    def _refuse(**_kwargs: object) -> str:
        raise OSError("config volume gone")

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_model_fallback."
        "resolve_fabro_bin",
        _refuse,
    )
    _ = _journal(tmp_path=tmp_path, records=(_failure_line(),))
    rows = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)
    assert rows[0].handoff.command.startswith("fabro events ")


def test_the_unattended_posture_stops_picking_while_the_attended_one_proceeds(
    tmp_path: Path,
) -> None:
    """The asymmetry, asserted in both directions over ONE journal."""
    path = _journal(tmp_path=tmp_path, records=(_failure_line(),))
    unattended = acp_projection_posture(journal_path=path, attended=False)
    attended = acp_projection_posture(journal_path=path, attended=True)
    assert unattended.stop_picking is True
    assert attended.stop_picking is False
    assert "Unattended picking is stopped" in str(unattended.warning)
    assert "may proceed" in str(attended.warning)
    assert unattended.journal_record()["stage"] == PROJECTION_STOP_STAGE
    assert attended.journal_record()["stage"] == PROJECTION_ATTENDED_STAGE
    assert attended.journal_record()["fact_ids"] == [_FACT_ID]


def test_a_clean_journal_leaves_the_posture_silent_and_picking(tmp_path: Path) -> None:
    """No fact, no warning, no stop -- the ordinary pass is untouched."""
    posture = acp_projection_posture(journal_path=tmp_path / "absent.jsonl", attended=False)
    assert (posture.stop_picking, posture.warning) == (False, None)


@dataclass(kw_only=True)
class _LoopStub:
    """The loop-command seams upstream of the posture gate, stubbed out."""

    items: list[Any] = field(default_factory=list)
    journal: Any = None


def _loop_args(*, repo: Path, journal: Path, items: list[str] | None) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal),
        items=items,
        budget=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
    )


def _stub_loop(*, monkeypatch: pytest.MonkeyPatch, journal_path: Path, waves: list[int]) -> None:
    """Stub every loop seam AROUND the posture gate, leaving the gate itself live."""
    module = _dispatcher_loop_command

    @dataclass(kw_only=True)
    class _Journal:
        path: Path
        records: list[dict[str, object]] = field(default_factory=list)

        def append(self, *, record: dict[str, object]) -> None:
            self.records.append(record)

    monkeypatch.setattr(module, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(module, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(module, "prepare", lambda **_kwargs: ([], _Journal(path=journal_path)))
    monkeypatch.setattr(module, "journal_path", lambda **_kwargs: journal_path)
    monkeypatch.setattr(module, "requested_items_preflight_error", lambda **_kwargs: None)
    monkeypatch.setattr(module, "candidates", lambda **_kwargs: [])
    # The criteria wall lives in the SHARED pre-dispatch wall both dispatch
    # paths run, not in the drain's own module; the drain imports the wall as
    # one name. Stub it where it is defined.
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall, "pre_dispatch_criteria_refusal", lambda **_kwargs: None
    )
    monkeypatch.setattr(module, "dispatch_loop_wave", lambda **_kwargs: waves.append(1) or [])


def test_the_unattended_drain_stops_before_reaching_the_dispatch_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate sits BEFORE claim: no wave runs and nothing is refused."""
    path = _journal(tmp_path=tmp_path, records=(_failure_line(),))
    waves: list[int] = []
    _stub_loop(monkeypatch=monkeypatch, journal_path=path, waves=waves)
    code = _dispatcher_loop_command.run_loop_command(
        args=_loop_args(repo=tmp_path, journal=path, items=None)
    )
    # A clean zero, not a refusal: the repository is not broken and no item is
    # at fault.
    assert code == 0
    assert waves == []
    assert "Unattended picking is stopped" in capsys.readouterr().err


def test_an_attended_item_dispatch_surfaces_the_warning_and_does_not_clear_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Surfacing is not clearing: the fact stands into the next pass."""
    path = _journal(tmp_path=tmp_path, records=(_failure_line(),))
    waves: list[int] = []
    _stub_loop(monkeypatch=monkeypatch, journal_path=path, waves=waves)
    code = _dispatcher_loop_command.run_loop_command(
        args=_loop_args(repo=tmp_path, journal=path, items=["bd-ib-xtgwpz"])
    )
    assert code == 0
    assert "may proceed" in capsys.readouterr().err
    # It PROCEEDED past the gate, and the fact is still unresolved.
    assert waves == [1]
    assert [entry.fact_id for entry in unresolved_projection_failures(journal_path=path)] == [
        _FACT_ID
    ]


def test_a_clean_journal_leaves_the_drain_silent_and_dispatching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ordinary pass is untouched: no warning text and the wave still runs."""
    path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    waves: list[int] = []
    _stub_loop(monkeypatch=monkeypatch, journal_path=path, waves=waves)
    code = _dispatcher_loop_command.run_loop_command(
        args=_loop_args(repo=tmp_path, journal=path, items=None)
    )
    assert (code, waves) == (0, [1])
    assert capsys.readouterr().err == ""


def _clear_argv(*, path: Path, **overrides: str) -> list[str]:
    flags = {
        "--fact-id": _FACT_ID,
        "--reason": "the factory was decommissioned; the run is gone for good",
        "--invoker": "human:tester",
        "--journal": str(path),
        "--repo": str(path.parent.parent),
    }
    flags.update(overrides)
    return [
        "clear-model-fallback-projection",
        *(item for pair in flags.items() for item in pair),
    ]


def test_an_attributed_clearance_retires_the_fact_and_touches_no_hold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Append-only, and scoped to the fact: the live typed hold survives."""
    path = _journal(tmp_path=tmp_path, records=(_failure_line(), _hold_line()))
    before = path.read_text(encoding="utf-8")
    assert dispatcher_main(argv=_clear_argv(path=path)) == 0
    assert path.read_text(encoding="utf-8").startswith(before)
    assert unresolved_projection_failures(journal_path=path) == ()
    # The hold the clearance must NOT reach is still live.
    assert read_acp_hold_ledger(journal_path=path, now_iso=_WITHIN_EXPIRY).holds
    assert "CLEARED" in capsys.readouterr().out


def test_the_valve_refuses_a_blank_reason_an_unattributed_caller_and_an_absent_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The three refusals, each naming what the operator must change."""
    path = _journal(tmp_path=tmp_path, records=(_failure_line(),))
    assert (
        dispatcher_main(argv=_clear_argv(path=path, **{"--reason": "   "}))
        == EXIT_PRECONDITION_ERROR
    )
    assert "--reason is blank" in capsys.readouterr().err
    assert (
        dispatcher_main(
            argv=_clear_argv(path=path, **{"--fact-id": "hygiene:model-fallback-projection:a:b:c"})
        )
        == EXIT_PRECONDITION_ERROR
    )
    assert "nothing to clear" in capsys.readouterr().err
    invoker = _acp_projection_clear
    monkeypatch.delenv(invoker.INVOKER_ENV_VAR, raising=False)
    anonymous = [
        "clear-model-fallback-projection",
        "--fact-id",
        _FACT_ID,
        "--reason",
        "it is gone",
        "--journal",
        str(path),
        "--repo",
        str(tmp_path),
    ]
    assert dispatcher_main(argv=anonymous) == EXIT_PRECONDITION_ERROR
    assert "asserted no identity" in capsys.readouterr().err
    # Nothing was appended by any refusal.
    assert unresolved_projection_failures(journal_path=path)


def test_the_clearance_defaults_its_repo_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The documented default, exercised so no caller has to pass `--repo`."""
    path = _journal(tmp_path=tmp_path, records=(_failure_line(),))
    monkeypatch.chdir(tmp_path)
    argv = [
        "clear-model-fallback-projection",
        "--fact-id",
        _FACT_ID,
        "--reason",
        "the run is gone for good",
        "--invoker",
        "human:tester",
    ]
    assert dispatcher_main(argv=argv) == 0
    assert unresolved_projection_failures(journal_path=path) == ()
    assert "CLEARED" in capsys.readouterr().out
