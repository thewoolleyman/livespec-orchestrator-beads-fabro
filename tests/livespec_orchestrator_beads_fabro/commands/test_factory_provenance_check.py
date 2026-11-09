"""Tests for the factory-provenance merge gate (R6a of mechanically-enforce-factory-usage)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    FLEET_FALLBACK_PRODUCT_PREFIXES,
    ProductPathPolicy,
)
from livespec_orchestrator_beads_fabro.commands._factory_provenance_event import PullRequestEvent
from livespec_orchestrator_beads_fabro.commands._incident_provenance import IncidentReceipt
from livespec_orchestrator_beads_fabro.commands.factory_provenance_check import (
    FACTORY_APP_LOGINS,
    FACTORY_OVERRIDE_LABEL,
    decide,
    exit_code,
    main,
    permits_merge,
    render_verdict,
    resolve_product_policy,
)

_PRODUCT_PY = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/thing.py"
_TEST_PY = "tests/livespec_orchestrator_beads_fabro/commands/test_thing.py"
_SPEC_MD = "SPECIFICATION/contracts.md"
_POLICY = ProductPathPolicy(prefixes=(".claude-plugin/scripts/",), origin="declared")
_REPOSITORY = "owner/repository"
_ITEM = "incident-1"
_BASE = "a" * 40
_HEAD = "b" * 40
_LANDED = ("c" * 40,)


class StubRunner:
    """A CommandRunner answering every argv with one canned result."""

    def __init__(self, *, result: CommandResult) -> None:
        self.result = result

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del argv, cwd, timeout_seconds, env, stdin
        return self.result


class ExactReceiptRunner:
    """The gate's two git reads for a retained, exact incident receipt."""

    def __init__(self, *, commits: CommandResult | None = None) -> None:
        self.argvs: list[list[str]] = []
        self.commits = (
            CommandResult(exit_code=0, stdout=f"{_LANDED[0]}\n", stderr="")
            if commits is None
            else commits
        )

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
        self.argvs.append(argv)
        if argv[:3] == ["git", "diff", "--name-only"]:
            return CommandResult(exit_code=0, stdout=f"{_PRODUCT_PY}\n", stderr="")
        assert argv[:3] == ["git", "rev-list", "--reverse"]
        return self.commits


def _event(
    *,
    login: str = "thewoolleyman",
    labels: tuple[str, ...] = (),
    pr_number: int = 73,
    repository: str = _REPOSITORY,
) -> PullRequestEvent:
    return PullRequestEvent(
        author_login=login,
        labels=labels,
        base_sha=_BASE,
        head_sha=_HEAD,
        pr_number=pr_number,
        repository=repository,
    )


def _write_event(
    *,
    path: Path,
    login: str,
    labels: tuple[str, ...] = (),
    repository: str | None = _REPOSITORY,
) -> None:
    payload: dict[str, Any] = {
        "number": 73,
        "pull_request": {
            "user": {"login": login},
            "labels": [{"name": name} for name in labels],
            "base": {"sha": _BASE},
            "head": {"sha": _HEAD},
        },
    }
    if repository is not None:
        payload["repository"] = {"full_name": repository}
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def _repo_with_declaration(*, root: Path) -> Path:
    _ = (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = [".claude-plugin/scripts"]\n',
        encoding="utf-8",
    )
    return root


def _receipt(*, phase: str = "repair", pr_number: int = 73) -> IncidentReceipt:
    return IncidentReceipt(
        repository=_REPOSITORY,
        item_id=_ITEM,
        phase=phase,
        pr_number=pr_number,
        head_sha=_HEAD,
        landed_commits=_LANDED,
        repayment_required=True,
    )


def _attempt(*, generation: int, phase: str) -> dict[str, Any]:
    return dict(
        repository=_REPOSITORY,
        item_id=_ITEM,
        attempt_id=f"attempt-{generation}",
        phase=phase,
        operation_id=f"operation-{generation}",
        generation=generation,
        owner="operator:alice",
        base=_BASE,
        head=_HEAD,
        pr_number=73,
        landed_commits=list(_LANDED),
        landed_trees=["d" * 40],
        original_paths=[_PRODUCT_PY],
        deferred_work=["normal-factory-proof"],
        repayment_required=True,
    )


def _tenant(*, phases: tuple[str, ...]) -> FakeBeadsClient:
    """An in-memory tenant holding one retained chain, one attempt per phase."""
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"))  # noqa: E731
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
    client.add_comment(
        issue_id=_ITEM,
        body=GENESIS_MARKER
        + canonical(dict(schema=1, repository=_REPOSITORY, item_id=_ITEM, root_token_id=token)),
    )
    for generation, phase in enumerate(phases, start=1):
        successor = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
        payload = dict(
            schema=1,
            repository=_REPOSITORY,
            item_id=_ITEM,
            prior_token_id=token,
            next_token_id=successor,
            attempt=_attempt(generation=generation, phase=phase),
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + canonical(payload)
        )
        token = successor
    return client


