"""Two compositions of the wait lanes over one unchanged evaluation.

The idle-factory clause of `SPECIFICATION/contracts.md` requires that
"Identical ledger, capacity, configuration, availability evidence, and
evaluation time MUST produce a byte-identical row", and the availability wait
the same clause enumerates is composed from the same verdict.

THE EVALUATION TIME IS A PREMISE OF THAT REQUIREMENT, which is why these cases
supply it rather than reading a clock twice and hoping. The availability wait
reports a SCHEDULED INSTANT, and where no governing hold carries an expiry that
instant is the cadence measured from the evaluation itself — so two passes at
two instants legitimately render two rows, and a caller that cannot hold the
evaluation time fixed cannot ask the question the clause answers.

EACH CASE HERE WOULD PASS ON A LANE THAT IGNORED ITS OWN INPUTS, so each is
paired with the reading that catches that: the byte-identity case forbids the
clock from being read at all, the discriminator shows the instant MOVING when
the evaluation time moves, and the default case shows the clock still reached
when no evaluation time is supplied.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE_NAME = f"{_PACKAGE}._needs_attention_availability_wait"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_availability_wait.py"
)
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_FACTORY = "hp"
_FIXED = "2026-10-01T00:00:00Z"
_LATER = "2026-10-01T06:00:00Z"
_DEFAULT_CADENCE_SECONDS = 300

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
    """A repository whose ONE declared factory refuses its own run listing.

    The unavailable-evidence arm, which is the only arm whose scheduled instant
    is derived from the evaluation time rather than from a hold's expiry — so it
    is the only fixture under which these three cases can distinguish a lane
    that honours its evaluation time from one that reads a clock.
    """
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


def _refuse_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    reader_module = importlib.import_module(f"{_PACKAGE}._acp_factory_run_reader")

    def _refuse(_self: object, *, factory: str) -> None:
        _ = factory

    monkeypatch.setattr(reader_module.FactoryRunReader, "list_runs", _refuse)


def _forbid_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any clock read inside the lane fail loudly rather than succeed.

    A lane that read the clock despite being handed an evaluation time would
    otherwise still render byte-identical rows whenever two passes landed in
    one second, which is most of the time — so the assertion would pass for a
    reason that has nothing to do with the requirement.
    """
    module = importlib.import_module(_MODULE_NAME)

    def _refuse() -> str:
        raise AssertionError("the lane read a clock although it was handed an evaluation time")

    monkeypatch.setattr(module, "utc_now_iso", _refuse)


def _rendered(*, attention: list[Any]) -> str:
    return json.dumps([asdict(item) for item in attention], indent=2, sort_keys=True)


def _availability_wait_items(**kwargs: object) -> list[Any]:
    module = importlib.import_module(_MODULE_NAME)
    return module.availability_wait_items(**kwargs)


def test_two_compositions_at_one_evaluation_time_render_byte_identical_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The requirement itself, with the clock forbidden so it cannot pass by luck."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    assert "now_iso" in module.availability_wait_items.__annotations__
    repo = _repo(tmp_path)
    _refuse_listing(monkeypatch)
    _forbid_clock(monkeypatch)
    inputs: dict[str, object] = {
        "project_root": repo,
        "repo": "repo",
        "items": [_item(id_="bd-ready")],
        "now_iso": _FIXED,
    }

    first = _availability_wait_items(**inputs)
    second = _availability_wait_items(**inputs)

    assert len(first) == 1
    assert _rendered(attention=first) == _rendered(attention=second)


def test_a_different_evaluation_time_moves_the_scheduled_instant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The discriminator: without it, a lane rendering a constant passes above.

    Where no governing hold carries an expiry the instant IS the cadence after
    this evaluation, so the evaluation time is load-bearing rather than
    incidental — which is exactly why the byte-identity requirement states it
    as a premise.
    """
    assert _MODULE_PATH.is_file()
    repo = _repo(tmp_path)
    _refuse_listing(monkeypatch)
    _forbid_clock(monkeypatch)
    items = [_item(id_="bd-ready")]

    early = _availability_wait_items(project_root=repo, repo="repo", items=items, now_iso=_FIXED)
    late = _availability_wait_items(project_root=repo, repo="repo", items=items, now_iso=_LATER)

    assert "scheduled_reevaluation_at=2026-10-01T00:05:00Z" in early[0].summary
    assert "scheduled_reevaluation_at=2026-10-01T06:05:00Z" in late[0].summary


def test_an_absent_evaluation_time_falls_back_to_this_pass_own_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: a lane that ignored the parameter entirely passes both cases above."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path)
    _refuse_listing(monkeypatch)
    reads: list[str] = []

    def _clock() -> str:
        reads.append(_FIXED)
        return _FIXED

    monkeypatch.setattr(module, "utc_now_iso", _clock)

    attention = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-ready")]
    )

    assert reads == [_FIXED]
    assert "scheduled_reevaluation_at=2026-10-01T00:05:00Z" in attention[0].summary


def test_the_forbidden_clock_tripwire_can_actually_fire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tripwire's own control: an instrument that cannot hit reports no hits.

    `_forbid_clock` is what makes the byte-identity case meaningful, and when it
    is armed correctly it is SILENT — so the one fault that would make it
    worthless looks exactly like the pass it is supposed to produce.
    """
    assert _MODULE_PATH.is_file()
    _ = tmp_path
    module = importlib.import_module(_MODULE_NAME)
    _forbid_clock(monkeypatch)

    with pytest.raises(AssertionError, match="read a clock"):
        _ = module.utc_now_iso()


def test_the_cadence_the_fallback_instant_uses_is_the_committed_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both instants above are one cadence on; read it rather than transcribing it.

    A constant copied into this module would keep agreeing with itself after the
    ratified default moved, so the two cases that assert an instant would then be
    asserting a cadence this repository no longer uses.
    """
    assert _MODULE_PATH.is_file()
    settings = importlib.import_module(f"{_PACKAGE}._dispatcher_policy_settings")
    repo = _repo(tmp_path)
    _refuse_listing(monkeypatch)
    _forbid_clock(monkeypatch)

    assert settings.DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS == _DEFAULT_CADENCE_SECONDS
    attention = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-ready")], now_iso=_FIXED
    )
    assert "scheduled_reevaluation_at=2026-10-01T00:05:00Z" in attention[0].summary
