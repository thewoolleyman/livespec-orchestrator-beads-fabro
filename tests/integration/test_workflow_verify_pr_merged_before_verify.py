"""The publish breaker must not report a MERGED pull request as never created.

Binds work-item `bd-ib-54ijva` (finding F7 of plan `definition-and-proof-of-done`,
epic `bd-ib-7sjdzv`). The breaker in
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro` predates the
draft-first flow of S5: it asks origin for a `feat/*` head containing this run's
HEAD and reports `LIVESPEC_PR_NOT_CREATED` when there is none. Since
`publish_draft` opens the pull request EARLY, its CI is already green when the
`pr` stage marks it ready and arms auto-merge, so the merge can land -- and the
forge can delete the head branch -- before `verify_pr` ever looks.

MEASURED 2026-10-04 on `livespec-dev-tooling-74c65i`, hp run
`01M4355ZXMCKY8R1GP5QSW0WB4`: every stage succeeded, PR #2308 merged at 10:54:06Z
as `5f1d2a41`, the forge deleted the branch, and the breaker then reported the
publish as never created. The run went to `needs_human` and the Dispatcher rested
a MERGED item at `blocked / needs-human`.

WHY THIS MODULE EXECUTES THE SCRIPT RATHER THAN READING IT. The sibling module
`test_workflow_verify_pr_publish_guard` asserts the breaker's SHAPE -- the node
vocabulary, its sentinels, its edges, and that the graph still renders. A shape
assertion cannot tell a correct discrimination from an incorrect one: the merged
arm and the absent arm differ only in what the script DOES with the forge's
answer. So the committed `script=` body is extracted, unescaped, and run by `sh`
against a throwaway origin/clone pair with a `gh` double on PATH, and the exit
code and stderr of each condition are the assertions.

THE CONTROLS ARE WHAT MAKE THE EXECUTION WORTH RUNNING. A breaker that answered
"published" to everything would satisfy the merged case alone, so three further
conditions are driven through the same harness: an absent pull request must still
refuse and must NAME the branch it looked for; a merged pull request from a
PREVIOUS run of the same item -- whose head commit this clone does not even carry
-- must NOT count as this run's publish; and a forge that could not be asked must
fail closed under the check-failed sentinel rather than be reported as a publish
that never happened.

The Dispatcher leg is asserted at its own seams rather than re-derived: an
already-MERGED view arms nothing, polls once, and reaches the post-merge janitor
green, which is what "recorded as merged rather than rested at blocked" means on
the host side.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import (
    await_merge,
    confirm_pr,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DOT = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_NOT_CREATED = "LIVESPEC_PR_NOT_CREATED"
_CHECK_FAILED = "LIVESPEC_PR_NOT_CREATED_CHECK_FAILED"
_MERGED_BEFORE_VERIFY = "LIVESPEC_PR_MERGED_BEFORE_VERIFY"

_PUBLISH_BRANCH = "feat/bd-ib-54ijva"
# A well-formed sha that NO repository in this fixture carries, standing in for
# the head of a pull request a PREVIOUS run of this item merged: after a
# rebase-merge the forge keeps the `headRefOid` but the object is unreachable
# from the default branch, so a fresh sandbox clone never fetches it.
_FOREIGN_OID = "0" * 39 + "1"

_NODE_BLOCK_RE = re.compile(r"\bverify_pr\s*\[(?P<body>[^\]]*)\]", re.DOTALL)
_SCRIPT_ATTR_RE = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')

# The `gh` double records one argument per line and closes each invocation with
# this marker, so the harness can report CALLS rather than a flat word list --
# "the forge was never asked" is an assertion this module makes twice.
_CALL_TERMINATOR = "--end-of-call--"


@dataclass(frozen=True, kw_only=True)
class _Breaker:
    """One execution of the committed breaker script."""

    exit_code: int
    stderr: str
    gh_calls: tuple[tuple[str, ...], ...]


def _verify_pr_script() -> str:
    """The committed `verify_pr` script body, unescaped into shell source.

    A `{{ inputs.* }}` token would make this an unrendered template rather than a
    runnable script, so its absence is asserted here instead of being assumed:
    the breaker deliberately takes its branch name from the run ENVIRONMENT,
    which is the only reason it can be executed outside a dispatch at all.
    """
    block = _NODE_BLOCK_RE.search(_WORKFLOW_DOT.read_text(encoding="utf-8"))
    assert block is not None
    attr = _SCRIPT_ATTR_RE.search(block.group("body"))
    assert attr is not None
    value = attr.group("value")
    assert "{{" not in value
    return value.replace('\\"', '"')


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
    )


def _origin_and_clone(*, tmp_path: Path) -> tuple[Path, Path, str]:
    """A bare origin plus a clone whose HEAD sits ATOP the sha the pr stage pushed.

    The checkpoint commit on top is not decoration: fabro commits a stage
    checkpoint once a node completes, so by the time the breaker runs HEAD has
    already moved past what was published. That is why every leg of the breaker
    asks an ANCESTRY question and never a sha-equality one.
    """
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "master", str(origin))
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "master")
    _git(work, "config", "user.email", "verify-pr-test@example.invalid")
    _git(work, "config", "user.name", "verify-pr-test")
    (work / "base.txt").write_text("base\n", encoding="utf-8")
    _git(work, "add", "base.txt")
    _git(work, "commit", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "origin", "master")
    (work / "impl.txt").write_text("implementation\n", encoding="utf-8")
    _git(work, "add", "impl.txt")
    _git(work, "commit", "-m", "the work the pr stage published")
    published = _git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "checkpoint.txt").write_text("stage checkpoint\n", encoding="utf-8")
    _git(work, "add", "checkpoint.txt")
    _git(work, "commit", "-m", "fabro stage checkpoint")
    return origin, work, published


def _gh_double(*, tmp_path: Path) -> Path:
    """A `gh` on PATH that answers from the environment and records its argv."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do printf \'%s\\n\' "$arg" >> "$GH_DOUBLE_LOG"; done\n'
        f"printf '%s\\n' '{_CALL_TERMINATOR}' >> \"$GH_DOUBLE_LOG\"\n"
        'if test -n "${GH_DOUBLE_STDOUT:-}"; then printf \'%s\\n\' "$GH_DOUBLE_STDOUT"; fi\n'
        'exit "${GH_DOUBLE_EXIT:-0}"\n',
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _calls(*, log: Path) -> tuple[tuple[str, ...], ...]:
    if not log.is_file():
        return ()
    calls: list[tuple[str, ...]] = []
    current: list[str] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if line == _CALL_TERMINATOR:
            calls.append(tuple(current))
            current = []
            continue
        current.append(line)
    return tuple(calls)


