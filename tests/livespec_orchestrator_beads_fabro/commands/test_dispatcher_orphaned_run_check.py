"""Tests for the fail-closed `orphaned-factory-run` Ledger invariant."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import LedgerFinding
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_orphaned_run_check"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    "/_dispatcher_orphaned_run_check.py"
)
_HP = "https://hp.example.test"


@dataclass(kw_only=True)
class _Runner:
    ps_by_server: dict[str, str] = field(default_factory=dict)
    failing_servers: frozenset[str] = frozenset()
    calls: list[list[str]] = field(default_factory=list)

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
        self.calls.append(argv)
        server = argv[argv.index("--server") + 1] if "--server" in argv else ""
        if server in self.failing_servers:
            return CommandResult(exit_code=7, stdout="", stderr="connection refused")
        return CommandResult(exit_code=0, stdout=self.ps_by_server.get(server, "[]"), stderr="")


def test_the_check_module_names_the_invariant_it_enforces() -> None:
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE)

    assert module.ORPHANED_FACTORY_RUN_CHECK == "orphaned-factory-run"
    assert sorted(module.__all__) == [
        "ORPHANED_FACTORY_RUN_CHECK",
        "orphaned_factory_run_findings",
    ]


def test_a_non_terminal_run_for_a_non_active_item_fails_the_invariant(tmp_path: Path) -> None:
    check = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="done"))
    runner = _Runner(ps_by_server={_HP: _ps(run_id="01ORPHAN", kind="blocked")})

    findings = check.orphaned_factory_run_findings(repo=repo, runner=runner)

    assert [(finding.check, finding.item_id, finding.severity) for finding in findings] == [
        ("orphaned-factory-run", "bd-ib-1", "fail")
    ]
    assert "01ORPHAN" in findings[0].message
    assert "'done'" in findings[0].message


def test_a_superseded_run_for_an_active_item_also_fails_the_invariant(tmp_path: Path) -> None:
    check = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="active"))
    _journal(
        repo=repo,
        records=[
            {
                "stage": "dispatch-run-stamp",
                "work_item_id": "bd-ib-1",
                "fabro_run_id": "01OLD",
            },
            {
                "stage": "dispatch-run-stamp",
                "work_item_id": "bd-ib-1",
                "fabro_run_id": "01NEW",
            },
        ],
    )
    runner = _Runner(ps_by_server={_HP: _ps(run_id="01OLD", kind="running")})

    findings = check.orphaned_factory_run_findings(repo=repo, runner=runner)

    assert [finding.item_id for finding in findings] == ["bd-ib-1"]
    assert "superseded-run" in findings[0].message


def test_a_clean_inventory_passes(tmp_path: Path) -> None:
    check = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="active"))
    runner = _Runner(ps_by_server={_HP: _ps(run_id="01LIVE", kind="running")})

    assert check.orphaned_factory_run_findings(repo=repo, runner=runner) == []


def test_an_unreachable_factory_is_its_own_finding_rather_than_a_pass(tmp_path: Path) -> None:
    check = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    runner = _Runner(failing_servers=frozenset({_HP}))

    findings = check.orphaned_factory_run_findings(repo=repo, runner=runner)

    assert [(finding.check, finding.item_id) for finding in findings] == [
        ("orphaned-factory-run", "-")
    ]
    assert "factory-ps-failed" in findings[0].message
    assert findings[0].severity == "fail"


def test_a_repo_declaring_no_factory_performs_no_survey(tmp_path: Path) -> None:
    check = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path, declare_factories=False)
    runner = _Runner()

    assert check.orphaned_factory_run_findings(repo=repo, runner=runner) == []
    assert runner.calls == []


def test_the_survey_is_a_dry_run_that_terminates_and_journals_nothing(tmp_path: Path) -> None:
    check = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="done"))
    runner = _Runner(ps_by_server={_HP: _ps(run_id="01ORPHAN", kind="blocked")})

    _ = check.orphaned_factory_run_findings(repo=repo, runner=runner)

    hook = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook"
    )
    assert [argv[1] for argv in runner.calls] == ["ps"]
    assert not hook.dispatch_journal_path(repo=repo).exists()


def test_the_invariant_runs_where_the_other_ledger_invariants_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        _dispatcher_run_checks,
        "orphaned_factory_run_findings",
        lambda **_: [
            LedgerFinding(
                check="orphaned-factory-run",
                item_id="bd-ib-1",
                message="non-terminal run 01ORPHAN on factory hp",
            )
        ],
    )

    exit_code = main(argv=["ledger-check", "--project-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert [finding["check"] for finding in payload] == ["orphaned-factory-run"]


def _repo(*, tmp_path: Path, declare_factories: bool = True) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    dispatcher_block: dict[str, object] = (
        {"default_factory": "hp", "factories": {"hp": {"server": _HP}}} if declare_factories else {}
    )
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": dispatcher_block,
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _journal(*, repo: Path, records: list[dict[str, str]]) -> None:
    hook = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook"
    )
    path = hook.dispatch_journal_path(repo=repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-orchestrator-beads-fabro",
        prefix="bd-ib",
        server_user="livespec-orchestrator-beads-fabro",
        database="livespec-orchestrator-beads-fabro",
        bd_path="bd",
        fake=True,
    )


def _ps(*, run_id: str, kind: str) -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "goal": "Work-item: bd-ib-1\nRepo: /tmp/repo",
                "status": {"kind": kind},
            }
        ]
    )


def _item(*, status: str) -> WorkItem:
    return WorkItem(
        id="bd-ib-1",
        type="task",
        status=status,
        title="bd-ib-1",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
