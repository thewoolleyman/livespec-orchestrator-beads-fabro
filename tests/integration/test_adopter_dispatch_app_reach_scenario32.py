"""Integration-tier acceptance for the App-reach half of Scenario 32.

Binds the first two gherkin `Then` lines of `SPECIFICATION/scenarios.md`
"Scenario 32 — Adopter-target dispatch compatibility" and the
`SPECIFICATION/contracts.md` per-tenant-engine-identity clause they realize:
"A dispatch preflight SHOULD verify the serving App can reach the target repo
BEFORE launching, refusing with an actionable diagnostic rather than failing
inside the engine run", and "The preflight and the adopter docs MUST therefore
surface that grant as one DELIBERATELY WITHHELD from the dispatch credential,
and MUST name the attended-host-session route for work requiring it — never as
an App-installation requirement to be granted."

DRIVING THE WALL RATHER THAN THE GATE is what makes "BEFORE launching"
observable, for the reason `test_fabro_currency_admission_scenario130` records:
`pre_dispatch_wall_exit` is the one sequence both dispatch paths run after
selection and before admission, so a refusal returning from it reached no
`admit_and_select` — nothing moved `ready -> active`, no assignee was set, and no
Fabro run was created. A gate-level assertion that a function returns a string
cannot show any of that.

THE APP-REACH ROW SITS SECOND IN THE WALL, immediately after the
publication-adapter row and ahead of the Fabro currency gate, which is why these
cases need no fixture for currency, the criteria wall, the proof-assets
prerelease, the proof-credential declaration or the host Codex credential: a
refusal here returns before any of them runs. The ordering is relevance-first
rather than convenient — a serving App that cannot reach the target means NO
engine on that server can run this dispatch, so grading that engine's own
currency answers a question about a server which cannot serve this target at
all.

TWO CONTROLS CARRY THE MODULE, and neither is optional. The reachable case is
the positive control that the gauge can return the OTHER answer: a refusal alone
is equally consistent with a preflight that refuses every dispatch, which would
stop the whole fleet while passing the refusal assertions byte for byte. And the
no-serving-App case is the control for the UNEVALUATED arm — a Dispatcher
holding no App identity at all has no serving App whose reach could be verified,
and that is a structural absence rather than a blinded gauge.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_app_reach_preflight"
# The module is loaded through `importlib` INSIDE each test body rather than
# imported at module top, and its path is asserted first, so the Red of this
# slice fails on a genuine assertion instead of dying at collection with a
# `ModuleNotFoundError` that proves only unimportability.
_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_app_reach_preflight.py"
)

# The ADOPTER target: a repository outside this fleet, which is exactly the
# population the fleet's shared server App is not installed for.
_TARGET = "an-adopter-org/an-adopter-repo"
# The serving App's own id, as the host credential environment names it. A
# number rather than a word, so "the diagnostic names the serving App" cannot be
# satisfied by prose that happens to contain the word "app".
_SERVING_APP_ID = "4277313"
_FACTORY = "hp"
_FACTORY_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_FABRO_BIN = "/home/ubuntu/.fabro/bin/fabro"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    """Stands in for the ONE seam that leaves the process: `gh`.

    Keyed on the whole argv, so a case cannot pass by answering a command the
    preflight never issued, and recording every call, so "no launch happened" is
    read off what was INVOKED rather than off an exit code.
    """

    results: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="unstubbed"))


def _runner(*, module: object, reach: CommandResult) -> _Runner:
    """The `gh` seam answering the identity read and then the reach probe.

    Both argvs come from the PRODUCTION builders rather than being retyped, so a
    case cannot keep passing against a preflight that started asking the forge
    something else.
    """
    identity_argv = tuple(module.TARGET_IDENTITY_ARGV)  # pyright: ignore[reportAttributeAccessIssue]
    probe_argv = tuple(module.target_reach_argv(target=_TARGET))  # pyright: ignore[reportAttributeAccessIssue]
    return _Runner(
        results={
            identity_argv: CommandResult(exit_code=0, stdout=f"{_TARGET}\n", stderr=""),
            probe_argv: reach,
        }
    )


def _not_found() -> CommandResult:
    """What `gh api repos/<owner>/<repo>` prints when the App cannot see it.

    An installation token scoped to another tenant's repositories is not DENIED
    the target — the forge answers as though it does not exist, which is the
    whole reason this reading is a definite negative about reach rather than
    about permissions.
    """
    return CommandResult(exit_code=1, stdout="", stderr="gh: Not Found (HTTP 404)\n")


def _install(*, module: object, monkeypatch: pytest.MonkeyPatch, runner: _Runner) -> None:
    """Stand in the two things that leave the process: the shell and the mint."""
    monkeypatch.setattr(module, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(
        module, "serving_app_token_supplier", lambda: (lambda: "ghs_an_installation_token")
    )
    monkeypatch.setenv("GITHUB_APP_ID", _SERVING_APP_ID)


def _repo(*, tmp_path: Path) -> Path:
    """An adopter target checkout carrying its own committed declaration."""
    repo = tmp_path / "adopter"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text("[workflow]\n", encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_NAME: {
                    "connection": {
                        "tenant": "an-adopter-repo",
                        "prefix": "ad",
                        "server_user": "an-adopter-repo",
                        "database": "an-adopter-repo",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "default_factory": _FACTORY,
                        "factories": {
                            _FACTORY: {"server": _FACTORY_SERVER, "bin": _FABRO_BIN},
                        },
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return replace(
        WorkItem(
            id="ad-1",
            type="task",
            status="ready",
            title="An adopter slice",
            description=(
                "## Definition of Done\n"
                "\n"
                "- The dispatched slice lands its change.\n"
                "\n"
                "References: ## Scenario 32 — Adopter-target dispatch compatibility\n"
            ),
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-23T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria="The dispatched slice is verified green by the check suite.",
        )
    )


def _wall_exit(*, repo: Path, journal_path: Path) -> int | None:
    """Seed the selection through the store seam, then run the REAL wall over it."""
    item = _item()
    append_work_item(path=store_config(repo=repo), item=item)
    args = argparse.Namespace(
        workflow=str(repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"),
        workflow_name=None,
        journal=str(journal_path),
        repo=str(repo),
        factory=None,
        fabro_bin=_FABRO_BIN,
    )
    return pre_dispatch_wall_exit(
        args=args,
        repo=repo,
        items=[item],
        journal=JournalFile(path=journal_path),
    )


def _records(*, module: object, journal_path: Path) -> list[dict[str, object]]:
    """This preflight's own journal records, in order.

    FILTERED BY STAGE, because an admitted dispatch goes on to run the rest of
    the wall and those gates journal too; deliberately NOT guarded onto an empty
    list for a missing file, since a missing journal reads identically to one
    carrying no app-reach record and that is half of what each case asserts.
    """
    stage = module.APP_REACH_STAGE  # pyright: ignore[reportAttributeAccessIssue]
    text = journal_path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines() if line]
    return [record for record in records if record["stage"] == stage]


def test_scenario32_an_unreachable_adopter_target_refuses_before_any_run_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole App-reach refusal, asserted on the ONE diagnostic it renders.

    Both gherkin `Then` lines of the scenario's first block are properties of the
    SAME message, which is why they are one case: the clause requires the
    preflight to refuse with an actionable diagnostic AND requires that
    diagnostic to carry the withheld-grant posture and the host-session route, so
    two cases asserting half the message each would both pass against a build
    that rendered two messages and showed an operator whichever one it liked.

    `before launching` is read off THREE instruments rather than an exit code: a
    refusal returning from the wall reached no admission, the stood-in shell was
    asked for the identity read and the reach probe and NOTHING else, and the
    journal carries this preflight's refusal record alone.
    """
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path)
    runner = _runner(module=module, reach=_not_found())
    _install(module=module, monkeypatch=monkeypatch, runner=runner)
    journal_path = tmp_path / "journal.jsonl"

    exit_code = _wall_exit(repo=repo, journal_path=journal_path)

    assert exit_code == EXIT_PRECONDITION_ERROR
    refusal = capsys.readouterr().err
    # The serving App and the target it cannot reach, so an operator can tell
    # WHICH pair failed rather than that some pair did.
    assert _SERVING_APP_ID in refusal
    assert _TARGET in refusal
    # The per-tenant server requirement, named as the target tenant's OWN App
    # identity rather than as a shared server to be reconfigured.
    assert "per-tenant" in refusal
    assert "target tenant's own" in refusal.casefold()
    # The withheld grant, named as deliberately withheld from the dispatch
    # credential rather than as an installation requirement to be granted.
    assert "workflows" in refusal
    assert "withheld" in refusal.casefold()
    assert "dispatch credential" in refusal
    # The route the withheld capability's work takes instead.
    assert "attended host session" in refusal
    # Nothing beyond the two reads this preflight owns was ever invoked.
    assert runner.calls == [
        tuple(module.TARGET_IDENTITY_ARGV),  # pyright: ignore[reportAttributeAccessIssue]
        tuple(module.target_reach_argv(target=_TARGET)),  # pyright: ignore[reportAttributeAccessIssue]
    ]
    records = _records(module=module, journal_path=journal_path)
    assert [record["reaches"] for record in records] == [False]
    assert records[0]["target"] == _TARGET
    assert records[0]["app_identity"] == _SERVING_APP_ID