def test_a_non_factory_author_changing_product_python_without_the_label_fails() -> None:
    verdict = decide(event=_event(), changed_paths=(_PRODUCT_PY,), policy=_POLICY)
    assert verdict.outcome == "fail"
    assert verdict.product_paths == (_PRODUCT_PY,)
    assert verdict.incident_receipt is None
    assert permits_merge(verdict=verdict) is False
    assert exit_code(verdict=verdict) == 1


@pytest.mark.parametrize("login", FACTORY_APP_LOGINS)
def test_both_factory_app_login_spellings_pass(login: str) -> None:
    verdict = decide(event=_event(login=login), changed_paths=(_PRODUCT_PY,), policy=_POLICY)
    assert verdict.outcome == "pass"
    assert verdict.factory_authored is True
    assert permits_merge(verdict=verdict) is True
    assert exit_code(verdict=verdict) == 0


def test_the_factory_override_label_passes_a_non_factory_author() -> None:
    verdict = decide(
        event=_event(labels=(FACTORY_OVERRIDE_LABEL,)),
        changed_paths=(_PRODUCT_PY,),
        policy=_POLICY,
    )
    assert verdict.outcome == "pass"
    assert verdict.override_labeled is True
    assert permits_merge(verdict=verdict) is True


def test_an_exact_retained_receipt_passes_a_non_factory_author_without_a_label() -> None:
    verdict = decide(
        event=_event(),
        changed_paths=(_PRODUCT_PY,),
        policy=_POLICY,
        landed_commits=_LANDED,
        incident_receipts=(_receipt(),),
    )
    assert verdict.outcome == "pass"
    assert verdict.incident_receipt == _receipt()
    assert permits_merge(verdict=verdict) is True


def test_the_label_does_not_pass_the_retained_normal_repayment_carrier() -> None:
    verdict = decide(
        event=_event(labels=(FACTORY_OVERRIDE_LABEL,)),
        changed_paths=(_PRODUCT_PY,),
        policy=_POLICY,
        landed_commits=_LANDED,
        incident_receipts=(_receipt(phase="repayment-active"),),
    )
    assert verdict.outcome == "fail"
    assert verdict.override_labeled is True
    assert verdict.incident_receipt is None
    assert verdict.repayment_carrier == _receipt(phase="repayment-active")
    assert "requires normal factory provenance" in render_verdict(verdict=verdict)


def test_a_diff_touching_no_product_python_permits_the_merge() -> None:
    verdict = decide(event=_event(), changed_paths=(_SPEC_MD, _TEST_PY), policy=_POLICY)
    assert verdict.product_paths == ()
    assert verdict.judged_path_count == 2
    assert permits_merge(verdict=verdict) is True
    assert exit_code(verdict=verdict) == 0
    # Ratified scoped-check vacuity clause: a scope that matched zero files
    # observed nothing, so the EVIDENCE it reports is vacuity rather than a
    # pass. The merge is permitted either way — that is what the two
    # assertions above establish.
    assert verdict.outcome == "vacuous-match"


def test_the_failure_message_names_the_author_and_the_product_paths() -> None:
    verdict = decide(event=_event(), changed_paths=(_PRODUCT_PY, _SPEC_MD), policy=_POLICY)
    message = render_verdict(verdict=verdict)
    assert "@thewoolleyman" in message
    assert _PRODUCT_PY in message
    assert _SPEC_MD not in message
    assert FACTORY_APP_LOGINS[0] in message
    assert f"`{FACTORY_OVERRIDE_LABEL}` label" in message
    assert "pull request body" in message
    assert "retained exact incident receipt" in message
    assert "label, trailer, marker" in message


def test_the_pass_message_names_which_ground_admitted_the_change() -> None:
    app_verdict = decide(
        event=_event(login=FACTORY_APP_LOGINS[0]), changed_paths=(_PRODUCT_PY,), policy=_POLICY
    )
    override_verdict = decide(
        event=_event(labels=(FACTORY_OVERRIDE_LABEL,)),
        changed_paths=(_PRODUCT_PY,),
        policy=_POLICY,
    )
    receipt_verdict = decide(
        event=_event(),
        changed_paths=(_PRODUCT_PY,),
        policy=_POLICY,
        landed_commits=_LANDED,
        incident_receipts=(_receipt(),),
    )
    assert "factory GitHub App" in render_verdict(verdict=app_verdict)
    assert FACTORY_OVERRIDE_LABEL in render_verdict(verdict=override_verdict)
    assert f"retained exact incident receipt of {_ITEM}" in render_verdict(verdict=receipt_verdict)


