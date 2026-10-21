"""What the factory-native clearance record IS, and how the write produces it.

The write half's own tests. `test_acp_clearance_factory_record.py` owns the
VALVE's gating of this write -- which refusals return before it, and that an
accepted clearance consults it exactly once -- and drives it through a stub;
these drive the real writer against an injected runner, so the argv, the label
and the rendered graph are asserted rather than assumed.

Binds the operator-clearance half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": "an operator clearance by a
minimal factory-native record whose recorded outcome carries the clearance's
exact identity, actor, time, and reason". Scenario 116 is the operator act it
records; Scenario 127's host-visible half is what the record exists for.

THE RUNNER IS ASSERTED ON RATHER THAN MERELY SATISFIED. A double that answers
whatever it is asked cannot tell a correct invocation from a plausible one, so
every launch below is read back out of the recorded argv: the label pair the
reader recognises the row by, and the graph file whose script carries the
clearance. The engine-version probe and the launch arrive as two distinct
invocations keyed on the fabro SUBCOMMAND, which is what lets the assertions
name which read they are about instead of counting calls.

Everything is HERMETIC: configuration lives in `tmp_path`, both engine
invocations are injected, no port reaches a server, and nothing launches an
adapter or touches a provider.
"""

from __future__ import annotations

import importlib
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WRITER_MODULE = "_acp_clearance_factory_record"
_RECORDS_MODULE = "_acp_clearance_records"

_RUN_ID = "01M5CLEARANCE0000000000000"
_CLEARED_AT = "2026-10-20T12:05:00Z"

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
    """Import the write half, proving its file exists first."""
    path = _COMMANDS / f"{_WRITER_MODULE}.py"
    assert path.is_file(), f"{_WRITER_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_WRITER_MODULE}")


def _records() -> Any:
    """Import the pure record shape, proving its file exists first."""
    path = _COMMANDS / f"{_RECORDS_MODULE}.py"
    assert path.is_file(), f"{_RECORDS_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_RECORDS_MODULE}")


def _clearance(*, reason: str = "the account allowance reset") -> Any:
    """One domain-scoped clearance of two live observations."""
    return _records().AcpHoldClearance(
        scope="availability-domain",
        hold_key="codex",
        candidate_key=None,
        observation_ids=("acpobs-aaaaaaaaaaaaaaaaaaaaaaaa", "acpobs-bbbbbbbbbbbbbbbbbbbbbbbb"),
        actor="human:tester",
        cleared_at=_CLEARED_AT,
        reason=reason,
    )


@dataclass(kw_only=True)
class _Command:
    """The one shape the port's runner protocol reads off a result."""

    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Runner:
    """A fabro runner keyed on SUBCOMMAND, recording every argv it was given."""

    run_exit_code: int = 0
    run_stdout: str = f"Run: {_RUN_ID}\n"
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
        return _Command(exit_code=self.run_exit_code, stdout=self.run_stdout)

    def launch_argv(self) -> list[str]:
        """The one recorded argv that is a `fabro run`."""
        launches = [argv for argv in self.calls if "run" in argv]
        assert len(launches) == 1, f"expected exactly one launch, got {len(launches)}"
        return launches[0]


