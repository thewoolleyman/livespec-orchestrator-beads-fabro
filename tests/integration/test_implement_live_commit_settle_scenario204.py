"""Scenario 179/204 (work-item bd-ib-xj3qqb) — a turn that ends mid-commit waits for the commit.

`SPECIFICATION/contracts.md` "An implement turn that ends incomplete does not
succeed" says that before an `implement`, `fix` or `review_fix` stage's outcome
is decided the run MUST wait until every commit run the turn started through the
detached commit runner has reached its own terminal state, and that the wait
MUST NOT consume the node's retry budget or count as a turn. Seven factory runs
(bd-ib-64eyd5 ... bd-ib-jqn7he) ended in LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS
because the agent ended its turn while the runner's commit hook was still
running.

The mechanism is two command nodes, `implement_commit_settle` and
`review_fix_commit_settle`, which run the runner's own `settle` operation, and a
reader in `implement_hook_route`. These cases execute the COMMITTED node script
bytes in a throwaway clone:

- the settle node keys on the runner's recorded commit runs, so a run the agent
  watched by hand and never `wait`ed on is still waited out;
- a `passed` run earns one re-entry that does not spend the incomplete-turn
  budget;
- a `failed` run's brief names the run and carries the hook's failed targets and
  error lines;
- a `no-verdict` run's brief states that it ended without a verdict and that no
  commit was made.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_NODE_TIMEOUT_SECONDS,
    derive_fabro_timeout_seconds,
    node_timeouts_from_block,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _PAYLOAD / "workflow.fabro"
_PROMPT = _PAYLOAD / "prompts" / "implement.md"

_IMPLEMENT_SETTLE = "implement_commit_settle"
_REVIEW_FIX_SETTLE = "review_fix_commit_settle"
_FIX_SETTLE = "fix_commit_settle"
_ROUTE = "implement_hook_route"

_LIVE_GIT_PATH = "livespec-implement-live-commit"
_REVIEW_FIX_LIVE_GIT_PATH = "livespec-review-fix-live-commit"
_FIX_LIVE_GIT_PATH = "livespec-fix-live-commit"
_REFUSAL_GIT_PATH = "livespec-implement-hook-refusal"
_REENTRIES_GIT_PATH = "livespec-implement-hook-reentries"
_SETTLED_REENTRIES_GIT_PATH = "livespec-implement-settled-reentries"
_RECORD_GIT_PATH = "livespec-implement-completion"
_STAGE_CAUSE_GIT_PATH = "livespec-stage-cause"

_RUN_ID = "commit-00000000000000000000000000000001"
_HEAD = "0123456789abcdef0123456789abcdef01234567"
_FAILED_TARGET = "check-types"
_ERROR_LINE = 'module.py:3:1 - error: Type of "x" is partially unknown (reportUnknownVariableType)'
_SETTLED_REENTER = "LIVESPEC_IMPLEMENT_COMMIT_RUN_SETTLED_REENTER"
_FAILED_REENTER = "LIVESPEC_IMPLEMENT_COMMIT_RUN_FAILED_REENTER"
_NO_VERDICT_REENTER = "LIVESPEC_IMPLEMENT_COMMIT_RUN_NO_VERDICT_REENTER"
_INCOMPLETE_REENTER = "LIVESPEC_IMPLEMENT_INCOMPLETE_REENTER"
_REENTRY_EXHAUSTED = "LIVESPEC_IMPLEMENT_REENTRY_BUDGET_EXHAUSTED"
_HOOK_REFUSED_EXHAUSTED = "LIVESPEC_IMPLEMENT_HOOK_REFUSED_BUDGET_EXHAUSTED"
_CONFIGURED_DELTA = 137
_SETTLE_VISITS = 3

# A refusing pre-commit hook: if the route ran it over the staged tree, its
# distinctive line would appear in the brief, which is what separates "the brief
# came from the commit run's own record" from "the route re-ran the hook".
_STAGED_HOOK_ONLY_LINE = "STAGED-TREE-HOOK-RERUN-MARKER"
_REFUSING_HOOK = f"""#!/bin/sh
printf '{_STAGED_HOOK_ONLY_LINE}\\n'
printf 'Failed targets (1):\\n'
printf '  - check-lint\\n'
exit 1
"""


def _targets(*, source: str) -> list[tuple[str, str]]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return [
        (edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
        if edge.source == source
    ]


def _attributes(*, node: str) -> dict[str, str]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return dict(parsed.nodes.get(node, {}))


def _clone(tmp_path: Path, *, hook: str | None = None, staged: bool = False) -> Path:
    repo = tmp_path / "clone"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    if hook is not None:
        hook_path = repo / ".git" / "hooks" / "pre-commit"
        _ = hook_path.write_text(hook, encoding="utf-8")
        hook_path.chmod(0o755)
    if staged:
        _ = (repo / "module.py").write_text("x = 1\n", encoding="utf-8")
        _ = subprocess.run(["git", "add", "module.py"], cwd=repo, check=True)
    _ = (repo / ".git" / _STAGE_CAUSE_GIT_PATH).write_text(
        "stage: implement\ncause: LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: stopped\n", encoding="utf-8"
    )
    _ = (repo / ".git" / _RECORD_GIT_PATH).write_text(
        '{"definition_of_done_complete": false}\n', encoding="utf-8"
    )
    return repo


def _git_file(*, repo: Path, name: str) -> Path:
    return repo / ".git" / name


def _run_node(*, repo: Path, node: str, plugins: Path) -> subprocess.CompletedProcess[str]:
    script = _attributes(node=node).get("script", "exit 2")
    env = dict(os.environ)
    env["LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT"] = str(plugins)
    return subprocess.run(
        ["sh", "-c", script], cwd=repo, check=False, capture_output=True, text=True, env=env
    )


def _plugins(tmp_path: Path) -> Path:
    plugins = tmp_path / "plugins"
    plugins.mkdir(parents=True)
    _ = (plugins / COMMIT_RUNNER_PROGRAM_FILENAME).write_text(
        commit_runner_program_source(), encoding="utf-8"
    )
    return plugins


def _run_record(*, repo: Path, record: dict[str, object], pid: int | None = None) -> Path:
    runs = repo / ".git" / "livespec-commit-runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{_RUN_ID}.json"
    _ = path.write_text(json.dumps(record), encoding="utf-8")
    if pid is not None:
        _ = path.with_suffix(".pid").write_text(f"{pid}\n", encoding="utf-8")
    return path


def _brief(*, state: str, body: str) -> str:
    return f"{state}\n{body}"


def _routed(*, repo: Path) -> subprocess.CompletedProcess[str]:
    script = _attributes(node=_ROUTE).get("script", "exit 2")
    return subprocess.run(
        ["sh", "-c", script], cwd=repo, check=False, capture_output=True, text=True, env=os.environ
    )


def test_the_turn_reaches_the_settle_before_the_completion_gate_on_both_outcomes() -> None:
    """`implement` and the amendment classifier both feed the settle; it feeds the gate."""
    assert ("implement_commit_settle", "") in _targets(source="implement")
    assert (_IMPLEMENT_SETTLE, "") in _targets(source="implement_amendment_route")
    assert _targets(source=_IMPLEMENT_SETTLE) == [("implement_completion", "")]


def test_review_fix_reaches_the_settle_before_the_janitor() -> None:
    """The review-fix turn's ordinary route waits out its commit runs, then validates."""
    assert ("review_fix_commit_settle", "") in _targets(source="review_fix")
    assert _targets(source=_REVIEW_FIX_SETTLE) == [("janitor", "")]
    assert ("needs_human", "outcome=failed") in _targets(source="review_fix")


