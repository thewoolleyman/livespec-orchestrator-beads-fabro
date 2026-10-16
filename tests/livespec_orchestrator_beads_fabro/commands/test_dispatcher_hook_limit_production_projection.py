"""The hook-limit figure, as the PRODUCTION dispatch path actually projects it.

Work-item ``bd-ib-xi63mq``, review round 1. The observation half of
`SPECIFICATION/scenarios.md` Scenario 177 is already bound by
`test_dispatcher_hook_limit_program.py`, which hands the resolver an absolute
graph itself. That is the one thing the dispatch does NOT do: it hands the
overlay the graph REFERENCE -- the name the written config has to carry -- and
for a package-era client `overlay_graph_reference` makes that name RELATIVE to
the collected package. A resolver reading it resolves it against the
Dispatcher's own working directory instead, which is not the payload.

WHY THAT FAILURE IS INVISIBLE WITHOUT THIS FILE, and why it is driven through
`materialize_overlay` rather than through the pure renderer. Every figure in
this chain degrades SAFELY and SILENTLY by design: an unreadable graph withholds
the limit, a withheld limit renders no figures file, and the node's own guard
reads the absent file and pushes exactly as it did before any of this existed.
So the whole mechanism arms or does not arm with no error, no warning and no
journal row either way -- and the only surface on which the difference is
observable is the config the dispatch WRITES. `materialize_overlay` is the
function that writes it.

THE DECOY IS THE AIM CONTROL. Asserting merely that the figure is present would
also pass if the resolver happened to find SOME `workflow.fabro` -- which is the
likeliest accident, because the relative reference is the conventional file name
and the Dispatcher runs from a repository that has one. So the package-era case
plants a decoy graph carrying a DIFFERENT literal duration in the process's
working directory and requires the projected figure to be the payload's. A
reading that resolves against the wrong root cannot pass that by luck.

The pinned-0.254 arm is a PRESERVATION assertion, recorded as one: that client's
reference is already absolute, so it cannot be given a failing Red of its own
without first shipping a regression for it.
"""

from __future__ import annotations

import json
import re
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_LIMITS_FILENAME,
    HOOK_LIMIT_PROGRAM_FILENAME,
    PUBLISH_DRAFT_NODE,
    push_observation_budget_seconds,
)

_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_REVIEW_FIX_VISIT_CAP = 4
_DISPATCH_SCOPE = "01M4XKJE3GZKJ739SRE9VTRDX2"
_WORK_ITEM = "bd-ib-xi63mq"

# The two client shapes `fabro_uses_workflow_package` separates. The Petri
# version is NOT the only non-pinned one that reaches this path: any string that
# is not `fabro 0.254.` takes the package route, including the 0.253.x and
# 0.255.x builds a routine per-host re-pin can land under the ratified `< 0.256`
# ceiling. That is why the package arm is the production arm rather than a
# forward-looking one.
_PINNED_VERSION = "fabro 0.254.0 (8869e88 2026-10-01)"
_PACKAGE_VERSION = "fabro 0.255.0 (deadbee 2026-10-10)"

# Opaque non-secret placeholders, bound to locals so ruff's hardcoded-credential
# rules do not read the literals at the call sites as real ones.
_FAKE_TOKEN = "hook-limit-projection-oauth-placeholder"
_FAKE_GITHUB_TOKEN = "hook-limit-projection-github-placeholder"

# This dispatch's RESOLVED figure, and a decoy that is not it. Both are literal
# durations a `publish_draft` attribute can carry, so neither is distinguishable
# from the other by shape -- only by which file it was read from.
_PAYLOAD_LIMIT_SECONDS = 3600
_DECOY_LIMIT_SECONDS = 900

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_FLEET_MANIFEST_TEXT = json.dumps({"owner": "thewoolleyman", "fleet": [{"repo": "livespec"}]})


