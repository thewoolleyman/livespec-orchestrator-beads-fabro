"""The gate and the audit read retained receipts themselves, and refuse when they cannot."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-y7ryj3
from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._factory_bypass_gh import GhSeam
from livespec_orchestrator_beads_fabro.commands._incident_provenance import IncidentReceipt
from livespec_orchestrator_beads_fabro.commands.factory_bypass_audit import main as audit_main
from livespec_orchestrator_beads_fabro.commands.factory_provenance_check import main as gate_main
from livespec_orchestrator_beads_fabro.incident_authority import AuthorityRefusal

_REPOSITORY = "owner/repository"
_PRODUCT = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/thing.py"
_SPEC = "SPECIFICATION/contracts.md"
_HEAD = "a" * 40
_LANDED = "b" * 40
_FACTORY_BOT = "thewoolleyman-factory-bot[bot]"


def _receipt() -> IncidentReceipt:
    return IncidentReceipt(
        repository=_REPOSITORY,
        item_id="incident-1",
        phase="repair",
        pr_number=73,
        head_sha=_HEAD,
        landed_commits=(_LANDED,),
        repayment_required=True,
    )


class RecordingLoader:
    """A receipt loader that records how it was asked and answers a canned result."""

    def __init__(self, *, result: tuple[IncidentReceipt, ...] | AuthorityRefusal) -> None:
        self.result = result
        self.calls: list[tuple[Path, str | None]] = []

    def __call__(
        self, *, repo: Path, repository: str | None
    ) -> tuple[IncidentReceipt, ...] | AuthorityRefusal:
        self.calls.append((repo, repository))
        return self.result


class GitRunner:
    """The gate's two git reads: the changed paths and the proposed commits."""

    def __init__(self, *, changed: str) -> None:
        self.changed = changed

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
        if argv[:3] == ["git", "diff", "--name-only"]:
            return CommandResult(exit_code=0, stdout=f"{self.changed}\n", stderr="")
        return CommandResult(exit_code=0, stdout=f"{_LANDED}\n", stderr="")


def _repo(*, root: Path) -> Path:
    _ = (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = [".claude-plugin/scripts"]\n',
        encoding="utf-8",
    )
    return root


def _event(*, root: Path, login: str) -> Path:
    path = root / "event.json"
    _ = path.write_text(
        json.dumps(
            {
                "number": 73,
                "repository": {"full_name": _REPOSITORY},
                "pull_request": {
                    "user": {"login": login},
                    "labels": [],
                    "base": {"sha": "c" * 40},
                    "head": {"sha": _HEAD},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _gate(
    *, root: Path, login: str, changed: str, loader: RecordingLoader | None = None
) -> tuple[int, RecordingLoader]:
    used = loader if loader is not None else RecordingLoader(result=())
    code = gate_main(
        argv=["--event-path", str(_event(root=root, login=login)), "--repo", str(_repo(root=root))],
        runner=GitRunner(changed=changed),
        receipt_loader=used,
    )
    return code, used


def test_the_gate_admits_a_non_factory_change_matching_a_retained_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    loader = RecordingLoader(result=(_receipt(),))
    code, used = _gate(root=tmp_path, login="thewoolleyman", changed=_PRODUCT, loader=loader)
    assert code == 0
    assert "retained exact incident receipt" in capsys.readouterr().out
    assert used.calls == [(tmp_path, _REPOSITORY)]


def test_the_gate_refuses_a_change_when_the_retained_receipts_match_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = IncidentReceipt(
        repository=_REPOSITORY,
        item_id="incident-2",
        phase="repair",
        pr_number=74,
        head_sha=_HEAD,
        landed_commits=(_LANDED,),
        repayment_required=True,
    )
    code, _ = _gate(
        root=tmp_path,
        login="thewoolleyman",
        changed=_PRODUCT,
        loader=RecordingLoader(result=(other,)),
    )
    assert code == 1
    assert "matches no retained exact incident receipt" in capsys.readouterr().err


def test_the_gate_refuses_when_the_retained_receipts_cannot_be_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    refusal = AuthorityRefusal(code="incident-authority-unavailable", detail="tenant down")
    code, _ = _gate(
        root=tmp_path,
        login="thewoolleyman",
        changed=_PRODUCT,
        loader=RecordingLoader(result=refusal),
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "incident-authority-unavailable" in captured.err
    assert "tenant down" in captured.err
    assert captured.out == ""


def test_the_gate_does_not_consult_the_ledger_for_a_factory_authored_change(
    tmp_path: Path,
) -> None:
    code, used = _gate(root=tmp_path, login=_FACTORY_BOT, changed=_PRODUCT)
    assert code == 0
    assert used.calls == []


def test_the_gate_does_not_consult_the_ledger_when_no_product_python_changes(
    tmp_path: Path,
) -> None:
    code, used = _gate(root=tmp_path, login="thewoolleyman", changed=_SPEC)
    assert code == 0
    assert used.calls == []


def test_the_default_gate_refuses_an_unconfigured_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = gate_main(
        argv=[
            "--event-path",
            str(_event(root=tmp_path, login="thewoolleyman")),
            "--repo",
            str(_repo(root=tmp_path)),
        ],
        runner=GitRunner(changed=_PRODUCT),
    )
    assert code == 2
    assert "incident-authority-unavailable" in capsys.readouterr().err


def test_the_default_gate_fails_a_change_when_the_configured_ledger_holds_no_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "test"}}}),
        encoding="utf-8",
    )
    code = gate_main(
        argv=[
            "--event-path",
            str(_event(root=tmp_path, login="thewoolleyman")),
            "--repo",
            str(_repo(root=tmp_path)),
        ],
        runner=GitRunner(changed=_PRODUCT),
    )
    assert code == 1
    assert "may not merge" in capsys.readouterr().err


