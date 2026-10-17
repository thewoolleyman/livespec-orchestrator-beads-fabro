"""Scenario 189 — the janitor's check run inherits none of the dispatcher's routing variables.

Binds `SPECIFICATION/scenarios.md` Scenario 189 and the post-merge and
reconcile janitor environment clause of `SPECIFICATION/contracts.md`.

THE CHECK AGGREGATE HERE IS A REAL CHILD PROCESS, and it is one that FAILS when
it can see a routing variable. That is not a contrivance: it is the measured
defect. A governed repository's suite legitimately exercises the code that reads
`LIVESPEC_FABRO_FACTORY` and `LIVESPEC_INVOKER` — this repository's own
`test_dispatcher_item_mode` and `test_drive_operator_defaults_scenario17` do —
so a janitor that inherits them runs a suite against an environment the merge
never saw. Measured 2026-10-17 on `bd-ib-o6aeji`: master was green on the merge
commit, the dispatch had been launched with both variables exported, and the
janitor went red on 25 tests in exactly those two areas, stranding a merged item
`active`.

So the probe child does three things: it dumps its own environment with NUL
framing (the only framing that cannot confuse a value's newline for a record
boundary), prints what it saw of each routing variable, and exits non-zero if
the variable under test reached it. A janitor that scrubs gets exit 0; one that
inherits gets the red this scenario exists to retire.

EACH CASE CARRIES ITS OWN CONTROL, because "the child saw no variable" is
evidence only if a child that WOULD have seen it is distinguishable. The control
is the same probe argv run through the same production `ShellCommandRunner` with
an unscrubbed overlay: it must report the variable's value. Without it, a probe
that simply cannot read its environment would pass every assertion here.

The git and provisioning stages around the janitor are canned, since none of
them is the subject; the janitor argv alone is handed to the production
`ShellCommandRunner`, and the journal is a real `JournalFile` read back off disk.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    CORE_PLUGIN_ROOT_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
    janitor_reconcile_checkout_path,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

# The two REQUIRED contract fields, without which the post-merge flow degrades
# before the janitor is ever reached.
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'

_JANITOR_STAGE = "janitor-post-merge"

# The journal-row field naming what the check run's environment lost.
_REMOVED_FIELD = "removed_env_vars"

# The dispatcher's two routing and attribution variables, spelled as LITERALS
# rather than imported from the production scrub set. A test that named the set
# it is grading could not tell a set missing a variable from a set that never
# claimed it.
_FACTORY_ENV_VAR = "LIVESPEC_FABRO_FACTORY"
_INVOKER_ENV_VAR = "LIVESPEC_INVOKER"

# The values the measured instance was dispatched with.
_FACTORY_VALUE = "hp-candidate"
_INVOKER_VALUE = "claude:fabro-currency"

# A credential-shaped value the check suite needs. The clause removes the
# routing variables and NOTHING else, so this one must arrive unchanged.
_CREDENTIAL_ENV_VAR = "LIVESPEC_SCENARIO189_CREDENTIAL"
_CREDENTIAL_VALUE = "the-credential-the-check-suite-needs"

# What the probe prints for a variable it could not see. A distinct marker, so
# an unset variable and an empty one are different readings.
_ABSENT = "<absent>"

# The probe's NUL-framed dump of its own environment, written into its cwd.
_ENV_DUMP = "janitor-child-env.nul"

# pull-primary, the venue's merge-containment probe, the preclean, and the five
# provisioning steps. The janitor argv itself is never taken from this queue.
_CANNED_STAGES_BEFORE_JANITOR = 8

# The in-memory tenant the reconcile case's item is seeded into.
_STORE = StoreConfig(
    tenant="livespec-orch-beads-fabro",
    prefix="bd-ib",
    server_user="livespec-orch-beads-fabro",
    database="livespec-orch-beads-fabro",
    bd_path="bd",
    fake=True,
)

# What `gh pr view` answers the reconcile valve: the merge it reconciles.
_PR_VIEW_JSON = json.dumps(
    {
        "number": 3157,
        "state": "MERGED",
        "autoMergeRequest": {},
        "mergeStateStatus": "CLEAN",
        "mergeCommit": {"oid": "0766415e"},
        "statusCheckRollup": [],
    }
)


def _probe_argv(*, fails_on: tuple[str, ...]) -> tuple[str, ...]:
    """A check aggregate that reports what it inherited and reds if it inherited too much.

    `fails_on` is the variable set whose presence this aggregate treats as a
    failure, which is how one probe stands in for a suite that exercises the
    factory resolver, for one that exercises the invoker default, and for one
    that reads neither.
    """
    guards = "".join(f'if [ -n "${{{name}-}}" ]; then exit 1; fi; ' for name in fails_on)
    return (
        "sh",
        "-c",
        (
            f"env -0 > {_ENV_DUMP}; "
            f'printf "FACTORY=%s\\n" "${{{_FACTORY_ENV_VAR}-{_ABSENT}}}"; '
            f'printf "INVOKER=%s\\n" "${{{_INVOKER_ENV_VAR}-{_ABSENT}}}"; '
            f"{guards}exit 0"
        ),
    )


@dataclass(kw_only=True)
class _JanitorChildRunner:
    """Canned results for every stage except the janitor, which runs for real."""

    janitor: tuple[str, ...]
    shell: ShellCommandRunner = field(default_factory=ShellCommandRunner)
    canned: list[CommandResult] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: object = None,
    ) -> CommandResult:
        if tuple(argv) == self.janitor:
            return self.shell.run(
                argv=argv,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                env=env,  # pyright: ignore[reportArgumentType]
            )
        return self.canned.pop(0)


def _merged() -> PrView:
    return PrView(
        number=3157,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha="0766415e",
        terminal_required_check_failures=(),
    )


def _plan(*, repo: Path, janitor: tuple[str, ...]) -> DispatchPlan:
    checkout = repo / "janitor-co"
    checkout.mkdir(parents=True, exist_ok=True)
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-fd26sc",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=janitor,
        janitor_checkout=checkout,
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )


@dataclass(frozen=True, kw_only=True)
class _Drive:
    """One post-merge janitor run, with everything an assertion needs off it."""

    outcome: DispatchOutcome
    row: dict[str, object]
    checkout: Path
    core_checkout: Path


def _drive(*, repo: Path, janitor: tuple[str, ...]) -> _Drive:
    plan = _plan(repo=repo, janitor=janitor)
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    runner = _JanitorChildRunner(
        janitor=janitor,
        canned=[CommandResult(exit_code=0, stdout="", stderr="")]
        * (_CANNED_STAGES_BEFORE_JANITOR + 1),
    )
    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    rows = [record for record in records if record.get("stage") == _JANITOR_STAGE]
    return _Drive(
        outcome=outcome,
        row=rows[-1],
        checkout=plan.janitor_checkout,
        core_checkout=plan.janitor_core_checkout,
    )


def _dump_entries(*, directory: Path) -> list[bytes]:
    """The child's own environment, NUL-framed so no value's newline can split a record."""
    return [entry for entry in (directory / _ENV_DUMP).read_bytes().split(b"\0") if entry]


def _child_env_names(*, directory: Path) -> frozenset[str]:
    return frozenset(
        entry.partition(b"=")[0].decode() for entry in _dump_entries(directory=directory)
    )


def _child_env_value(*, directory: Path, name: str) -> str | None:
    """One value out of the child's dump, read by name so no assertion renders the rest."""
    for entry in _dump_entries(directory=directory):
        key, _, value = entry.partition(b"=")
        if key.decode() == name:
            return value.decode()
    return None


