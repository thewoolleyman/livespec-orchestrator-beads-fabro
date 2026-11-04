"""Hold instants read from real Fabro listings, which carry their own UTC offset.

`fabro ps -a --json` reports `start_time` with an explicit offset and nine
sub-second digits -- `2026-10-19T03:33:56.022531726+00:00` on hp, measured
2026-10-19 across all 939 rows on hp and 750 on vps. The earlier fixtures in
`test_acp_factory_hold_evidence.py` spell every instant with a `Z` suffix, which
is exactly the shape that hid this defect: an offset-bearing instant had
`+00:00` appended a second time, parsed as nothing, and every failed row on a
factory was reported `attempt-occurrence-unreadable`. With the production reader
wired into admission that left every ACP candidate unconfirmed and refused every
dispatch (bd-ib-fjpgxu, stop-the-line ruling R228).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

# A start time copied from the live hp listing, after the sub-second strip the
# evidence module applies before parsing.
_FABRO_START = "2026-10-19T03:33:56+00:00"
_FABRO_START_RAW = "2026-10-19T03:33:56.022531726+00:00"

_RUN_ID = "01M4TN6V5M5WSRA57JENX0MVXW"
_PEER_REPOSITORY = "livespec-console-beads-fabro"
_LABELS: dict[str, str] = {
    "livespec.repository": _PEER_REPOSITORY,
    "livespec.dispatch.factory": "hp",
    "livespec.acp.implement.availability": "codex",
    "livespec.acp.implement.candidate": "primary",
}
_FACTORIES_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {
        "hp": {"server": "https://hp.example.ts.net:32276"}
      }
    }
  }
}
"""
_CEILING_CAUSE = "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage"


def _records() -> Any:
    return importlib.import_module(f"{_PACKAGE}._acp_hold_records")


def _evidence() -> Any:
    return importlib.import_module(f"{_PACKAGE}._acp_factory_hold_evidence")


def _repo(*, tmp_path: Path) -> Path:
    (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    return tmp_path


def _rows(*, start_time: str, wall_time_ms: int) -> tuple[Any, ...]:
    """One failed row, in the shape `fabro ps -a --json` reports on hp."""
    records = importlib.import_module(f"{_PACKAGE}._fabro_port_records")
    return records.fabro_run_summaries_from_payload(
        payload=[
            {
                "run_id": _RUN_ID,
                "status": {"kind": "failed"},
                "goal": "Work-item: bd-peer-1\n",
                "repo_origin_url": f"https://github.com/thewoolleyman/{_PEER_REPOSITORY}",
                "labels": dict(_LABELS),
                "start_time": start_time,
                "wall_time_ms": wall_time_ms,
            }
        ]
    )


def _inspect_payload() -> list[dict[str, Any]]:
    """One `fabro inspect --json` record whose `implement` node hit a usage ceiling."""
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "failed"},
            "checkpoint": {
                "current_node": "needs_human",
                "completed_nodes": ["setup", "dod_gate", "implement"],
                "node_outcomes": {
                    "implement": {
                        "status": "failed",
                        "failure": {
                            "category": "transient_infra",
                            "signature": "implement|transient_infra|acp turn failed",
                            "causes": ["ACP protocol error", _CEILING_CAUSE],
                        },
                    },
                },
            },
        }
    ]


@dataclass(kw_only=True)
class _Reader:
    rows: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    payloads: dict[tuple[str, str], object] = field(default_factory=dict)
    inspected: list[tuple[str, str]] = field(default_factory=list)

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self.rows.get(factory, ())

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        self.inspected.append((factory, run_id))
        return self.payloads.get((factory, run_id))


def test_a_fabro_start_time_carrying_its_own_offset_parses_to_that_instant() -> None:
    parsed = _records().parse_hold_instant(text=_FABRO_START)

    assert parsed == datetime(2026, 10, 19, 3, 33, 56, tzinfo=timezone.utc)


def test_a_z_suffixed_journal_instant_still_parses_to_the_same_instant() -> None:
    parsed = _records().parse_hold_instant(text="2026-10-19T03:33:56Z")

    assert parsed == datetime(2026, 10, 19, 3, 33, 56, tzinfo=timezone.utc)


def test_a_weeks_old_failed_row_with_an_offset_start_time_is_out_of_window_not_unreadable(
    tmp_path: Path,
) -> None:
    """The 739 rows R228 measured were exactly this shape: old, failed, fully dated."""
    reader = _Reader(
        rows={"hp": _rows(start_time="2026-09-10T14:42:51.810036085+00:00", wall_time_ms=600_000)}
    )

    evidence = _evidence().factory_hold_evidence(
        repo=_repo(tmp_path=tmp_path), reader=reader, now_iso="2026-10-19T05:00:00Z"
    )

    assert evidence.unobservable == ()
    assert evidence.observations == ()
    assert reader.inspected == []


def test_an_in_window_failed_row_with_an_offset_start_time_yields_its_observation(
    tmp_path: Path,
) -> None:
    """Started 03:33:56, ran ten minutes, so the ceiling hit at 03:43:56 -- six minutes ago."""
    reader = _Reader(
        rows={"hp": _rows(start_time=_FABRO_START_RAW, wall_time_ms=600_000)},
        payloads={("hp", _RUN_ID): _inspect_payload()},
    )

    evidence = _evidence().factory_hold_evidence(
        repo=_repo(tmp_path=tmp_path), reader=reader, now_iso="2026-10-19T03:50:00Z"
    )

    assert evidence.unobservable == ()
    assert reader.inspected == [("hp", _RUN_ID)]
    assert len(evidence.observations) == 1
