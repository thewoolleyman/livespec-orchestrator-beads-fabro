"""A record observed on ONE account does not hold out another of its vendor.

Binds `SPECIFICATION/scenarios.md` "## Scenario 186" cases "A dispatch on
another credential identity is admitted while the record is live" and "A
dispatch on the same credential identity is refused while the record is live",
against the clause in `SPECIFICATION/contracts.md` section "Dispatcher
admission, WIP cap, and post-merge acceptance": "A record carrying a credential
identity covers only a dispatch whose admission projects that same identity for
a covered candidate; a dispatch projecting a different identity, including one
admitted after the credential behind the candidate was rotated to another
account of the same vendor, MUST NOT be refused by it."

THREE TIERS, AND THE FIRST IS THE ONE THE FIX LIVES OR DIES ON. An
identity-bearing record reaches a dispatch by TWO routes, not one: the
provider-exhaustion admission gate, and -- because `_legacy_providers` feeds
every live record's vendor into the typed candidate filter as a legacy
provider-only blanket -- the chain-exhaustion refusal one condition later.
Measured on this repository's own node shape before the fix, a single
`anthropic` record naming account "A" emptied SEVEN of eight admission-required
nodes with a `legacy-provider-hold` skip, so a gate taught to admit account "B"
would have been refused by the next condition anyway, and the whole fix would
have been inert. A record that NAMES an account is not a provider-only record,
so it is no longer part of that blanket.

EVERY CASE IS PAIRED, because each negative here is the plausible-wrong-answer
shape: a gate that simply stopped reading the journal admits account "B"
exactly as a correctly scoped one does. So each admit sits beside a refusal on
the SAME journal -- the same vendor, the same expiry, one account apart.

Everything is HERMETIC: the repository and journal are files under `tmp_path`,
readings are literals, no provider is reached and no adapter is launched.
"""

from __future__ import annotations

import inspect
import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomReading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T17:40:00Z"
_LIVE_EXPIRY = "2099-01-01T00:00:00Z"
# The account four in-flight runs exhausted, and the one the selection had
# already rotated onto. Opaque digests: only their inequality carries meaning.
_EXHAUSTED_ACCOUNT = "1111111111111111"
_ROTATED_ACCOUNT = "2222222222222222"
_OPUS_ENTRY: dict[str, Any] = {
    "agent": "claude-acp",
    "model": "claude-opus-5",
    "effort": "high",
}


def _exhaustion() -> Any:
    return import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")


def _observation(*, identity: str | None) -> dict[str, object]:
    return {
        "at": _NOW,
        "stage": "provider-exhaustion-observed",
        "work_item_id": "bd-observer",
        "provider": "anthropic",
        "credential_identity": identity,
        "governing_condition": "provider_usage_limit",
        "record_expires_at": _LIVE_EXPIRY,
    }


def _journal_file(*, tmp_path: Path, identity: str | None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text(f"{json.dumps(_observation(identity=identity))}\n", encoding="utf-8")
    return path


def _rendered_anthropic() -> Any:
    """One built-in Anthropic candidate, the shape a live legacy record covers."""
    schema = import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = import_module(f"{_PACKAGE}._acp_node_adapters")
    coverage = import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    return coverage.RenderedCandidate(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="claude-adapter", env={}, args=()),
            identity=schema.AcpCandidateIdentity(
                display_name="built-in Anthropic ACP adapter",
                candidate_key="builtin-anthropic-0000000000000000",
                availability_key="anthropic",
            ),
        ),
        builtin=True,
    )