def test_both_settle_nodes_are_command_nodes_that_run_the_runners_settle_operation() -> None:
    """The mechanism is the runner's own bounded wait, over its own recorded runs."""
    for node, brief in (
        (_IMPLEMENT_SETTLE, _LIVE_GIT_PATH),
        (_REVIEW_FIX_SETTLE, _REVIEW_FIX_LIVE_GIT_PATH),
    ):
        attributes = _attributes(node=node)
        assert attributes.get("shape") == "parallelogram", node
        assert "settle --timeout-seconds" in attributes.get("script", ""), node
        assert f"git rev-parse --git-path {brief}" in attributes.get("script", ""), node
        assert attributes.get("max_visits") == str(_SETTLE_VISITS), node


def test_the_settle_node_writes_the_brief_for_a_run_that_ended_without_a_verdict(
    tmp_path: Path,
) -> None:
    """A commit run the turn left behind with no live process made no commit, and says so."""
    repo = _clone(tmp_path)
    plugins = _plugins(tmp_path)
    _ = _run_record(repo=repo, record={"state": "running"}, pid=4194303)

    result = _run_node(repo=repo, node=_IMPLEMENT_SETTLE, plugins=plugins)

    assert result.returncode == 0, result.stderr
    lines = _git_file(repo=repo, name=_LIVE_GIT_PATH).read_text(encoding="utf-8").splitlines()
    assert lines[0] == "no-verdict"
    assert _RUN_ID in "\n".join(lines[1:])
    assert "no commit was made" in "\n".join(lines[1:])


