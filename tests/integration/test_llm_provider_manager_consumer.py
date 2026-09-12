"""Integration-tier acceptance for the llm-provider-manager credential consumer.

Binds this repository's side of livespec-overseer `SPECIFICATION/contracts.md` section
"The LLM credential-provider operation" (ratified at v051), as carried by
`plan/llm-provider-manager-consumer/research/001-carrier-scope.md`: the Dispatcher's
per-run overlay seam obtains its Anthropic inference credential from an injectable manager
request instead of selecting a legacy environment-pool slot.

EVERY CASE DRIVES `materialize_overlay`, THE REAL SEAM. Only the manager PROCESS is stood
in — through the port the production code already depends on — so the request the
Dispatcher sends, the value it projects, the receipt it records and the refusal it reports
are all production behaviour rather than a rehearsal of it.

THE REFUSAL CASES ASSERT THE OVERLAY IS BYTE-IDENTICAL, NOT MERELY ABSENT. An overlay that
was never written and an overlay that was written and then rolled back look the same when
the test starts from nothing, so each refusal case plants a PRIOR overlay first and
compares its bytes afterwards. Without that, "leaves the overlay byte-identical" would be
satisfied by a path that truncates it.

THE LEGACY POOL IS LEFT IN THE ENVIRONMENT ON PURPOSE. It is what the pre-launch probe
still reads during coexistence, and leaving it there is what makes "the overlay carries
the MANAGER's credential" discriminating: were the pool absent, a projection that had
silently fallen back to it would fail for the wrong reason, or project an empty string.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_sibling_clones
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_failure_report import (
    report_run_failure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    ANTHROPIC_PROVIDER,
    FACTORY_PURPOSE,
    INFERENCE_KIND,
    ISOLATED_RUN_ADAPTER,
    CredentialReceipt,
    ManagerRefusal,
    ProvisionedCredential,
    RunFailureReport,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_io import (
    LlmProviderManagerClient,
    ManagerCommandResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)
_FLEET_MANIFEST_TEXT = (
    '{\n  "owner": "thewoolleyman",\n  "members": [{ "repo": "livespec", "class": "core" }]\n}\n'
)

_DISPATCH_ID = "dispatch-wqhes7-1"
_WORK_ITEM_ID = "bd-ib-wqhes7"
_MANAGER_CREDENTIAL = "sk-ant-oat-selected-by-the-manager"
_LEGACY_POOL_CREDENTIAL = "sk-ant-oat-legacy-pool-slot"
_RECORD_ID = "5f1b7a0c-0000-4000-8000-00000000cafe"
_ACCOUNT_ID = "anthropic-3"
_GITHUB_TOKEN = "test-github-token"
_GIT_AUTHOR = GitAuthor(name="Chad Woolley", email="thewoolleyman@gmail.com")
_PRIOR_OVERLAY_BYTES = "# a previous dispatch's overlay\n"


def _receipt() -> CredentialReceipt:
    return CredentialReceipt(
        record_id=_RECORD_ID,
        account_id=_ACCOUNT_ID,
        validated_at="2026-09-12T08:00:00Z",
        purpose=FACTORY_PURPOSE,
        lease_expires_at="2026-09-12T14:00:00Z",
    )


class _ManagerStandIn:
    """The injected manager port: records what it was asked, answers what it was told."""

    def __init__(self, *, refusal: ManagerRefusal | None = None) -> None:
        self.refusal = refusal
        self.provision_runs: list[str] = []
        self.reports: list[RunFailureReport] = []

    def provision(self, *, consumer_run_id: str) -> ProvisionedCredential | ManagerRefusal:
        self.provision_runs.append(consumer_run_id)
        if self.refusal is not None:
            return self.refusal
        return ProvisionedCredential(receipt=_receipt(), value=_MANAGER_CREDENTIAL)

    def report(self, *, report: RunFailureReport) -> ManagerRefusal | None:
        self.reports.append(report)
        return None


@pytest.fixture(autouse=True)
def _dispatch_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # The LEGACY pool, left standing: it is what the pre-launch probe reads during
    # coexistence, and its presence is what makes the projection assertions discriminate.
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _LEGACY_POOL_CREDENTIAL)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )


def _workflow_toml(*, tmp_path: Path) -> Path:
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return committed


def _materialize(
    *,
    tmp_path: Path,
    overlay: Path,
    manager: _ManagerStandIn,
    receipts: list[CredentialReceipt] | None = None,
) -> str | None:
    return materialize_overlay(
        committed=_workflow_toml(tmp_path=tmp_path),
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id=_WORK_ITEM_ID,
        dispatch_id=_DISPATCH_ID,
        token=lambda: _GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        credential_manager=manager,
        receipt_sink=None if receipts is None else receipts.append,
    )


# ---------------------------------------------------------------------------
# Criterion 1 and 2 — the manager request, and where its answer goes
# ---------------------------------------------------------------------------


def test_the_overlay_carries_the_manager_selected_credential_not_a_legacy_pool_slot(
    tmp_path: Path,
) -> None:
    """Criterion 1 and 2 together, with the legacy pool present as the discriminator."""
    overlay = tmp_path / "overlay.toml"
    manager = _ManagerStandIn()
    receipts: list[CredentialReceipt] = []

    error = _materialize(tmp_path=tmp_path, overlay=overlay, manager=manager, receipts=receipts)

    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    assert f'CLAUDE_CODE_OAUTH_TOKEN = "{_MANAGER_CREDENTIAL}"' in rendered
    assert _LEGACY_POOL_CREDENTIAL not in rendered
    assert manager.provision_runs == [_DISPATCH_ID]
    assert receipts == [_receipt()]


def test_the_credential_lands_only_in_the_isolated_mode_600_run_overlay(
    tmp_path: Path,
) -> None:
    """Criterion 2's "only into the existing isolated run overlay".

    The whole temp tree is swept rather than just the overlay, because the manager writes
    its selection to a per-run target file that the client must discard once the value has
    crossed into the overlay. A second copy left behind would satisfy a check that only
    read the overlay.
    """
    overlay = tmp_path / "overlay.toml"

    error = _materialize(tmp_path=tmp_path, overlay=overlay, manager=_ManagerStandIn())

    assert error is None
    assert stat.S_IMODE(overlay.stat().st_mode) == 0o600
    carriers = [
        path
        for path in tmp_path.rglob("*")
        if path.is_file()
        and _MANAGER_CREDENTIAL in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert carriers == [overlay]


def test_the_recorded_receipt_identity_carries_no_credential_bytes(tmp_path: Path) -> None:
    """Criterion 2's "records a secret-free receipt identity"."""
    receipts: list[CredentialReceipt] = []

    error = _materialize(
        tmp_path=tmp_path,
        overlay=tmp_path / "overlay.toml",
        manager=_ManagerStandIn(),
        receipts=receipts,
    )

    assert error is None
    recorded = receipts[0]
    assert recorded.record_id == _RECORD_ID
    assert recorded.account_id == _ACCOUNT_ID
    assert recorded.purpose == FACTORY_PURPOSE
    assert _MANAGER_CREDENTIAL not in repr(recorded)


