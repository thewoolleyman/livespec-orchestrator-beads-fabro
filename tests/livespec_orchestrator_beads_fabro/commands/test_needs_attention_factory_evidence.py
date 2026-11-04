"""The factory-native availability evidence a snapshot composition observes.

The idle-factory clause of `SPECIFICATION/contracts.md` requires the fact to
"consume the shared admission-eligibility verdict, including a read-only
observation of the factory-native availability evidence required by" the
fallback-priority clause, and in the same breath forbids the composition from
executing "credential probes, availability confirmation turns, or mutations".

THE TWO HALVES NEED DIFFERENT INSTRUMENTS, which is why this module carries
both. That the production reader is PASSED is a claim about one call's
arguments, and only a spy on that call can fail on it. That the reader is
REACHED is a claim about behaviour, and only a declared factory whose listing
refuses can show it: an unreadable evidence source is surfaced on the verdict,
so the wait row names it — a composition that never asked the factory composes
no row at all and every argument assertion still passes.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WAITS_MODULE = f"{_PACKAGE}._needs_attention_waits"
_WAITS_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_waits.py"
)
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_FACTORY = "hp"
_UNAVAILABLE_EVIDENCE = "unavailable-availability-evidence"

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


def _dispatcher_block(*, factories: dict[str, object] | None) -> dict[str, object]:
    block: dict[str, object] = {
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
        }
    }
    if factories is not None:
        block["factories"] = factories
    return block


def _repo(root: Path, *, factories: dict[str, object] | None) -> Path:
    workflow = root / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": _dispatcher_block(factories=factories)
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


def _availability_wait_items(**kwargs: object) -> list[Any]:
    module = importlib.import_module(f"{_PACKAGE}._needs_attention_availability_wait")
    return module.availability_wait_items(**kwargs)


def _idle_factory_items(**kwargs: object) -> list[Any]:
    module = importlib.import_module(f"{_PACKAGE}._needs_attention_idle_factory")
    return module.idle_factory_items(**kwargs)


def _recording_listing_refusal(*, asked: list[str]) -> Callable[..., None]:
    """A `list_runs` that records which factory it was asked about and refuses.

    ONE stub, shared by the declared-factory case and its no-factory control,
    because the control's whole claim is that this body never runs — a stub of
    its own would be an uncovered line asserting the same thing twice.
    """

    def _refuse(_self: object, *, factory: str) -> None:
        asked.append(factory)

    return _refuse


def test_the_idle_factory_composer_passes_the_production_factory_run_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assertion 3's argument half: the reader the admission pass uses, bound here."""
    assert _WAITS_PATH.is_file()
    waits = importlib.import_module(_WAITS_MODULE)
    reader_module = importlib.import_module(f"{_PACKAGE}._acp_factory_run_reader")
    verdict_module = importlib.import_module(f"{_PACKAGE}._acp_preflight_verdict")
    captured: list[dict[str, Any]] = []

    def _spy(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return verdict_module.AcpPreflightVerdict(fallback_enabled=False)

    monkeypatch.setattr(waits, "resolve_acp_preflight", _spy)
    repo = _repo(tmp_path, factories=None)

    _ = _idle_factory_items(project_root=repo, repo="repo", items=[_item(id_="bd-ready")])

    assert len(captured) == 1
    reader = captured[0]["factory_runs"]
    assert isinstance(reader, reader_module.FactoryRunReader)
    assert reader.repo == repo


def test_a_declared_factory_whose_listing_refuses_is_observed_and_surfaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assertion 3's behavioural half, which no argument assertion can establish.

    The listing is asked for and refuses, so the evidence source is UNAVAILABLE.
    The clause forbids reading that as an empty hold set or as proof of
    eligibility, and the wait row naming it is how the snapshot says so.
    """
    assert _WAITS_PATH.is_file()
    reader_module = importlib.import_module(f"{_PACKAGE}._acp_factory_run_reader")
    asked: list[str] = []
    monkeypatch.setattr(
        reader_module.FactoryRunReader, "list_runs", _recording_listing_refusal(asked=asked)
    )
    repo = _repo(tmp_path, factories={_FACTORY: {"server": "https://factory.example:32276"}})

    attention = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-ready")]
    )

    assert asked == [_FACTORY]
    assert [item.id for item in attention] == ["hygiene:acp-availability-wait:bd-ready"]
    assert f"governing_condition={_UNAVAILABLE_EVIDENCE}" in attention[0].summary
    # No admission-required node is empty: the clause requires a refused listing
    # to be surfaced and retried WITHOUT emptying any chain, because a reading
    # that emptied every chain would wedge every dispatch in the fleet the
    # moment one factory became unreachable.
    assert "admission_required_node=none" in attention[0].summary


def test_a_repository_declaring_no_factory_reads_none_and_composes_no_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: without it, a composer that never reads passes the case above."""
    assert _WAITS_PATH.is_file()
    reader_module = importlib.import_module(f"{_PACKAGE}._acp_factory_run_reader")
    asked: list[str] = []
    monkeypatch.setattr(
        reader_module.FactoryRunReader, "list_runs", _recording_listing_refusal(asked=asked)
    )
    repo = _repo(tmp_path, factories=None)

    attention = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-ready")]
    )

    assert asked == []
    assert attention == []