def test_the_settle_node_keys_on_recorded_runs_not_on_how_the_turn_watched_them(
    tmp_path: Path,
) -> None:
    """bd-ib-jqn7he polled the state file by hand and never used `wait`; it is still settled."""
    repo = _clone(tmp_path)
    plugins = _plugins(tmp_path)
    path = _run_record(repo=repo, record={"state": "running"}, pid=4194303)
    _ = path.with_suffix(".output").write_text(
        f"lefthook hook: pre-commit\nFailed targets (1):\n  - {_FAILED_TARGET}\n", encoding="utf-8"
    )

    result = _run_node(repo=repo, node=_IMPLEMENT_SETTLE, plugins=plugins)

    assert result.returncode == 0, result.stderr
    assert _git_file(repo=repo, name=_LIVE_GIT_PATH).exists()


def test_the_settle_node_removes_a_stale_brief_when_no_commit_run_is_live(tmp_path: Path) -> None:
    """A turn that ended with every commit run terminal leaves no brief behind."""
    repo = _clone(tmp_path)
    plugins = _plugins(tmp_path)
    _ = _run_record(repo=repo, record={"state": "passed", "exit_code": 0, "head": _HEAD})
    _ = _git_file(repo=repo, name=_LIVE_GIT_PATH).write_text("passed\nstale\n", encoding="utf-8")

    result = _run_node(repo=repo, node=_IMPLEMENT_SETTLE, plugins=plugins)

    assert result.returncode == 0, result.stderr
    assert not _git_file(repo=repo, name=_LIVE_GIT_PATH).exists()


def test_the_review_fix_settle_writes_its_own_brief_and_exits_zero(tmp_path: Path) -> None:
    """The review-fix wait never touches the implement brief the hook route reads."""
    repo = _clone(tmp_path)
    plugins = _plugins(tmp_path)
    _ = _run_record(repo=repo, record={"state": "running"}, pid=4194303)

    result = _run_node(repo=repo, node=_REVIEW_FIX_SETTLE, plugins=plugins)

    assert result.returncode == 0, result.stderr
    assert _git_file(repo=repo, name=_REVIEW_FIX_LIVE_GIT_PATH).exists()
    assert not _git_file(repo=repo, name=_LIVE_GIT_PATH).exists()


def test_an_absent_runner_leaves_no_brief_and_still_exits_zero(tmp_path: Path) -> None:
    """A run whose sandbox never materialized the runner has no commit run to wait on."""
    repo = _clone(tmp_path)
    plugins = tmp_path / "empty-plugins"
    plugins.mkdir()
    _ = _git_file(repo=repo, name=_LIVE_GIT_PATH).write_text("passed\nstale\n", encoding="utf-8")

    result = _run_node(repo=repo, node=_IMPLEMENT_SETTLE, plugins=plugins)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_COMMIT_SETTLE_RUNNER_ABSENT" in result.stderr
    assert not _git_file(repo=repo, name=_LIVE_GIT_PATH).exists()


