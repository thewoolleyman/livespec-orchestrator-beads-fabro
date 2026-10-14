"""A graph reference this process cannot resolve is never read against its CWD.

Work-item ``bd-ib-xi63mq``, review round 1. The sibling file
`test_dispatcher_hook_limit_production_projection.py` asserts that the dispatch
projects the PAYLOAD graph's own limit; this asserts what happens when the
overlay is given only the NAME and no artifact to read it at, which is the state
the whole defect lived in.

WHY THIS IS A GUARD AND NOT DEAD CODE. The production caller now always supplies
the absolute artifact, so the relative arm cannot be reached from
`materialize_overlay` today. It is the fail-closed answer to the next caller that
forgets, and the direction it fails in is what matters: a relative reference is
NOT an unreadable path, it is a readable path to the WRONG file, because
`workflow.fabro` is the conventional graph name and a dispatching repository has
one. Resolved against the Dispatcher's working directory it yields a real literal
duration from a real graph -- which the node would enforce and then NAME as the
limit that ended its push. So the arm is asserted with a decoy in place: the only
pass available is "read nothing", and reading the decoy is a distinguishable
failure rather than a silent one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_LIMITS_FILENAME,
    HOOK_LIMIT_PROGRAM_FILENAME,
    PUBLISH_DRAFT_NODE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

# Opaque non-secret placeholders, bound to locals so ruff's hardcoded-credential
# rules do not read the literals at the call sites as real ones.
_FAKE_TOKEN = "relative-reference-oauth-placeholder"
_FAKE_GITHUB_TOKEN = "relative-reference-github-placeholder"

# A deliberately odd duration, so "this number is absent from the rendered
# config" is evidence about the decoy rather than about a round figure the
# overlay might carry for some unrelated reason.
_DECOY_LIMIT_SECONDS = 913
_FIGURE_RE = re.compile(r"LIVESPEC_PUBLISH_DRAFT_[A-Z_]+_SECONDS=(\d+)")

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_DECOY_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "\n"
    f"    {PUBLISH_DRAFT_NODE} [\n"
    f'        timeout="{_DECOY_LIMIT_SECONDS}s"\n'
    "    ]\n"
    "}\n"
)


def test_a_relative_graph_reference_withholds_the_limit_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reference is not resolved against the working directory the decoy sits in.

    Three things are required of one call, and each would pass while another
    failed: the observer is still landed (withholding bounds nothing, it does not
    disable the mechanism), no figure at all is projected, and the DECOY's
    duration specifically is absent -- which is the assertion that tells
    "resolved nothing" apart from "resolved the wrong graph".
    """
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / "workflow.fabro").write_text(_DECOY_GRAPH, encoding="utf-8")
    surfaced: list[str] = []

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path / "committed",
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        graph_override=Path("workflow.fabro"),
        warn=surfaced.append,
    )

    assert rendered is not None
    assert HOOK_LIMIT_PROGRAM_FILENAME in rendered
    assert HOOK_LIMIT_LIMITS_FILENAME not in rendered
    assert _FIGURE_RE.findall(rendered) == []
    assert str(_DECOY_LIMIT_SECONDS) not in rendered
    assert len(surfaced) == 1
    assert PUBLISH_DRAFT_NODE in surfaced[0]
    assert "workflow.fabro" in surfaced[0]
