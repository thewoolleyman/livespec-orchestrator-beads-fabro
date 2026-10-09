"""The port reads both engines' payloads: `validate`, `inspect`, `events`, `ps`.

Plan `fabro-currency` P4 (`bd-ib-227cbw`). Every fixture here is driven through
`FabroPort` itself rather than through a parser helper, because the port is
where the two engines' outputs stop being different: a payload the port cannot
parse arrives at every consumer as `None`, which the ACP projection reads as an
unreadable fetch and the watchdog reads as no signal.

PROVENANCE, stated per payload because it is the only thing that makes these
fixtures evidence rather than invention. All four candidate shapes are
TRANSCRIBED from measurements taken on the real v0.378.0-nightly.0 binary
(`64b9d88`) against the `hp-candidate` instance on 2026-10-08 and recorded in
`plan/fabro-currency/research/006-hp-candidate-first-measurements-2026-10-08.md`
plus the P3 rider on the work-item; the 0.254 shapes are the ones already
measured on the pinned build. What the notes record is each payload's KEY SET
(and, for `validate`, its verdict and its error and warning COUNTS), so the key
sets here are faithful and the values are representative. Two deliberate
consequences:

- the `validate` fixture carries each diagnostic as its measured CODE rather
  than as an object, because the note records the codes and the counts and not
  the per-entry field names. Inventing those names would dress a guess as a
  measurement;
- the candidate `inspect` fixture reproduces the whole top-level key set
  (`checkpoint, conclusion, parent_id, run_id, run_spec, sandbox, stages,
  start_record, status`) but not the full `run_spec`, which research note 006
  records as inlining the resolved environment and which no reader here touches.

The `events` payload is asserted in BOTH containers for the reason recorded in
`_fabro_port_events`: the note calls the candidate's output "a stream of
envelopes" and each envelope carries a `stream_seq`, so it can arrive one object
per line, and a line-delimited stream is not one JSON document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget

_CANDIDATE_RUN_ID = "01M4DCQPCX6Z"
_PINNED_RUN_ID = "01M0EFZND0Z7K2SY1H21Q59GVF"
_RECORDED_AT_MS = 1791462895207

# `validate --json` on the production graph, candidate client: `valid: false`,
# three `attractor.condition.syntax` errors from `inputs.*` tokens inside edge
# conditions (lines 784, 786, 787) and seven warnings.
_CANDIDATE_VALIDATE: dict[str, Any] = {
    "valid": False,
    "errors": [
        "attractor.condition.syntax:784",
        "attractor.condition.syntax:786",
        "attractor.condition.syntax:787",
    ],
    "warnings": [
        "ignored.workflow_toml.run.checkpoint",
        "ignored.workflow_toml.run.integrations",
        "ignored.workflow_toml.run.meta_branch",
        "ignored.workflow_toml.run.pull_request",
        "ignored.workflow_toml.run.run_branch",
        "ignored.environments.livespec-ci.resources",
        "info.budget.default",
    ],
}

# `inspect --json` for a COMPLETED candidate run: status is `{kind, reason}` and
# the conclusion is keyed `diff, final_git_commit_sha, stages, status,
# timestamp, timing, total_retries`. Stages are named `node@visit`.
_CANDIDATE_INSPECT_COMPLETED: list[dict[str, Any]] = [
    {
        "run_id": _CANDIDATE_RUN_ID,
        "parent_id": None,
        "status": {"kind": "succeeded", "reason": "completed"},
        "stages": ["001-start@1", "002-implement@1", "003-exit@1"],
        "start_record": {"kind": "run.created", "recorded_at": 1791462869813},
        "run_spec": {"environment": {"provider": "docker"}},
        "sandbox": {"container": f"petri-{_CANDIDATE_RUN_ID}-l0"},
        "checkpoint": {"timestamp": "2026-10-08T12:34:55.207000000Z"},
        "conclusion": {
            "diff": None,
            "final_git_commit_sha": "9bcd4faa2e3c4d5f6071829304a5b6c7d8e9f012",
            "stages": ["001-start@1", "002-implement@1", "003-exit@1"],
            "status": "succeeded",
            "timestamp": "2026-10-08T12:34:55.207431905Z",
            "timing": {"wall_time_ms": 41231},
            "total_retries": 0,
        },
    }
]

# The same payload for a FAILED candidate run: `conclusion.failure` is keyed
# `{reason, detail: {message, category}}`, with no `causes`, no `signature` and
# no `transient_infra`.
_CANDIDATE_INSPECT_FAILED: list[dict[str, Any]] = [
    {
        "run_id": _CANDIDATE_RUN_ID,
        "parent_id": None,
        "status": {"kind": "failed", "reason": "workflow_error"},
        "stages": ["001-start@1", "002-implement@1"],
        "conclusion": {
            "diff": None,
            "final_git_commit_sha": "9bcd4faa2e3c4d5f6071829304a5b6c7d8e9f012",
            "stages": ["001-start@1", "002-implement@1"],
            "status": "failed",
            "timestamp": "2026-10-08T12:36:11.004213877Z",
            "timing": {"wall_time_ms": 600412},
            "total_retries": 1,
            "failure": {
                "reason": "workflow_error",
                "detail": {
                    "message": "checkpoint operation budget exceeded: git commit timed out",
                    "category": "deterministic",
                },
            },
        },
    }
]

_CANDIDATE_EVENT_ENVELOPES: list[dict[str, Any]] = [
    {
        "run_id": _CANDIDATE_RUN_ID,
        "stream_seq": 7,
        "kind": "step.finished",
        "id": f"{_CANDIDATE_RUN_ID}-7",
        "recorded_at": _RECORDED_AT_MS,
        "item": {
            "seq": 7,
            "recorded_at": _RECORDED_AT_MS,
            "record": {
                "kind": "step.finished",
                "body": {"event": "step.finished", "outcome": "succeeded"},
            },
        },
    },
    {
        "run_id": _CANDIDATE_RUN_ID,
        "stream_seq": 8,
        "kind": "token.emitted",
        "id": f"{_CANDIDATE_RUN_ID}-8",
        "recorded_at": _RECORDED_AT_MS,
        "item": {
            "seq": 8,
            "recorded_at": _RECORDED_AT_MS,
            "record": {"kind": "token.emitted", "body": {"event": "token.emitted"}},
        },
    },
]

# `ps --json`, candidate: the measured key set, including `wall_time_ms` beside
# `total_usd_micros`.
_CANDIDATE_PS: list[dict[str, Any]] = [
    {
        "goal": "Work-item: bd-ib-227cbw\nAdapt Fabro parsing to Petri outputs",
        "labels": [],
        "parent_id": None,
        "repo_origin_url": "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro",
        "run_id": _CANDIDATE_RUN_ID,
        "source_directory": "/home/cwoolley/src",
        "start_time": "2026-10-08T12:34:14.182000000Z",
        "status": {"kind": "succeeded", "reason": "completed"},
        "total_usd_micros": 1250,
        "wall_time_ms": 41231,
        "workflow_graph_name": "ImplementWorkItem",
        "workflow_name": "implement-work-item",
        "workflow_slug": "implement-work-item",
    }
]

# The pinned build's own shapes, kept beside the candidate's: `inspect` returns
# a single-element LIST and `events` a JSON array of ISO-stamped records.
_PINNED_INSPECT: list[dict[str, Any]] = [
    {
        "run_id": _PINNED_RUN_ID,
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
        },
    }
]

_PINNED_EVENTS: list[dict[str, Any]] = [
    {"timestamp": "2026-08-20T03:21:30Z", "event": "agent.session.activated"},
    {"timestamp": "2026-08-20T03:21:37Z", "event": "run.completed"},
]


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return self.result


def _port(*, tmp_path: Path, stdout: str, exit_code: int = 0) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://hp-xubuntu.perch-rudd.ts.net:32278"),
        runner=_Runner(result=CommandResult(exit_code=exit_code, stdout=stdout, stderr="")),
        cwd=tmp_path,
    )


def test_candidate_validate_payload_parses(tmp_path: Path) -> None:
    result = _port(tmp_path=tmp_path, stdout=json.dumps(_CANDIDATE_VALIDATE)).validate(
        workflow_toml=tmp_path / "workflow.fabro", timeout_seconds=1.0
    )

    assert result.payload == _CANDIDATE_VALIDATE


def test_candidate_inspect_payloads_parse_for_a_completed_and_a_failed_run(
    tmp_path: Path,
) -> None:
    completed = _port(tmp_path=tmp_path, stdout=json.dumps(_CANDIDATE_INSPECT_COMPLETED)).inspect(
        run_id=_CANDIDATE_RUN_ID, timeout_seconds=1.0
    )
    failed = _port(tmp_path=tmp_path, stdout=json.dumps(_CANDIDATE_INSPECT_FAILED)).inspect(
        run_id=_CANDIDATE_RUN_ID, timeout_seconds=1.0
    )

    assert completed.status_kind == "succeeded"
    assert completed.failure is None
    assert failed.status_kind == "failed"
    assert failed.failure is not None
    assert failed.failure.category == "deterministic"
    assert failed.failure.cause == ("checkpoint operation budget exceeded: git commit timed out")
    assert failed.failure.signature is None


def test_candidate_events_payload_parses_as_an_array_and_as_a_stream(
    tmp_path: Path,
) -> None:
    array_form = json.dumps(_CANDIDATE_EVENT_ENVELOPES)
    stream_form = "\n".join(json.dumps(envelope) for envelope in _CANDIDATE_EVENT_ENVELOPES) + "\n"

    assert (
        _port(tmp_path=tmp_path, stdout=array_form)
        .events(run_id=_CANDIDATE_RUN_ID, timeout_seconds=1.0)
        .payload
        == _CANDIDATE_EVENT_ENVELOPES
    )
    assert (
        _port(tmp_path=tmp_path, stdout=stream_form)
        .events(run_id=_CANDIDATE_RUN_ID, timeout_seconds=1.0)
        .payload
        == _CANDIDATE_EVENT_ENVELOPES
    )


def test_an_unreadable_events_read_is_absent_rather_than_empty(tmp_path: Path) -> None:
    """Read failure is not absence: neither arm may become an empty event list."""
    refused = _port(tmp_path=tmp_path, stdout="run not found", exit_code=1).events(
        run_id=_CANDIDATE_RUN_ID, timeout_seconds=1.0
    )
    garbled = _port(tmp_path=tmp_path, stdout="connection reset by peer").events(
        run_id=_CANDIDATE_RUN_ID, timeout_seconds=1.0
    )

    assert refused.payload is None
    assert garbled.payload is None


def test_candidate_ps_payload_parses_into_run_summaries(tmp_path: Path) -> None:
    result = _port(tmp_path=tmp_path, stdout=json.dumps(_CANDIDATE_PS)).ps(timeout_seconds=1.0)

    assert len(result.runs) == 1
    summary = result.runs[0]
    assert summary.run_id == _CANDIDATE_RUN_ID
    assert summary.status_kind == "succeeded"
    assert summary.total_usd_micros == 1250
    assert summary.work_item_id == "bd-ib-227cbw"


def test_the_pinned_build_payloads_parse_unchanged_beside_the_candidate(
    tmp_path: Path,
) -> None:
    inspect = _port(tmp_path=tmp_path, stdout=json.dumps(_PINNED_INSPECT)).inspect(
        run_id=_PINNED_RUN_ID, timeout_seconds=1.0
    )
    events = _port(tmp_path=tmp_path, stdout=json.dumps(_PINNED_EVENTS)).events(
        run_id=_PINNED_RUN_ID, timeout_seconds=1.0
    )

    assert inspect.status_kind == "failed"
    assert inspect.failure is not None
    assert inspect.failure.category == "deterministic"
    assert events.payload == _PINNED_EVENTS