def test_the_request_the_client_sends_names_the_four_coordinates_the_item_specifies(
    tmp_path: Path,
) -> None:
    """Provider `anthropic`, the inference capability, purpose `factory`, the run identity.

    Asserted through the PRODUCTION client, so the request objects are the ones a real
    manager would receive; only the process that would run the manager is replaced.
    """
    sent: list[tuple[str, dict[str, object]]] = []
    destination = tmp_path / f"fabro-run-credential-{_DISPATCH_ID}" / "credential"

    def runner(*, command: str, request: dict[str, object]) -> ManagerCommandResult:
        import json

        sent.append((command, request))
        if command == "target":
            return ManagerCommandResult(
                stdout=json.dumps(
                    {
                        "version": 1,
                        "status": "ok",
                        "operation": "target",
                        "target_ref": "ref-xyz",
                        "expires_at": "2026-09-13T09:00:00Z",
                    }
                )
            )
        _ = destination.write_text(_MANAGER_CREDENTIAL, encoding="utf-8")
        return ManagerCommandResult(
            stdout=json.dumps(
                {
                    "version": 1,
                    "status": "ok",
                    "operation": "provision",
                    "receipt": {
                        "record_id": _RECORD_ID,
                        "account_id": _ACCOUNT_ID,
                        "validated_at": "2026-09-12T08:00:00Z",
                        "purpose": FACTORY_PURPOSE,
                        "lease_expires_at": "2026-09-12T14:00:00Z",
                    },
                }
            )
        )

    client = LlmProviderManagerClient(
        temp_dir=tmp_path,
        runner=runner,
        state_dir=lambda: tmp_path / "manager-state",
        clock=lambda: 1_789_000_000.0,
    )

    provisioned = client.provision(consumer_run_id=_DISPATCH_ID)

    assert isinstance(provisioned, ProvisionedCredential)
    target_request = dict(sent[0][1])
    provision_request = dict(sent[1][1])
    assert target_request["adapter"] == ISOLATED_RUN_ADAPTER
    assert target_request["consumer_run_id"] == _DISPATCH_ID
    assert provision_request["provider"] == ANTHROPIC_PROVIDER
    assert provision_request["kind"] == INFERENCE_KIND
    assert provision_request["purpose"] == FACTORY_PURPOSE
    assert provision_request["consumer_run_id"] == _DISPATCH_ID
    assert provision_request["target_ref"] == "ref-xyz"


