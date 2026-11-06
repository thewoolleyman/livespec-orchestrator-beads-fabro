"""Incident receipts reach the provenance gate and retrospective audit."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._factory_bypass_gh import PullRequest
from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    ProductPathPolicy,
)
from livespec_orchestrator_beads_fabro.commands._factory_bypass_report_types import AuditPolicy
from livespec_orchestrator_beads_fabro.commands._factory_provenance_event import PullRequestEvent
from livespec_orchestrator_beads_fabro.commands._incident_provenance import IncidentReceipt
from livespec_orchestrator_beads_fabro.commands.factory_bypass_audit import audit_pull_requests
from livespec_orchestrator_beads_fabro.commands.factory_provenance_check import (
    decide,
    main,
    permits_merge,
)

_REPOSITORY = "owner/repository"
_HEAD = "a" * 40
_LANDED = ("b" * 40,)
_PRODUCT = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/thing.py"
_PATH_POLICY = ProductPathPolicy(prefixes=(".claude-plugin/scripts/",), origin="declared")


def _reading(*, phase: str = "repair") -> IncidentReading:
    committed_token = "token-1"
    current_token = "token-2"
    return IncidentReading(
        attempt=IncidentAttempt(
            repository=_REPOSITORY,
            item_id="incident-1",
            attempt_id="attempt-1",
            phase=phase,
            operation_id="operation-1",
            generation=1,
            owner="operator:alice",
            base="c" * 40,
            head=_HEAD,
            pr_number=73,
            landed_commits=_LANDED,
            landed_trees=("d" * 40,),
            original_paths=(_PRODUCT,),
            deferred_work=("normal-factory-proof",),
            repayment_required=True,
        ),
        committed_token_id=committed_token,
        current_token_id=current_token,
        is_current=False,
    )


def test_trusted_historical_receipts_are_exact_exceptions_with_repayment_outstanding() -> None:
    incident = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._incident_provenance"
    )
    assert hasattr(incident, "receipt_from_authority_reading")
    receipt = incident.receipt_from_authority_reading(reading=_reading())
    assert receipt is not None
    event = PullRequestEvent(
        author_login="thewoolleyman",
        labels=(),
        base_sha="c" * 40,
        head_sha=_HEAD,
        pr_number=73,
    )
    verdict = decide(
        event=event,
        changed_paths=(_PRODUCT,),
        policy=_PATH_POLICY,
        landed_commits=_LANDED,
        incident_receipts=(receipt,),
    )
    assert permits_merge(verdict=verdict)
    report = audit_pull_requests(
        prs=[
            PullRequest(
                number=73,
                title="repair",
                author_login="thewoolleyman",
                files=(_PRODUCT,),
                labels=(),
                head_sha=_HEAD,
                landed_commits=_LANDED,
                commit_messages=(),
            )
        ],
        policy=AuditPolicy(
            factory_app_login="app/thewoolleyman-factory-bot",
            allow_authors=frozenset(),
            allow_labels=frozenset(),
            product_paths=_PATH_POLICY,
            incident_receipts=(receipt,),
        ),
    )
    assert report.findings == ()
    assert report.exceptions[0].repayment_outstanding is True
    assert report.exceptions[0].item_id == "incident-1"
    assert not permits_merge(
        verdict=decide(
            event=event,
            changed_paths=(_PRODUCT,),
            policy=_PATH_POLICY,
            landed_commits=("e" * 40,),
            incident_receipts=(receipt,),
        )
    )
    assert (
        incident.receipt_from_authority_reading(reading=_reading(phase="repayment-active")) is None
    )


class UnreadableReceiptCommitRunner:
    """The gate must not treat an unavailable exact identity as an exception."""

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
            return CommandResult(exit_code=0, stdout=f"{_PRODUCT}\n", stderr="")
        assert argv == ["git", "rev-list", "--reverse", "base1234..head5678"]
        return CommandResult(exit_code=128, stdout="", stderr="bad revision")


def test_gate_refuses_when_a_candidate_incident_receipt_lacks_commit_provenance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = [".claude-plugin/scripts"]\n',
        encoding="utf-8",
    )
    event_path = tmp_path / "event.json"
    _ = event_path.write_text(
        json.dumps(
            {
                "number": 73,
                "repository": {"full_name": _REPOSITORY},
                "pull_request": {
                    "user": {"login": "thewoolleyman"},
                    "labels": [],
                    "base": {"sha": "base1234"},
                    "head": {"sha": "head5678"},
                },
            }
        ),
        encoding="utf-8",
    )
    receipt = IncidentReceipt(
        repository=_REPOSITORY,
        item_id="incident-1",
        phase="repair",
        pr_number=73,
        head_sha="head5678",
        landed_commits=("landed1234",),
        repayment_required=True,
    )

    code = main(
        argv=["--event-path", str(event_path), "--repo", str(tmp_path)],
        runner=UnreadableReceiptCommitRunner(),
        incident_receipts=(receipt,),
    )

    assert code == 2
    assert "could not read the commits" in capsys.readouterr().err
