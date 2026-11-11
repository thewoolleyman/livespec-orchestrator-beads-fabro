"""A review_fix turn that ends on an open Red re-enters review_fix for its Green.

Binds work-item `bd-ib-czhqoq` against `SPECIFICATION/scenarios.md` "Scenario
199 — A fix turn grades each tree once, through its commit hook", the
review_fix half of v335. The commit hook accepts a correctly failing Red, so a
review_fix turn that ends with only the Red commit settles as passed. Routing
that straight to the janitor failed the open Red and the review_fix node never
got a turn to write its Green. These tests execute the `review_fix_open_red_route`
command node decoded from the committed graph, so the factory and the test run
the same bytes.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROUTE = "review_fix_open_red_route"
_STAGE = "review_fix"
_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _WORKFLOW_DIR / "workflow.fabro"
_PROMPT = _WORKFLOW_DIR / "prompts" / "review-fix.md"
_BRIEF_GIT_PATH = "livespec-review-fix-open-red-brief"
_CAUSE_GIT_PATH = "livespec-stage-cause"
_RED_TRAILER = "TDD-Red-Test-File-Checksum: abc123"
_GREEN_TRAILER = "TDD-Green-Verified-At: 2026-11-09T00:00:00Z"
_CHECKPOINT = "fabro(01TESTRUN): review_fix_commit_settle (success)"


def _node(*, name: str) -> dict[str, str]:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    assert name in graph.nodes
    return graph.nodes[name]


def _script() -> str:
    """The route's script from the shipped graph, with the branch input rendered."""
    return _node(name=_ROUTE)["script"].replace("{{ inputs.default_branch }}", "master")


def _run(*, repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _script()], cwd=repo, check=False, capture_output=True, text=True
    )


def _git(*args: str, repo: Path) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _git_file(*, repo: Path, name: str) -> Path:
    return repo / _git("rev-parse", "--git-path", name, repo=repo)


def _repo(*, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _ = subprocess.run(["git", "init", "--bare", "--quiet", str(origin)], check=True)
    repo = tmp_path / "repo"
    _ = subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    _git("config", "user.name", "Test User", repo=repo)
    _git("config", "user.email", "test@example.test", repo=repo)
    _ = (repo / "work.txt").write_text("initial\n", encoding="utf-8")
    _git("add", "work.txt", repo=repo)
    _git("commit", "--quiet", "-m", "initial", repo=repo)
    _git("remote", "add", "origin", str(origin), repo=repo)
    _git("push", "--quiet", "origin", "HEAD:master", repo=repo)
    _git("fetch", "--quiet", "origin", "master", repo=repo)
    return repo


def _commit_test_file(*, repo: Path, message: str) -> str:
    """Commit a test-only change with the given message; return its abbreviated id."""
    tests = repo / "tests"
    tests.mkdir(exist_ok=True)
    _ = (tests / "test_thing.py").write_text(f"# {message}\n", encoding="utf-8")
    _git("add", "tests/test_thing.py", repo=repo)
    _git("commit", "--quiet", "-m", message, repo=repo)
    return _git("rev-parse", "--short", "HEAD", repo=repo)


def _checkpoint(*, repo: Path) -> None:
    """The engine's empty per-node checkpoint, which sits above the turn's own commits."""
    _git("commit", "--quiet", "--allow-empty", "-m", _CHECKPOINT, repo=repo)


def _label(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stderr
    label = json.loads(result.stdout)["preferred_next_label"]
    assert isinstance(label, str)
    return label


def test_an_open_red_at_the_end_of_the_review_fix_turn_routes_back_to_review_fix(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _commit_test_file(repo=repo, message=f"fix: red\n\n{_RED_TRAILER}")
    _checkpoint(repo=repo)

    assert _label(_run(repo=repo)) == _STAGE


def test_the_re_entered_review_fix_brief_names_the_open_red_and_directs_its_green(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    red = _commit_test_file(repo=repo, message=f"fix: red\n\n{_RED_TRAILER}")
    _checkpoint(repo=repo)

    _ = _run(repo=repo)

    brief = _git_file(repo=repo, name=_BRIEF_GIT_PATH).read_text(encoding="utf-8")
    assert red in brief
    assert "Green amend" in brief
    assert "new Red" in brief
    assert "folds engine checkpoint commits above the open Red onto it before amending" in brief
    assert "Do not run git reset --soft, git reset --hard, or any other rewrite" in brief


def test_a_completed_red_green_pair_routes_to_janitor_admission_as_before(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _commit_test_file(repo=repo, message=f"fix: pair\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}")
    _checkpoint(repo=repo)

    assert _label(_run(repo=repo)) == "continue"
    assert not _git_file(repo=repo, name=_BRIEF_GIT_PATH).exists()


def test_a_last_commit_with_no_tdd_trailers_routes_to_janitor_admission_as_before(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _commit_test_file(repo=repo, message="docs: no trailers")
    _checkpoint(repo=repo)

    assert _label(_run(repo=repo)) == "continue"


def test_a_brief_from_an_earlier_visit_is_cleared_once_the_red_is_completed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _commit_test_file(repo=repo, message=f"fix: red\n\n{_RED_TRAILER}")
    assert _label(_run(repo=repo)) == _STAGE
    assert _git_file(repo=repo, name=_BRIEF_GIT_PATH).exists()

    _ = _commit_test_file(repo=repo, message=f"fix: green\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}")

    assert _label(_run(repo=repo)) == "continue"
    assert not _git_file(repo=repo, name=_BRIEF_GIT_PATH).exists()


def test_the_review_fix_visit_limit_reached_on_an_open_red_ends_at_needs_human_naming_it(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    red = _commit_test_file(repo=repo, message=f"fix: red\n\n{_RED_TRAILER}")

    limit = int(_node(name=_STAGE)["max_visits"])
    labels = [_label(_run(repo=repo)) for _ in range(limit)]

    assert labels == [_STAGE] * (limit - 1) + ["needs_human"]
    cause = _git_file(repo=repo, name=_CAUSE_GIT_PATH).read_text(encoding="utf-8")
    assert f"stage: {_STAGE}" in cause
    assert f"open Red commit {red}" in cause


def test_the_graph_routes_the_settled_review_fix_turn_through_the_open_red_route() -> None:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition", ""))
        for edge in graph.edges
    }

    assert ("review_fix_commit_settle", _ROUTE, "") in edges
    assert ("review_fix_commit_settle", "janitor_admission", "") not in edges
    assert (_ROUTE, _STAGE, f"preferred_label={_STAGE}") in edges
    assert (_ROUTE, "needs_human", "preferred_label=needs_human") in edges
    assert (_ROUTE, "janitor_admission", "") in edges
    assert graph.nodes[_ROUTE].get("output_schema") == "routing"


def test_the_review_fix_prompt_reads_the_open_red_brief_and_directs_the_green_amend() -> None:
    text = _PROMPT.read_text(encoding="utf-8")
    section = re.search(
        r"(?s)^## [^\n]*open Red[^\n]*\n(?P<body>.*?)(?=^## |\Z)", text, re.MULTILINE
    )

    assert section is not None
    assert _BRIEF_GIT_PATH in section.group("body")
    assert "Green amend" in section.group("body")