def _control(*, probe: tuple[str, ...], directory: Path) -> str:
    """What the SAME probe reports with nothing scrubbed: the instrument's positive case."""
    directory.mkdir(parents=True, exist_ok=True)
    result = ShellCommandRunner().run(
        argv=list(probe),
        cwd=directory,
        timeout_seconds=120.0,
        env={CORE_PLUGIN_ROOT_ENV_VAR: str(directory)},
    )
    return result.stdout


def _routed_dispatcher_env(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """The dispatcher environment of the measured instance."""
    monkeypatch.setenv(_FACTORY_ENV_VAR, _FACTORY_VALUE)
    monkeypatch.setenv(_INVOKER_ENV_VAR, _INVOKER_VALUE)
    monkeypatch.setenv(_CREDENTIAL_ENV_VAR, _CREDENTIAL_VALUE)


def test_a_dispatch_routed_through_the_factory_variable_gets_the_verdict_its_merge_earns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A routed dispatch and an unrouted one reach the same green janitor verdict."""
    probe = _probe_argv(fails_on=(_FACTORY_ENV_VAR,))
    # The control: this probe CAN see the variable, so an absent reading below
    # is the scrub rather than a child that cannot read its own environment.
    monkeypatch.setenv(_FACTORY_ENV_VAR, _FACTORY_VALUE)
    control = _control(probe=probe, directory=tmp_path / "control")
    monkeypatch.delenv(_FACTORY_ENV_VAR)

    unrouted = _drive(repo=_repo(tmp_path=tmp_path, name="unrouted"), janitor=probe)
    _routed_dispatcher_env(monkeypatch=monkeypatch)
    routed = _drive(repo=_repo(tmp_path=tmp_path, name="routed"), janitor=probe)

    assert f"FACTORY={_FACTORY_VALUE}" in control
    assert _child_env_value(directory=routed.checkout, name=_FACTORY_ENV_VAR) is None
    assert f"FACTORY={_ABSENT}" in str(routed.row["detail"])
    assert (routed.outcome.status, routed.outcome.stage) == ("green", "done")
    assert (routed.outcome.status, routed.outcome.stage) == (
        unrouted.outcome.status,
        unrouted.outcome.stage,
    )


def test_the_janitor_check_run_keeps_every_environment_value_it_did_not_remove(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Credentials and the toolchain path reach the check unchanged; only routing goes.

    This case is an INVARIANT rather than a new behaviour: it must hold before
    the scrub exists and after, which is exactly why it is worth asserting. The
    obvious wrong way to run a child without two variables is to hand it a
    curated environment built from scratch, and a check suite that reached for
    a credential or for `PATH` in that environment would fail for a reason no
    journal row would ever name.
    """
    _routed_dispatcher_env(monkeypatch=monkeypatch)
    dispatcher_names = frozenset(os.environ)

    drive = _drive(repo=_repo(tmp_path=tmp_path, name="kept"), janitor=_probe_argv(fails_on=()))
    child_names = _child_env_names(directory=drive.checkout)

    assert _child_env_value(directory=drive.checkout, name=_CREDENTIAL_ENV_VAR) == _CREDENTIAL_VALUE
    assert _child_env_value(directory=drive.checkout, name="PATH") == os.environ["PATH"]
    # The one deliberate ADDITION the janitor makes, asserted by VALUE because
    # this host's own environment already carries that name.
    assert _child_env_value(directory=drive.checkout, name=CORE_PLUGIN_ROOT_ENV_VAR) == str(
        drive.core_checkout / ".claude-plugin"
    )
    # Nothing else joins the child, and every name it lost is a routing or
    # attribution variable.
    assert child_names - dispatcher_names <= {CORE_PLUGIN_ROOT_ENV_VAR}
    assert dispatcher_names - child_names <= {_FACTORY_ENV_VAR, _INVOKER_ENV_VAR}


def test_the_invoker_attribution_variable_is_removed_from_the_check_run_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dispatch attributed through LIVESPEC_INVOKER still gets a green janitor.

    The invoker variable is the OTHER half of the measured instance, and it
    fails the suite for a different reason than the factory route does: the
    operator-default tests resolve the journal invoker from it, so under the
    dispatcher's attribution they resolve differently than they do under CI.
    """
    probe = _probe_argv(fails_on=(_INVOKER_ENV_VAR,))
    monkeypatch.setenv(_INVOKER_ENV_VAR, _INVOKER_VALUE)
    control = _control(probe=probe, directory=tmp_path / "control")

    _routed_dispatcher_env(monkeypatch=monkeypatch)
    drive = _drive(repo=_repo(tmp_path=tmp_path, name="attributed"), janitor=probe)

    assert f"INVOKER={_INVOKER_VALUE}" in control
    assert _child_env_value(directory=drive.checkout, name=_INVOKER_ENV_VAR) is None
    assert f"INVOKER={_ABSENT}" in str(drive.row["detail"])
    assert (drive.outcome.status, drive.outcome.stage) == ("green", "done")


def test_the_janitor_post_merge_journal_row_names_each_variable_it_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The row names both removed variables, so a reader can tell a scrubbed run.

    The row is the only durable account of the scrub: the child's environment
    is gone the moment the check exits, and the clause asks for the removal to
    be legible afterwards rather than inferred from a green verdict.
    """
    _routed_dispatcher_env(monkeypatch=monkeypatch)

    drive = _drive(repo=_repo(tmp_path=tmp_path, name="named"), janitor=_probe_argv(fails_on=()))

    # Read with `get`, so an ABSENT field and an EMPTY list are distinguishable
    # readings rather than one KeyError -- the next case turns on exactly that.
    assert drive.row.get(_REMOVED_FIELD) == [_FACTORY_ENV_VAR, _INVOKER_ENV_VAR]


def test_the_reconcile_merged_janitor_applies_the_same_environment_scrub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The reconcile valve's own janitor check run carries neither routing variable.

    Driven through the REAL `dispatcher.main(argv=["reconcile-merged", ...])`
    entry point over the real store seam, with the check aggregate taken off
    the repository's own committed `dispatcher.janitor.check_suite`
    declaration, because the valve builds its own plan and no argument of this
    test could put a probe into it. The valve is a SECOND entry into the
    post-merge flow, which is why the clause names it separately: a scrub wired
    at one caller rather than inside the flow would leave this one inheriting.
    """
    reset_fake_singleton()
    probe = _probe_argv(fails_on=(_FACTORY_ENV_VAR, _INVOKER_ENV_VAR))
    # The in-memory tenant: this tier never reaches a live Dolt server.
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _routed_dispatcher_env(monkeypatch=monkeypatch)
    repo = _reconcile_repo(tmp_path=tmp_path, probe=probe)
    item = _reconcile_item()
    append_work_item(path=_STORE, item=item)
    checkout = janitor_reconcile_checkout_path(repo=repo, work_item_id=item.id)
    checkout.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner",
        lambda: _ReconcileRunner(janitor=probe),
    )

    _ = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--json"])

    assert _child_env_value(directory=checkout, name=_FACTORY_ENV_VAR) is None
    assert _child_env_value(directory=checkout, name=_INVOKER_ENV_VAR) is None
    # The same retention control the post-merge cases carry: the check run keeps
    # the credential it was invoked with.
    assert _child_env_value(directory=checkout, name=_CREDENTIAL_ENV_VAR) == _CREDENTIAL_VALUE


@dataclass(kw_only=True)
class _ReconcileRunner:
    """The reconcile valve's runner, keyed on the SUBCOMMAND rather than on call order.

    Keying on argv rather than on a queue is what lets the janitor run for real
    wherever the valve reaches it, without this test encoding the valve's own
    stage sequence -- which is not the subject and whose drift would make the
    case fail for a reason that has nothing to do with the environment.
    """

    janitor: tuple[str, ...]
    shell: ShellCommandRunner = field(default_factory=ShellCommandRunner)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: object = None,
    ) -> CommandResult:
        if tuple(argv) == self.janitor:
            return self.shell.run(
                argv=argv,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                env=env,  # pyright: ignore[reportArgumentType]
            )
        if "symbolic-ref" in argv:
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[:3] == ["gh", "pr", "view"]:
            return CommandResult(exit_code=0, stdout=_PR_VIEW_JSON, stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


def _reconcile_repo(*, tmp_path: Path, probe: tuple[str, ...]) -> Path:
    """A governed repository DECLARING the probe as its janitor check suite."""
    repo = tmp_path / "reconcile-repo"
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "compat": {"pinned": "master"},
                    "dispatcher": {
                        "acceptance_mode": "ai-only",
                        "janitor": {"check_suite": list(probe)},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _reconcile_item() -> WorkItem:
    return WorkItem(
        id="bd-ib-fd26sc-reconcile",
        type="bug",
        status="active",
        title="A merged item the reconcile valve re-runs the janitor for",
        description="Reconcile the already merged pull request.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    return repo
