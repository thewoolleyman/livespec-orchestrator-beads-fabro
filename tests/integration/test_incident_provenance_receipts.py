"""Incident provenance exceptions remain exact and repayable (bd-ib-y7ryj3).

Scenario: ## Scenario: incident provenance exceptions remain exact and repayable.
Contract: ## Expedited incident lifecycle, "A valid incident repair receipt MUST
admit only the exact authorized local repair carrier through factory provenance
and the retrospective bypass audit ... Historical validation MUST bind exact
PR/head/landed identities after environment and labels disappear. An arbitrary
label, caller environment, Factory-Override trailer or code marker alone MUST
NOT confer an exception ... Normal factory repayment MUST require normal
provenance and complete validation."

Every case drives a consumer's public entry point — the factory-provenance merge
gate's `main` or the retrospective factory-bypass audit's `main` — with the
arguments an operator would pass, against the in-memory tenant the repository
under `tmp_path` configures. The retained incident chain is seeded into that
tenant exactly as the canonical writer records it: a genesis comment on the
item and closed epoch tokens carrying the immutable attempts.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    fake_singleton,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.commands import (
    factory_bypass_audit,
    factory_provenance_check,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._factory_bypass_gh import GhSeam

REPOSITORY = "owner/repository"
ITEM = "bd-ib-incident1"
PRODUCT = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/thing.py"
HUMAN = "thewoolleyman"
FACTORY_APP = "thewoolleyman-factory-bot[bot]"
BASE = "a" * 40
HEAD = "b" * 40
LANDED = ("c" * 40, "d" * 40)
TREES = ("e" * 40, "f" * 40)
REPAY_HEAD = "1" * 40
REPAY_LANDED = ("2" * 40,)
REPAY_TREES = ("3" * 40,)
_PYPROJECT = '[tool.livespec_dev_tooling]\nsource_trees = [".claude-plugin/scripts"]\n'


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(**changes: Any) -> dict[str, Any]:
    return (
        dict(
            repository=REPOSITORY,
            item_id=ITEM,
            attempt_id="attempt-1",
            phase="repair",
            operation_id="operation-1",
            generation=1,
            owner="operator:alice",
            base=BASE,
            head=HEAD,
            pr_number=73,
            landed_commits=list(LANDED),
            landed_trees=list(TREES),
            original_paths=[PRODUCT],
            deferred_work=["normal-factory-proof"],
            repayment_required=True,
        )
        | changes
    )


def _repayment(*, generation: int, phase: str) -> dict[str, Any]:
    return _attempt(
        attempt_id=f"attempt-{generation}",
        operation_id=f"operation-{generation}",
        generation=generation,
        phase=phase,
        pr_number=80,
        head=REPAY_HEAD,
        landed_commits=list(REPAY_LANDED),
        landed_trees=list(REPAY_TREES),
    )


def _token(client: FakeBeadsClient) -> str:
    return client.create_no_history_issue(
        title=TOKEN_TITLE, description="Retained immutable incident authority."
    )


def _seed_chain(*, attempts: list[dict[str, Any]]) -> FakeBeadsClient:
    """Record the item, its genesis and one closed token per committed attempt."""
    client = fake_singleton()
    client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    token = _token(client)
    client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + _canonical(dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id=token)),
    )
    for attempt in attempts:
        successor = _token(client)
        payload = dict(
            schema=1,
            repository=REPOSITORY,
            item_id=ITEM,
            prior_token_id=token,
            next_token_id=successor,
            attempt=attempt,
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + _canonical(payload)
        )
        token = successor
    return client


def _repo(*, root: Path) -> Path:
    """A repository whose declaration names the product tree and whose store is in memory."""
    _ = (root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "fake": True}}}
        ),
        encoding="utf-8",
    )
    return root


def _event(
    *,
    root: Path,
    name: str,
    login: str,
    pr_number: int,
    head: str,
    labels: tuple[str, ...] = (),
) -> Path:
    """One pull_request event payload as the forge delivers it."""
    path = root / name
    _ = path.write_text(
        json.dumps(
            {
                "number": pr_number,
                "repository": {"full_name": REPOSITORY},
                "pull_request": {
                    "user": {"login": login},
                    "labels": [{"name": label} for label in labels],
                    "base": {"sha": BASE},
                    "head": {"sha": head},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


class CarrierRunner:
    """The gate's two git reads: the changed paths, and the commits the PR lands."""

    def __init__(self, *, landed: tuple[str, ...]) -> None:
        self.landed = landed

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
            return CommandResult(exit_code=0, stdout=f"{PRODUCT}\n", stderr="")
        assert argv[:3] == ["git", "rev-list", "--reverse"]
        return CommandResult(exit_code=0, stdout="".join(f"{c}\n" for c in self.landed), stderr="")