def _run_breaker(*, tmp_path: Path, work: Path, overrides: Mapping[str, str]) -> _Breaker:
    """Run the committed script in `work` with a doubled forge.

    `COVERAGE_PROCESS_START` and the `COV_CORE_*` family are scrubbed so the
    child cannot self-instrument and race the parallel check dispatcher's
    coverage data, which is the condition the shared no-subprocess guard names.
    """
    log = tmp_path / "gh-calls.log"
    bin_dir = _gh_double(tmp_path=tmp_path)
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["GH_DOUBLE_LOG"] = str(log)
    env["LIVESPEC_PUBLISH_BRANCH"] = _PUBLISH_BRANCH
    env.update(overrides)
    result = subprocess.run(
        ["sh", "-c", _verify_pr_script()],
        cwd=str(work),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return _Breaker(exit_code=result.returncode, stderr=result.stderr, gh_calls=_calls(log=log))


def test_a_pull_request_that_merged_before_verification_reports_published(
    tmp_path: Path,
) -> None:
    """The measured incident: merged pull request, branch deleted, breaker green.

    The forge is asked for merged pull requests on the publish branch and answers
    with the head commit this run pushed. That commit is an ancestor of HEAD, so
    the publish is PROVEN rather than assumed from the pull request's existence,
    and the breaker exits 0 -- which is the `verify_pr -> exit` edge, not the
    unconditional fallback into `needs_human`.
    """
    _, work, published = _origin_and_clone(tmp_path=tmp_path)

    breaker = _run_breaker(tmp_path=tmp_path, work=work, overrides={"GH_DOUBLE_STDOUT": published})

    assert breaker.exit_code == 0
    assert _MERGED_BEFORE_VERIFY in breaker.stderr
    assert _PUBLISH_BRANCH in breaker.stderr
    assert f"{_NOT_CREATED}:" not in breaker.stderr


def test_the_forge_is_asked_for_a_merged_pull_request_on_the_publish_branch(
    tmp_path: Path,
) -> None:
    """The QUERY, not only its answer: a mis-aimed lookup returns a clean empty set.

    `gh pr list` defaults to OPEN pull requests, so a breaker that forgot
    `--state merged` would ask a question the merged case can never answer yes
    to, and would report the identical refusal a genuinely absent pull request
    produces.
    """
    _, work, published = _origin_and_clone(tmp_path=tmp_path)

    breaker = _run_breaker(tmp_path=tmp_path, work=work, overrides={"GH_DOUBLE_STDOUT": published})

    assert len(breaker.gh_calls) == 1
    argv = breaker.gh_calls[0]
    assert argv[:2] == ("pr", "list")
    assert "--head" in argv
    assert argv[argv.index("--head") + 1] == _PUBLISH_BRANCH
    assert "--state" in argv
    assert argv[argv.index("--state") + 1] == "merged"


def test_an_absent_pull_request_still_refuses_and_names_the_missing_branch(
    tmp_path: Path,
) -> None:
    """The arm the breaker exists for survives the new leg, and says which branch.

    Naming the branch is what makes the refusal actionable: the original message
    could only report that SOME `feat/*` head was missing, which reads as a
    defect in the work item rather than in the pr stage.
    """
    _, work, _ = _origin_and_clone(tmp_path=tmp_path)

    breaker = _run_breaker(tmp_path=tmp_path, work=work, overrides={"GH_DOUBLE_STDOUT": ""})

    assert breaker.exit_code == 1
    assert f"{_NOT_CREATED}:" in breaker.stderr
    assert _PUBLISH_BRANCH in breaker.stderr
    assert _MERGED_BEFORE_VERIFY not in breaker.stderr


def test_a_previous_runs_merged_pull_request_is_not_this_runs_publish(
    tmp_path: Path,
) -> None:
    """A merged pull request whose head this run does not carry proves nothing.

    This is the control that keeps the new leg from being a name lookup. A
    re-dispatch of an item whose earlier run already merged would find that
    merged pull request on the same branch name; its `headRefOid` survives the
    merge, but after a rebase-merge the object is unreachable from the default
    branch and a fresh sandbox clone never fetches it -- so the ancestry test
    cannot resolve it and the breaker must refuse.
    """
    _, work, _ = _origin_and_clone(tmp_path=tmp_path)

    breaker = _run_breaker(
        tmp_path=tmp_path, work=work, overrides={"GH_DOUBLE_STDOUT": _FOREIGN_OID}
    )

    assert breaker.exit_code == 1
    assert f"{_NOT_CREATED}:" in breaker.stderr
    assert _MERGED_BEFORE_VERIFY not in breaker.stderr


def test_a_forge_that_could_not_be_asked_is_not_an_unpublished_run(tmp_path: Path) -> None:
    """ "We could not look" keeps its own sentinel, as the branch leg already does.

    Collapsing this into the not-created arm would tell an operator the pr stage
    failed whenever the forge was unreachable, which is the distinction this
    breaker drew from its first landing.
    """
    _, work, _ = _origin_and_clone(tmp_path=tmp_path)

    breaker = _run_breaker(
        tmp_path=tmp_path,
        work=work,
        overrides={"GH_DOUBLE_STDOUT": "", "GH_DOUBLE_EXIT": "7"},
    )

    assert breaker.exit_code == 7
    assert f"{_CHECK_FAILED}:" in breaker.stderr
    assert f"{_NOT_CREATED}:" not in breaker.stderr


def test_an_unnamed_publish_branch_fails_closed_without_asking_the_forge(
    tmp_path: Path,
) -> None:
    """With no branch in the environment the two conditions cannot be told apart.

    So the breaker refuses under the check-failed sentinel rather than guessing a
    ref or reporting a publish that nobody established did not happen.
    """
    _, work, _ = _origin_and_clone(tmp_path=tmp_path)

    breaker = _run_breaker(tmp_path=tmp_path, work=work, overrides={"LIVESPEC_PUBLISH_BRANCH": ""})

    assert breaker.exit_code == 1
    assert f"{_CHECK_FAILED}:" in breaker.stderr
    assert breaker.gh_calls == ()


def test_a_live_publish_branch_still_passes_without_reaching_the_forge(
    tmp_path: Path,
) -> None:
    """The ordinary green run is unchanged, and costs no forge call.

    The merged leg is a FALLBACK behind the branch-ancestry leg, so the healthy
    dispatch -- whose pull request has not merged yet when the breaker runs --
    takes exactly the path it always took.
    """
    origin, work, published = _origin_and_clone(tmp_path=tmp_path)
    _git(work, "push", str(origin), f"{published}:refs/heads/{_PUBLISH_BRANCH}")

    breaker = _run_breaker(tmp_path=tmp_path, work=work, overrides={"GH_DOUBLE_STDOUT": ""})

    assert breaker.exit_code == 0
    assert breaker.gh_calls == ()
    assert breaker.stderr == ""


# --- The Dispatcher leg: a pre-verification merge is recorded as merged -------

_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'


@dataclass(kw_only=True)
class _Runner:
    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        assert env is None or isinstance(env, dict)
        self.calls.append((argv, cwd))
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-54ijva",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )


def _merged_pr_json() -> str:
    return json.dumps(
        {
            "number": 2308,
            "state": "MERGED",
            "autoMergeRequest": None,
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": "5f1d2a41"},
            "statusCheckRollup": [],
        }
    )


def test_a_dispatch_whose_pull_request_already_merged_arms_nothing_and_goes_green(
    tmp_path: Path,
) -> None:
    """The host side of the incident, once the breaker lets the run reach exit.

    `confirm_pr` sees MERGED on its first read and makes no forge WRITE -- arming
    auto-merge on a merged pull request is the fallback that would otherwise fire
    -- the poll returns that view without sleeping, and the post-merge janitor
    runs and reports `green at done`. That is what "recorded as merged and
    proceeds to the post-merge janitor" means, as against the measured
    `blocked / needs-human` rest.
    """
    plan = _plan(repo=tmp_path)
    confirm_runner = _Runner(queue=[_ok(stdout=_merged_pr_json())])
    journal = _Journal()

    view = confirm_pr(plan=plan, runner=confirm_runner, journal=journal)

    assert view is not None
    assert view.state == "MERGED"
    assert [argv[:3] for argv, _ in confirm_runner.calls] == [["gh", "pr", "view"]]
    assert [record["stage"] for record in journal.records] == ["pr-view"]

    naps: list[float] = []
    merged = await_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=_Runner(queue=[_ok(stdout=_merged_pr_json())]),
        journal=_Journal(),
        sleep=naps.append,
        poll=PollPolicy(attempts=2, interval_seconds=0.5),
    )

    assert not isinstance(merged, DispatchOutcome)
    assert merged is not None
    assert naps == []

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=_Runner(queue=[_ok(), _ok(), *[_ok() for _ in range(8)]]),
        journal=_Journal(),
        merged=merged,
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
