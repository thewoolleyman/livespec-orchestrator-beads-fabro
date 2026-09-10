"""Fail-closed edge coverage for the Dispatcher Git-author policy."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import (
    GitAuthor,
    apply_workflow_git_author,
    git_author_env_lines,
    read_dispatch_git_author,
    resolve_workflow_git_author,
    workflow_git_author_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_AUTHOR = GitAuthor(name="Chad Woolley", email="thewoolleyman@gmail.com")
_WORKER_TOKEN = "operator-worker-token"
_TRANSPORT_TOKEN = "transport-app-token"


def _write_policy(*, repo: Path, policy: object) -> None:
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(json.dumps({"git_author": policy}), encoding="utf-8")


@pytest.mark.parametrize("body", ["{ broken", "[]"], ids=("malformed", "non-object"))
def test_unreadable_config_shapes_refuse(tmp_path: Path, body: str) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(body, encoding="utf-8")

    refusal = read_dispatch_git_author(repo=tmp_path)

    assert isinstance(refusal, str)
    assert ".livespec.jsonc" in refusal


def test_absent_config_refuses(tmp_path: Path) -> None:
    refusal = read_dispatch_git_author(repo=tmp_path)

    assert isinstance(refusal, str)
    assert "cannot read" in refusal


@pytest.mark.parametrize(
    "policy",
    [
        {
            "operator_name": "Chad Woolley",
            "operator_email": "thewoolleyman@gmail.com",
            "mechanical_authors": {},
        },
        {
            "operator_name": "Chad Woolley",
            "operator_email": "thewoolleyman@gmail.com",
            "mechanical_authors": ["release-bot"],
        },
        {
            "operator_name": "Chad Woolley",
            "operator_email": "thewoolleyman@gmail.com",
            "mechanical_authors": [{"name": "Release Bot", "email": ""}],
        },
        {
            "operator_name": "Chad Woolley",
            "operator_email": "thewoolleyman@gmail.com",
            "mechanical_authors": [{"name": "Chad Woolley", "email": "thewoolleyman@gmail.com"}],
        },
    ],
    ids=("non-array", "non-object-entry", "empty-entry", "operator-is-mechanical"),
)
def test_invalid_mechanical_author_classifications_refuse(tmp_path: Path, policy: object) -> None:
    _write_policy(repo=tmp_path, policy=policy)

    refusal = read_dispatch_git_author(repo=tmp_path)

    assert isinstance(refusal, str)
    assert "git_author" in refusal


def test_workflow_author_duplicate_or_incomplete_sections_refuse() -> None:
    duplicate = (
        '[run.git.author]\nname = "Chad Woolley"\nemail = "thewoolleyman@gmail.com"\n'
        '[run.git.author]\nname = "Chad Woolley"\nemail = "thewoolleyman@gmail.com"\n'
    )
    incomplete = '[run.git.author]\nname = ""\nemail = 7\n'

    assert "more than once" in (
        workflow_git_author_error(committed_text=duplicate, author=_AUTHOR) or ""
    )
    assert "non-empty" in (
        workflow_git_author_error(committed_text=incomplete, author=_AUTHOR) or ""
    )


def test_author_projection_helpers_cover_noop_append_and_conflict_paths() -> None:
    matching = '[run.git.author]\nname = "Chad Woolley"\nemail = "thewoolleyman@gmail.com"\n'
    conflicting = '[run.git.author]\nname = "Fabro"\nemail = "fabro@local"\n'

    assert apply_workflow_git_author(committed_text=matching, author=_AUTHOR) == matching
    appended = apply_workflow_git_author(committed_text="[workflow]", author=_AUTHOR)
    assert appended.startswith("[workflow]\n\n")
    assert git_author_env_lines(author=None) == ""
    assert resolve_workflow_git_author(committed_text="[workflow]\n", author=None) == (
        "[workflow]\n"
    )
    assert resolve_workflow_git_author(committed_text=conflicting, author=_AUTHOR) is None


def test_materialization_and_overlay_refuse_a_conflicting_workflow_author(
    tmp_path: Path,
) -> None:
    _write_policy(
        repo=tmp_path,
        policy={
            "operator_name": _AUTHOR.name,
            "operator_email": _AUTHOR.email,
        },
    )
    workflow = tmp_path / "workflow.toml"
    committed = (
        '_version = 1\n[workflow]\ngraph = "workflow.fabro"\n'
        '[run.environment]\nid = "livespec-ci"\n'
        '[run.git.author]\nname = "Fabro"\nemail = "fabro@local"\n'
    )
    _ = workflow.write_text(committed, encoding="utf-8")
    _ = (tmp_path / "workflow.fabro").write_text(
        'digraph Work { graph [stall_timeout="60s"] }\n', encoding="utf-8"
    )

    result = materialize_dispatch(
        args=argparse.Namespace(
            workflow=str(workflow),
            workflow_name=None,
            repo=str(tmp_path),
            acp_node=None,
        ),
        repo=tmp_path,
        work_item_id="bd-ib-conflicting-author",
        journal=Mock(),
    )
    rendered = render_run_config_overlay(
        committed_text=committed,
        workflow_dir=tmp_path,
        token=_WORKER_TOKEN,
        github_token=_TRANSPORT_TOKEN,
        siblings=None,
        git_author=_AUTHOR,
    )

    assert isinstance(result, MaterializationRefusal)
    assert result.stage == "git-author"
    assert rendered is None


def test_unreadable_workflow_reaches_the_payload_refusal(tmp_path: Path) -> None:
    _write_policy(
        repo=tmp_path,
        policy={
            "operator_name": _AUTHOR.name,
            "operator_email": _AUTHOR.email,
        },
    )

    result = materialize_dispatch(
        args=argparse.Namespace(
            workflow=str(tmp_path / "absent-workflow.toml"),
            workflow_name=None,
            repo=str(tmp_path),
            acp_node=None,
        ),
        repo=tmp_path,
        work_item_id="bd-ib-unreadable-workflow",
        journal=Mock(),
    )

    assert isinstance(result, MaterializationRefusal)
    assert result.stage == "workflow-payload"
    assert "unreadable" in result.detail


def test_locked_red_journal_helper_executes_its_append_path() -> None:
    """Keep coverage whole without changing the integrity-locked Red file."""
    namespace = runpy.run_path(str(Path(__file__).with_name("test_dispatcher_git_author.py")))
    journal = namespace["_RecordingJournal"]()

    journal.append(record={"stage": "coverage"})

    assert journal.records == [{"stage": "coverage"}]
