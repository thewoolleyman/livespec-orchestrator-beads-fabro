"""The POST-CLAIM Codex projection, scoped to dispatches that route Codex.

`bd-ib-meejjz`, the second of the three surfaces. `SPECIFICATION/scenarios.md`
Scenario 18 is the projection itself and Scenario 19 the freshness refusal
beside it; `SPECIFICATION/contracts.md` section "Worker credential projection"
leaves WHICH projected credentials the freshness gate covers to the
implementation, so not projecting the host Codex credential for a dispatch that
routes no node to Codex is conformant -- there is no projected credential for
the gate to cover.

WHY SKIPPING THE PRE-CLAIM GATE ALONE WOULD NOT HAVE DONE. This leg grades the
credential a SECOND time, after `admit_and_select` has moved the item
`ready -> active` and set its assignee. Left armed, it would refuse there on the
same ageing token the pre-claim gate had just been told to ignore, and the
refusal would leave an `active` row nobody is working with no factory run to
reap -- the stranded shape the pre-claim position was adopted to retire. So the
two surfaces have to agree, which is why they consult ONE predicate.

THE CONTROL IS AN ABSENT HOST CREDENTIAL. Every case below that asserts an
unprotected overlay runs with `read_host_codex_auth` returning `None`, which is
the shape that refuses the dispatch outright today and names `codex login`. An
overlay written at all under that credential is therefore the measurement; a
fixture with a healthy credential could not have returned a hit.

AND THE CODEX TELEMETRY PROJECTION TRAVELS WITH THE CREDENTIAL, which is the
non-obvious half. `$CODEX_HOME` reaches the sandbox only on the credential's own
env lines, and the telemetry step opens with `mkdir -p "$CODEX_HOME"`. Rendered
without the credential it would expand to `mkdir -p ""`, fail, and abort the
sandbox in a prepare step -- so a dispatch that projects no Codex credential
must project no Codex `[otel]` table either. That is asserted here rather than
left to the reader, because it breaks EVERY dispatch rather than an edge case.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_SHIPPED_WORKFLOW = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)

_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_REVIEW_FIX_VISIT_CAP = 4
_NOW = 1_700_000_000
_ONE_HOUR = 3600

_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)

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

_GIT_AUTHOR_BLOCK = {"operator_name": "Operator", "operator_email": "operator@example.com"}


class _RecordingJournal:
    """Collects journal records so a materialization can be asserted on."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _auth_json_with_exp(*, exp: int) -> str:
    """A host Codex `auth.json` whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


def _workflow_files(*, tmp_path: Path) -> Path:
    """A committed run config plus the graph the leg's route check reads."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return committed


def _leg(*, routes_codex: bool, committed: Path) -> Any:
    """Drive the projection leg for one routing, through its real module."""
    module = importlib.import_module(f"{_PACKAGE}._dispatcher_codex_overlay_leg")
    return module.project_codex_overlay_leg(
        committed=committed,
        block={},
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        graph_override=None,
        adapter_inputs=frozenset(),
        clock=lambda: _NOW,
        routes_codex=routes_codex,
    )


def test_an_all_claude_dispatch_neither_grades_nor_projects_the_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No read, no snapshot, no credential-use deadline, and no refusal.

    The host credential is ABSENT, which is the condition this leg refuses on
    today -- so the empty log plus a returned leg is what says the credential
    was never consulted, rather than consulted and forgiven.
    """
    reads: list[str] = []
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: reads.append("read") or None,
    )

    leg = _leg(routes_codex=False, committed=_workflow_files(tmp_path=tmp_path))

    assert not isinstance(leg, str), leg
    assert leg.snapshot is None
    assert leg.credential_use is None
    assert reads == []


def test_a_codex_routing_dispatch_grades_and_stamps_the_deadline_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 18's projection and its enforcement inputs are untouched.

    One argument separates this from the case above -- same workflow, same
    clock -- so a build that returned the unprotected leg unconditionally
    passes that test and fails this one.
    """
    reads: list[str] = []
    fresh = _auth_json_with_exp(exp=_NOW + 10 * _ONE_HOUR)
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: reads.append("read") or fresh,
    )

    leg = _leg(routes_codex=True, committed=_workflow_files(tmp_path=tmp_path))

    assert not isinstance(leg, str), leg
    assert leg.snapshot is not None
    assert leg.credential_use is not None
    # The three enforcement inputs the sandbox guard needs, stamped from this
    # dispatch's own measurements rather than defaulted.
    assert leg.credential_use.credential_expiry_epoch == _NOW + 10 * _ONE_HOUR
    assert leg.credential_use.deadline_epoch > _NOW
    assert leg.credential_use.required_remaining_seconds > 0
    assert reads == ["read"]


