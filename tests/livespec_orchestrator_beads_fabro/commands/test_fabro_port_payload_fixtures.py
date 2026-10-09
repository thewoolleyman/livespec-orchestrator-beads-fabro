"""The port parses BOTH engines' payloads from one typed fixture set.

Each engine is one `_EnginePayloads` value carrying its `validate`, `ps`,
`inspect`, terminal `conclusion` and `events` payloads, so the parse assertions
below are written ONCE and run against both. A reader comparing the two
fixtures can see exactly which fields the Petri-era rebase had to account for;
two separate hand-rolled test files could not show that.

PROVENANCE, stated per payload because it differs and the difference matters.
`tests/fixtures/fabro_payloads/PROVENANCE.md` is the full record.

- The 0.378 `validate` payload is CAPTURED: real output of the
  v0.378.0-nightly.0 binary, whose release-asset and binary SHA-256 digests
  both match the ones research note 006 recorded for the `hp-candidate`
  instance. It reproduces that note's measurement of this graph exactly —
  `valid: false`, 7 warnings, 3 `attractor.condition.syntax` errors at lines
  784, 786 and 787.
- The 0.378 `inspect`, `conclusion` and `events` payloads are TRANSCRIBED from
  the field sets notes 006 and 007 measured. They are NOT captured here: all
  three need a configured server plus a completed sandbox run, and this sandbox
  has no Docker, no route to `:32278`, and a server that comes up demanding an
  interactive install token. Capturing them against the released build on an
  operator host is the host leg.
- The 0.254 payloads are the shapes this repository already had under test,
  measured 2026-08-20 (the six real `inspect` payloads behind
  `test_fabro_port_inspect_list_shape`) and recorded in `_dispatcher_cost`'s
  docstring for the cost and token fields.

WHAT THE 0.254 FIXTURE IS FOR, since it is the half most easily dropped as
redundant: it is the CONTROL. Every assertion below that distinguishes the
engines would also pass if the reader had simply started ignoring the pinned
shapes, and nothing in a Petri-only test would say so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    parse_last_event_epoch,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_failure import (
    fabro_failure_detail_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_run_summaries_from_payload,
    fabro_status_kind_from_payload,
    fabro_token_usage_from_payload,
)

_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "fabro_payloads"
_CAPTURED_VALIDATE = _FIXTURES / "validate-0.378.0-nightly.0.json"


@dataclass(frozen=True, kw_only=True)
class _EnginePayloads:
    """One engine's four payload kinds, as its own CLI reports them."""

    label: str
    validate: object
    ps: list[dict[str, Any]]
    inspect: list[dict[str, Any]]
    events: list[dict[str, Any]]
    expected_status_kind: str
    expected_failure_category: str
    expected_cause_contains: str
    expects_wall_time: bool
    expects_token_usage: bool


def _captured_validate() -> object:
    assert _CAPTURED_VALIDATE.is_file()
    return json.loads(_CAPTURED_VALIDATE.read_text())


def _petri() -> _EnginePayloads:
    return _EnginePayloads(
        label="0.378.0-nightly.0 (Petri)",
        validate=_captured_validate(),
        ps=[
            {
                "goal": "Work-item: bd-ib-227cbw\n",
                "labels": [],
                "parent_id": None,
                "repo_origin_url": "https://github.com/thewoolleyman/x",
                "run_id": "01M4DCSSJM6C",
                "source_directory": "/workspace",
                "start_time": "2026-10-08T08:00:00Z",
                "status": {"kind": "failed", "reason": "node_failed"},
                "total_usd_micros": 412_000,
                "wall_time_ms": 903_221,
                "workflow_graph_name": "ImplementWorkItem",
                "workflow_name": "implement-work-item",
                "workflow_slug": "implement-work-item",
            }
        ],
        inspect=[
            {
                "checkpoint": {},
                "conclusion": {
                    "diff": "",
                    "final_git_commit_sha": "2aaa5085",
                    "stages": ["implement@1"],
                    "status": "failed",
                    "timestamp": "2026-10-08T12:00:00Z",
                    "timing": {},
                    "total_retries": 0,
                    "failure": {
                        "reason": "script exited with status 1",
                        "detail": {
                            # `category` is a representative string: note 006
                            # records the KEY and never a value, and the reader
                            # passes it through rather than matching a table.
                            "category": "node_failure",
                            "message": "the goal gate was not satisfied",
                        },
                    },
                },
                "parent_id": None,
                "run_id": "01M4DCSSJM6C",
                "run_spec": {},
                "sandbox": {},
                "stages": ["implement@1"],
                "start_record": {},
                "status": {"kind": "failed", "reason": "node_failed"},
            }
        ],
        events=[
            {
                "run_id": "01M4DCSSJM6C",
                "stream_seq": 1,
                "kind": "step.started",
                "id": "e1",
                "recorded_at": 1_760_000_000_123,
                "item": {
                    "seq": 1,
                    "recorded_at": 1_760_000_000_123,
                    "record": {
                        "kind": "step.started",
                        "body": {"event": "step.started", "firing": 1, "attempt": 1},
                    },
                },
            },
            {
                "run_id": "01M4DCSSJM6C",
                "stream_seq": 2,
                "kind": "token.emitted",
                "id": "e2",
                "recorded_at": 1_760_000_060_456,
                "item": {
                    "seq": 2,
                    "recorded_at": 1_760_000_060_456,
                    "record": {
                        "kind": "token.emitted",
                        "body": {
                            "event": "token.emitted",
                            "input_tokens": 1_500,
                            "output_tokens": 300,
                        },
                    },
                },
            },
        ],
        expected_status_kind="failed",
        expected_failure_category="node_failure",
        expected_cause_contains="goal gate",
        expects_wall_time=True,
        expects_token_usage=True,
    )


