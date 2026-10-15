"""How a dispatch NAMES its rendered graph, per resolved factory client.

Work-item bd-ib-uu5dqq. The launch hands a Petri-era engine the workflow
PACKAGE directory, and that engine collects the package's own `workflow.toml`
as a local workflow -- so an absolute `[workflow] graph` inside it is refused
outright, before any run exists: `invalid file inline reference in
workflow.toml: /tmp/fabro-workflow-<id>/workflow.fabro; invalid workflow path
...: absolute paths are not allowed`. The package must therefore name its graph
relative to its own directory, which is also where the engine resolves an
inline reference from.

The pinned 0.254 client is handed an overlay FILE that lives OUTSIDE the
payload, so its graph can only be named absolutely -- the absolutization that
overlay has always carried -- and that is what the second assertion holds in
place.

Both assertions are driven through `materialize_overlay`, which is the function
that WRITES the file in question; the version-keyed projection it routes
through lives in `_fabro_client`, beside `fabro_uses_workflow_package`, because
that is the module that already owns the pinned-versus-Petri distinction.

The pinned case is a PRESERVATION assertion, and it is recorded here as one: it
cannot be given a failing Red of its own without first shipping a regression for
it, so it is authored in the same Red as the Petri case and holds that
behaviour in place from there on.
"""

from __future__ import annotations

import json
from inspect import signature
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor

_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_REVIEW_FIX_VISIT_CAP = 4
_DISPATCH_SCOPE = "01M4KXRR2ATNJTVP06SWFF3HW7"
_PINNED_VERSION = "fabro 0.254.0 (8869e88 2026-10-01)"
_PETRI_VERSION = "fabro 0.378.0-nightly.0 (candidate)"

# Opaque non-secret placeholders, bound to locals so ruff's hardcoded-credential
# rules do not read the literals at the call sites as real ones.
_FAKE_TOKEN = "package-graph-oauth-placeholder"
_FAKE_GITHUB_TOKEN = "package-graph-github-placeholder"

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)
_FLEET_MANIFEST_TEXT = json.dumps(
    {"owner": "thewoolleyman", "fleet": [{"repo": "livespec"}]},
)


def _written_graph_value(*, text: str) -> str:
    """The one `[workflow] graph` value a materialized config declares."""
    declarations = [line for line in text.splitlines() if line.startswith("graph = ")]
    assert len(declarations) == 1
    return declarations[0].removeprefix('graph = "').removesuffix('"')


def _package_dir(*, tmp_path: Path) -> Path:
    """This dispatch's materialized workflow package."""
    return tmp_path / f"fabro-workflow-{_DISPATCH_SCOPE}"


def _materialize(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overlay: Path,
    fabro_version: str,
) -> str:
    """Materialize one dispatch's config and return the text it wrote.

    The committed workflow, the per-dispatch payload and the overlay destination
    are three separate places on purpose: the payload's rendered graph is what
    the run is pointed at, and WHERE the written config sits relative to it is
    the whole question.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}), encoding="utf-8"
    )
    committed_dir = tmp_path / "ImplementWorkItem"
    committed_dir.mkdir(parents=True, exist_ok=True)
    committed = committed_dir / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed_dir / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    package_dir = _package_dir(tmp_path=tmp_path)
    package_dir.mkdir(parents=True, exist_ok=True)
    rendered_graph = package_dir / "workflow.fabro"
    _ = rendered_graph.write_text(_MINIMAL_GRAPH, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    now = 1_700_000_000
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: now)
    # NO host Codex credential is stood in. This fixture's repository declares no
    # node adapters, so it routes no node to the `codex-acp` agent and the overlay
    # leg projects no Codex credential at all (`bd-ib-meejjz`) -- which is the
    # posture this repository actually dispatches in. A stub here would be dead
    # scaffolding for a read that no longer happens.
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=repo,
        work_item_id="bd-ib-uu5dqq",
        dispatch_id=_DISPATCH_SCOPE,
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        graph_override=rendered_graph,
        fabro_version=fabro_version,
    )
    assert error is None
    return overlay.read_text(encoding="utf-8")


def test_a_petri_package_names_its_graph_relative_to_the_package_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The config INSIDE the package names the graph beside it, not by absolute path.

    The relative value is asserted twice over: as the literal the engine will
    accept, and by RESOLVING it against the package directory to the package's
    own rendered graph -- a reference that parses but points nowhere would fail
    the run just as completely.

    The materializer has to be TOLD which client this dispatch resolved before
    either naming can be that client's own rather than the only one there is, so
    that parameter is asserted first and by itself: without it the call below
    cannot even be made, and a failure there would prove the parameter missing
    rather than the naming wrong.
    """
    assert "fabro_version" in set(signature(materialize_overlay).parameters)

    package_dir = _package_dir(tmp_path=tmp_path)
    package_dir.mkdir(parents=True, exist_ok=True)
    overlay = package_dir / "workflow.toml"

    written = _materialize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        overlay=overlay,
        fabro_version=_PETRI_VERSION,
    )

    graph_value = _written_graph_value(text=written)
    assert not Path(graph_value).is_absolute()
    assert graph_value == "workflow.fabro"
    assert (package_dir / graph_value).resolve() == (package_dir / "workflow.fabro").resolve()


def test_the_pinned_client_keeps_an_absolute_graph_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned 0.254 overlay lives OUTSIDE the payload, so it names it absolutely.

    A relative reference would resolve against whatever directory the engine
    happened to read the overlay from, which for this launch shape is not the
    payload -- so the absolutization is the only reference this client can
    resolve, and it must survive the Petri case above unchanged.
    """
    overlay = tmp_path / f"fabro-run-config-{_DISPATCH_SCOPE}.toml"

    written = _materialize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        overlay=overlay,
        fabro_version=_PINNED_VERSION,
    )

    graph_value = _written_graph_value(text=written)
    assert Path(graph_value).is_absolute()
    assert Path(graph_value) == _package_dir(tmp_path=tmp_path) / "workflow.fabro"