def test_a_passed_commit_run_earns_a_reentry_that_does_not_spend_the_budget(
    tmp_path: Path,
) -> None:
    """The turn only stopped waiting: re-enter, leave the incomplete-turn counter untouched."""
    repo = _clone(tmp_path, hook=_REFUSING_HOOK, staged=True)
    _ = _git_file(repo=repo, name=_LIVE_GIT_PATH).write_text(
        _brief(state="passed", body=f"Commit run {_RUN_ID} has since PASSED; HEAD is {_HEAD}.\n"),
        encoding="utf-8",
    )

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _SETTLED_REENTER in result.stderr
    assert not _git_file(repo=repo, name=_REENTRIES_GIT_PATH).exists()
    assert (
        _git_file(repo=repo, name=_SETTLED_REENTRIES_GIT_PATH).read_text(encoding="utf-8") == "1\n"
    )
    brief = _git_file(repo=repo, name=_REFUSAL_GIT_PATH).read_text(encoding="utf-8")
    assert _RUN_ID in brief
    assert _STAGED_HOOK_ONLY_LINE not in brief
    assert not _git_file(repo=repo, name=_RECORD_GIT_PATH).exists()
    assert not _git_file(repo=repo, name=_STAGE_CAUSE_GIT_PATH).exists()
    assert not _git_file(repo=repo, name=_LIVE_GIT_PATH).exists()


def test_a_passed_commit_run_after_the_free_reentry_is_spent_counts_as_an_ordinary_turn(
    tmp_path: Path,
) -> None:
    """The free re-entry is one: a second passed-but-incomplete turn spends the budget."""
    repo = _clone(tmp_path)
    _ = _git_file(repo=repo, name=_SETTLED_REENTRIES_GIT_PATH).write_text("1\n", encoding="utf-8")
    _ = _git_file(repo=repo, name=_LIVE_GIT_PATH).write_text(
        _brief(state="passed", body=f"Commit run {_RUN_ID} has since PASSED.\n"), encoding="utf-8"
    )

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _INCOMPLETE_REENTER in result.stderr
    assert _SETTLED_REENTER not in result.stderr
    assert _git_file(repo=repo, name=_REENTRIES_GIT_PATH).read_text(encoding="utf-8") == "1\n"


def test_a_failed_commit_run_is_briefed_with_its_name_failed_targets_and_error_lines(
    tmp_path: Path,
) -> None:
    """The re-entered brief names the run and carries the hook's own verdict, not a re-run's."""
    repo = _clone(tmp_path, hook=_REFUSING_HOOK, staged=True)
    body = (
        f"failed targets: {_FAILED_TARGET}\n\nCommit run {_RUN_ID}, which the previous turn "
        f"started through the commit runner, ended FAILED with exit status 1.\n\n{_ERROR_LINE}\n"
    )
    _ = _git_file(repo=repo, name=_LIVE_GIT_PATH).write_text(
        _brief(state="failed", body=body), encoding="utf-8"
    )

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _FAILED_REENTER in result.stderr
    brief = _git_file(repo=repo, name=_REFUSAL_GIT_PATH).read_text(encoding="utf-8")
    assert brief.startswith(f"failed targets: {_FAILED_TARGET}\n")
    assert _RUN_ID in brief
    assert _ERROR_LINE in brief
    assert _STAGED_HOOK_ONLY_LINE not in brief
    assert _git_file(repo=repo, name=_REENTRIES_GIT_PATH).read_text(encoding="utf-8") == "1\n"
    assert not _git_file(repo=repo, name=_LIVE_GIT_PATH).exists()


def test_a_terminal_runner_refusal_reenters_even_when_nothing_remains_staged(
    tmp_path: Path,
) -> None:
    """The latest runner-recorded refusal outranks the empty staged tree and its output tail."""
    repo = _clone(tmp_path)
    _run_record(
        repo=repo,
        record={"state": "failed", "exit_code": 1, "hook_ran": True},
    ).with_suffix(".output").write_text(
        f"lefthook hook: pre-commit\nFailed targets (1):\n  - {_FAILED_TARGET}\n"
        + f"{_ERROR_LINE}\n" * 81,
        encoding="utf-8",
    )
    runs = _git_file(repo=repo, name="livespec-commit-runs")
    _ = (runs / "latest").write_text(f"{_RUN_ID}\n", encoding="utf-8")

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _FAILED_REENTER in result.stderr
    brief = _git_file(repo=repo, name=_REFUSAL_GIT_PATH).read_text(encoding="utf-8")
    assert brief.startswith(f"failed targets: {_FAILED_TARGET}\n")
    assert _RUN_ID in brief
    assert _ERROR_LINE in brief