def test_the_vacuous_message_says_it_observed_nothing_and_does_not_block() -> None:
    verdict = decide(event=_event(), changed_paths=(_SPEC_MD,), policy=_POLICY)
    message = render_verdict(verdict=verdict)
    assert "vacuous-match" in message
    assert "not a pass" in message
    assert "not blocked" in message


def test_resolve_product_policy_reads_the_repository_declaration(tmp_path: Path) -> None:
    policy = resolve_product_policy(repo=_repo_with_declaration(root=tmp_path))
    assert policy.origin == "declared"
    assert policy.prefixes == (".claude-plugin/scripts/",)


def test_resolve_product_policy_falls_back_when_the_repository_declares_nothing(
    tmp_path: Path,
) -> None:
    policy = resolve_product_policy(repo=tmp_path)
    assert policy.origin == "fleet-fallback"
    assert policy.prefixes == FLEET_FALLBACK_PRODUCT_PREFIXES


def test_main_fails_a_hand_authored_product_python_pull_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman")
    code = main(
        argv=[
            "--event-path",
            str(event_path),
            "--repo",
            str(repo),
            "--changed-file",
            _PRODUCT_PY,
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "may not merge" in captured.err
    assert _PRODUCT_PY in captured.err
    assert captured.out == ""


def test_main_passes_a_factory_authored_pull_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman-factory-bot[bot]")
    code = main(
        argv=[
            "--event-path",
            str(event_path),
            "--repo",
            str(repo),
            "--changed-file",
            _PRODUCT_PY,
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "pass" in captured.out
    assert captured.err == ""


def test_main_reads_the_named_incident_from_the_ledger_and_passes_only_its_exact_carrier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman")
    runner = ExactReceiptRunner()
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo), "--incident-item", _ITEM],
        runner=runner,
        authority_client=_tenant(phases=("repair",)),
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "retained exact incident receipt" in captured.out
    assert captured.err == ""
    assert runner.argvs == [
        ["git", "diff", "--name-only", f"{_BASE}...{_HEAD}"],
        ["git", "rev-list", "--reverse", f"{_BASE}..{_HEAD}"],
    ]
    other = ExactReceiptRunner(commits=CommandResult(exit_code=0, stdout="9" * 40, stderr=""))
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo), "--incident-item", _ITEM],
        runner=other,
        authority_client=_tenant(phases=("repair",)),
    )
    assert code == 1
    assert "matches no retained exact incident receipt" in capsys.readouterr().err


def test_main_refuses_a_named_incident_whose_chain_cannot_be_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman", labels=(FACTORY_OVERRIDE_LABEL,))
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo), "--incident-item", "absent"],
        runner=ExactReceiptRunner(),
        authority_client=FakeBeadsClient(),
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "incident item absent could not be verified" in captured.err
    assert "incident-authority-unavailable" in captured.err
    assert captured.out == ""


def test_main_refuses_a_named_incident_when_the_event_names_no_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman", repository=None)
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo), "--incident-item", _ITEM],
        runner=ExactReceiptRunner(),
        authority_client=_tenant(phases=("repair",)),
    )
    assert code == 2
    assert "names no repository" in capsys.readouterr().err


def test_main_refuses_a_named_incident_when_the_landed_commits_cannot_be_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman")
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo), "--incident-item", _ITEM],
        runner=ExactReceiptRunner(commits=CommandResult(exit_code=128, stdout="", stderr="bad")),
        authority_client=_tenant(phases=("repair",)),
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "could not read the commits" in captured.err
    assert "fetch-depth: 0" in captured.err


def test_main_reads_the_changed_paths_from_git_when_no_changed_file_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman")
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo)],
        runner=StubRunner(result=CommandResult(exit_code=0, stdout=f"{_PRODUCT_PY}\n", stderr="")),
    )
    assert code == 1
    assert _PRODUCT_PY in capsys.readouterr().err


def test_main_takes_the_event_path_from_the_actions_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman", labels=(FACTORY_OVERRIDE_LABEL,))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    code = main(argv=["--repo", str(repo), "--changed-file", _PRODUCT_PY])
    assert code == 0
    assert FACTORY_OVERRIDE_LABEL in capsys.readouterr().out


def test_main_refuses_when_no_event_payload_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    code = main(argv=[])
    assert code == 2
    assert "no event payload" in capsys.readouterr().err


def test_main_refuses_an_unreadable_event_payload_rather_than_passing_unobserved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "absent.json"
    code = main(argv=["--event-path", str(missing)])
    captured = capsys.readouterr()
    assert code == 2
    assert "could not read a pull_request event payload" in captured.err
    assert str(missing) in captured.err


def test_main_refuses_when_the_diff_cannot_be_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman")
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo)],
        runner=StubRunner(result=CommandResult(exit_code=128, stdout="", stderr="bad revision")),
    )
    captured = capsys.readouterr()
    assert code == 2
    assert f"{_BASE}...{_HEAD}" in captured.err
    assert "fetch-depth: 0" in captured.err