def _pinned() -> _EnginePayloads:
    return _EnginePayloads(
        label="0.254.0 (pinned)",
        validate={"workflow_name": "ImplementWorkItem", "valid": True, "diagnostics": []},
        ps=[
            {
                "run_id": "01M0EFZND0Z7K2SY1H21Q59GVF",
                "status": {"kind": "failed", "reason": "workflow_error"},
                "goal": "Work-item: bd-ib-227cbw\n",
                # Null on every 0.254 run, which is the measurement the
                # fail-closed cost gate exists for.
                "total_usd_micros": None,
            }
        ],
        inspect=[
            {
                "run_id": "01M0EFZND0Z7K2SY1H21Q59GVF",
                "parent_id": None,
                "status": {"kind": "failed", "reason": "workflow_error"},
                "conclusion": {
                    "timestamp": "2026-08-20T03:21:37.561802885Z",
                    "status": "failed",
                    "failure": {
                        "reason": "workflow_error",
                        "detail": {
                            "message": "stage abandon failed with no outgoing fail edge",
                            "category": "deterministic",
                        },
                    },
                    "final_git_commit_sha": "25d7983efc964251287e239bfb3996d0f760abb6",
                },
                "checkpoint": {
                    "failure": {
                        "message": "stage abandon failed with no outgoing fail edge",
                        "category": "deterministic",
                    }
                },
            }
        ],
        events=[{"timestamp": "2026-08-20T03:21:37Z", "event": "run.completed"}],
        expected_status_kind="failed",
        expected_failure_category="deterministic",
        expected_cause_contains="no outgoing fail edge",
        expects_wall_time=False,
        expects_token_usage=False,
    )


_ENGINES = (_pinned(), _petri())


def test_every_engine_fixture_parses_all_four_payload_kinds() -> None:
    for engine in _ENGINES:
        assert isinstance(engine.validate, dict), engine.label
        assert "workflow_name" in engine.validate, engine.label

        summary = fabro_run_summaries_from_payload(payload=engine.ps)[0]
        assert summary.work_item_id == "bd-ib-227cbw", engine.label
        assert (summary.wall_time_ms is not None) is engine.expects_wall_time, engine.label

        assert (
            fabro_status_kind_from_payload(payload=engine.inspect) == engine.expected_status_kind
        ), engine.label

        failure = fabro_failure_detail_from_payload(payload=engine.inspect)
        assert failure is not None, engine.label
        assert failure.category == engine.expected_failure_category, engine.label
        assert failure.cause is not None, engine.label
        assert engine.expected_cause_contains in failure.cause, engine.label

        assert (
            parse_last_event_epoch(events_json=json.dumps(engine.events)) is not None
        ), engine.label

        usage = fabro_token_usage_from_payload(payload=engine.events)
        assert (usage is not None) is engine.expects_token_usage, engine.label


def test_the_captured_validate_payload_reproduces_the_research_note_measurement() -> None:
    """The capture is only evidence if it says what the note said it says.

    Asserted on the DIAGNOSTIC LINES rather than just the counts: three errors
    of the right rule at the wrong lines would be a different graph, and the
    counts alone cannot tell those apart.
    """
    payload = _captured_validate()
    assert isinstance(payload, dict)

    assert payload["valid"] is False
    assert payload["workflow_name"] == "ImplementWorkItem"
    assert payload["nodes"] == 18
    assert payload["edges"] == 37

    diagnostics = payload["diagnostics"]
    errors = [d for d in diagnostics if d["severity"] == "Error"]
    warnings = [d for d in diagnostics if d["severity"] == "Warning"]

    assert len(warnings) == 7
    assert [d["rule"] for d in errors] == ["attractor.condition.syntax"] * 3
    assert sorted(d["line"] for d in errors) == [784, 786, 787]


def test_the_two_fixtures_differ_in_the_fields_the_rebase_had_to_account_for() -> None:
    """The control: the fixtures must actually disagree where the engines do.

    Without this, two fixtures that had silently converged on one shape would
    satisfy every assertion above while testing one engine twice.
    """
    pinned, petri = _pinned(), _petri()

    # Only the Petri `ps` record carries a duration.
    assert "wall_time_ms" in petri.ps[0]
    assert "wall_time_ms" not in pinned.ps[0]

    # Only the pinned `inspect` carries the FLAT checkpoint failure block that
    # made the nested one readable without being read.
    assert "failure" in pinned.inspect[0]["checkpoint"]
    assert petri.inspect[0]["checkpoint"] == {}

    # The event timestamp field differs in NAME and in UNIT.
    assert "recorded_at" in petri.events[0]
    assert "timestamp" in pinned.events[0]
    assert isinstance(petri.events[0]["recorded_at"], int)
    assert isinstance(pinned.events[0]["timestamp"], str)