def _gate(
    *,
    root: Path,
    event: Path,
    landed: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
    items: tuple[str, ...] = (ITEM,),
) -> tuple[int, str, str]:
    """Run the merge gate as CI would, once the gate can read a retained-authority tenant."""
    assert (
        "authority_client" in inspect.signature(factory_provenance_check.main).parameters
    ), "the merge gate takes no retained-authority tenant yet"
    argv = ["--event-path", str(event), "--repo", str(root)]
    for item in items:
        argv += ["--incident-item", item]
    code = factory_provenance_check.main(argv=argv, runner=CarrierRunner(landed=landed))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _merged(
    *,
    number: int,
    author: str,
    head: str,
    landed: tuple[str, ...],
    labels: tuple[str, ...] = (),
    messages: tuple[str, ...] = (),
) -> dict[str, Any]:
    """One merged pull request as `gh pr list --json` renders it."""
    return {
        "number": number,
        "title": f"change {number} ({ITEM})",
        "author": {"login": author},
        "files": [{"path": PRODUCT}],
        "labels": [{"name": label} for label in labels],
        "headRefOid": head,
        "commits": [
            {"oid": oid, "messageHeadline": f"commit {oid[:4]}", "messageBody": body}
            for oid, body in zip(landed, (*messages, *([""] * len(landed))), strict=False)
        ],
    }


def _audit(
    *,
    root: Path,
    prs: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    items: tuple[str, ...] = (ITEM,),
) -> dict[str, Any]:
    """Run the retrospective audit as an operator would, with the parsed `--json` report."""

    def _gh(*, args: list[str]) -> str:
        return _PYPROJECT if args[0] == "api" else json.dumps(prs)

    assert (
        "authority_client" in inspect.signature(factory_bypass_audit.main).parameters
    ), "the retrospective audit takes no retained-authority tenant yet"
    argv = ["--json", "--repo", REPOSITORY, "--project-root", str(root)]
    for item in items:
        argv += ["--incident-item", item]
    code = factory_bypass_audit.main(argv=argv, seam=GhSeam(run=_gh))
    assert code == 0
    return json.loads(capsys.readouterr().out)


def test_factory_provenance_recognizes_a_trusted_receipt_only_for_its_exact_pr_head_and_landed_commits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = _seed_chain(attempts=[_attempt()])
    root = _repo(root=tmp_path)
    exact = _event(root=root, name="exact.json", login=HUMAN, pr_number=73, head=HEAD)

    code, out, err = _gate(root=root, event=exact, landed=LANDED, capsys=capsys)

    assert (code, err) == (0, "")
    assert "retained exact incident receipt" in out
    assert ITEM in out
    assert "deferred verification" in out
    other_pr = _event(root=root, name="pr74.json", login=HUMAN, pr_number=74, head=HEAD)
    other_head = _event(root=root, name="head.json", login=HUMAN, pr_number=73, head="9" * 40)
    refused = [
        _gate(root=root, event=other_pr, landed=LANDED, capsys=capsys),
        _gate(root=root, event=other_head, landed=LANDED, capsys=capsys),
        _gate(root=root, event=exact, landed=LANDED[:1], capsys=capsys),
        _gate(root=root, event=exact, landed=(*LANDED, "7" * 40), capsys=capsys),
    ]
    assert [code for code, _, _ in refused] == [1, 1, 1, 1]
    assert all("matches no retained exact incident receipt" in err for _, _, err in refused)