def _seam(*, pull_requests: list[dict[str, object]]) -> GhSeam:
    def run(*, args: list[str]) -> str:
        if args[:2] == ["pr", "list"]:
            return json.dumps(pull_requests)
        return '[tool.livespec_dev_tooling]\nsource_tree_prefixes = [".claude-plugin/scripts/"]\n'

    return GhSeam(run=run)


def _merged_repair(*, number: int = 73, author: str = "thewoolleyman") -> dict[str, object]:
    return {
        "number": number,
        "title": "fix: expedited repair",
        "author": {"login": author},
        "files": [{"path": _PRODUCT}],
        "labels": [],
        "commits": [{"oid": _LANDED, "messageHeadline": "fix", "messageBody": ""}],
        "headRefOid": _HEAD,
    }


def test_the_audit_reports_a_retained_receipt_with_its_repayment_outstanding(
    capsys: pytest.CaptureFixture[str],
) -> None:
    loader = RecordingLoader(result=(_receipt(),))
    code = audit_main(
        argv=["--json", "--repo", _REPOSITORY],
        seam=_seam(pull_requests=[_merged_repair()]),
        receipt_loader=loader,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["count"] == 0
    assert payload["exceptions"] == [
        {
            "author": "thewoolleyman",
            "item_id": "incident-1",
            "number": 73,
            "repayment_outstanding": True,
            "title": "fix: expedited repair",
        }
    ]
    assert [repository for _, repository in loader.calls] == [_REPOSITORY]


def test_the_audit_still_flags_a_change_no_retained_receipt_matches(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = audit_main(
        argv=["--json", "--repo", _REPOSITORY],
        seam=_seam(pull_requests=[_merged_repair(number=99)]),
        receipt_loader=RecordingLoader(result=(_receipt(),)),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["count"] == 1
    assert payload["exception_count"] == 0


def test_the_audit_refuses_rather_than_reporting_on_unreadable_receipts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = AuthorityRefusal(code="incident-authority-unavailable", detail="tenant down")
    code = audit_main(
        argv=["--json", "--repo", _REPOSITORY],
        seam=_seam(pull_requests=[_merged_repair()]),
        receipt_loader=RecordingLoader(result=refusal),
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "incident-authority-unavailable" in captured.err
    assert captured.out == ""


def test_the_audit_does_not_consult_the_ledger_when_the_factory_authored_everything(
    capsys: pytest.CaptureFixture[str],
) -> None:
    loader = RecordingLoader(result=())
    code = audit_main(
        argv=["--json", "--repo", _REPOSITORY],
        seam=_seam(pull_requests=[_merged_repair(author="app/thewoolleyman-factory-bot")]),
        receipt_loader=loader,
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0
    assert loader.calls == []


def test_declared_receipts_are_used_without_reading_the_ledger(
    capsys: pytest.CaptureFixture[str],
) -> None:
    loader = RecordingLoader(result=())
    code = audit_main(
        argv=["--json", "--repo", _REPOSITORY],
        seam=_seam(pull_requests=[_merged_repair()]),
        incident_receipts=(_receipt(),),
        receipt_loader=loader,
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["exception_count"] == 1
    assert loader.calls == []