def _repo(*, tmp_path: Path, factories: bool = True) -> Path:
    if factories:
        (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    return tmp_path


def _flag_value(*, argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_the_record_is_one_labelled_run_whose_script_carries_the_clearance(
    tmp_path: Path,
) -> None:
    """The label a reader recognises it by, and the outcome that carries it.

    Both halves are read out of the launch itself: the `--label` pair the
    reader's own constant names, and the rendered graph on disk at the moment
    of the launch -- recovered from the argv rather than from the writer's
    internals, because a payload assembled anywhere else is a payload no
    engine would have received.
    """
    writer = _writer()
    records = _records()
    runner = _Runner()

    recorded = writer.record_factory_clearance(
        repo=_repo(tmp_path=tmp_path), clearance=_clearance(), runner=runner
    )

    assert recorded == writer.FactoryClearanceRecord(factory="hp", run_id=_RUN_ID)
    assert recorded.reference == f"hp:{_RUN_ID}"
    argv = runner.launch_argv()
    assert (
        _flag_value(argv=argv, flag="--label")
        == f"{records.CLEARANCE_LABEL_KEY}={records.CLEARANCE_LABEL_VALUE}"
    )
    assert _flag_value(argv=argv, flag="--server") == "https://hp.example.ts.net:32276"


def test_the_rendered_graph_prints_the_clearance_line_through_both_encodings() -> None:
    """One node, and a script whose shell word is exactly the recorded line.

    The reason below carries BOTH quote characters, which is the only input
    under which the two encodings can be observed to compose: a single quote
    exercises the shell quoting and a double quote exercises the DOT escape,
    and a reason carrying neither passes against an implementation that
    performs neither.
    """
    writer = _writer()
    records = _records()
    clearance = _clearance(reason='the operator\'s "reset" landed')

    graph = writer.clearance_workflow_graph(clearance=clearance)

    assert f"{writer.CLEARANCE_NODE} [shape=parallelogram" in graph
    assert f"start -> {writer.CLEARANCE_NODE} -> exit" in graph
    script = graph.split('script="', maxsplit=1)[1].rsplit('"]', maxsplit=1)[0]
    # Undo the DOT escape, then the shell quoting, and the line stands.
    unescaped = script.replace('\\"', '"').replace("\\\\", "\\")
    printed = shlex.split(unescaped)[-1]
    assert printed == records.clearance_outcome_text(clearance=clearance)
    assert json.loads(printed)["reason"] == 'the operator\'s "reset" landed'


def test_a_marked_line_whose_fields_are_malformed_reads_back_as_nothing() -> None:
    """The parse's strict half, on lines that DO carry the record's own marker.

    Every payload below would be rejected by the marker test if it lacked one,
    so each one carries it: these cases are about a line this format OWNS whose
    fields are nonetheless unusable, which is the only shape under which a
    lenient parse could assemble a clearance out of the parts that happened to
    read. A retirement cannot be undone, so each one must read back as nothing.
    """
    records = _records()
    sound = json.loads(records.clearance_outcome_text(clearance=_clearance()))
    malformed: tuple[dict[str, Any], ...] = (
        {**sound, "observation_ids": "acpobs-aaaa"},
        {**sound, "observation_ids": ["acpobs-aaaa", 7]},
        {**sound, "candidate_key": 7},
        {**sound, "actor": "   "},
        {**sound, "cleared_at": None},
        {**sound, "reason": None},
    )

    for payload in malformed:
        assert (
            records.clearance_from_outcome(text=json.dumps(payload, sort_keys=True)) is None
        ), payload
    # The CONTROL: the same assembly, unmodified, does read back -- without it
    # a parse that refused everything would satisfy every case above.
    assert records.clearance_from_outcome(text=json.dumps(sound, sort_keys=True)) == _clearance()


def test_the_recorded_outcome_carries_the_identity_actor_time_and_reason() -> None:
    """The four things the clause requires the outcome to carry, plus the target."""
    records = _records()
    clearance = _clearance()

    payload = json.loads(records.clearance_outcome_text(clearance=clearance))

    assert payload[records.CLEARANCE_MARKER_KEY] == records.CLEARANCE_MARKER_VALUE
    assert payload["scope"] == "availability-domain"
    assert payload["hold_key"] == "codex"
    assert payload["candidate_key"] is None
    assert payload["observation_ids"] == list(clearance.observation_ids)
    assert payload["actor"] == "human:tester"
    assert payload["cleared_at"] == _CLEARED_AT
    assert payload["reason"] == "the account allowance reset"
    # Byte-identical across two renderings, which is what lets a reader compare
    # a record against the clearance it claims to be.
    assert records.clearance_outcome_text(clearance=clearance) == json.dumps(
        payload, sort_keys=True
    )


def test_a_factory_declaring_no_server_is_refused_before_any_launch(tmp_path: Path) -> None:
    """Nothing is launched, so nothing a peer could misread was written."""
    writer = _writer()
    runner = _Runner()

    refusal = writer.record_factory_clearance(
        repo=_repo(tmp_path=tmp_path, factories=False), clearance=_clearance(), runner=runner
    )

    assert isinstance(refusal, str)
    assert "no participating factory" in refusal
    assert runner.calls == []


def test_a_failed_launch_and_an_unreadable_run_id_are_each_refused(tmp_path: Path) -> None:
    """Two distinct ways the record did not land, each named rather than assumed.

    The second case is the one a reader is most likely to fold into the first:
    the launch EXITED ZERO, so the record may well exist on the factory, and
    the refusal says the id could not be read back rather than that the write
    failed -- which is what tells an operator to look at the factory instead of
    at their own configuration.
    """
    writer = _writer()
    repo = _repo(tmp_path=tmp_path)

    failed = writer.record_factory_clearance(
        repo=repo, clearance=_clearance(), runner=_Runner(run_exit_code=1)
    )
    assert isinstance(failed, str)
    assert "exited 1" in failed

    headless = writer.record_factory_clearance(
        repo=repo, clearance=_clearance(), runner=_Runner(run_stdout="no identifier here\n")
    )
    assert isinstance(headless, str)
    assert "run id could not be read back" in headless
