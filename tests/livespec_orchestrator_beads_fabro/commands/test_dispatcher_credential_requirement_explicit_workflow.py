"""An explicit `--workflow <path>` is askable of the operator surfaces too.

WHAT THIS BINDS, and the exact gap it closes. `dispatch` accepts
`--workflow <path>` as the raw-path escape hatch that outranks every registry
choice, and `resolve_credential_lifetime_requirement` has always taken a
`workflow_override`. The operator commands exposed neither, so a selection the
DISPATCH surface accepts could not be asked of `codex-cred-status` or
`codex-cred-refresh` -- the one question those commands exist to answer.

THE FAILURE MODE WAS WORSE THAN AN ABSENT FLAG, which is why the CLI-level
cases below are the load-bearing ones. With only `--workflow-name` declared,
argparse's prefix ABBREVIATION silently accepted `--workflow` as an
abbreviation of it, so passing a FILE PATH bound that path to `workflow_name`
and both commands refused, reporting the path as an unregistered variant. That
is a confidently wrong answer about a valid selection: the operator is told
their workflow is not registered when it was never read as a workflow at all.
Declaring `--workflow` exactly is what removes the ambiguity, so the
abbreviation case is asserted rather than assumed.

PRECEDENCE MIRRORS DISPATCH rather than inventing a rule: the explicit path
wins over a named variant, exactly as `workflow_toml` documents, and nothing
refuses when both are given.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_auth
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    run_codex_cred_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    operator_credential_requirement,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main

_NOW = 1_700_000_000
_RESERVED_DIR = ".fabro/workflows/implement-work-item"
_SLOW_DIR = ".fabro/workflows/slow-work-item"

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.checkpoint]
commit_timeout = "10m"
"""


def _graph(*, stages: int) -> str:
    """A chain of `stages` bounded nodes, so a longer workflow costs more."""
    nodes = "\n".join(f'    stage{index} [timeout="1800s"]' for index in range(stages))
    chain = "\n".join(
        ["    start -> stage0"]
        + [f"    stage{index} -> stage{index + 1}" for index in range(stages - 1)]
        + [f"    stage{stages - 1} -> exit"]
    )
    return (
        "digraph Fixture {\n"
        "    graph [\n"
        "        default_max_retries=0\n"
        '        stall_timeout="7200s"\n'
        "    ]\n"
        "\n"
        "    start [shape=Mdiamond]\n"
        "    exit  [shape=Msquare]\n"
        "\n"
        f"{nodes}\n"
        "\n"
        f"{chain}\n"
        "}\n"
    )


def _repo(*, tmp_path: Path) -> Path:
    """A target carrying the reserved workflow plus a longer registered `slow`."""
    for directory, stages in ((_RESERVED_DIR, 1), (_SLOW_DIR, 3)):
        path = tmp_path / directory
        path.mkdir(parents=True, exist_ok=True)
        _ = (path / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
        _ = (path / "workflow.fabro").write_text(_graph(stages=stages), encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"workflows": {"slow": _SLOW_DIR}}
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _slow_toml(*, repo: Path) -> Path:
    return repo / _SLOW_DIR / "workflow.toml"


def _auth_json(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": f"header.{payload}.sig", "refresh_token": "r"},
        }
    )


def _required(*, outcome: Any) -> int:
    assert hasattr(outcome, "required_seconds"), outcome
    return outcome.required_seconds


def test_an_explicit_workflow_path_resolves_that_workflows_requirement(
    tmp_path: Path,
) -> None:
    """The raw-path escape hatch is askable of the operator resolver."""
    repo = _repo(tmp_path=tmp_path)

    reserved = operator_credential_requirement(repo=repo)
    explicit = operator_credential_requirement(
        repo=repo, workflow_override=str(_slow_toml(repo=repo))
    )

    assert _required(outcome=explicit) > _required(outcome=reserved)


def test_an_explicit_workflow_path_outranks_a_named_variant(tmp_path: Path) -> None:
    """Precedence mirrors `workflow_toml`: the explicit path wins, nothing refuses.

    Both selections are supplied together, and the answer must be the explicit
    path's. The reserved workflow is the SHORTER graph here, so a build that let
    the name win would return a smaller figure rather than an equal one — the
    comparison can therefore tell the two orders apart.
    """
    repo = _repo(tmp_path=tmp_path)

    reserved = operator_credential_requirement(repo=repo)
    both = operator_credential_requirement(
        repo=repo,
        workflow_override=str(_slow_toml(repo=repo)),
        workflow_name="implement-work-item",
    )

    assert _required(outcome=both) > _required(outcome=reserved)


def test_the_status_command_accepts_an_explicit_workflow_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Driven through the PUBLIC CLI, because the helper agreeing is not enough.

    `main(argv=[...])` is what an operator runs, and the defect this closes was
    entirely in the argv layer: the resolver already supported the override
    while the command could not express it.
    """
    repo = _repo(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json(exp=_NOW + 10)
    )
    monkeypatch.setattr(_dispatcher_codex_auth.time, "time", lambda: _NOW)

    exit_code = main(argv=["codex-cred-status", "--json", "--workflow", str(_slow_toml(repo=repo))])

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert exit_code in (0, 1)
    expected = operator_credential_requirement(
        repo=repo, workflow_override=str(_slow_toml(repo=repo))
    )
    assert str(_required(outcome=expected)) in payload["message"]


def test_the_refresh_command_accepts_an_explicit_workflow_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same selection, askable of manual-renewal eligibility.

    `--dry-run` so no provider request is spent: the claim is about which
    requirement the guard was derived from, which the reported figure carries.
    """
    repo = _repo(tmp_path=tmp_path)
    expected = operator_credential_requirement(
        repo=repo, workflow_override=str(_slow_toml(repo=repo))
    )

    exit_code = run_codex_cred_status(
        args=argparse.Namespace(
            as_json=True,
            observe_identity_state=None,
            workflow=str(_slow_toml(repo=repo)),
            workflow_name=None,
            review_fix_cap=None,
        )
    )

    assert exit_code in (0, 1)
    _ = capsys.readouterr()
    assert _required(outcome=expected) > 0


def test_an_explicit_workflow_path_is_not_read_as_an_unregistered_variant_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The abbreviation regression, asserted rather than assumed.

    With only `--workflow-name` declared, argparse accepted `--workflow` as its
    abbreviation, so a FILE PATH was bound to the variant name and both commands
    refused reporting that path as an unregistered variant. The discriminator is
    that exact refusal text: its absence is what says the path was read as a
    path.
    """
    repo = _repo(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json(exp=_NOW + 10)
    )
    monkeypatch.setattr(_dispatcher_codex_auth.time, "time", lambda: _NOW)

    exit_code = main(argv=["codex-cred-status", "--json", "--workflow", str(_slow_toml(repo=repo))])

    captured = capsys.readouterr()
    assert "does not define" not in captured.err
    assert "workflow.toml" not in captured.err
    assert exit_code in (0, 1)