class _RecordingJournal:
    """The journal seam, recording what a refusal wrote rather than writing it."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _repo_declaring_claude_nodes(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"acp_nodes": {"implement": dict(_OPUS_ENTRY)}}
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def test_a_record_naming_another_account_leaves_the_whole_candidate_chain_intact(
    tmp_path: Path,
) -> None:
    """The legacy blanket is for provider-ONLY records; a named account is not one."""
    acp_preflight = import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    repo = _repo_declaring_claude_nodes(tmp_path=tmp_path)

    scoped = acp_preflight.resolve_acp_preflight(
        repo=repo,
        journal_path=_journal_file(tmp_path=tmp_path, identity=_EXHAUSTED_ACCOUNT),
        now_iso=_NOW,
    )

    assert scoped.refusal is None
    assert (
        scoped.exhausted == ()
    ), "an account-scoped record is still feeding the legacy provider-only blanket"
    assert [skip.reason for node in scoped.nodes for skip in node.skipped] == []
    # The control, on the same repository and the same vendor: a record that
    # names NO account keeps the vendor-wide blanket the clause grants it, so
    # the admission-required nodes DO empty. Without this half, a filter that
    # had simply stopped reading the journal would satisfy the case above.
    blanket = acp_preflight.resolve_acp_preflight(
        repo=repo,
        journal_path=_journal_file(tmp_path=tmp_path / "blanket", identity=None),
        now_iso=_NOW,
    )

    assert blanket.exhausted != ()
    assert {skip.reason for node in blanket.nodes for skip in node.skipped} == {
        "legacy-provider-hold"
    }


def test_the_gate_refuses_the_exhausted_account_and_admits_the_rotated_one(
    tmp_path: Path,
) -> None:
    """Scenario 186: one account apart, on one journal, two verdicts."""
    exhaustion = _exhaustion()
    assert (
        "projected_identities"
        in inspect.signature(exhaustion.covering_provider_exhaustion).parameters
    ), "the gate cannot yet be told which account this dispatch projects"
    path = _journal_file(tmp_path=tmp_path, identity=_EXHAUSTED_ACCOUNT)

    def covering(*, projected: frozenset[str]) -> Any:
        return exhaustion.covering_provider_exhaustion(
            journal_path=path,
            now_iso=_NOW,
            candidates=(_rendered_anthropic(),),
            projected_identities=projected,
        )

    refused = covering(projected=frozenset({_EXHAUSTED_ACCOUNT}))
    assert refused is not None
    assert refused.credential_identity == _EXHAUSTED_ACCOUNT
    # The rotation the record was minted DURING: a dispatch projecting the
    # account the selection moved to could not have hit this ceiling.
    assert covering(projected=frozenset({_ROTATED_ACCOUNT})) is None


def test_the_refusal_names_the_account_whose_allowance_is_gone(tmp_path: Path) -> None:
    """An operator reading the refusal is told WHICH account, not just which vendor."""
    exhaustion = _exhaustion()
    journal = _RecordingJournal()

    outcome = exhaustion.provider_exhaustion_refusal(
        work_item_id="bd-ib-b53dhr",
        journal=journal,
        journal_path=_journal_file(tmp_path=tmp_path, identity=_EXHAUSTED_ACCOUNT),
        now_iso=_NOW,
        candidates=(_rendered_anthropic(),),
        projected_identities=frozenset({_EXHAUSTED_ACCOUNT}),
    )

    assert outcome is not None
    assert f"credential_identity={_EXHAUSTED_ACCOUNT}" in outcome.detail
    refusal = journal.records[-1]
    assert refusal["stage"] == "provider-exhaustion-refusal"
    assert refusal["credential_identity"] == _EXHAUSTED_ACCOUNT


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-b53dhr",
        type="bug",
        status="ready",
        title="Ready candidate",
        description="## Definition of Done\n\n- The product satisfies one assertion.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _verdict(*, identity: str) -> AcpPreflightVerdict:
    """A viable verdict whose admission assessment projected ONE account."""
    return AcpPreflightVerdict(
        fallback_enabled=True,
        success_critical=("implement",),
        headroom_assessments=(
            SessionHeadroomReading(
                credential_identity=identity,
                observed_at=_NOW,
                utilization_percent=10.0,
                remaining_percent=90.0,
            ),
        ),
        session_headroom_floor_percent=20,
    )


def _admission_repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = tmp_path / "admission"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"adopted_assertion_count_ceiling": None},
                }
            }
        ),
        encoding="utf-8",
    )
    append_work_item(path=_config(repo_root=repo), item=_item())
    return repo


def test_the_admission_valve_threads_the_account_its_own_assessment_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring, which no assertion about the gate alone can establish.

    A gate that scopes perfectly is inert if the valve hands it an empty set
    forever -- and an empty set is exactly what the fail-closed arm treats as
    an unreadable projection, so the dispatch would be refused with no error
    and no sign that the account was never threaded through.
    """
    repo = _admission_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=tmp_path / "admission-journal.jsonl")
    journal.append(record=_observation(identity=_EXHAUSTED_ACCOUNT))

    admitted, refused = filter_eligible_candidates(
        repo=repo,
        preflight=_verdict(identity=_ROTATED_ACCOUNT),
        candidates=[_item()],
        journal=journal,
    )

    assert refused == []
    assert [item.id for item in admitted] == ["bd-ib-b53dhr"]
    # The control on the same journal: the valve DOES refuse when its own
    # assessment projected the account the record names.
    held, held_refusals = filter_eligible_candidates(
        repo=repo,
        preflight=_verdict(identity=_EXHAUSTED_ACCOUNT),
        candidates=[_item()],
        journal=journal,
    )

    assert held == []
    assert [outcome.stage for outcome in held_refusals] == ["provider-exhaustion"]
    assert f"credential_identity={_EXHAUSTED_ACCOUNT}" in held_refusals[0].detail
