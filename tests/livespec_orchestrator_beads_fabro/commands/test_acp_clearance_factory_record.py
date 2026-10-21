"""The factory-native record an operator clearance writes, and what gates it.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Observations, successful availability confirmations, and operator
clearances MUST each be recorded as a factory-native record on the
participating factory whose evidence they create or retire -- ... and an
operator clearance by a minimal factory-native record whose recorded outcome
carries the clearance's exact identity, actor, time, and reason -- so
retirement is reconstructible from the same source as observation." Scenario
116 grades the valve's own refusals, and Scenario 127's host-visible half is
what the record exists for.

THE ORDER IS THE CLAIM UNDER TEST HERE, not the record's content. A clearance
asserts a fact about the world that no observation supports, so each of the
valve's refusals has to return BEFORE anything lands on a factory every other
repository reads: a refused clearance that had already written its record
would have published an assertion the valve went on to reject, and no later
read could tell that record from an accepted one. The recorder below therefore
counts its calls rather than inspecting them.

THE FOURTH REFUSAL IS THE NEW ONE. The factory-native record is the
AUTHORITATIVE clearance and the journal line is its audit reference, so a
repository with no participating factory to record on cannot clear anything:
journalling alone would retire the record for this checkout and leave every
peer dispatching into a hold their operator believes is gone.

Everything is HERMETIC: journals and configuration live in `tmp_path`, the
invoker is supplied through the documented flag, the command's wall clock is
pinned, the writer is stubbed, and nothing reaches a factory or a provider.
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
_VALVE_MODULE = "_acp_hold_clear"
_WRITER_MODULE = "_acp_clearance_factory_record"

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


def _writer() -> Any:
    """Import the clearance writer, proving its file exists first."""
    path = _COMMANDS / f"{_WRITER_MODULE}.py"
    assert path.is_file(), f"{_WRITER_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_WRITER_MODULE}")


def _valve() -> Any:
    """Import the clearance valve the writer is consulted from."""
    return importlib.import_module(f"{_PACKAGE}.{_VALVE_MODULE}")


@dataclass(kw_only=True)
class _Recorder:
    """A clearance writer that counts the calls the valve actually made."""

    record: Any
    calls: list[Any] = field(default_factory=list)

    def __call__(self, *, repo: Path, clearance: Any) -> Any:
        self.calls.append(clearance)
        _ = repo
        return self.record


def _observation() -> dict[str, Any]:
    """One live domain-scoped observation for the valve to find."""
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    built = records.hold_observation_record(
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


def _repo(*, tmp_path: Path, factories: bool = True) -> Path:
    """A repository that declares one participating factory, or declares none."""
    if factories:
        (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    return tmp_path


def _journal(*, repo: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path = repo / "journal.jsonl"
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


def _argv(*, path: Path, **overrides: str) -> list[str]:
    flags = {
        "--scope": "availability-domain",
        "--hold-key": "codex",
        "--reason": "the account allowance reset",
        "--invoker": "human:tester",
        "--journal": str(path),
        "--repo": str(path.parent),
    }
    flags.update(overrides)
    return ["clear-acp-availability-hold", *(item for pair in flags.items() for item in pair)]


def _install(*, monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """Pin the valve's clock and replace its writer with a counting recorder."""
    writer = _writer()
    valve = _valve()
    recorder = _Recorder(record=writer.FactoryClearanceRecord(factory="hp", run_id="01MCLEAR"))
    monkeypatch.setattr(valve, "utc_now_iso", lambda: _NOW)
    monkeypatch.setattr(valve, "record_factory_clearance", recorder)
    return recorder


def _run(*, argv: list[str]) -> int:
    dispatcher = importlib.import_module(f"{_PACKAGE}.dispatcher")
    return dispatcher.main(argv=argv)


def _lines(*, path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _precondition_error() -> int:
    return int(
        importlib.import_module(f"{_PACKAGE}._dispatcher_command_common").EXIT_PRECONDITION_ERROR
    )


def test_every_valve_refusal_returns_before_any_factory_native_record_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each refusal publishes nothing a peer repository could read as a clearance."""
    recorder = _install(monkeypatch=monkeypatch)
    repo = _repo(tmp_path=tmp_path)
    path = _journal(repo=repo, records=(_observation(),))

    blank = _argv(path=path, **{"--reason": "   "})
    assert _run(argv=blank) == _precondition_error()
    assert "--reason is blank" in capsys.readouterr().err

    invoker = importlib.import_module(f"{_PACKAGE}._dispatcher_invoker")
    monkeypatch.delenv(invoker.INVOKER_ENV_VAR, raising=False)
    anonymous = [token for token in _argv(path=path) if token not in ("--invoker", "human:tester")]
    assert _run(argv=anonymous) == _precondition_error()
    assert "asserted no identity" in capsys.readouterr().err

    keyless = _argv(path=path, **{"--scope": "candidate"})
    assert _run(argv=keyless) == _precondition_error()
    assert "pass --candidate-key" in capsys.readouterr().err

    absent = _argv(path=path, **{"--hold-key": "anthropic"})
    assert _run(argv=absent) == _precondition_error()
    assert "nothing to clear" in capsys.readouterr().err

    # No record was written on any of the four, and the journal is untouched.
    assert recorder.calls == []
    assert len(_lines(path=path)) == 1


def test_an_accepted_clearance_records_once_on_the_participating_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The write happens exactly once, past every refusal, on the live target."""
    recorder = _install(monkeypatch=monkeypatch)
    repo = _repo(tmp_path=tmp_path)
    path = _journal(repo=repo, records=(_observation(),))

    assert _run(argv=_argv(path=path)) == 0

    assert len(recorder.calls) == 1
    assert "CLEARED" in capsys.readouterr().out
    assert len(_lines(path=path)) == 2


def test_a_repository_with_no_participating_factory_cannot_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clearance no peer could read is refused rather than journalled alone.

    The refusal is the WRITER's own, surfaced by the valve: the journal line is
    an audit reference to the factory record, so a checkout that cannot write
    the record has nothing to reference and would retire the hold for itself
    alone.
    """
    _ = _install(monkeypatch=monkeypatch)
    valve = _valve()
    recorder = _Recorder(record="no participating factory declares a server")
    monkeypatch.setattr(valve, "record_factory_clearance", recorder)
    repo = _repo(tmp_path=tmp_path, factories=False)
    path = _journal(repo=repo, records=(_observation(),))

    assert _run(argv=_argv(path=path)) == _precondition_error()

    assert "no participating factory" in capsys.readouterr().err
    assert len(_lines(path=path)) == 1