def test_a_terminal_runner_refusal_with_budget_spent_names_its_full_output_targets(
    tmp_path: Path,
) -> None:
    """A needs-human cause retains targets that scrolled out of the runner report tail."""
    repo = _clone(tmp_path)
    _run_record(
        repo=repo,
        record={"state": "failed", "exit_code": 1, "hook_ran": True},
    ).with_suffix(".output").write_text(
        f"lefthook hook: pre-commit\nFailed targets (1):\n  - {_FAILED_TARGET}\n"
        + f"{_ERROR_LINE}\n" * 81,
        encoding="utf-8",
    )
    runs = _git_file(repo=repo, name="livespec-commit-runs")
    _ = (runs / "latest").write_text(f"{_RUN_ID}\n", encoding="utf-8")
    _ = _git_file(repo=repo, name=_REENTRIES_GIT_PATH).write_text("1\n", encoding="utf-8")

    result = _routed(repo=repo)

    assert result.returncode != 0, result.stderr
    assert _FAILED_TARGET in result.stderr
    cause = _git_file(repo=repo, name=_STAGE_CAUSE_GIT_PATH).read_text(encoding="utf-8")
    assert _FAILED_TARGET in cause


def test_a_terminal_runner_refusal_naming_no_targets_with_budget_spent_is_still_a_refusal(
    tmp_path: Path,
) -> None:
    """A hook refusal that printed no failed-targets block is not 'no refused commit attempt'."""
    repo = _clone(tmp_path)
    _run_record(
        repo=repo,
        record={"state": "failed", "exit_code": 1, "hook_ran": True},
    ).with_suffix(".output").write_text(
        f"lefthook hook: pre-commit\n{_ERROR_LINE}\n", encoding="utf-8"
    )
    runs = _git_file(repo=repo, name="livespec-commit-runs")
    _ = (runs / "latest").write_text(f"{_RUN_ID}\n", encoding="utf-8")
    _ = _git_file(repo=repo, name=_REENTRIES_GIT_PATH).write_text("1\n", encoding="utf-8")

    result = _routed(repo=repo)

    assert result.returncode != 0, result.stderr
    assert _HOOK_REFUSED_EXHAUSTED in result.stderr
    assert "no refused commit attempt" not in result.stderr
    cause = _git_file(repo=repo, name=_STAGE_CAUSE_GIT_PATH).read_text(encoding="utf-8")
    assert _HOOK_REFUSED_EXHAUSTED in cause


def test_a_commit_run_that_ended_without_a_verdict_is_briefed_as_having_made_no_commit(
    tmp_path: Path,
) -> None:
    """The brief states that the run ended without a verdict and that no commit was made."""
    repo = _clone(tmp_path)
    body = (
        f"Commit run {_RUN_ID}, which the previous turn started through the commit runner, "
        "ended without a verdict, so no commit was made.\n"
    )
    _ = _git_file(repo=repo, name=_LIVE_GIT_PATH).write_text(
        _brief(state="no-verdict", body=body), encoding="utf-8"
    )

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _NO_VERDICT_REENTER in result.stderr
    brief = _git_file(repo=repo, name=_REFUSAL_GIT_PATH).read_text(encoding="utf-8")
    assert brief.startswith("failed targets: none\n")
    assert "ended without a verdict" in brief
    assert "no commit was made" in brief
    assert _git_file(repo=repo, name=_REENTRIES_GIT_PATH).read_text(encoding="utf-8") == "1\n"


def test_a_failed_commit_run_with_the_budget_exhausted_fails_the_stage(tmp_path: Path) -> None:
    """A failed commit run is an ordinary incomplete turn once the budget is spent."""
    repo = _clone(tmp_path)
    _ = _git_file(repo=repo, name=_REENTRIES_GIT_PATH).write_text("1\n", encoding="utf-8")
    _ = _git_file(repo=repo, name=_LIVE_GIT_PATH).write_text(
        _brief(state="failed", body="failed targets: check-types\n"), encoding="utf-8"
    )

    result = _routed(repo=repo)

    assert result.returncode != 0, result.stderr
    assert _REENTRY_EXHAUSTED in result.stderr


