"""How the resume entry reaches the run, and the two seams that read it.

The derivation itself is asserted beside it; this file asserts the WIRING, which
is where a resume fails silently rather than loudly. Both seams read their
attribute DEFENSIVELY off the invocation, because every other dispatch command
reaches them with a Namespace that never carried one — and a defensive read that
misses resolves ABSENT, which means the dispatch proceeds as a plain one and the
resumed run re-implements from `start`. Nothing in the output says so.

So the positive case is the load-bearing one here: an invocation carrying the
resume attributes must produce a checkout, and a payload asked to enter at a
declared node must carry the moved `start` edge in the graph the run is handed.

THE NEGATIVE CASES COVER THE OTHER DIRECTION. An ordinary dispatch's Namespace
yields no checkout and leaves the rendered graph byte-identical, which is what
keeps the resume path from changing anything about every other dispatch; and a
head that is present but empty yields no checkout rather than a `ResumeCheckout`
carrying an empty sha, which `git checkout --detach ''` would fail on inside the
sandbox instead of at the invocation.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_resume_entry.py"
)

_HEAD = "a" * 40
_ITEM = "bd-ib-fngpwg"

_GRAPH = """digraph ImplementWorkItem {
    graph [
        goal="Implement one ready work-item"
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond, label="Start"]
    dod_gate [
        label="gate"
        timeout="1800s"
    ]
    pr [
        label="publish"
        timeout="1800s"
    ]

    start -> dod_gate
    dod_gate -> pr
}
"""

# Opaque non-secret placeholders: the overlay renders whatever it is handed, and
# a literal spelled like a credential at the call site reads to the lint rule as
# a hardcoded one.
_FAKE_TOKEN = "overlay-token-placeholder"
_FAKE_GITHUB_TOKEN = "overlay-github-placeholder"

_WORKFLOW_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "sandbox"\n'


def _entry_module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _committed(*, tmp_path: Path) -> Path:
    workflow = tmp_path / "workflow"
    workflow.mkdir()
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    config = workflow / "workflow.toml"
    _ = config.write_text(_WORKFLOW_TOML, encoding="utf-8")
    return config


def _timeouts() -> NodeTimeouts:
    return NodeTimeouts(configured={}, stall_seconds=7200, stall_layer="workflow-default")


def test_a_node_name_that_is_not_an_identifier_refuses() -> None:
    """A name that could never be a node is refused before the declaration scan."""
    module = _entry_module()
    for malformed in ("pr; rm -rf /", "pr pr", "", "dod gate"):
        assert module.graph_entered_at(graph_text=_GRAPH, node=malformed) is None


def test_an_invocation_carrying_the_resume_head_yields_a_checkout() -> None:
    """The positive case: without it, a missed read is indistinguishable from none."""
    module = _entry_module()
    args = argparse.Namespace(**{module.RESUME_HEAD_ARG: _HEAD})
    checkout = module.resume_checkout_for(args=args, branch=f"feat/{_ITEM}")
    assert checkout is not None
    assert checkout.head == _HEAD
    assert _ITEM in checkout.branch


def test_an_ordinary_invocation_yields_no_checkout() -> None:
    """Every other dispatch reaches this seam with a Namespace carrying nothing."""
    module = _entry_module()
    assert module.resume_checkout_for(args=argparse.Namespace(), branch=f"feat/{_ITEM}") is None


def test_a_present_but_unusable_head_yields_no_checkout() -> None:
    """An empty or non-string head would fail inside the sandbox, not here."""
    module = _entry_module()
    for unusable in ("", None, 7):
        args = argparse.Namespace(**{module.RESUME_HEAD_ARG: unusable})
        assert module.resume_checkout_for(args=args, branch=f"feat/{_ITEM}") is None


def test_the_payload_graph_is_derived_when_an_entry_node_is_asked_for(tmp_path: Path) -> None:
    """The graph the run is handed carries the moved `start` edge."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
        materialize_workflow_payload,
    )

    payload = materialize_workflow_payload(
        committed=_committed(tmp_path=tmp_path),
        payload_dir=tmp_path / "payload",
        timeouts=_timeouts(),
        adapters={},
        entry_node="pr",
    )
    assert not isinstance(payload, str)
    derived = payload.graph.read_text(encoding="utf-8")
    assert "start -> pr" in derived
    assert "start -> dod_gate" not in derived


def test_the_payload_refuses_an_entry_node_the_graph_does_not_declare(tmp_path: Path) -> None:
    """Refused before the run exists, naming the node, not at run-create."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
        materialize_workflow_payload,
    )

    payload = materialize_workflow_payload(
        committed=_committed(tmp_path=tmp_path),
        payload_dir=tmp_path / "payload",
        timeouts=_timeouts(),
        adapters={},
        entry_node="review_fix",
    )
    assert isinstance(payload, str)
    assert "review_fix" in payload


def test_the_payload_graph_is_untouched_without_an_entry_node(tmp_path: Path) -> None:
    """An ordinary dispatch ships exactly the graph it always shipped."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
        materialize_workflow_payload,
    )

    payload = materialize_workflow_payload(
        committed=_committed(tmp_path=tmp_path),
        payload_dir=tmp_path / "payload",
        timeouts=_timeouts(),
        adapters={},
    )
    assert not isinstance(payload, str)
    assert "start -> dod_gate" in payload.graph.read_text(encoding="utf-8")


def test_the_overlay_renders_the_resume_checkout_step(tmp_path: Path) -> None:
    """The step reaches the run config a resumed run is launched with."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
        render_run_config_overlay,
    )

    module = _entry_module()
    rendered = render_run_config_overlay(
        committed_text=_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        resume_checkout=module.ResumeCheckout(branch=f"feat/{_ITEM}", head=_HEAD),
    )
    assert rendered is not None
    assert _HEAD in rendered
    assert f"refs/heads/feat/{_ITEM}" in rendered


def test_the_overlay_renders_no_checkout_step_for_an_ordinary_dispatch(tmp_path: Path) -> None:
    """No resume, no step — the overlay every other dispatch has always carried."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
        render_run_config_overlay,
    )

    rendered = render_run_config_overlay(
        committed_text=_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert "resume checkout" not in rendered