def _graph(*, publish_draft_timeout: str | None) -> str:
    """A minimal graph whose `publish_draft` node carries the given duration.

    `None` renders the node with no `timeout` attribute at all, which is the
    shape that makes the figure genuinely unresolvable rather than merely read
    from the wrong place -- the arm that must still degrade safely AND say so.
    """
    timeout = (
        "" if publish_draft_timeout is None else f'        timeout="{publish_draft_timeout}"\n'
    )
    return (
        "digraph ImplementWorkItem {\n"
        "    graph [\n"
        '        stall_timeout="7200s"\n'
        "    ]\n"
        "\n"
        "    implement [\n"
        '        timeout="1800s"\n'
        "    ]\n"
        "\n"
        f"    {PUBLISH_DRAFT_NODE} [\n"
        '        label="Publish the branch"\n'
        f"{timeout}"
        "    ]\n"
        "}\n"
    )


def _package_dir(*, tmp_path: Path) -> Path:
    """This dispatch's materialized workflow package."""
    return tmp_path / f"fabro-workflow-{_DISPATCH_SCOPE}"


def _materialize(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fabro_version: str,
    payload_graph_text: str,
) -> str:
    """Materialize one dispatch's config and return the text it wrote.

    The overlay destination follows the launch shape the version selects, exactly
    as the dispatch places it: INSIDE the package for a package-era client, and
    outside it for the pinned 0.254 client. That placement is what decides
    whether the written reference is relative, so a test that pinned one
    destination for both versions would be asserting against a geometry no
    dispatch produces.
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
    _ = (committed_dir / "workflow.fabro").write_text(
        _graph(publish_draft_timeout="1800s"), encoding="utf-8"
    )
    package_dir = _package_dir(tmp_path=tmp_path)
    package_dir.mkdir(parents=True, exist_ok=True)
    rendered_graph = package_dir / "workflow.fabro"
    _ = rendered_graph.write_text(payload_graph_text, encoding="utf-8")
    overlay = (
        package_dir / "workflow.toml"
        if fabro_version != _PINNED_VERSION
        else tmp_path / f"fabro-run-config-{_DISPATCH_SCOPE}.toml"
    )
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    now = 1_700_000_000
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: now)
    # NO host Codex credential is stood in, and that is a property of the
    # fixture rather than an omission: its `.livespec.jsonc` declares an empty
    # `dispatcher` block, so `codex_routing_for_dispatch` answers that this
    # dispatch routes no node to Codex and `project_codex_overlay_leg` returns
    # before the credential is read at all. A stand-in here would be scaffolding
    # for a read this path cannot reach -- which is exactly how it read when the
    # routing short-circuit landed underneath it.
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=repo,
        work_item_id=_WORK_ITEM,
        dispatch_id=_DISPATCH_SCOPE,
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        graph_override=rendered_graph,
        fabro_version=fabro_version,
    )
    assert error is None, error
    return overlay.read_text(encoding="utf-8")


def _plant_decoy(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Put a DIFFERENT `workflow.fabro` where a relative read would land.

    The Dispatcher runs from a repository that has a `workflow.fabro` of its own,
    so "resolve the reference against the current directory" does not fail
    loudly -- it finds a real graph and reads a real duration out of it. This is
    that condition, reproduced.
    """
    decoy_root = tmp_path / "dispatcher-cwd"
    decoy_root.mkdir(parents=True, exist_ok=True)
    _ = (decoy_root / "workflow.fabro").write_text(
        _graph(publish_draft_timeout=f"{_DECOY_LIMIT_SECONDS}s"), encoding="utf-8"
    )
    monkeypatch.chdir(decoy_root)


# Matched over the WHOLE config text rather than line by line: the figures ride
# a heredoc inside a TOML `script` value, which the renderer emits as one JSON
# string, so their newlines are escapes and they have no physical lines of their
# own. A line-oriented reader finds nothing here and reports every dispatch as
# unarmed.
_FIGURE_RE = re.compile(r"(LIVESPEC_PUBLISH_DRAFT_[A-Z_]+_SECONDS)=(\d+)")