def test_the_implement_prompt_tells_a_reentered_turn_about_a_commit_run_brief() -> None:
    """The brief file is the prompt's re-entry contract, so the commit-run case is in it."""
    prompt = _PROMPT.read_text(encoding="utf-8")

    assert "commit run" in prompt
    assert "ended while a commit run" in prompt


def test_the_settle_nodes_are_billed_into_the_subprocess_ceiling() -> None:
    """A node absent from the budget is billed at zero; each settle runs once per visit of three."""
    defaulted = node_timeouts_from_block(block={})
    assert not isinstance(defaulted, str), defaulted
    default_ceiling = derive_fabro_timeout_seconds(timeouts=defaulted)
    for node in (_IMPLEMENT_SETTLE, _REVIEW_FIX_SETTLE):
        configured = node_timeouts_from_block(
            block={"node_timeouts": {node: DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA}}
        )
        assert not isinstance(configured, str), configured
        assert derive_fabro_timeout_seconds(timeouts=configured) == (
            default_ceiling + _SETTLE_VISITS * _CONFIGURED_DELTA
        ), node


def test_fix_reaches_the_settle_before_the_janitor() -> None:
    """A succeeded fix turn waits out its commit runs, then the janitor validates the tree."""
    assert (_FIX_SETTLE, "") in _targets(source="fix")
    assert ("janitor", "") not in _targets(source="fix")
    assert _targets(source=_FIX_SETTLE) == [("janitor", "")]


def test_a_failed_fix_turn_still_goes_to_needs_human_without_the_settle() -> None:
    """The settle sits on the success path only; a failed fix preserves the tree."""
    targets = _targets(source="fix")
    assert ("needs_human", "outcome=failed") in targets
    assert [destination for destination, _ in targets].count(_FIX_SETTLE) == 1
    assert (_FIX_SETTLE, "outcome=failed") not in targets


def test_the_fix_settle_is_a_bounded_command_node_with_its_own_brief() -> None:
    """The fix wait runs the runner's `settle` with a bounded timeout and its own brief path."""
    attributes = _attributes(node=_FIX_SETTLE)
    script = attributes.get("script", "")
    assert attributes.get("shape") == "parallelogram"
    assert f"git rev-parse --git-path {_FIX_LIVE_GIT_PATH}" in script
    bound = re.search(r"settle --timeout-seconds (\d+)", script)
    assert bound is not None, script
    assert 0 < int(bound.group(1)) < int(attributes.get("timeout", "0s").rstrip("s"))


def test_the_fix_settle_writes_its_own_brief_and_exits_zero(tmp_path: Path) -> None:
    """The fix wait never touches the implement or review-fix briefs."""
    repo = _clone(tmp_path)
    plugins = _plugins(tmp_path)
    _ = _run_record(repo=repo, record={"state": "running"}, pid=4194303)

    result = _run_node(repo=repo, node=_FIX_SETTLE, plugins=plugins)

    assert result.returncode == 0, result.stderr
    assert _git_file(repo=repo, name=_FIX_LIVE_GIT_PATH).exists()
    assert not _git_file(repo=repo, name=_LIVE_GIT_PATH).exists()
    assert not _git_file(repo=repo, name=_REVIEW_FIX_LIVE_GIT_PATH).exists()


def test_the_fix_settle_is_billed_into_the_subprocess_ceiling() -> None:
    """A node absent from the budget is billed at zero; the fix settle runs once per fix visit."""
    defaulted = node_timeouts_from_block(block={})
    assert not isinstance(defaulted, str), defaulted
    default_ceiling = derive_fabro_timeout_seconds(timeouts=defaulted)
    configured = node_timeouts_from_block(
        block={"node_timeouts": {_FIX_SETTLE: DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA}}
    )
    assert not isinstance(configured, str), configured
    assert derive_fabro_timeout_seconds(timeouts=configured) > default_ceiling