# ---------------------------------------------------------------------------
# Criterion 3 — a refusal leaves the overlay byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_type",
    ["retryable-exhaustion", "store-unavailable", "provisioning-failed", "manager-unreachable"],
)
def test_a_manager_refusal_leaves_a_prior_overlay_byte_identical(
    tmp_path: Path, error_type: str
) -> None:
    """Criterion 3's first half, with a PRIOR overlay so "unchanged" can be observed."""
    overlay = tmp_path / "overlay.toml"
    _ = overlay.write_text(_PRIOR_OVERLAY_BYTES, encoding="utf-8")
    manager = _ManagerStandIn(
        refusal=ManagerRefusal(
            error_type=error_type, message="the manager refused.", remedy="do the thing."
        )
    )

    error = _materialize(tmp_path=tmp_path, overlay=overlay, manager=manager)

    assert error is not None
    assert overlay.read_text(encoding="utf-8") == _PRIOR_OVERLAY_BYTES


def test_a_manager_refusal_produces_a_typed_actionable_dispatch_refusal(
    tmp_path: Path,
) -> None:
    """Criterion 3's second half: the TYPE and the REMEDY both reach the operator."""
    manager = _ManagerStandIn(
        refusal=ManagerRefusal(
            error_type="retryable-exhaustion",
            message="no valid credential satisfies this request.",
            remedy="Acquire an Anthropic account through `llm-provider-manager acquire`.",
        )
    )

    error = _materialize(tmp_path=tmp_path, overlay=tmp_path / "overlay.toml", manager=manager)

    assert error is not None
    assert "retryable-exhaustion" in error
    assert "no valid credential satisfies this request." in error
    assert "llm-provider-manager acquire" in error
    assert ANTHROPIC_PROVIDER in error
    assert FACTORY_PURPOSE in error


def test_a_refused_dispatch_never_falls_back_to_the_legacy_pool(tmp_path: Path) -> None:
    """The prohibition that makes criterion 1 mean anything after it has been satisfied.

    A fallback would be indistinguishable from success at every other assertion in this
    module, and would leave the factory believing it runs on manager-selected accounts.
    """
    overlay = tmp_path / "overlay.toml"
    manager = _ManagerStandIn(
        refusal=ManagerRefusal(error_type="store-unavailable", message="m", remedy="r")
    )

    error = _materialize(tmp_path=tmp_path, overlay=overlay, manager=manager)

    assert error is not None
    assert not overlay.exists()


def test_a_caller_injecting_no_manager_still_refuses_through_the_default_client(
    tmp_path: Path, hermetic_credential_manager: object
) -> None:
    """The DEFAULT arm: production passes no manager and gets the real client.

    Driven through the suite-wide hermetic manager rather than an explicit argument, so
    this exercises the `credential_manager or LlmProviderManagerClient(...)` construction
    the Dispatcher itself takes — the arm an always-injecting test can never reach.
    """
    overlay = tmp_path / "overlay.toml"
    _ = overlay.write_text(_PRIOR_OVERLAY_BYTES, encoding="utf-8")
    hermetic_credential_manager.refusal = ManagerRefusal(  # pyright: ignore[reportAttributeAccessIssue]
        error_type="retryable-exhaustion", message="pool exhausted.", remedy="acquire an account."
    )

    error = materialize_overlay(
        committed=_workflow_toml(tmp_path=tmp_path),
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id=_WORK_ITEM_ID,
        dispatch_id=_DISPATCH_ID,
        token=lambda: _GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
    )

    assert error is not None
    assert "retryable-exhaustion" in error
    assert overlay.read_text(encoding="utf-8") == _PRIOR_OVERLAY_BYTES


# ---------------------------------------------------------------------------
# Criterion 4 — the failure reports a run owes its credential
# ---------------------------------------------------------------------------


def _outcome_fields(*, cause: str, provider_usage_limit: bool = False) -> dict[str, object]:
    """One parametrized failure shape, as keywords rather than a bare boolean argument."""
    return {"cause": cause, "provider_usage_limit": provider_usage_limit}


def _outcome(*, cause: str, provider_usage_limit: bool = False) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_WORK_ITEM_ID,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="the run failed",
        fabro_failure_cause=cause,
        provider_usage_limit=provider_usage_limit,
    )