def _figures(*, written: str) -> dict[str, str]:
    """The `KEY=value` figures the materialized config carries, if any."""
    return dict(_FIGURE_RE.findall(written))


def test_a_package_era_dispatch_projects_the_payload_graphs_own_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 177: the bound arms on the client every re-pin can land.

    The three assertions are deliberately not one. The observer must be present
    (it always is); the figures file must be present (it is what arms the bound
    at all); and the figure must be the PAYLOAD's, not the decoy's (it is what
    makes the bound the one the engine will also enforce). A dispatch can fail
    the second while passing the first, and the third while passing both.
    """
    _plant_decoy(tmp_path=tmp_path, monkeypatch=monkeypatch)

    written = _materialize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        fabro_version=_PACKAGE_VERSION,
        payload_graph_text=_graph(publish_draft_timeout=f"{_PAYLOAD_LIMIT_SECONDS}s"),
    )

    assert HOOK_LIMIT_PROGRAM_FILENAME in written
    assert (
        HOOK_LIMIT_LIMITS_FILENAME in written
    ), "the package-era dispatch withheld the publish_draft limit, so its push runs unbounded"
    assert _figures(written=written) == {
        "LIVESPEC_PUBLISH_DRAFT_LIMIT_SECONDS": str(_PAYLOAD_LIMIT_SECONDS),
        "LIVESPEC_PUBLISH_DRAFT_PUSH_BUDGET_SECONDS": str(
            push_observation_budget_seconds(limit_seconds=_PAYLOAD_LIMIT_SECONDS)
        ),
    }


def test_the_pinned_client_keeps_projecting_the_payload_graphs_own_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The absolute-reference client's figure must survive the package-era fix.

    Its reference has always been absolute, so this arm passes today. It is
    asserted beside the package arm because the repair moves which path the
    figure is read from, and a repair that armed the package client by breaking
    the pinned one would look exactly like success from the arm above.
    """
    _plant_decoy(tmp_path=tmp_path, monkeypatch=monkeypatch)

    written = _materialize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        fabro_version=_PINNED_VERSION,
        payload_graph_text=_graph(publish_draft_timeout=f"{_PAYLOAD_LIMIT_SECONDS}s"),
    )

    assert _figures(written=written) == {
        "LIVESPEC_PUBLISH_DRAFT_LIMIT_SECONDS": str(_PAYLOAD_LIMIT_SECONDS),
        "LIVESPEC_PUBLISH_DRAFT_PUSH_BUDGET_SECONDS": str(
            push_observation_budget_seconds(limit_seconds=_PAYLOAD_LIMIT_SECONDS)
        ),
    }


def test_a_genuinely_unresolvable_limit_is_withheld_and_surfaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A figure nothing can resolve still degrades safely -- but no longer quietly.

    The payload graph here names `publish_draft` and gives it no timeout, so the
    resolver is pointed correctly and still has nothing to read. Withholding
    remains right: an invented bound would be enforced and then REPORTED as the
    limit that ended the push. What must not remain is the silence -- the one
    record that the push went out unbounded has to reach the dispatcher stderr
    the `drive` result carries, naming the node and the artifact it could not
    read the figure from.
    """
    written = _materialize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        fabro_version=_PACKAGE_VERSION,
        payload_graph_text=_graph(publish_draft_timeout=None),
    )

    assert HOOK_LIMIT_PROGRAM_FILENAME in written
    assert HOOK_LIMIT_LIMITS_FILENAME not in written
    assert _figures(written=written) == {}
    surfaced = capsys.readouterr().err
    assert (
        PUBLISH_DRAFT_NODE in surfaced
    ), "a withheld publish_draft limit left no record that the push runs unbounded"
    assert str(_package_dir(tmp_path=tmp_path) / "workflow.fabro") in surfaced
