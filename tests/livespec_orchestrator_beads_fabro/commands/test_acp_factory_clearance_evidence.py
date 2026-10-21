"""Reading one operator clearance back off the factory record that carries it.

Binds the operator-clearance half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": "an operator clearance by a
minimal factory-native record whose recorded outcome carries the clearance's
exact identity, actor, time, and reason -- so retirement is reconstructible
from the same source as observation", together with the provider-exhaustion
clause's "For a current record the authoritative clearance is the
factory-native record ... and the journal record is its audit reference."
Scenario 116 is the operator act; Scenario 127's host-visible half is what the
record exists for.

THE ROUND TRIP IS THE CLAIM, not the rendering. A recorded outcome is only
evidence in so far as a reader that never saw the clearance can recover it, so
every case below renders through the writer and reads back through the reader,
and the assertion is on the recovered VALUE rather than on the text in between.
A test asserting the text alone passes against a renderer whose output nothing
can parse.

BOTH ENGINE SHAPES ARE EXERCISED, because the two generations record a node's
outcome in different places -- the Petri-era build in the record's own
top-level `stages` map and the pinned build in its checkpoint's
`node_outcomes` -- and a reader of one returns a clean `None` on the other,
which at the evidence surface is indistinguishable from a run that recorded no
clearance.

Everything is HERMETIC: payloads are the engines' own measured shapes built
inline, configuration lives in `tmp_path`, the launch is injected, and nothing
reaches a factory or a provider.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_EVIDENCE_MODULE = "_acp_factory_clearance_evidence"
_RECORDS_MODULE = "_acp_clearance_records"
_WRITER_MODULE = "_acp_clearance_factory_record"
_VALVE_MODULE = "_acp_hold_clear"

_RUN_ID = "01M5CLEARANCE0000000000000"
_CLEARED_AT = "2026-10-20T12:05:00Z"
_OCCURRED = "2026-10-20T12:00:00Z"
_NOW = "2026-10-20T12:05:00Z"

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


def _evidence() -> Any:
    """Import the factory-side read, proving its file exists first."""
    path = _COMMANDS / f"{_EVIDENCE_MODULE}.py"
    assert path.is_file(), f"{_EVIDENCE_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_EVIDENCE_MODULE}")


def _records() -> Any:
    return importlib.import_module(f"{_PACKAGE}.{_RECORDS_MODULE}")


def _clearance(*, candidate_key: str | None = None) -> Any:
    """One clearance of two live observations, scoped by its own key shape."""
    return _records().AcpHoldClearance(
        scope="candidate" if candidate_key is not None else "availability-domain",
        hold_key="codex",
        candidate_key=candidate_key,
        observation_ids=("acpobs-aaaaaaaaaaaaaaaaaaaaaaaa", "acpobs-bbbbbbbbbbbbbbbbbbbbbbbb"),
        actor="human:tester",
        cleared_at=_CLEARED_AT,
        reason='the operator\'s own "reset" landed',
    )


def _petri_payload(*, output: str) -> list[dict[str, Any]]:
    """The Petri-era shape: the per-stage map on the record itself."""
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "succeeded"},
            "stages": {
                "001-start@1": {"handler": "sentinel", "state": "succeeded"},
                "002-record@1": {"handler": "script", "state": "succeeded", "output": output},
            },
        }
    ]


def _pinned_payload(*, output: str) -> list[dict[str, Any]]:
    """The pinned shape: the per-node map on the newest checkpoint."""
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "succeeded"},
            "checkpoint": {
                "current_node": "exit",
                "node_outcomes": {
                    "record": {"status": "succeeded", "output": output},
                },
            },
        }
    ]


def _outcome(*, clearance: Any) -> str:
    return _records().clearance_outcome_text(clearance=clearance)


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Runner:
    """A fabro runner that answers the version probe and one launch."""

    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> _Command:
        self.calls.append(list(argv))
        _ = (cwd, timeout_seconds, env)
        if "--version" in argv:
            return _Command(exit_code=0, stdout="fabro 0.254.0 (8869e88 2026-10-01)\n")
        return _Command(exit_code=0, stdout=f"Run: {_RUN_ID}\n")


def _observation() -> dict[str, Any]:
    """One live domain-scoped observation for the valve to clear."""
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    built = hold_records.hold_observation_record(
        failure=classifier.AcpAvailabilityFailure(
            cause="quota",
            scope="availability-domain",
            hold_key="codex",
            availability_key="codex",
            candidate_key=None,
            source="protocol.message",
        ),
        evidence_kind="candidate-attempt",
        evidence_id="run-1:availability-domain:codex",
        occurred_at=_OCCURRED,
        work_item_id="bd-ib-dtfv2p",
        node="implement",
    )
    assert isinstance(built, dict)
    return dict(built)


def test_the_journal_clearance_line_references_the_factory_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority is the factory run, and the journal line names it.

    Driven through the REAL writer against an injected launch, so the
    reference the journal carries is the one a factory actually minted rather
    than a value a stub chose.
    """
    _ = _evidence()
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_factory_hold_records")
    valve = importlib.import_module(f"{_PACKAGE}.{_VALVE_MODULE}")
    writer = importlib.import_module(f"{_PACKAGE}.{_WRITER_MODULE}")
    (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    path = tmp_path / "journal.jsonl"
    path.write_text(json.dumps(_observation(), sort_keys=True) + "\n", encoding="utf-8")
    runner = _Runner()
    monkeypatch.setattr(valve, "utc_now_iso", lambda: _NOW)
    monkeypatch.setattr(
        valve,
        "record_factory_clearance",
        lambda *, repo, clearance: writer.record_factory_clearance(
            repo=repo, clearance=clearance, runner=runner
        ),
    )

    dispatcher = importlib.import_module(f"{_PACKAGE}.dispatcher")
    argv = [
        "clear-acp-availability-hold",
        "--scope",
        "availability-domain",
        "--hold-key",
        "codex",
        "--reason",
        "the account allowance reset",
        "--invoker",
        "human:tester",
        "--journal",
        str(path),
        "--repo",
        str(tmp_path),
    ]
    assert dispatcher.main(argv=argv) == 0

    line = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert line[hold_records.AUDIT_REFERENCE_KEY] == f"hp:{_RUN_ID}"


@pytest.mark.parametrize("candidate_key", [None, "gpt-5-5"])
def test_a_recorded_outcome_reads_back_as_the_exact_clearance(candidate_key: str | None) -> None:
    """The four required things plus the exact target, recovered from the record.

    Both scopes are driven, because a domain clearance names NO candidate key
    and a candidate clearance must name one -- a reader that dropped the field
    would agree with the domain case and silently widen the candidate one.
    """
    evidence = _evidence()
    clearance = _clearance(candidate_key=candidate_key)

    read = evidence.recorded_clearance(payload=_petri_payload(output=_outcome(clearance=clearance)))

    assert read == clearance


def test_the_pinned_engine_checkpoint_shape_reads_back_identically() -> None:
    """One reader for both engines, so neither records evidence the other loses."""
    evidence = _evidence()
    clearance = _clearance()

    read = evidence.recorded_clearance(
        payload=_pinned_payload(output=_outcome(clearance=clearance))
    )

    assert read == clearance


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not a record at all", id="unreadable-payload"),
        pytest.param([{"run_id": _RUN_ID, "status": {"kind": "succeeded"}}], id="no-stage-map"),
        pytest.param(
            [{"run_id": _RUN_ID, "stages": {"002-record@1": {"state": "failed"}}}], id="no-output"
        ),
        pytest.param(
            [{"run_id": _RUN_ID, "stages": {"002-record@1": {"output": "hello\n"}}}],
            id="prose-output",
        ),
        pytest.param(
            [{"run_id": _RUN_ID, "stages": {"002-record@1": {"output": '{"scope": "x"}'}}}],
            id="unmarked-object",
        ),
    ],
)
def test_a_run_recording_no_clearance_reads_back_as_nothing(payload: object) -> None:
    """Every shape that is NOT a clearance record answers nothing, never a guess.

    A partial read would be worse than none: a retirement is the destructive
    direction, so a clearance assembled out of whichever fields happened to
    parse would retire a record nobody cleared.
    """
    assert _evidence().recorded_clearance(payload=payload) is None


def test_a_clearance_run_is_recognised_from_its_listing_labels_alone() -> None:
    """Which rows are worth a per-run read, decided before one is spent."""
    records = _records()

    assert records.is_clearance_run(
        labels={records.CLEARANCE_LABEL_KEY: records.CLEARANCE_LABEL_VALUE}
    )
    assert not records.is_clearance_run(labels={"livespec.repository": "livespec-overseer"})
    assert not records.is_clearance_run(labels={records.CLEARANCE_LABEL_KEY: "something-else"})