def test_the_retrospective_bypass_audit_reports_recorded_incident_exceptions_with_outstanding_repayment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = _seed_chain(attempts=[_attempt()])
    root = _repo(root=tmp_path)
    prs = [
        _merged(number=73, author=HUMAN, head=HEAD, landed=LANDED),
        _merged(number=74, author=HUMAN, head="9" * 40, landed=("8" * 40,)),
        _merged(number=75, author=HUMAN, head=HEAD, landed=LANDED),
    ]

    payload = _audit(root=root, prs=prs, capsys=capsys)

    assert payload["exceptions"] == [
        {
            "author": HUMAN,
            "item_id": ITEM,
            "kind": "incident-receipt",
            "number": 73,
            "repayment_outstanding": True,
            "title": f"change 73 ({ITEM})",
        }
    ]
    assert [finding["number"] for finding in payload["findings"]] == [74, 75]
    assert payload["incident_refusals"] == []
    reset_fake_singleton()
    _ = _seed_chain(
        attempts=[
            _attempt(),
            _repayment(generation=2, phase="repayment-active"),
            _repayment(generation=3, phase="closed"),
        ]
    )
    repaid = _audit(root=root, prs=prs[:1], capsys=capsys)
    assert repaid["exceptions"][0]["repayment_outstanding"] is False
    assert repaid["findings"] == []


def test_historical_receipt_verification_remains_available_after_labels_and_environment_disappear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_INCIDENT_CONTEXT", json.dumps(_attempt()))
    _ = [
        monkeypatch.delenv(name)
        for name in list(os.environ)
        if name.startswith(("LIVESPEC_INCIDENT", "GITHUB_"))
    ]
    assert "LIVESPEC_INCIDENT_CONTEXT" not in os.environ
    _ = _seed_chain(
        attempts=[
            _attempt(),
            _attempt(
                attempt_id="attempt-2",
                operation_id="operation-2",
                generation=2,
                phase="master-observation",
            ),
            _attempt(
                attempt_id="attempt-3",
                operation_id="operation-3",
                generation=3,
                phase="repayment-admission",
            ),
        ]
    )
    root = _repo(root=tmp_path)
    unlabeled = _event(root=root, name="later.json", login=HUMAN, pr_number=73, head=HEAD)

    code, out, err = _gate(root=root, event=unlabeled, landed=LANDED, capsys=capsys)

    assert (code, err) == (0, "")
    assert ITEM in out
    assert "normal repayment outstanding" in out
    unnamed = _gate(root=root, event=unlabeled, landed=LANDED, capsys=capsys, items=())
    assert unnamed[0] == 1
    unreadable = _gate(
        root=root, event=unlabeled, landed=LANDED, capsys=capsys, items=("bd-ib-unknown",)
    )
    assert unreadable[0] == 2
    assert "bd-ib-unknown" in unreadable[2]
    assert "incident-authority" in unreadable[2]
    assert "refuses rather than passing unobserved" in unreadable[2]


def test_normal_repayment_requires_normal_factory_provenance_while_flags_labels_trailers_and_markers_remain_insufficient(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = _seed_chain(attempts=[_attempt(), _repayment(generation=2, phase="repayment-active")])
    root = _repo(root=tmp_path)
    monkeypatch.setenv("LIVESPEC_INCIDENT_CONTEXT", json.dumps(_attempt()))
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "1")
    labeled = _event(
        root=root,
        name="labeled.json",
        login=HUMAN,
        pr_number=80,
        head=REPAY_HEAD,
        labels=("factory-override", "expedited-incident-response"),
    )

    code, _, err = _gate(root=root, event=labeled, landed=REPAY_LANDED, capsys=capsys)

    assert code == 1
    assert "retained normal repayment carrier" in err
    assert "requires normal factory provenance" in err
    assert "insufficient authorization" in err
    factory = _event(
        root=root, name="factory.json", login=FACTORY_APP, pr_number=80, head=REPAY_HEAD
    )
    code, out, _ = _gate(root=root, event=factory, landed=REPAY_LANDED, capsys=capsys)
    assert code == 0
    assert "factory GitHub App" in out
    payload = _audit(
        root=root,
        prs=[
            _merged(
                number=80,
                author=HUMAN,
                head=REPAY_HEAD,
                landed=REPAY_LANDED,
                labels=("factory-override",),
                messages=(f"Factory-Override: incident {ITEM}",),
            ),
            _merged(
                number=81,
                author=HUMAN,
                head="9" * 40,
                landed=("8" * 40,),
                labels=("expedited-incident-response",),
                messages=(f"# EXPEDITED_INCIDENT_RESPONSE flag: {ITEM}",),
            ),
        ],
        capsys=capsys,
    )
    assert [recorded["kind"] for recorded in payload["exceptions"]] == ["factory-override"]
    assert payload["exceptions"][0]["item_id"] == ""
    assert payload["exceptions"][0]["repayment_outstanding"] is False
    assert [finding["number"] for finding in payload["findings"]] == [81]
