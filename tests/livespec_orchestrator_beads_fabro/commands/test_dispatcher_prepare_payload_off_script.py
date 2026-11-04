"""No prepare-step payload rides a step's script (bd-ib-coxsfu).

The Petri engine's default `compact` fidelity renders every completed command
stage into every later agent request as its FULL `Script:` text and renders none
of the stage's `env`. A helper program or a base64 archive embedded in a prepare
script is therefore re-sent on every turn of every agent node: measured on petri,
46 prepare scripts were 358,046 characters, about 241,400 tokens, 71% of the
338k-token first-request floor.

This file renders the whole dispatch overlay with every payload-bearing emitter
switched on and grades what a `Script:` line would carry.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PublicationMetadata,
)

_COMMITTED = '[workflow]\ngraph = "workflow.fabro"\n[run.environment]\nid = "sandbox"\n'
# A run of base64 alphabet this long is a payload, not a command: every real
# shell word in a prepare script is far shorter.
_LONG_BASE64_RUN = re.compile(r"[A-Za-z0-9+/=]{200,}")
# What the compact preamble may carry per step. The largest honest script is a
# directory-exclusion or a settings-merge command, a few KB at most.
_MAX_SCRIPT_CHARS = 6000
_MAX_TOTAL_SCRIPT_CHARS = 60000


@pytest.fixture(name="steps")
def _steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
    overlay = render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=tmp_path,
        token="",
        github_token="",
        siblings=None,
        publication_metadata=PublicationMetadata(
            title="Title (bd-x)", body="Work-item bd-x\n\n## Definition of Done\n\n- one.\n"
        ),
    )
    assert overlay is not None
    return list(tomli.loads(overlay)["run"]["prepare"]["steps"])


def test_no_prepare_script_carries_a_heredoc_or_a_base64_chunk(
    steps: list[dict[str, object]],
) -> None:
    offenders = [
        str(step["script"])[:80]
        for step in steps
        if "<<" in str(step["script"]) or _LONG_BASE64_RUN.search(str(step["script"]))
    ]
    assert offenders == []


def test_prepare_scripts_are_small_in_total(steps: list[dict[str, object]]) -> None:
    sizes = [len(str(step["script"])) for step in steps]
    assert max(sizes) <= _MAX_SCRIPT_CHARS
    assert sum(sizes) <= _MAX_TOTAL_SCRIPT_CHARS
