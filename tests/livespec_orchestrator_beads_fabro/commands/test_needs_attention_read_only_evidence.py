"""Every engine invocation a snapshot composition spends, graded.

The idle-factory clause of `SPECIFICATION/contracts.md` forbids the
composition from executing "credential probes, availability confirmation
turns, or mutations", and the clause it inherits its evidence read from adds
that "No separate hold sidecar file, cache, or store MAY hold or mirror this
evidence". Both are claims about what the composition DOES, not about what it
returns, so nothing about a composed row can establish either.

THE GUARD IS BOUND TO A DECLARED VERB SET RATHER THAN TO A LIST SPELLED HERE.
`READ_ONLY_FABRO_VERBS` is the reader's own statement of which engine verbs it
may spend, so a future reader method reaching for a mutating verb fails this
module instead of agreeing with a copy of the old list that nobody rechecks --
the "concurrence is not independence when the method is shared" problem,
arriving as a test and its subject sharing one transcription.

THE COMPOSITION IS DRIVEN WITH A DECLARED FACTORY, because a repository
declaring none spends no invocation at all and every assertion below would
pass over an empty recording. The engine's answers are refused, which is the
UNAVAILABLE-evidence arm: the composition still has to compose, and what it
must not do is probe a credential or take a confirmation turn to resolve the
gap.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_READER_MODULE = f"{_PACKAGE}._acp_factory_run_reader"
_READER_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_acp_factory_run_reader.py"
)
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_FACTORY = "hp"
_FIXED = "2026-10-01T00:00:00Z"
_READ_ONLY_VERBS = ("inspect", "ps", "settings")
# Every engine verb that would make the composition something other than a
# read: a run submission IS the availability confirmation turn, `auth` and
# `secret` write host and server credential state, and `rm` destroys a run.
_MUTATING_VERBS = ("auth", "rm", "run", "secret")

_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
"""

_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""


def _repo(root: Path) -> Path:
    workflow = root / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": {_FACTORY: {"server": "https://factory.example:32276"}},
                        "acp_nodes": {
                            "implement": {
                                "display_name": "Primary",
                                "candidate_key": "primary",
                                "availability_key": "codex",
                                "command": "adapter-primary",
                                "fallbacks": [
                                    {
                                        "display_name": "Fallback",
                                        "candidate_key": "fallback",
                                        "availability_key": "anthropic",
                                        "command": "adapter-fallback",
                                    }
                                ],
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    journal = root / _JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("", encoding="utf-8")
    return root


def _item(*, id_: str) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status="ready",
        title=f"{id_} title",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base)


def _record_invocations(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture every argv the production runner is asked to execute, and refuse.

    Patched at the RUNNER rather than at the reader, because the reader is what
    this module is grading: a stub reader would record the calls a correct
    reader makes and say nothing about the calls it actually makes.
    """
    runner_module = importlib.import_module(f"{_PACKAGE}._dispatcher_shell_runner")
    types_module = importlib.import_module(f"{_PACKAGE}._dispatcher_engine_types")
    recorded: list[list[str]] = []

    def _refuse(_self: object, *, argv: list[str], **_rest: object) -> Any:
        recorded.append(list(argv))
        return types_module.CommandResult(exit_code=1, stdout="", stderr="refused")

    monkeypatch.setattr(runner_module.ShellCommandRunner, "run", _refuse)
    return recorded


def _verbs(*, recorded: list[list[str]]) -> list[str]:
    """The engine verb of each recorded invocation: the word after the binary."""
    return [argv[1] for argv in recorded if len(argv) > 1]


def _availability_wait_items(**kwargs: object) -> list[Any]:
    module = importlib.import_module(f"{_PACKAGE}._needs_attention_availability_wait")
    return module.availability_wait_items(**kwargs)


def _idle_factory_items(**kwargs: object) -> list[Any]:
    module = importlib.import_module(f"{_PACKAGE}._needs_attention_idle_factory")
    return module.idle_factory_items(**kwargs)


def test_the_reader_declares_the_read_only_verb_set_it_may_spend(
    tmp_path: Path,
) -> None:
    """The guard's own subject: a verb set the reader states rather than one we assume."""
    assert _READER_PATH.is_file()
    _ = tmp_path
    reader_module = importlib.import_module(_READER_MODULE)

    assert "READ_ONLY_FABRO_VERBS" in reader_module.__all__
    assert reader_module.READ_ONLY_FABRO_VERBS == _READ_ONLY_VERBS
    assert not set(reader_module.READ_ONLY_FABRO_VERBS) & set(_MUTATING_VERBS)


def test_every_verb_the_reader_itself_spends_is_in_that_declared_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The binding: the declaration is worthless if the reader can leave it.

    All three reader methods are driven, because a declaration graded against
    only the method the composition happens to call cannot fail on the two it
    does not.
    """
    assert _READER_PATH.is_file()
    reader_module = importlib.import_module(_READER_MODULE)
    repo = _repo(tmp_path)
    recorded = _record_invocations(monkeypatch)
    reader = reader_module.FactoryRunReader(repo=repo)

    assert reader.list_runs(factory=_FACTORY) is None
    assert reader.scheduler_max_concurrent_runs(factory=_FACTORY) is None
    assert reader.inspect_payload(factory=_FACTORY, run_id="01RUN") is None

    assert sorted(set(_verbs(recorded=recorded))) == sorted(reader_module.READ_ONLY_FABRO_VERBS)


def test_both_wait_lanes_compose_without_a_probe_a_confirmation_turn_or_a_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assertion 5 as a measurement: the argv a composition actually executed.

    The availability-wait row IS composed here, which is what makes the zero
    counts mean something: a composition that refused to compose anything would
    satisfy every absence below while reporting no wait at all.
    """
    assert _READER_PATH.is_file()
    reader_module = importlib.import_module(_READER_MODULE)
    repo = _repo(tmp_path)
    recorded = _record_invocations(monkeypatch)

    waits = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-ready")], now_iso=_FIXED
    )
    _ = _idle_factory_items(project_root=repo, repo="repo", items=[_item(id_="bd-ready")])

    assert len(waits) == 1
    assert recorded != []
    assert set(_verbs(recorded=recorded)) <= set(reader_module.READ_ONLY_FABRO_VERBS)
    assert [verb for verb in _verbs(recorded=recorded) if verb in _MUTATING_VERBS] == []
    # The credential-probe seam is not merely unused: there is no probe argument
    # for this path to pass, so no subcommand of any credential surface can
    # appear among the invocations a composition spends.
    assert [argv for argv in recorded if "cred" in " ".join(argv)] == []


def test_composing_the_wait_lanes_leaves_the_dispatch_journal_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mutation half: a read that wrote would still return a plausible row."""
    assert _READER_PATH.is_file()
    repo = _repo(tmp_path)
    journal = repo / _JOURNAL
    journal.write_text('{"stage": "pre-existing"}\n', encoding="utf-8")
    before = journal.read_bytes()
    _ = _record_invocations(monkeypatch)

    _ = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-ready")], now_iso=_FIXED
    )
    _ = _idle_factory_items(project_root=repo, repo="repo", items=[_item(id_="bd-ready")])

    assert journal.read_bytes() == before
