"""The measured built-in tables reach a candidate resolved THROUGH its agent.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Built-in Claude and Codex candidates MUST carry exact, measured
mappings for stable diagnostics exposed by the pinned adapters." The measured
minimum set it then fixes is named BY AGENT -- "for `claude-acp`, the
session-limit form (literals `hit your session limit`) ... for `codex-acp`, the
structured usage-limit field in BOTH its camelCase spelling ... and the message
forms" -- and the same section requires that "Every listed measured form MUST
be exercised against its recorded executed candidate". Scenario 65 and Scenario
127 govern.

WHAT THE TABLES COULD NOT REACH. `effective_signatures` attached them on ONE
provenance route: the `builtin` flag `_acp_dispatch_coverage` sets from the
rendered-bytes table of `_acp_builtin_candidates`. That table keys on the exact
adapter strings THIS BUILD renders -- the workflow's own Anthropic defaults and
the two un-pinned Codex bases -- so it matches a MANUAL-form candidate and can
never match a STRUCTURED one, whose identity is derived from the catalogs and
whose `candidate_key` is the canonical `<agent>/<provider>/<model>` triple
rather than a digest of bytes. Every ACP node of this repository's graph
resolves through the structured form, so the measured minimum set applied to
none of them: the session-limit sentence reached `unmatched`, which is
non-eligible, so the failure minted no typed hold and the release fell through
to the legacy cause-text arm.

MEASURED 2026-10-24, the two runs this work-item was filed from. An in-flight
run keeps the Claude credential projected at dispatch, so a caam account
rotation protects only new dispatches and a run live when its account's
five-hour window empties dies where it stands: `livespec-dev-tooling-ool6ws`
run 01M5PZCS5Y2V failed at `proof_verify@2` and `livespec-dev-tooling-epcoja`
run 01M5PZY50N7J failed at `proof_capture@1`, each with the agent answering
`session/prompt` with "Internal error: You've hit your session limit · resets
3:40pm (UTC)".

TWO CONTROLS, POINTED IN OPPOSITE DIRECTIONS, and neither is optional. A
REGISTRY-SEEDED agent must still match nothing: the measured tables belong to
the two agents whose diagnostics were measured, never to every agent a catalog
declares, and lending Claude's measurements to an adapter nobody has seen emit
them is the same defect as inferring identity from command text. And a
candidate resolved through NO agent must stay exactly where it was -- the
conservative legacy posture the contract keeps covered by every unexpired
legacy provider record, whose only route out is declaring explicit identity.

THE CANDIDATES BELOW ARE RESOLVED THROUGH THE REAL CATALOGS rather than
hand-written, because the identity a structured entry derives is the whole
subject: a hand-written triple would keep passing after the derivation changed
shape. The agent and model each entry names are this file's own fixture choice
and are deliberately not read from the committed routing, which
`tests/conftest.py` replaces with a tripwire for exactly that reason.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    ANTHROPIC_DOMAIN,
    CODEX_DOMAIN,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures import (
    builtin_availability_signatures,
    effective_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_structured import (
    parse_structured_candidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import builtin_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    DOMAIN_SCOPE,
    AcpAvailabilityFailure,
    AcpNonEligibleFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
    classified_release,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_disposition import (
    dispose_provider_limit_release,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome import (
    PROVIDER_LIMIT_RELEASE_STATUS,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_QUOTA = "quota"
_MESSAGE_SOURCE = "protocol.message"
_MACHINE_CODE_SOURCE = "protocol.machine_code"

# The measured sentence, in the two shapes this work-item names: the
# `session/prompt` error the engine recorded, and the bare message an engine
# that kept no structured payload leaves behind.
_RECORDED_SESSION_LIMIT = (
    "the agent answered `session/prompt` with an error: Internal error: "
    "You've hit your session limit · resets 3:40pm (UTC)"
)
_BARE_SESSION_LIMIT = "You've hit your session limit · resets 3:40pm (UTC)"

# The Codex forms, so the agent route is exercised on BOTH built-in agents
# rather than on the one this work-item was filed from.
_CODEX_USAGE_LIMIT = (
    "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
    "to purchase more credits or try again at Aug 20th, 2026 3:33 AM."
)
_CODEX_STRUCTURED_TOKEN = "usageLimitExceeded"

# An ordinary adapter fault, which no measured table may claim however it was
# reached. Without it a table loosened into a broader match would satisfy every
# positive below while holding the whole account over a stream fault.
_ORDINARY_MESSAGE = "the agent answered `session/prompt` with an error: stream ended early"

_ITEM_ID = "bd-ib-structured-plrelease"
_RUN = "01M5PZY50N7J"
_FACTORY = "petri"
_NOW = "2026-10-24T15:26:47Z"

# The two proof nodes the measured runs died at.
_PROOF_NODES = ("proof_capture", "proof_verify")


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _structured(*, agent: str, model: str, effort: str | None = None) -> AcpCandidate:
    """One structured candidate, resolved through the real built-in catalogs."""
    entry: dict[str, object] = {"agent": agent, "model": model}
    if effort is not None:
        entry["effort"] = effort
    candidate = parse_structured_candidate(
        entry=entry, key="dispatcher.acp_nodes.probe", catalogs=builtin_catalogs()
    )
    assert isinstance(candidate, AcpCandidate), candidate
    return candidate


def _claude() -> AcpCandidate:
    return _structured(agent="claude-acp", model="claude-opus-5", effort="high")


def _codex() -> AcpCandidate:
    return _structured(agent="codex-acp", model="gpt-5.6-luna", effort="medium")


def _registry_seeded() -> AcpCandidate:
    """A catalog agent that is NOT one of the two whose diagnostics were measured."""
    return _structured(agent="opencode", model="anthropic/claude-opus-5")


def _manual() -> AcpCandidate:
    """An identified MANUAL-form candidate this build never rendered."""
    return AcpCandidate(
        adapter=AcpAdapter(command="acme-acp", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name="operator text",
            candidate_key="acme-primary",
            availability_key="acme-router",
        ),
    )


def _verdict(
    *, candidate: AcpCandidate, message: str | None = None, machine_code: str | None = None
) -> AcpAvailabilityFailure | AcpNonEligibleFailure:
    """One candidate attempt graded on exactly the evidence it was handed.

    `builtin=False` throughout, which is the whole point: every structured
    candidate carries that flag, because its identity derives from the catalogs
    and so is absent from the rendered-bytes table the flag is read from.
    """
    return classify_acp_failure(
        signal=AcpFailureSignal(
            original_identity="proof_verify|deterministic|acp turn failed",
            protocol_message=message,
            machine_code=machine_code,
        ),
        candidate=candidate,
        builtin=False,
    )


def _failure(*, cause: str) -> FabroFailureDetail:
    """The failure block a provider-limit terminal recorded, as the port reads it.

    The typed flag and its provider ride along exactly as
    `_fabro_port_records._failure_detail` sets them for this sentence, because
    the release's legacy arm reads them and the point of the assertion below is
    that the TYPED arm is what answers instead.
    """
    return FabroFailureDetail(
        cause=cause,
        category="deterministic",
        signature="proof_verify|deterministic|acp turn failed",
        provider_usage_limit=True,
        provider_usage_limit_provider=ANTHROPIC_DOMAIN,
    )


def _release(*, node_attempt: str) -> ProviderLimitRelease | None:
    candidate = _claude()
    return classified_release(
        failure=_failure(cause=_RECORDED_SESSION_LIMIT),
        rendered=RenderedCandidate(candidate=candidate, builtin=False),
        node_attempt=node_attempt,
        factory=_FACTORY,
        run_id=_RUN,
        recovery_source=f"the tree was preserved on refs/heads/needs-human/{_RUN}",
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return replace(
        WorkItem(
            id=_ITEM_ID,
            type="bug",
            status="active",
            title="A proof node whose account emptied mid-run",
            description="Implement the slice.",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee="fabro",
            depends_on=(),
            captured_at="2026-10-24T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria="The release leaves the item re-dispatchable.",
        )
    )


def _records(*, journal: JournalFile) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    ]


def _of_stage(*, journal: JournalFile, stage: str) -> list[dict[str, object]]:
    return [record for record in _records(journal=journal) if record.get("stage") == stage]


def test_the_measured_session_limit_classifies_for_a_structured_claude_candidate() -> None:
    """The recorded `session/prompt` error, and the bare sentence beside it.

    Both shapes the work-item names, each reaching the typed domain verdict a
    spent five-hour allowance owes: the hold is the ACCOUNT's, so it carries
    the availability key and no candidate key at all.
    """
    for message in (_RECORDED_SESSION_LIMIT, _BARE_SESSION_LIMIT):
        verdict = _verdict(candidate=_claude(), message=message)
        assert isinstance(verdict, AcpAvailabilityFailure), message
        assert verdict.cause == _QUOTA, message
        assert verdict.scope == DOMAIN_SCOPE, message
        assert verdict.source == _MESSAGE_SOURCE, message
        assert verdict.hold_key == ANTHROPIC_DOMAIN, message
        assert verdict.availability_key == ANTHROPIC_DOMAIN, message
        assert verdict.candidate_key is None, message


def test_the_structured_codex_candidate_reaches_its_own_measured_table() -> None:
    """The agent route serves BOTH built-in agents, on either transport.

    The structured token is asserted beside the sentence because the contract
    requires the mapping to survive an engine that kept only one of them, and a
    route that reached the table on one transport alone would satisfy half the
    clause.
    """
    sentence = _verdict(candidate=_codex(), message=_CODEX_USAGE_LIMIT)
    assert isinstance(sentence, AcpAvailabilityFailure)
    assert sentence.cause == _QUOTA
    assert sentence.source == _MESSAGE_SOURCE
    assert sentence.hold_key == CODEX_DOMAIN
    token = _verdict(candidate=_codex(), machine_code=_CODEX_STRUCTURED_TOKEN)
    assert isinstance(token, AcpAvailabilityFailure)
    assert token.cause == _QUOTA
    assert token.source == _MACHINE_CODE_SOURCE
    assert token.hold_key == CODEX_DOMAIN


def test_a_registry_seeded_agent_is_lent_no_measured_table() -> None:
    """CONTROL: the tables belong to the two agents that were MEASURED.

    A catalog declares agents whose diagnostics nobody in this fleet has
    observed, and classifying their failures against Claude's sentences would
    hold an account over a refusal their adapter may never emit. The failure
    keeps its own identity, which is the contract's own terminal rule.
    """
    verdict = _verdict(candidate=_registry_seeded(), message=_RECORDED_SESSION_LIMIT)
    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"
    assert verdict.original_identity == "proof_verify|deterministic|acp turn failed"
    assert effective_signatures(candidate=_registry_seeded(), builtin=False) == ()


def test_a_candidate_resolved_through_no_agent_keeps_the_legacy_posture() -> None:
    """CONTROL: the identified MANUAL-form route is byte-for-byte unchanged.

    An arbitrary adapter this build never rendered resolves through no agent
    and matches no built-in bytes, so it declares its own signatures or it
    classifies nothing -- the conservative posture every unexpired legacy
    provider record covers.
    """
    candidate = _manual()
    assert candidate.agent_id is None
    assert effective_signatures(candidate=candidate, builtin=False) == ()
    verdict = _verdict(candidate=candidate, message=_RECORDED_SESSION_LIMIT)
    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"


def test_an_ordinary_adapter_fault_still_matches_no_measured_table() -> None:
    """CONTROL: the agent route claims no diagnostic it was not measured on."""
    for candidate in (_claude(), _codex()):
        verdict = _verdict(candidate=candidate, message=_ORDINARY_MESSAGE)
        assert isinstance(verdict, AcpNonEligibleFailure), candidate.agent_id
        assert verdict.reason == "unmatched", candidate.agent_id


def test_each_measured_form_appears_once_however_many_routes_reach_it() -> None:
    """One table, two keys into it, and a candidate's own signatures first.

    A candidate can satisfy BOTH provenance routes at once -- an operator may
    override a structured entry's identity onto a built-in pair whose bytes
    this build renders -- and the effective answer is a registry claim readers
    count, so each measured form has to appear exactly once however many routes
    reached it.
    """
    configured = AcpAvailabilitySignature(
        source=_MESSAGE_SOURCE,
        cause=_QUOTA,
        scope=DOMAIN_SCOPE,
        all_literals=("an operator's own measurement",),
    )
    candidate = replace(_claude(), signatures=(configured,))
    agent_route = effective_signatures(candidate=candidate, builtin=False)
    both_routes = effective_signatures(candidate=candidate, builtin=True)
    assert agent_route[0] is configured
    assert both_routes == agent_route
    assert tuple(agent_route[1:]) == builtin_availability_signatures(
        availability_key=ANTHROPIC_DOMAIN
    )


def test_an_identity_less_candidate_is_given_no_table_on_either_route() -> None:
    """CONTROL: no identity means no domain, so no table, whatever ran.

    A typed hold needs an entitlement pair to be scoped by, and inventing one
    would mint an entitlement nobody declared -- so an identity-less adapter
    keeps the legacy blanket even when it resolved through a built-in agent.
    """
    candidate = replace(_claude(), identity=None)
    assert candidate.agent_id == "claude-acp"
    assert effective_signatures(candidate=candidate, builtin=True) == ()
    verdict = _verdict(candidate=candidate, message=_RECORDED_SESSION_LIMIT)
    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "identity_absent"


def test_the_release_for_either_proof_node_is_typed_rather_than_legacy_only() -> None:
    """The release names the spent allowance instead of a cause-text vendor.

    `classified_release` already released this failure through its LEGACY arm,
    because the recorded sentence sets the typed provider-usage-limit flag -- so
    the discriminating assertion is `matched`, the typed verdict that mints the
    domain hold the next dispatch is filtered by. A release carrying none mints
    no typed record at all.
    """
    for node in _PROOF_NODES:
        release = _release(node_attempt=node)
        assert release is not None, node
        matched = release.matched
        assert isinstance(matched, AcpAvailabilityFailure), node
        assert matched.cause == _QUOTA, node
        assert matched.scope == DOMAIN_SCOPE, node
        assert matched.hold_key == ANTHROPIC_DOMAIN, node
        assert release.legacy_provider is None, node
        executed = release.executed
        assert executed is not None, node
        assert executed.candidate_key == "claude-acp/anthropic/claude-opus-5", node
        assert release.release_key == f"{_FACTORY}:{_RUN}:{node}", node


def test_the_released_item_returns_to_ready_rather_than_resting_for_a_human(
    tmp_path: Path,
) -> None:
    """The work-item's headline claim, end to end from the measured failure.

    The disposition's own four ordered steps are asserted by
    `test_dispatcher_provider_limit_disposition`; what is asserted here is the
    COMPOSITION nothing else covers -- that a release built from this measured
    sentence reaches that disposition at all, mints the provider-limit hold,
    and leaves the item re-dispatchable rather than parked at `blocked` with
    `needs-human`.
    """
    append_work_item(path=_config(), item=_item())
    release = _release(node_attempt="proof_verify")
    assert release is not None
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    dispose_provider_limit_release(
        repo=_repo(tmp_path=tmp_path),
        item=_item(),
        outcome=DispatchOutcome(
            work_item_id=_ITEM_ID,
            status=PROVIDER_LIMIT_RELEASE_STATUS,
            stage="provider-limit-release",
            pr_number=None,
            merge_sha=None,
            detail="",
            fabro_run_id=_RUN,
            provider_limit_release=release,
        ),
        journal=journal,
        now_iso=_NOW,
        attempt_cost_of=lambda **_: {"stage": "acp-attempt-cost"},
    )

    holds = _of_stage(journal=journal, stage="acp-availability-observed")
    assert len(holds) == 1
    assert holds[0]["scope"] == DOMAIN_SCOPE
    assert holds[0]["hold_key"] == ANTHROPIC_DOMAIN
    releases = _of_stage(journal=journal, stage="provider-limit-release")
    assert len(releases) == 1
    assert releases[0]["release_key"] == f"{_FACTORY}:{_RUN}:proof_verify"
    released = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    assert released.status == "ready"
    assert released.assignee is None
    assert released.blocked_reason is None
    assert released.admission_policy == "auto"
