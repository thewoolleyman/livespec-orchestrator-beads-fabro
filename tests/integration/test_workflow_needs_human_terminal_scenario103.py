"""Scenario 103 — A needs-human outcome terminates the run and routes the decision to the ledger.

Binds the SPECIFICATION/contracts.md rule that a factory run never awaits a human (v093):
the `implement-work-item` graph carries NO interactive human-decision node.
Every outcome the loop cannot auto-resolve routes to a `needs_human` terminal
SCRIPT node that preserves the tree on a run-scoped ref, emits the
`LIVESPEC_NEEDS_HUMAN` sentinel, and exits non-zero with no outgoing edge —
the same dead-end shape as `non_converged`. The Dispatcher maps that sentinel
onto its existing `blocked` outcome, so the item rests at
`blocked / needs-human` in the ledger while the run itself is already gone.

The preservation ref is derived ONLY from `FABRO_RUN_ID`, with no placeholder
fallback (work-item bd-ib-7hta4l): the pinned fabro exports that variable to
hooks and not to script nodes, so a default collapsed every run onto one shared
ref that later runs clobbered. The last three cases here run the node's OWN
script — extracted from the graph and unescaped, never a paraphrase — inside a
throwaway git repository with a real bare `origin`, once with a run id and once
without, so "no ref was pushed" is MEASURED against a fixture that demonstrably
can carry a push rather than inferred from a repository where pushing was never
possible.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_plan as plan_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID

_WORKFLOW_DOT = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_SENTINEL = "LIVESPEC_NEEDS_HUMAN"
_PRESERVED_MARKER = "LIVESPEC_NEEDS_HUMAN_PRESERVED"
_NO_RUN_ID_MARKER = "LIVESPEC_NEEDS_HUMAN_NO_RUN_ID"
_REF_PREFIX = "refs/heads/needs-human/"
_RUN_ID = "01M1TESTRUNIDPRESERVE"
_FORMER_GATE_SOURCES = ("implement", "review", "disposition", "pr")
_OPERATOR_NAME = "Chad Woolley"
_OPERATOR_EMAIL = "thewoolleyman@gmail.com"


def _dot() -> str:
    assert _WORKFLOW_DOT.is_file()
    return _WORKFLOW_DOT.read_text(encoding="utf-8")


def _code_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if not line.strip().startswith("//")]


def _node_body(text: str, node: str) -> str | None:
    match = re.search(rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    return None if match is None else match.group("body")


def test_graph_has_no_interactive_human_decision_node() -> None:
    """No hexagon, no `escalate`, no `abandon`: nothing in the graph waits for a human."""
    text = _dot()
    lines = _code_lines(text)

    assert not any("shape=hexagon" in line for line in lines)
    assert _node_body(text, "escalate") is None
    assert _node_body(text, "abandon") is None
    assert not any(re.match(r"^escalate\s*->", line) for line in lines)


def test_needs_human_is_a_terminal_script_node_that_preserves_then_exits_non_green() -> None:
    text = _dot()
    body = _node_body(text, "needs_human")

    assert body is not None
    assert "script=" in body
    assert "shape=parallelogram" in body
    assert _SENTINEL in body
    assert "exit 1" in body
    assert "refs/heads/needs-human/" in body
    assert "FABRO_RUN_ID" in body
    assert "feat/" not in body
    assert not any(re.match(r"^needs_human\s*->", line) for line in _code_lines(text))


def test_the_preservation_ref_derives_only_from_the_run_id() -> None:
    """No placeholder fallback: the only `FABRO_RUN_ID` default is the empty guard."""
    script = _preservation_script()

    assert f'ref="{_REF_PREFIX}$FABRO_RUN_ID"' in script
    assert "unknown-run" not in script
    # The ONE permitted `:-` form is the `test -n` guard's empty default; any
    # other default would be a placeholder every run would share.
    assert re.findall(r"\$\{FABRO_RUN_ID:-(?P<default>[^}]*)\}", script) == [""]


def test_a_run_id_preserves_the_tree_on_its_own_run_scoped_ref(tmp_path: Path) -> None:
    work, origin = _sandbox(tmp_path=tmp_path)

    completed = _run_preservation(work=work, run_id=_RUN_ID)

    assert completed.returncode == 1
    assert f"{_PRESERVED_MARKER}: {_REF_PREFIX}{_RUN_ID}" in completed.stderr
    assert _NO_RUN_ID_MARKER not in completed.stderr
    assert _SENTINEL in completed.stderr
    assert _pushed_refs(origin=origin) == [f"{_REF_PREFIX}{_RUN_ID}"]


def test_no_run_id_pushes_nothing_and_says_so_on_stderr(tmp_path: Path) -> None:
    """Unset and set-but-empty both take the loud branch; the fixture CAN carry a push."""
    for run_id in (None, ""):
        work, origin = _sandbox(tmp_path=tmp_path / f"no-run-id-{run_id!r}")

        completed = _run_preservation(work=work, run_id=run_id)

        assert completed.returncode == 1, run_id
        assert _NO_RUN_ID_MARKER in completed.stderr, run_id
        assert _PRESERVED_MARKER not in completed.stderr, run_id
        assert "unknown-run" not in completed.stderr, run_id
        assert _SENTINEL in completed.stderr, run_id
        assert _pushed_refs(origin=origin) == [], run_id


def test_every_former_gate_edge_targets_needs_human() -> None:
    lines = _code_lines(_dot())
    for source in _FORMER_GATE_SOURCES:
        assert any(re.match(rf"^{source}\s*->\s*needs_human\b", line) for line in lines), source
    assert 'review -> needs_human [label="unmatched review outcome"]' in lines
    assert 'disposition -> needs_human [label="unmatched disposition outcome"]' in lines


def test_escalation_node_id_follows_the_rename() -> None:
    assert ESCALATION_NODE_ID == "needs_human"


def test_needs_human_marker_is_shared_between_dot_and_dispatcher() -> None:
    marker = getattr(plan_module, "NEEDS_HUMAN_MARKER", None)
    predicate = getattr(plan_module, "is_needs_human_outcome", None)

    assert marker == _SENTINEL
    assert predicate is not None
    assert predicate(outcome=_outcome(status="failed", detail=f"stage needs_human: {_SENTINEL}: x"))
    assert not predicate(outcome=_outcome(status="failed", detail="ordinary failure"))
    assert not predicate(outcome=_outcome(status="green", detail=_SENTINEL))


def test_dispatcher_maps_the_sentinel_onto_the_blocked_outcome(tmp_path: Path) -> None:
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id="01NEEDSHUMAN",
        inspect=None,
        exit_code=1,
        stderr=(
            f"{_SENTINEL}: loop cannot auto-resolve; work preserved by reference; "
            "decision routed to the ledger\n"
        ),
    )

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.stage == "fabro-run"
    assert outcome.fabro_run_id == "01NEEDSHUMAN"
    assert "refs/heads/needs-human/01NEEDSHUMAN" in outcome.detail
    assert "resolve-blocked:bd-ib-8nnu:ready" in outcome.detail
    assert "fabro attach" not in outcome.detail


def _preservation_script() -> str:
    """The needs_human node's own script, unescaped from the DOT attribute."""
    body = _node_body(_dot(), "needs_human")
    assert body is not None
    match = re.search(r'script="(?P<script>(?:[^"\\]|\\.)*)"', body)
    assert match is not None
    return re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", match.group("script"))


