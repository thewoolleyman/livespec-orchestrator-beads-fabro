"""The forge read a resume's first three refusals are decided from.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" spends three of its eight refusals on one forge answer — the
branch carries no open pull request, the head moved, the pull request is closed
or merged — and Scenario 143 asserts each separately, with a DIFFERENT remedy per
state. So one listing has to answer four things: which pull request, at which
head, in which state, and whether the forge answered at all.

WHY `--state all` IS ASSERTED ON THE ARGV RATHER THAN LEFT TO THE DEFAULT. This is
the arm that cannot be caught downstream. `gh pr list` defaults to OPEN, so a
closed or merged pull request would come back as an EMPTY listing — and an empty
listing is a legitimate, error-free answer meaning "this branch carries no pull
request", whose remedy is a plain dispatch. For a MERGED pull request that remedy
is wrong and expensive: Scenario 143 requires `reconcile-merged`, "which requires a
real merge and stays the only valve for one", so the plain-dispatch advice sends an
operator to cut an empty branch against work that has already landed.

WHY AN UNUSABLE PAYLOAD IS ASSERTED AS UNOBSERVED. The clause says the resume
"MUST NOT proceed on an unobservable answer", and a zero exit carrying something
that is not a JSON array is a read that did not happen. Collapsing it into "no
pull request" is the fail-open direction, and it is indistinguishable at the
surface from the genuine empty answer.

WHY THE NEWEST NUMBER IS ASSERTED. A branch can carry more than one pull request
over its life, and the one a resume finishes is the one the dead run last
published to. The listing's ORDER is not promised by `gh`, so the test fixes the
rule — maximum number — and deliberately feeds the rows oldest-last so a
first-entry implementation fails.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_forge"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_resume_forge.py"
)
_BRANCH = "feat/bd-ib-fngpwg"
_HEAD = "f" * 40


@dataclass(kw_only=True)
class _StubRunner:
    """A CommandRunner answering one listing, recording the argv it was given."""

    result: CommandResult
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        return self.result


def _listing(*, rows: list[dict[str, object]]) -> str:
    return json.dumps(rows)


def test_the_listing_asks_for_every_state_and_for_the_head_oid() -> None:
    """The one argv that cannot be repaired downstream: a merged pull request must appear."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    argv = module.branch_pull_request_argv(branch=_BRANCH)
    assert argv[:4] == ["gh", "pr", "list", "--head"]
    assert argv[4] == _BRANCH
    assert "--state" in argv
    assert argv[argv.index("--state") + 1] == "all"
    assert "headRefOid" in argv[argv.index("--json") + 1]


def test_one_row_is_read_as_its_number_state_and_head() -> None:
    """The three fields three different refusals are decided from."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    read = module.branch_pull_request_from_stdout(
        stdout=_listing(rows=[{"number": 2639, "state": "OPEN", "headRefOid": _HEAD}])
    )
    assert read.observed is True
    assert read.pull_request is not None
    assert read.pull_request.number == 2639
    assert read.pull_request.state == "OPEN"
    assert read.pull_request.head == _HEAD


def test_a_merged_pull_request_is_reported_rather_than_hidden() -> None:
    """Its remedy is reconcile-merged; an empty listing would advise a plain dispatch."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    read = module.branch_pull_request_from_stdout(
        stdout=_listing(rows=[{"number": 7, "state": "MERGED", "headRefOid": _HEAD}])
    )
    assert read.pull_request is not None
    assert read.pull_request.state == "MERGED"


def test_the_newest_pull_request_of_the_branch_wins() -> None:
    """Fed newest-FIRST, so a max-by-number rule passes and a last-entry rule fails."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    read = module.branch_pull_request_from_stdout(
        stdout=_listing(
            rows=[
                {"number": 2639, "state": "OPEN", "headRefOid": _HEAD},
                {"number": 11, "state": "CLOSED", "headRefOid": "a" * 40},
            ]
        )
    )
    assert read.pull_request is not None
    assert read.pull_request.number == 2639


def test_an_empty_listing_is_an_answer_and_not_an_outage() -> None:
    """The branch carries no pull request; the remedy is a plain dispatch."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    read = module.branch_pull_request_from_stdout(stdout=_listing(rows=[]))
    assert read.observed is True
    assert read.pull_request is None


def test_an_unusable_payload_is_unobserved_and_not_an_empty_answer() -> None:
    """A resume does not proceed on an unobservable answer, so the two must differ."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    assert module.branch_pull_request_from_stdout(stdout="not json").observed is False
    assert module.branch_pull_request_from_stdout(stdout='{"number": 1}').observed is False


def test_a_row_missing_its_number_or_state_is_dropped() -> None:
    """Nothing can be refused about a row naming neither; a default state would proceed."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    read = module.branch_pull_request_from_stdout(
        stdout=_listing(
            rows=[
                {"state": "OPEN", "headRefOid": _HEAD},
                {"number": 5, "headRefOid": _HEAD},
                {"number": 6, "state": "", "headRefOid": _HEAD},
                "not-a-row",
            ]
        )
    )
    assert read.observed is True
    assert read.pull_request is None


def test_an_absent_head_oid_is_none_rather_than_an_empty_sha() -> None:
    """An empty sha would be compared against the record's head and reported as moved."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    read = module.branch_pull_request_from_stdout(
        stdout=_listing(rows=[{"number": 8, "state": "OPEN", "headRefOid": ""}])
    )
    assert read.pull_request is not None
    assert read.pull_request.head is None


def test_a_nonzero_exit_is_unobserved_whatever_it_printed() -> None:
    """Exit code and payload shape are two ways for one read not to happen."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    runner = _StubRunner(
        result=CommandResult(
            exit_code=1,
            stdout=_listing(rows=[{"number": 9, "state": "OPEN", "headRefOid": _HEAD}]),
            stderr="gh: could not resolve host",
        )
    )
    read = module.branch_pull_request(repo=Path("/repo"), branch=_BRANCH, runner=runner)
    assert read.observed is False
    assert read.pull_request is None


def test_the_read_runs_the_listing_it_declares() -> None:
    """One argv builder, one caller: a second spelling is how the two would drift."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    runner = _StubRunner(
        result=CommandResult(
            exit_code=0,
            stdout=_listing(rows=[{"number": 4, "state": "OPEN", "headRefOid": _HEAD}]),
            stderr="",
        )
    )
    read = module.branch_pull_request(repo=Path("/repo"), branch=_BRANCH, runner=runner)
    assert runner.argvs == [module.branch_pull_request_argv(branch=_BRANCH)]
    assert read.pull_request is not None
    assert read.pull_request.number == 4
