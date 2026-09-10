"""Tests for targeted per-item reconciliation and its post-write hook."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.store import append_work_item, record_dispatch_factory
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    "/_dispatcher_run_reconcile_hook.py"
)
_HP = "https://hp.example.test"
_VPS = "https://vps.example.test"
_QUESTIONS = json.dumps([{"id": "q-1", "options": ["[A] Abandon (leave open for triage)"]}])


@dataclass(kw_only=True)
class _Runner:
    """A fake `fabro` CLI keyed by the server each argv names."""

    ps_by_server: dict[str, str] = field(default_factory=dict)
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
        if argv[1] == "ps":
            return CommandResult(exit_code=0, stdout=self.ps_by_server.get(server, "[]"), stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Transport:
    calls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (headers, body, timeout_seconds)
        self.calls.append(f"{method} {url}")
        return FabroHttpResult(
            status=200,
            body=_QUESTIONS if url.endswith("/questions") else "{}",
            error=None,
            payload=None,
            succeeded=True,
        )


def test_the_hook_module_exposes_the_targeted_reconciler_and_its_post_write_seam() -> None:
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE)

    assert sorted(module.__all__) == [
        "JOURNAL_STAGE_HOOK_ERROR",
        "dispatch_journal_path",
        "reconcile_after_lifecycle_write",
        "reconcile_runs_for_item",
        "targeted_factories",
    ]


def test_a_landing_on_active_reconciles_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    hook = importlib.import_module(_MODULE)
    calls = _spy_reconcile(hook=hook, monkeypatch=monkeypatch)

    hook.reconcile_after_lifecycle_write(
        path=_config(repo_root=Path("/nowhere")),
        item_id="bd-ib-1",
        status="active",
    )

    assert calls == []


def test_a_config_without_a_repo_root_is_a_documented_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = importlib.import_module(_MODULE)
    calls = _spy_reconcile(hook=hook, monkeypatch=monkeypatch)

    hook.reconcile_after_lifecycle_write(path=_config(), item_id="bd-ib-1", status="done")

    assert calls == []


def test_a_landing_off_active_reconciles_that_item(monkeypatch: pytest.MonkeyPatch) -> None:
    hook = importlib.import_module(_MODULE)
    calls = _spy_reconcile(hook=hook, monkeypatch=monkeypatch)

    hook.reconcile_after_lifecycle_write(
        path=_config(repo_root=Path("/repo")),
        item_id="bd-ib-1",
        status="ready",
    )

    assert calls == [(Path("/repo"), "bd-ib-1")]


def test_a_repo_declaring_no_factory_surveys_nothing_and_reads_no_store(tmp_path: Path) -> None:
    hook = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path, factories={})
    runner = _Runner()

    summary = hook.reconcile_runs_for_item(repo=repo, item_id="bd-ib-1", runner=runner)

    assert hook.targeted_factories(repo=repo, item_id="bd-ib-1") == ()
    assert (summary.reconciled, summary.errors, summary.dry_run) == ((), (), False)
    assert runner.calls == []


def test_the_stamped_factory_is_the_only_one_surveyed(tmp_path: Path) -> None:
    hook = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="done"))
    record_dispatch_factory(path=_config(), work_item_id="bd-ib-1", factory="vps")
    _journal_dispatch(repo=repo, item_id="bd-ib-1", run_id="01ORPHAN")
    runner = _Runner(ps_by_server={_VPS: _ps(run_id="01ORPHAN", kind="blocked")})

    summary = hook.reconcile_runs_for_item(
        repo=repo,
        item_id="bd-ib-1",
        runner=runner,
        http=_Transport(),
    )

    assert [target.name for target in hook.targeted_factories(repo=repo, item_id="bd-ib-1")] == [
        "vps"
    ]
    assert [run.factory_name for run in summary.reconciled] == ["vps"]
    assert _servers_surveyed(runner=runner) == [_VPS]


def test_an_unstamped_item_falls_back_to_every_declared_factory(tmp_path: Path) -> None:
    hook = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="done"))
    runner = _Runner()

    _ = hook.reconcile_runs_for_item(repo=repo, item_id="bd-ib-1", runner=runner)

    assert _servers_surveyed(runner=runner) == [_HP, _VPS]


def test_only_the_named_items_run_is_reconciled(tmp_path: Path) -> None:
    hook = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="done"))
    append_work_item(path=_config(), item=_item(item_id="bd-ib-2", status="done"))
    _journal_dispatch(repo=repo, item_id="bd-ib-1", run_id="01MINE")
    _journal_dispatch(repo=repo, item_id="bd-ib-2", run_id="01THEIRS")
    runner = _Runner(
        ps_by_server={
            _HP: _ps(run_id="01MINE", kind="blocked", work_item_id="bd-ib-1"),
            _VPS: _ps(run_id="01THEIRS", kind="blocked", work_item_id="bd-ib-2"),
        }
    )

    summary = hook.reconcile_runs_for_item(
        repo=repo,
        item_id="bd-ib-1",
        runner=runner,
        http=_Transport(),
    )

    assert [run.run_id for run in summary.reconciled] == ["01MINE"]


def test_an_already_terminal_run_is_left_alone_so_the_hook_is_idempotent(tmp_path: Path) -> None:
    hook = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="done"))
    runner = _Runner(ps_by_server={_HP: _ps(run_id="01DONE", kind="succeeded")})
    transport = _Transport()

    summary = hook.reconcile_runs_for_item(
        repo=repo, item_id="bd-ib-1", runner=runner, http=transport
    )

    assert (summary.reconciled, summary.errors) == ((), ())
    assert transport.calls == []


def test_a_reconciliation_failure_is_journaled_and_never_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)

    def _boom(**_: object) -> None:
        raise RuntimeError("factory said no")

    monkeypatch.setattr(hook, "reconcile_runs_for_item", _boom)

    hook.reconcile_after_lifecycle_write(
        path=_config(repo_root=repo), item_id="bd-ib-1", status="done"
    )

    records = _journal_records(repo=repo)
    assert [record["stage"] for record in records] == [hook.JOURNAL_STAGE_HOOK_ERROR]
    assert records[0]["work_item_id"] == "bd-ib-1"
    assert records[0]["reason"] == "RuntimeError"
    assert records[0]["detail"] == "factory said no"


def test_the_journal_write_failure_is_itself_swallowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path)

    def _boom(**_: object) -> None:
        raise OSError("factory said no")

    def _unwritable(self: object, *, record: dict[str, object]) -> None:
        _ = (self, record)
        raise OSError("journal is read-only")

    monkeypatch.setattr(hook, "reconcile_runs_for_item", _boom)
    monkeypatch.setattr(hook.JournalFile, "append", _unwritable)

    hook.reconcile_after_lifecycle_write(
        path=_config(repo_root=repo), item_id="bd-ib-1", status="done"
    )

    assert not hook.dispatch_journal_path(repo=repo).exists()


def _spy_reconcile(
    *,
    hook: object,
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[Path, str]]:
    calls: list[tuple[Path, str]] = []

    def _record(*, repo: Path, item_id: str) -> None:
        calls.append((repo, item_id))

    monkeypatch.setattr(hook, "reconcile_runs_for_item", _record)
    return calls


def _servers_surveyed(*, runner: _Runner) -> list[str]:
    return [argv[argv.index("--server") + 1] for argv in runner.calls if argv[1] == "ps"]


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    hook = importlib.import_module(_MODULE)
    text = hook.dispatch_journal_path(repo=repo).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def _journal_dispatch(*, repo: Path, item_id: str, run_id: str) -> None:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(
            json.dumps(
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": item_id,
                    "run_id": run_id,
                }
            )
            + "\n"
        )


def _repo(*, tmp_path: Path, factories: dict[str, str] | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    declared = {"hp": {"server": _HP}, "vps": {"server": _VPS}} if factories is None else factories
    dispatcher_block: dict[str, object] = {"factories": declared}
    if declared:
        dispatcher_block["default_factory"] = "hp"
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


def _config(*, repo_root: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-orchestrator-beads-fabro",
        prefix="bd-ib",
        server_user="livespec-orchestrator-beads-fabro",
        database="livespec-orchestrator-beads-fabro",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _ps(*, run_id: str, kind: str, work_item_id: str = "bd-ib-1") -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "goal": f"Work-item: {work_item_id}\nRepo: /tmp/repo",
                "status": {"kind": kind},
            }
        ]
    )


def _item(*, item_id: str = "bd-ib-1", status: str = "active") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        title=item_id,
        description=item_id,
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