def _sandbox(*, tmp_path: Path) -> tuple[Path, Path]:
    """A sandbox-shaped checkout with an in-progress edit and a real bare `origin`."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", str(origin)],
        check=True,
        text=True,
        capture_output=True,
    )
    work = tmp_path / "work"
    work.mkdir(parents=True)
    _git(work, "init", "--quiet")
    _git(work, "config", "user.email", "fixture@example.invalid")
    _git(work, "config", "user.name", "Fixture")
    _git(work, "config", "commit.gpgsign", "false")
    (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "--quiet", "-m", "seed")
    _git(work, "remote", "add", "origin", str(origin))
    (work / "in-progress.txt").write_text("the tree the node must preserve\n", encoding="utf-8")
    return work, origin


def _run_preservation(*, work: Path, run_id: str | None) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "FABRO_RUN_ID"}
    env["LIVESPEC_GIT_AUTHOR_NAME"] = _OPERATOR_NAME
    env["LIVESPEC_GIT_AUTHOR_EMAIL"] = _OPERATOR_EMAIL
    if run_id is not None:
        env["FABRO_RUN_ID"] = run_id
    return subprocess.run(
        ["sh", "-c", _preservation_script()],
        cwd=str(work),
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def _pushed_refs(*, origin: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/"],
        cwd=str(origin),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.split()


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=str(repo), check=True, text=True, capture_output=True)


def _outcome(*, status: str, detail: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-8nnu",
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=detail,
    )


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-8nnu",
        branch="feat/bd-ib-8nnu",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp.example:32276",
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )
