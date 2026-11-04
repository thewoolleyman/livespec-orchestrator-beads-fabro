"""Scenario 204 (v208, widened v214) — an incomplete implement turn re-enters implement.

`SPECIFICATION/scenarios.md` "Scenario 204" and the paragraph "An implement turn
that ends incomplete does not succeed" of `SPECIFICATION/contracts.md` section
"Self-contained plugin dispatch", as modified in v208 (work-item bd-ib-y7372n).
The incident is run 01M5QNH88NHN68ST28Y80CZJ48 of bd-ib-8zyan: its Green amend
was refused by `check-types` (three pyright errors), the turn wrote
`definition_of_done_complete: false` about 30 s later with about 196 minutes of
allowance left, and the run rested at needs-human on a fixable gate.

The decision lives in the `implement_hook_route` command node, which
`implement_completion`'s failure edge reaches. The node runs the repository's
own pre-commit hook over what the turn left staged, which is how v208 defines a
refused commit attempt. The sub-scenarios execute the committed script bytes in
a real clone whose hook is a stub printing what the real pre-commit aggregate
printed when it refused this item's own Green amend on 2026-10-24: bare
`::: just <target>` headers, CRLF line endings from lefthook's terminal, and the
failed names only in the closing `Failed targets (N):` / `  - <name>` block. The
exit code is the whole of the engine's decision, because a command node has
exactly two outcomes.

v214 (work-item bd-ib-r4fl2h) widened the route: EVERY incomplete turn re-enters
once while the budget lasts, not only a hook-refused one. bd-ib-idpr32 run
01M5QVBJ2573 quit with only check-per-file-coverage and check-coverage failing in
its own check-suite run and nothing refused, and bd-ib-3kqdln run 01M5QW46JGG0
stated no completion field; both rested for a human with most of the allowance
unspent. The brief is the latest failing gate: the hook verdict, otherwise a
failing run of the declared check suite, otherwise a statement that none was
recorded. The implement prompt runs the prepared recorder whenever it runs the
declared suite, so the route reads the prior failed tool output and never runs a
fresh suite over the tree the turn left.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

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

_GATE = "implement_completion"
_ROUTE = "implement_hook_route"
_IMPLEMENT = "implement"
_NEEDS_HUMAN = "needs_human"

_REFUSAL_GIT_PATH = "livespec-implement-hook-refusal"
_REENTRIES_GIT_PATH = "livespec-implement-hook-reentries"
_RECORD_GIT_PATH = "livespec-implement-completion"
_STAGE_CAUSE_GIT_PATH = "livespec-stage-cause"
_SUITE_VERDICT_GIT_PATH = "livespec-implement-check-suite-verdict"

_PARTIAL_PROGRESS = "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS"
_REENTER = "LIVESPEC_IMPLEMENT_HOOK_REFUSED_REENTER"
_EXHAUSTED = "LIVESPEC_IMPLEMENT_HOOK_REFUSED_BUDGET_EXHAUSTED"
_SUITE_REENTER = "LIVESPEC_IMPLEMENT_CHECK_SUITE_FAILED_REENTER"
_INCOMPLETE_REENTER = "LIVESPEC_IMPLEMENT_INCOMPLETE_REENTER"
_REENTRY_EXHAUSTED = "LIVESPEC_IMPLEMENT_REENTRY_BUDGET_EXHAUSTED"
_NO_RECORDED_GATE = "ended incomplete with no recorded failing gate"

# The incident's own refusal, in the check aggregate's own output shape.
_FAILED_TARGET = "check-types"
_ERROR_LINE = (
    '_dispatcher_dod_judgement_disagreement.py:63:76 - error: Type of "x" is '
    "partially unknown (reportUnknownVariableType)"
)
_REFUSING_HOOK = f"""#!/bin/sh
printf '::: just check-lint\\r\\n'
printf '::: just {_FAILED_TARGET}\\r\\n'
printf '%s\\r\\n' '{_ERROR_LINE}'
printf 'Failed targets (1):\\r\\n'
printf '  - {_FAILED_TARGET}\\r\\n'
printf 'error: Recipe check-pre-commit failed with exit code 1\\r\\n'
exit 1
"""
# bd-ib-idpr32's own check-suite run: only the two coverage targets failed.
_SUITE_TARGETS = "check-per-file-coverage check-coverage"
_SUITE_ERROR_LINE = "commands/_dispatcher_provider_limit_outcome.py: 97% < 100% line coverage"
_FAILING_SUITE_OUTPUT = f"""::: just check-per-file-coverage\r
{_SUITE_ERROR_LINE}\r
Failed targets (2):\r
  - check-per-file-coverage\r
  - check-coverage\r
"""
_ACCEPTING_HOOK = """#!/bin/sh
echo 'All 85 targets passed.'
exit 0
"""
# The cause `implement_completion` leaves behind when it fails the stage.
_PARTIAL_CAUSE = f"stage: implement\ncause: {_PARTIAL_PROGRESS}: the turn stated incomplete\n"
# Fabro's node-retry budget for `implement` is one retry; the re-entry budget
# matches it, and the settled-commit re-entry that does not spend it adds one
# more, so the turn's worst case is three visits.
_ROUTE_VISITS = 3
_IMPLEMENT_VISITS = 6
_CONFIGURED_DELTA = 137


def _targets(*, source: str) -> list[tuple[str, str]]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return [
        (edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
        if edge.source == source
    ]


def _route_attributes() -> dict[str, str]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return dict(parsed.nodes.get(_ROUTE, {}))


def _clone(
    *,
    tmp_path: Path,
    hook: str | None,
    staged: bool,
    completion: str | None = '{"definition_of_done_complete": false}\n',
) -> Path:
    """A throwaway clone with a stub hook and an optional staged change."""
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
    _ = (repo / ".git" / _STAGE_CAUSE_GIT_PATH).write_text(_PARTIAL_CAUSE, encoding="utf-8")
    if completion is not None:
        _ = (repo / ".git" / _RECORD_GIT_PATH).write_text(completion, encoding="utf-8")
    return repo


def _routed(*, repo: Path) -> subprocess.CompletedProcess[str]:
    """Run the committed route bytes after the implement turn has ended."""
    script = _route_attributes().get("script", "exit 2")
    return subprocess.run(
        ["sh", "-c", script], cwd=repo, check=False, capture_output=True, text=True, env=os.environ
    )


def _git_file(*, repo: Path, name: str) -> Path:
    return repo / ".git" / name


def _recorded_suite(*, repo: Path, output: str) -> None:
    """Materialize the failed suite output the previous turn's recorder retained."""
    _ = _git_file(repo=repo, name=_SUITE_VERDICT_GIT_PATH).write_text(output, encoding="utf-8")


def test_an_incomplete_turn_reaches_the_hook_route_and_the_route_can_reenter_implement() -> None:
    """The completion gate's failure edge leads to the route, and the route back to implement.

    The route's fallthrough is `needs_human`, unconditional, so the ending every
    non-qualifying turn reached before v208 is unchanged. `max_visits` cuts the
    new cycle for the execution-budget derivation, at the re-entry budget plus
    the visit that refuses.
    """
    assert (_ROUTE, "outcome=failed") in _targets(source=_GATE)
    assert (_NEEDS_HUMAN, "outcome=failed") not in _targets(source=_GATE)
    route = _targets(source=_ROUTE)
    assert (_IMPLEMENT, "outcome=succeeded") in route, route
    assert (_NEEDS_HUMAN, "") in route, route
    assert _route_attributes().get("max_visits") == str(_ROUTE_VISITS)


def test_a_refused_commit_with_budget_left_reenters_with_the_hooks_own_verdict(
    tmp_path: Path,
) -> None:
    """Sub-scenario: refused, budget left -> exit 0 and a brief built from the hook output.

    The brief file carries the failed target and the hook's own error line, read
    from what the hook printed rather than from any reply. The completion record
    and the partial-progress cause are cleared, so the re-entered turn does not
    inherit the previous turn's verdict.
    """
    repo = _clone(tmp_path=tmp_path, hook=_REFUSING_HOOK, staged=True)

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _REENTER in result.stderr
    brief = _git_file(repo=repo, name=_REFUSAL_GIT_PATH).read_text(encoding="utf-8")
    assert f"failed targets: {_FAILED_TARGET}\n" in brief
    assert _ERROR_LINE in brief
    assert _git_file(repo=repo, name=_REENTRIES_GIT_PATH).read_text(encoding="utf-8") == "1\n"
    assert not _git_file(repo=repo, name=_RECORD_GIT_PATH).exists()
    assert not _git_file(repo=repo, name=_STAGE_CAUSE_GIT_PATH).exists()
    assert not (repo / "suite-ran").exists(), "a refused commit outranks the check suite"


def test_a_refused_commit_with_the_budget_exhausted_fails_naming_the_failed_targets(
    tmp_path: Path,
) -> None:
    """Sub-scenario: refused, budget spent -> non-zero, cause names the hook's targets.

    Both surfaces carry it: stderr, which the Dispatcher puts on the dispatch
    outcome detail, and the stage-cause file `needs_human` renders.
    """
    repo = _clone(tmp_path=tmp_path, hook=_REFUSING_HOOK, staged=True)
    _ = _git_file(repo=repo, name=_REENTRIES_GIT_PATH).write_text("1\n", encoding="utf-8")

    result = _routed(repo=repo)

    assert result.returncode != 0, result.stderr
    assert _EXHAUSTED in result.stderr
    assert _FAILED_TARGET in result.stderr
    cause = _git_file(repo=repo, name=_STAGE_CAUSE_GIT_PATH).read_text(encoding="utf-8")
    assert cause.startswith(f"stage: {_IMPLEMENT}\n")
    assert _EXHAUSTED in cause
    assert _FAILED_TARGET in cause


def test_an_incomplete_turn_whose_check_suite_fails_reenters_with_that_runs_targets(
    tmp_path: Path,
) -> None:
    """Sub-scenario: nothing refused, the check suite fails -> re-enter with its verdict.

    bd-ib-idpr32's ending: nothing staged, the suite failing only on coverage. The
    hook here would refuse, which is the control: nothing is staged, so the route
    must not read it as a refused commit attempt.
    """
    repo = _clone(tmp_path=tmp_path, hook=_REFUSING_HOOK, staged=False)
    _recorded_suite(repo=repo, output=_FAILING_SUITE_OUTPUT)

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _SUITE_REENTER in result.stderr
    assert _REENTER not in result.stderr
    brief = _git_file(repo=repo, name=_REFUSAL_GIT_PATH).read_text(encoding="utf-8")
    assert f"failed targets: {_SUITE_TARGETS}\n" in brief
    assert _SUITE_ERROR_LINE in brief
    assert _git_file(repo=repo, name=_REENTRIES_GIT_PATH).read_text(encoding="utf-8") == "1\n"
    assert not _git_file(repo=repo, name=_STAGE_CAUSE_GIT_PATH).exists()


def test_an_incomplete_turn_with_no_failing_gate_reenters_saying_so(tmp_path: Path) -> None:
    """Sub-scenario: nothing staged and no retained failed suite -> the fixed no-gate brief."""
    repo = _clone(tmp_path=tmp_path, hook=_REFUSING_HOOK, staged=False)

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _INCOMPLETE_REENTER in result.stderr
    brief = _git_file(repo=repo, name=_REFUSAL_GIT_PATH).read_text(encoding="utf-8")
    assert _NO_RECORDED_GATE in brief
    assert not _git_file(repo=repo, name=_RECORD_GIT_PATH).exists()


def test_staged_changes_the_hook_accepts_reenter_implement(tmp_path: Path) -> None:
    """Sub-scenario: staged but accepted -> no refused commit, so the turn re-enters."""
    repo = _clone(tmp_path=tmp_path, hook=_ACCEPTING_HOOK, staged=True)

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _INCOMPLETE_REENTER in result.stderr
    assert _REENTER not in result.stderr


def test_a_repository_with_no_commit_hook_reenters_implement(tmp_path: Path) -> None:
    """Sub-scenario: staged changes but no hook at all -> nothing refused them.

    `git hook run --ignore-missing` exits zero when the repository installs no
    pre-commit hook, so an adopter without hooks takes the check-suite arm.
    """
    repo = _clone(tmp_path=tmp_path, hook=None, staged=True)
    _recorded_suite(repo=repo, output=_FAILING_SUITE_OUTPUT)

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _SUITE_REENTER in result.stderr


def test_a_turn_with_no_completion_field_reenters_implement(tmp_path: Path) -> None:
    """Sub-scenario: bd-ib-3kqdln's ending, no completion field and nothing staged."""
    repo = _clone(tmp_path=tmp_path, hook=None, staged=False, completion=None)

    result = _routed(repo=repo)

    assert result.returncode == 0, result.stderr
    assert _INCOMPLETE_REENTER in result.stderr


def test_an_unrefused_incomplete_turn_with_the_budget_exhausted_fails_as_partial_progress(
    tmp_path: Path,
) -> None:
    """Sub-scenario: no refused commit, budget spent -> non-zero, the partial-progress cause stands.

    Stderr repeats the cause, because the route is the stage whose stderr the
    Dispatcher puts on the dispatch outcome detail. The suite is not run, since
    no brief can follow.
    """
    repo = _clone(tmp_path=tmp_path, hook=_ACCEPTING_HOOK, staged=True)
    _ = _git_file(repo=repo, name=_REENTRIES_GIT_PATH).write_text("1\n", encoding="utf-8")

    result = _routed(repo=repo)

    assert result.returncode != 0, result.stderr
    assert _REENTRY_EXHAUSTED in result.stderr
    assert _PARTIAL_PROGRESS in result.stderr
    assert _git_file(repo=repo, name=_STAGE_CAUSE_GIT_PATH).read_text(encoding="utf-8") == (
        _PARTIAL_CAUSE
    )
    assert not _git_file(repo=repo, name=_REFUSAL_GIT_PATH).exists()


def test_the_implement_prompt_directs_a_reentered_turn_to_the_hooks_verdict() -> None:
    """The brief is the prompt plus the per-clone file the route writes."""
    prompt = _PROMPT.read_text(encoding="utf-8")

    assert f"git rev-parse --git-path {_REFUSAL_GIT_PATH}" in prompt
    assert "check suite" in prompt
    assert _NO_RECORDED_GATE in prompt
    assert "livespec-implement-check-suite" in prompt


def test_the_route_never_reruns_the_declared_suite() -> None:
    """The brief consumes the prior recorder output, never a new check-suite result."""
    script = _route_attributes().get("script", "")

    assert "{{ inputs.sandbox_check_suite }}" not in script
    assert "livespec-run-plugin-gate.py" not in script


def test_the_route_and_the_reentered_turn_are_billed_into_the_subprocess_ceiling() -> None:
    """The route runs the hook, so it is billed; the two re-entries triple implement's visits."""
    defaulted = node_timeouts_from_block(block={})
    assert not isinstance(defaulted, str), defaulted
    base = derive_fabro_timeout_seconds(timeouts=defaulted)
    for node, visits in ((_ROUTE, _ROUTE_VISITS), (_IMPLEMENT, _IMPLEMENT_VISITS)):
        configured = node_timeouts_from_block(
            block={"node_timeouts": {node: DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA}}
        )
        assert not isinstance(configured, str), configured
        assert derive_fabro_timeout_seconds(timeouts=configured) == (
            base + visits * _CONFIGURED_DELTA
        ), node