def _materialized_overlay_text(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    routes_codex: bool,
) -> str | None:
    """Materialize one overlay against an ABSENT host Codex credential.

    Returns the written overlay text, or `None` when the dispatch was refused.
    An absent credential is the control: it refuses every dispatch today, so an
    overlay existing at all is the measurement.
    """
    committed = _workflow_files(tmp_path=tmp_path)
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: _NOW)
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: None)

    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="bd-ib-meejjz",
        dispatch_id="disp-1",
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        routes_codex=routes_codex,
    )
    if error is not None:
        assert not overlay.exists()
        return None
    return overlay.read_text(encoding="utf-8")


def test_an_all_claude_dispatch_writes_an_overlay_with_no_codex_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unprotected shape, end to end through the overlay writer.

    FOUR absences are asserted rather than one, because each is a separate
    projection and three of them are what a partial implementation leaves
    behind: the credential value, the `$CODEX_HOME` it is written under, the
    credential-use guard, and the Codex `[otel]` table whose own prepare step
    opens with `mkdir -p "$CODEX_HOME"` and would therefore abort the sandbox
    for every dispatch if it were rendered without the credential.

    The Claude OAuth projection is asserted PRESENT in the same breath, which is
    what tells "the Codex credential is not projected" apart from "the overlay
    projects no credentials at all".
    """
    rendered = _materialized_overlay_text(
        tmp_path=tmp_path, monkeypatch=monkeypatch, routes_codex=False
    )

    assert rendered is not None
    assert "CODEX_AUTH_JSON" not in rendered
    assert "CODEX_HOME" not in rendered
    assert "credential-use" not in rendered
    assert "CODEX_OTEL_CONFIG_TOML" not in rendered
    assert "CLAUDE_CODE_OAUTH_TOKEN = " in rendered


def test_a_codex_routing_dispatch_still_refuses_an_absent_host_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 19's post-claim refusal survives where a node routes to Codex.

    The pair of this case and the one above it is the whole claim: one argument
    apart, one writes an overlay and the other refuses naming `codex login`.
    """
    rendered = _materialized_overlay_text(
        tmp_path=tmp_path, monkeypatch=monkeypatch, routes_codex=True
    )

    assert rendered is None


def test_materialize_dispatch_resolves_this_target_routing_once(tmp_path: Path) -> None:
    """The ONE resolution per dispatch, taken where the ACP nodes are resolved.

    It is taken HERE rather than at each consumer because two surfaces read it
    on the dispatch path -- the launch wrap this materialization renders into the
    payload graph, and the projection leg the plan carries it to -- and a second
    reading of the same configuration could not be proven to agree with the
    first while both produced a well-formed answer.

    The fixture is a real copy of the SHIPPED workflow, so the candidates
    resolved are the ones this repository actually dispatches: every one of them
    names `claude-acp`, which is why the answer is `False`.
    """
    repo = tmp_path / "repo"
    variant = repo / ".fabro/workflows/implement-work-item"
    variant.parent.mkdir(parents=True)
    _ = shutil.copytree(_SHIPPED_WORKFLOW.parent, variant)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"git_author": _GIT_AUTHOR_BLOCK}), encoding="utf-8"
    )

    materialized = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        repo=repo,
        work_item_id="bd-ib-meejjz",
        journal=_RecordingJournal(),
    )

    assert not isinstance(materialized, MaterializationRefusal), materialized
    assert materialized.routes_codex is False


def test_the_dispatch_plan_carries_the_routing_and_defaults_to_protected(
    tmp_path: Path,
) -> None:
    """The plan is the carrier, and a caller wiring nothing stays protected.

    Both directions are asserted because the default is what every caller that
    builds a plan for something other than a factory dispatch inherits -- the
    host-record target and the reconcile-merged valve among them -- and a
    default of `False` would silently exempt them.
    """
    common: dict[str, Any] = {
        "repo": tmp_path,
        "work_item_id": "bd-ib-meejjz",
        "workflow_toml": tmp_path / "overlay.toml",
        "goal_file": tmp_path / "goal.md",
        "fabro_bin": "fabro",
        "janitor": None,
        "janitor_checkout": tmp_path / "checkout",
    }

    assert build_plan(**common).routes_codex is True
    assert build_plan(**common, routes_codex=False).routes_codex is False