@pytest.mark.parametrize(
    ("failure", "classification"),
    [
        (_outcome_fields(cause="HTTP 401 Unauthorized"), "authentication"),
        (_outcome_fields(cause="session limit reached", provider_usage_limit=True), "rate-limit"),
        (_outcome_fields(cause="HTTP 529 overloaded_error"), "provider-outage"),
        (_outcome_fields(cause="the janitor found a failing test"), "unknown"),
    ],
)
def test_each_run_failure_reports_its_classification_against_the_run_and_record(
    tmp_path: Path, failure: dict[str, object], classification: str
) -> None:
    """Criterion 4: the four classifications, each tied to both identities."""
    receipts: list[CredentialReceipt] = []
    manager = _ManagerStandIn()
    assert (
        _materialize(
            tmp_path=tmp_path,
            overlay=tmp_path / "overlay.toml",
            manager=manager,
            receipts=receipts,
        )
        is None
    )

    refusal = report_run_failure(
        manager=manager,
        receipt=receipts[0],
        consumer_run_id=_DISPATCH_ID,
        outcome=_outcome(**failure),  # pyright: ignore[reportArgumentType]
        occurred_at_epoch=1_789_000_000.0,
    )

    assert refusal is None
    report = manager.reports[0]
    assert report.classification == classification
    assert report.consumer_run_id == _DISPATCH_ID
    assert report.record_id == _RECORD_ID


def test_a_repeated_report_of_one_failure_is_the_same_report(tmp_path: Path) -> None:
    """Criterion 4's "idempotent": the manager deduplicates on exactly these members."""
    receipts: list[CredentialReceipt] = []
    manager = _ManagerStandIn()
    assert (
        _materialize(
            tmp_path=tmp_path,
            overlay=tmp_path / "overlay.toml",
            manager=manager,
            receipts=receipts,
        )
        is None
    )
    outcome = _outcome(cause="HTTP 401 Unauthorized")

    for _ in range(2):
        _ = report_run_failure(
            manager=manager,
            receipt=receipts[0],
            consumer_run_id=_DISPATCH_ID,
            outcome=outcome,
            occurred_at_epoch=1_789_000_000.0,
        )

    assert manager.reports[0] == manager.reports[1]


def test_no_report_carries_credential_bytes(tmp_path: Path) -> None:
    """Criterion 4's "secret-free", asserted over the whole rendered report."""
    receipts: list[CredentialReceipt] = []
    manager = _ManagerStandIn()
    assert (
        _materialize(
            tmp_path=tmp_path,
            overlay=tmp_path / "overlay.toml",
            manager=manager,
            receipts=receipts,
        )
        is None
    )

    _ = report_run_failure(
        manager=manager,
        receipt=receipts[0],
        consumer_run_id=_DISPATCH_ID,
        outcome=_outcome(cause=f"provider rejected {_MANAGER_CREDENTIAL}"),
        occurred_at_epoch=1_789_000_000.0,
    )

    rendered = repr(manager.reports[0])
    assert _MANAGER_CREDENTIAL not in rendered
    assert _LEGACY_POOL_CREDENTIAL not in rendered


# ---------------------------------------------------------------------------
# Criterion 5 — the review node runs on the same run-scoped credential
# ---------------------------------------------------------------------------


def test_the_run_scoped_credential_reaches_every_node_through_one_environment_table(
    tmp_path: Path,
) -> None:
    """Criterion 5's mechanism: ONE `[environments.<id>.env]` table, not a per-node key.

    The review node's adapter inherits that table, so it authenticates as the same
    manager-selected account as the implementer. The count is asserted because a second
    table would mean a second credential the manager never selected.
    """
    overlay = tmp_path / "overlay.toml"

    assert _materialize(tmp_path=tmp_path, overlay=overlay, manager=_ManagerStandIn()) is None

    rendered = overlay.read_text(encoding="utf-8")
    assert rendered.count("[environments.livespec-ci.env]") == 1
    assert rendered.count(f'CLAUDE_CODE_OAUTH_TOKEN = "{_MANAGER_CREDENTIAL}"') == 1


# ---------------------------------------------------------------------------
# The preserved neighbours
# ---------------------------------------------------------------------------


def test_the_codex_github_and_sibling_projections_survive_the_credential_change(
    tmp_path: Path,
) -> None:
    """ "Preserve the current credential probe, Codex projection, GitHub App projection".

    The manager supplies the Anthropic credential and nothing else, so every other
    projection the overlay carries must be exactly what it was.
    """
    overlay = tmp_path / "overlay.toml"

    assert _materialize(tmp_path=tmp_path, overlay=overlay, manager=_ManagerStandIn()) is None

    rendered = overlay.read_text(encoding="utf-8")
    assert f'GITHUB_TOKEN = "{_GITHUB_TOKEN}"' in rendered
    assert 'CODEX_HOME = "/workspace/.codex"' in rendered
    assert "CODEX_AUTH_JSON = " in rendered
    assert "LIVESPEC_SIBLING_CLONES_ROOT = " in rendered
