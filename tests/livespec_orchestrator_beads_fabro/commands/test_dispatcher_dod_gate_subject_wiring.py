"""The overlay carries the `dod_gate` subject, and the dispatch leg forwards it (bd-ib-tzvtgc).

The module that renders the subject steps is covered on its own; this is the
WIRING half, and each case fails for a reason the module's own cases cannot see.
The overlay case shows the parameter reaches the rendered run config (and that a
caller passing none renders none). The dispatch-leg case shows the one caller a
real dispatch goes through forwards the subject a HOST TAKING would grade for the
same item and the same recorded riders -- a renderer that is correct and never
reached satisfies every assertion in the module's own file.

The materializer is replaced by a recorder in the leg case: the claim is which
value the leg DERIVES, and a real materialization would mint credentials and write
a mode-600 file to establish nothing further.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_subject import (
    DOD_GATE_SUBJECT_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    judgement_subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_overlay import (
    DispatchOverlay,
    materialize_dispatch_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_record import RecordedDispatch
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import WorkflowPayload
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import pack_payload
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import VaultSecret
from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"
_PROBE_VAULT_KEY = "LIVESPEC_DISPATCH_SUBJECT_PROBE_REFERENCE"
_HEADING = "## Scenario 174 — The judgement runs before admission"
_RIDER = "Rider: narrow the first assertion to the admission wall."
_RECEIPT = "livespec-dod-judgement-unavailable\n\nThe judgement did not run."


def _render(*, tmp_path: Path, **extra: Any) -> str:
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        **extra,
    )
    assert rendered is not None
    return rendered


def test_the_overlay_materializes_the_subject_it_is_handed(tmp_path: Path) -> None:
    rendered = _render(tmp_path=tmp_path, dod_gate_subject="A subject for the node.\n")

    assert rendered.count(DOD_GATE_SUBJECT_MARKER) == 1
    packed = pack_payload(text="A subject for the node.\n")
    assert f'LIVESPEC_PREPARE_PAYLOAD = "{packed}"' in rendered


def test_a_caller_handing_no_subject_renders_none(tmp_path: Path) -> None:
    assert DOD_GATE_SUBJECT_MARKER not in _render(tmp_path=tmp_path)


def test_the_dispatch_leg_forwards_the_subject_a_host_taking_grades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "scenarios.md").write_text(
        f"{_HEADING}\n\nThe shared subject text.\n", encoding="utf-8"
    )
    recorder: dict[str, object] = {}

    def _record(**kwargs: Any) -> str | None:
        recorder.update(kwargs)
        return None

    monkeypatch.setattr(_dispatcher_loop_overlay, "materialize_overlay", _record)
    overlay = _overlay(tmp_path=tmp_path)

    assert materialize_dispatch_overlay(overlay=overlay) is None

    expected = judgement_subject(item=overlay.item, cwd=tmp_path, comments=(_RIDER,))
    assert isinstance(overlay.secret_sink, _Sink)
    assert overlay.secret_sink.stored == []
    assert recorder["dod_gate_subject"] == expected
    assert "The shared subject text." in expected
    assert _RIDER in expected
    assert "livespec-dod-judgement-unavailable" not in expected


def _overlay(*, tmp_path: Path) -> DispatchOverlay:
    return DispatchOverlay(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        recorded=RecordedDispatch(
            plan=build_plan(
                repo=tmp_path,
                work_item_id="bd-ib-7f66ar",
                workflow_toml=tmp_path / "wf.toml",
                goal_file=tmp_path / "goal.md",
                fabro_bin="fabro",
                janitor=None,
                janitor_checkout=tmp_path / "janitor-co",
                config_text='{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}',
                default_branch="master",
                fabro_factory_name="hp",
            ),
            committed_workflow=tmp_path / "wf.toml",
            payload=WorkflowPayload(
                payload_dir=tmp_path / "payload",
                graph=tmp_path / "payload" / "workflow.fabro",
                timeouts=NodeTimeouts(
                    configured={}, stall_seconds=900, stall_layer="workflow-default"
                ),
                node_seconds={},
                node_commands={},
            ),
            git_author=GitAuthor(name="Factory", email="factory@example.invalid"),
            comments=tuple(
                WorkItemComment(text=text, author=None, created_at=None)
                for text in (_RIDER, _RECEIPT)
            ),
        ),
        overlay_file=tmp_path / "overlay.toml",
        dispatch_id="0f6d2f1a9f1c4f0b9d3a2c5e7b8a4d61",
        token=lambda: _GITHUB_TOKEN,
        secret_sink=_Sink(),
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-7f66ar",
        type="feature",
        status="active",
        title="Judge the Definition of Done before dispatch",
        description=(
            "## Definition of Done\n\n"
            "- The judgement runs before an item moves to ready.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-20T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


@dataclass(kw_only=True)
class _Sink:
    """A vault sink that records rather than stores."""

    stored: list[str] = field(default_factory=list)

    def set(self, *, secret: VaultSecret) -> str | None:
        self.stored.append(secret.secret_name)
        return None


def test_the_recording_vault_sink_double_can_observe_a_store() -> None:
    """The control on the double: an EMPTY stored set above has to mean something."""
    sink = _Sink()

    secret = VaultSecret(env_name="GITHUB_TOKEN", secret_name=_PROBE_VAULT_KEY, value="v")
    assert sink.set(secret=secret) is None
    assert sink.stored == [_PROBE_VAULT_KEY]