def test_scenario32_a_reachable_target_is_admitted_by_the_same_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control: the gauge can return the other answer.

    Without it, the refusal above is equally consistent with a preflight that
    refuses every dispatch — which would stop the whole fleet while satisfying
    every assertion of that case byte for byte. The reading is read back off the
    journal as well as off the absent refusal, because an admitted dispatch goes
    on to the rest of the wall and may be refused there for its own reasons.
    """
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path)
    runner = _runner(module=module, reach=CommandResult(exit_code=0, stdout="", stderr=""))
    _install(module=module, monkeypatch=monkeypatch, runner=runner)
    journal_path = tmp_path / "journal.jsonl"

    refusal = module.app_reach_refusal(
        repo=repo, items=[_item()], journal=JournalFile(path=journal_path)
    )  # pyright: ignore[reportAttributeAccessIssue]

    assert refusal is None
    records = _records(module=module, journal_path=journal_path)
    assert [record["reaches"] for record in records] == [True]


def test_scenario32_a_dispatcher_holding_no_app_identity_evaluates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The UNEVALUATED arm: no serving App identity, so nothing to verify.

    This is a structural absence rather than a blinded gauge — there is no
    serving App whose reach could be read — so the preflight spends no forge read
    at all, which is what the empty call list asserts, and writes no journal row,
    which is what the empty record list asserts. That arm fires for every
    invocation made outside the credential wrapper, so a row there would be a
    property of the INVOCATION rather than of the dispatch: written on every
    local call and every drain pass on a host holding no App identity, informing
    no action, and the one row an operator reading the journal has to learn to
    skip.
    """
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path)
    runner = _runner(module=module, reach=_not_found())
    _install(module=module, monkeypatch=monkeypatch, runner=runner)
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    # A sibling row is written through the SAME journal first, so the empty read
    # below is evidence this preflight wrote nothing rather than evidence the
    # file was never created — which `_records` would raise on instead, and which
    # a build writing the row under some other stage would satisfy just as well.
    journal.append(record={"stage": "a-sibling-row"})

    refusal = module.app_reach_refusal(repo=repo, items=[_item()], journal=journal)  # pyright: ignore[reportAttributeAccessIssue]

    assert refusal is None
    assert runner.calls == []
    assert _records(module=module, journal_path=journal_path) == []
