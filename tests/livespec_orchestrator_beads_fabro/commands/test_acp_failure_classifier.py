"""Classifying ONE ACP candidate failure against the closed signature grammar.

Binds the classifier half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" and the two Scenario 127
scenarios that govern it -- "The recorded removed-model diagnostic falls
back but a generic 400 does not" and "Non-eligible failures outrank
configured text overlap".

THE LOAD-BEARING CONTROLS ARE THE NEGATIVE ONES. Almost anything can be
made to classify a provider outage as a provider outage; the claim worth
testing is that a configured signature CANNOT claim an authentication
failure, an exit 127, a signal, a node timeout, a transport fault, a
compaction 404, a code/test failure, or a bare HTTP 400 -- and that two
signatures disagreeing about one diagnostic refuse rather than letting
declaration order decide. Each of those is asserted with the overlapping
literal actually present in the diagnostic, so a classifier that dropped
its guard would pass the positive tests and fail only here.

Everything is HERMETIC: no adapter is launched, no provider is reached,
and no journal is written -- the classifier returns a verdict and mints
nothing.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NEW_MODULES = (
    "_acp_failure_text",
    "_acp_failure_signals",
    "_acp_failure_matching",
    "_acp_builtin_signatures",
    "_acp_failure_classifier",
)

# The measured ChatGPT-account removal that motivated the whole contract
# (`SPECIFICATION/history/v107/proposed_changes/pr-node-default-claude-haiku.md`).
# It is an HTTP 400, which is exactly why it is the sharpest control: the
# status alone must stay non-eligible while this sentence must not.
_MEASURED_400 = (
    "stream error: HTTP 400 Bad Request: The requested model "
    "'gpt-5.4-mini' is not supported when using Codex with a ChatGPT account."
)
_GENERIC_400 = "stream error: HTTP 400 Bad Request: your request could not be processed"
_MEASURED_404 = "404 Not Found: The model 'gpt-5.5' does not exist or you do not have access to it"
_GENERIC_404 = "HTTP 404 Not Found"
_CODEX_USAGE_LIMIT = (
    "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
    "or try again at 2026-09-12T04:00:00Z"
)
_COMPACTION_404 = (
    "Error running remote compact task: 404 Not Found "
    "(POST https://api.openai.com/v1/responses/compact)"
)


def _modules() -> dict[str, Any]:
    """Import the slice's modules, proving each file exists first."""
    for name in _NEW_MODULES:
        assert (_COMMANDS / f"{name}.py").is_file(), f"{name}.py is not implemented yet"
    return {name: importlib.import_module(f"{_PACKAGE}.{name}") for name in _NEW_MODULES}


def _candidate(
    *,
    modules: dict[str, Any],
    signatures: tuple[Any, ...] = (),
    identity: Any | None = None,
) -> Any:
    """One candidate carrying the signatures under test."""
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    _ = modules
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=identity,
        signatures=signatures,
    )


def _identity(*, availability_key: str = "codex", candidate_key: str = "gpt-5-5") -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    return schema.AcpCandidateIdentity(
        display_name="Codex spark",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _signature(*, modules: dict[str, Any], **fields: Any) -> Any:
    return modules["_acp_failure_signals"] and importlib.import_module(
        f"{_PACKAGE}._acp_candidate_signatures"
    ).AcpAvailabilitySignature(**fields)


def test_normalized_text_is_case_folded_and_whitespace_collapsed() -> None:
    """The one comparison every table uses folds case and collapses runs."""
    text = _modules()["_acp_failure_text"]
    assert text.normalized(text="  HTTP\t400   Bad\nRequest ") == "http 400 bad request"
    assert text.conjunction_matches(literals=("bad", "request"), text="BAD  REQUEST")
    assert not text.conjunction_matches(literals=("bad", "absent"), text="BAD REQUEST")
    # An empty conjunction reports NO match rather than the vacuous truth
    # `all` would return; a signature matching every diagnostic is the one
    # outcome no caller wants.
    assert not text.conjunction_matches(literals=(), text="anything")
    assert text.matches_any_conjunction(conjunctions=(("nope",), ("bad",)), text="bad request")
    assert not text.matches_any_conjunction(conjunctions=(("nope",),), text="bad request")


def test_provider_evidence_and_declared_class_vocabulary() -> None:
    """Evidence is any readable field; an unmodelled declared class is still out."""
    signals = _modules()["_acp_failure_signals"]
    blank = signals.AcpFailureSignal(original_identity="x", protocol_message="   ")
    assert not blank.has_provider_evidence
    assert signals.AcpFailureSignal(
        original_identity="x", terminal_diagnostic="said something"
    ).has_provider_evidence
    assert signals.declared_non_eligible_reason(declared_class="non_convergence") == (
        "non_convergence"
    )
    # A class this module does not model is NOT relabelled as one it does:
    # that would put a fabricated identity on the record.
    assert signals.declared_non_eligible_reason(declared_class="wedged") == (
        "declared_non_eligible"
    )
    assert "declared_non_eligible" in signals.NON_ELIGIBLE_REASONS


def test_exit_status_and_marker_guards_name_their_own_class() -> None:
    """Exit statuses and measured markers each resolve to a closed reason."""
    signals = _modules()["_acp_failure_signals"]
    build = signals.AcpFailureSignal
    assert signals.non_eligible_reason(signal=build(original_identity="x", exit_code=127)) == (
        "command_not_found"
    )
    assert signals.non_eligible_reason(signal=build(original_identity="x", exit_code=126)) == (
        "command_not_found"
    )
    assert signals.non_eligible_reason(signal=build(original_identity="x", exit_code=137)) == (
        "signal_exit"
    )
    # 1-125 is the band a configured `exit_code` may refine, so it names no
    # class of its own.
    assert signals.non_eligible_reason(signal=build(original_identity="x", exit_code=3)) is None
    assert signals.non_eligible_reason(signal=build(original_identity="x")) is None
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", declared_class="code_test_review_or_tool_failure")
        )
        == "code_test_review_or_tool_failure"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", terminal_diagnostic=_COMPACTION_404)
        )
        == "remote_compaction_404"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", protocol_message="401 Unauthorized")
        )
        == "authentication"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(
                original_identity="x", protocol_message="Temporary failure in name resolution"
            )
        )
        == "unattributed_sandbox_or_transport"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", terminal_diagnostic="node deadline exceeded")
        )
        == "node_deadline"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", terminal_diagnostic="stall timeout after 1800s")
        )
        == "stall_expiry"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", terminal_diagnostic="operation was cancelled")
        )
        == "cancellation"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", terminal_diagnostic="invalid configuration: nope")
        )
        == "malformed_configuration"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", terminal_diagnostic="the loop did not converge")
        )
        == "non_convergence"
    )
    assert (
        signals.non_eligible_reason(
            signal=build(original_identity="x", terminal_diagnostic="a quiet unremarkable failure")
        )
        is None
    )


def test_signature_matching_reads_only_the_field_its_source_names() -> None:
    """The source selects one field; nothing searches the others."""
    modules = _modules()
    matching = modules["_acp_failure_matching"]
    signals = modules["_acp_failure_signals"]
    literal = _signature(
        modules=modules,
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("usage limit",),
    )
    # The identical text on the OTHER readable field does not satisfy a
    # `protocol.message` signature.
    assert not matching.signature_matches(
        signature=literal,
        signal=signals.AcpFailureSignal(
            original_identity="x", terminal_diagnostic="hit your usage limit"
        ),
    )
    assert matching.signature_matches(
        signature=literal,
        signal=signals.AcpFailureSignal(
            original_identity="x", protocol_message="hit your USAGE  LIMIT"
        ),
    )
    terminal = _signature(
        modules=modules,
        source="process.terminal_diagnostic",
        cause="model_unsupported",
        scope="candidate",
        all_literals=("requested model",),
    )
    assert matching.signature_matches(
        signature=terminal,
        signal=signals.AcpFailureSignal(original_identity="x", terminal_diagnostic=_MEASURED_400),
    )
    # An absent field can never match.
    assert not matching.signature_matches(
        signature=terminal, signal=signals.AcpFailureSignal(original_identity="x")
    )


def test_exit_code_refines_a_discriminator_and_never_stands_alone() -> None:
    """A declared exit code narrows a match; a differing status defeats it."""
    modules = _modules()
    matching = modules["_acp_failure_matching"]
    signals = modules["_acp_failure_signals"]
    refined = _signature(
        modules=modules,
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("usage limit",),
        exit_code=1,
    )
    assert matching.signature_matches(
        signature=refined,
        signal=signals.AcpFailureSignal(
            original_identity="x", protocol_message="usage limit", exit_code=1
        ),
    )
    assert not matching.signature_matches(
        signature=refined,
        signal=signals.AcpFailureSignal(
            original_identity="x", protocol_message="usage limit", exit_code=2
        ),
    )


def test_machine_code_matching_is_exact_and_tolerates_no_absent_code() -> None:
    """A machine code compares exactly; a code-less machine signature matches nothing."""
    modules = _modules()
    matching = modules["_acp_failure_matching"]
    signals = modules["_acp_failure_signals"]
    coded = _signature(
        modules=modules,
        source="protocol.machine_code",
        cause="rate_limit",
        scope="availability-domain",
        machine_code="provider.rate_limited",
    )
    assert matching.signature_matches(
        signature=coded,
        signal=signals.AcpFailureSignal(
            original_identity="x", machine_code=" provider.rate_limited "
        ),
    )
    assert not matching.signature_matches(
        signature=coded,
        signal=signals.AcpFailureSignal(original_identity="x", machine_code="provider.rate"),
    )
    # The PARSER forbids a machine-code source with no code; the dataclass
    # does not, so the defensive arm is asserted directly rather than left
    # to a configuration path that can never reach it.
    codeless = _signature(
        modules=modules,
        source="protocol.machine_code",
        cause="rate_limit",
        scope="availability-domain",
    )
    assert not matching.signature_matches(
        signature=codeless,
        signal=signals.AcpFailureSignal(original_identity="x", machine_code="anything"),
    )


def test_generic_status_detection_and_the_discriminator_rule() -> None:
    """A 400/404 is recognised, and status-only literals do not discriminate."""
    modules = _modules()
    matching = modules["_acp_failure_matching"]
    signals = modules["_acp_failure_signals"]
    build = signals.AcpFailureSignal
    assert (
        matching.generic_status_reason(
            signal=build(original_identity="x", protocol_message=_GENERIC_400)
        )
        == "generic_http_400"
    )
    assert (
        matching.generic_status_reason(
            signal=build(original_identity="x", terminal_diagnostic=_GENERIC_404)
        )
        == "generic_http_404"
    )
    assert matching.generic_status_reason(signal=build(original_identity="x")) is None
    assert (
        matching.generic_status_reason(
            signal=build(original_identity="x", protocol_message="a plain failure")
        )
        is None
    )
    status_only = _signature(
        modules=modules,
        source="protocol.message",
        cause="model_unavailable",
        scope="candidate",
        all_literals=("400", "bad request"),
    )
    assert not matching.signature_discriminates(signature=status_only)
    assert matching.signature_discriminates(
        signature=_signature(
            modules=modules,
            source="protocol.message",
            cause="model_unavailable",
            scope="candidate",
            all_literals=("bad request", "model retired"),
        )
    )
    assert matching.signature_discriminates(
        signature=_signature(
            modules=modules,
            source="protocol.machine_code",
            cause="model_unavailable",
            scope="candidate",
            machine_code="400",
        )
    )


def test_builtin_signature_table_is_domain_scoped_and_never_lent_out() -> None:
    """The measured tables belong to their own domains and to built-ins only."""
    modules = _modules()
    builtin = modules["_acp_builtin_signatures"]
    assert builtin.builtin_availability_signatures(availability_key="codex")
    assert builtin.builtin_availability_signatures(availability_key="anthropic")
    # A repository naming its own domain declares its own signatures; it is
    # never lent Codex's measurements.
    assert builtin.builtin_availability_signatures(availability_key="acme-router") == ()
    identity = _identity()
    configured = _signature(
        modules=modules,
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("mine",),
    )
    candidate = _candidate(modules=modules, signatures=(configured,), identity=identity)
    assert builtin.effective_signatures(candidate=candidate, builtin=False) == (configured,)
    combined = builtin.effective_signatures(candidate=candidate, builtin=True)
    assert combined[0] is configured
    assert len(combined) > 1
    # No identity means no domain to look a table up by.
    assert builtin.effective_signatures(
        candidate=_candidate(modules=modules, signatures=(configured,)), builtin=True
    ) == (configured,)


def test_measured_removed_model_400_is_eligible_but_a_generic_400_is_not() -> None:
    """Scenario 127: the model-naming sentence falls back; the bare status does not."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    candidate = _candidate(modules=modules, identity=_identity())
    verdict = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp-protocol-error",
            terminal_diagnostic=_MEASURED_400,
            turn_started=True,
        ),
        candidate=candidate,
        builtin=True,
    )
    assert isinstance(verdict, classifier.AcpAvailabilityFailure)
    assert verdict.cause == "model_unsupported"
    assert verdict.scope == classifier.CANDIDATE_SCOPE
    assert verdict.hold_key == "codex"
    assert verdict.candidate_key == "gpt-5-5"
    generic = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp-protocol-error",
            terminal_diagnostic=_GENERIC_400,
            turn_started=True,
        ),
        candidate=candidate,
        builtin=True,
    )
    assert isinstance(generic, classifier.AcpNonEligibleFailure)
    assert generic.reason == "generic_http_400"
    assert generic.original_identity == "acp-protocol-error"


def test_measured_404_and_usage_limit_carry_their_contract_scopes() -> None:
    """A removed model is candidate-scoped; a spent allowance is domain-scoped."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    candidate = _candidate(modules=modules, identity=_identity())
    removed = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp", terminal_diagnostic=_MEASURED_404, turn_started=True
        ),
        candidate=candidate,
        builtin=True,
    )
    assert isinstance(removed, classifier.AcpAvailabilityFailure)
    assert (removed.cause, removed.scope) == ("model_not_found", classifier.CANDIDATE_SCOPE)
    spent = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp", protocol_message=_CODEX_USAGE_LIMIT, turn_started=True
        ),
        candidate=candidate,
        builtin=True,
    )
    assert isinstance(spent, classifier.AcpAvailabilityFailure)
    assert (spent.cause, spent.scope) == ("quota", classifier.DOMAIN_SCOPE)
    # Domain scope holds the whole entitlement, so it names no candidate.
    assert spent.candidate_key is None
    assert spent.hold_key == "codex"
    bare = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp", terminal_diagnostic=_GENERIC_404, turn_started=True
        ),
        candidate=candidate,
        builtin=True,
    )
    assert isinstance(bare, classifier.AcpNonEligibleFailure)
    assert bare.reason == "generic_http_404"


def test_every_non_eligible_class_outranks_an_overlapping_configured_literal() -> None:
    """Scenario 127: the guard wins even when the signature's literal IS present."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    # The literal is chosen to appear in EVERY diagnostic below, so a
    # classifier that dropped its guard would return eligible for each.
    greedy = _signature(
        modules=modules,
        source="process.terminal_diagnostic",
        cause="provider_capacity",
        scope="availability-domain",
        all_literals=("failed",),
    )
    candidate = _candidate(modules=modules, signatures=(greedy,), identity=_identity())
    overlaps: tuple[tuple[str, dict[str, Any]], ...] = (
        ("authentication", {"terminal_diagnostic": "failed: 401 Unauthorized"}),
        ("command_not_found", {"terminal_diagnostic": "failed", "exit_code": 127}),
        ("signal_exit", {"terminal_diagnostic": "failed", "exit_code": 137}),
        ("node_deadline", {"terminal_diagnostic": "failed: node deadline exceeded"}),
        ("stall_expiry", {"terminal_diagnostic": "failed: stall timeout"}),
        ("cancellation", {"terminal_diagnostic": "failed: operation was cancelled"}),
        ("remote_compaction_404", {"terminal_diagnostic": f"failed {_COMPACTION_404}"}),
        (
            "malformed_configuration",
            {"terminal_diagnostic": "failed: malformed configuration"},
        ),
        (
            "unattributed_sandbox_or_transport",
            {"terminal_diagnostic": "failed: connection refused"},
        ),
        ("non_convergence", {"terminal_diagnostic": "failed: did not converge"}),
        (
            "code_test_review_or_tool_failure",
            {
                "terminal_diagnostic": "failed",
                "declared_class": "code_test_review_or_tool_failure",
            },
        ),
    )
    for reason, fields in overlaps:
        verdict = classifier.classify_acp_failure(
            signal=signals.AcpFailureSignal(
                original_identity="original", turn_started=True, **fields
            ),
            candidate=candidate,
        )
        assert isinstance(verdict, classifier.AcpNonEligibleFailure), reason
        assert verdict.reason == reason
        assert verdict.original_identity == "original"


def test_pre_turn_without_evidence_and_identity_absence_mint_nothing() -> None:
    """A silent pre-turn death is not provider evidence; a legacy adapter stays legacy."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    quiet = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(original_identity="spawn-failed"),
        candidate=_candidate(modules=modules, identity=_identity()),
    )
    assert isinstance(quiet, classifier.AcpNonEligibleFailure)
    assert quiet.reason == "pre_turn_without_provider_evidence"
    # A startup diagnostic IS provider evidence even before a turn: the
    # contract names the terminal adapter startup diagnostic as a source.
    speaking = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(original_identity="acp", terminal_diagnostic=_MEASURED_400),
        candidate=_candidate(modules=modules, identity=_identity()),
        builtin=True,
    )
    assert isinstance(speaking, classifier.AcpAvailabilityFailure)
    # An identity-less legacy adapter cannot be classified typed at all,
    # however unambiguous the diagnostic is.
    legacy = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp", terminal_diagnostic=_MEASURED_400, turn_started=True
        ),
        candidate=_candidate(modules=modules),
        builtin=True,
    )
    assert isinstance(legacy, classifier.AcpNonEligibleFailure)
    assert legacy.reason == "identity_absent"


def test_machine_codes_take_precedence_and_disagreement_is_ambiguous() -> None:
    """A structured code settles it; two disagreeing matches refuse instead."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    coded = _signature(
        modules=modules,
        source="protocol.machine_code",
        cause="rate_limit",
        scope="availability-domain",
        machine_code="provider.rate_limited",
    )
    texted = _signature(
        modules=modules,
        source="protocol.message",
        cause="model_not_entitled",
        scope="candidate",
        all_literals=("slow down",),
    )
    both = signals.AcpFailureSignal(
        original_identity="acp",
        machine_code="provider.rate_limited",
        protocol_message="please slow down",
        turn_started=True,
    )
    verdict = classifier.classify_acp_failure(
        signal=both,
        candidate=_candidate(modules=modules, signatures=(texted, coded), identity=_identity()),
    )
    assert isinstance(verdict, classifier.AcpAvailabilityFailure)
    assert verdict.cause == "rate_limit"
    # Two TEXT signatures disagreeing on disposition refuse rather than
    # letting declaration order decide.
    other = _signature(
        modules=modules,
        source="protocol.message",
        cause="provider_capacity",
        scope="availability-domain",
        all_literals=("slow",),
    )
    ambiguous = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp", protocol_message="please slow down", turn_started=True
        ),
        candidate=_candidate(modules=modules, signatures=(texted, other), identity=_identity()),
    )
    assert isinstance(ambiguous, classifier.AcpNonEligibleFailure)
    assert ambiguous.reason == "ambiguous"
    # Two MACHINE-CODE signatures disagreeing are equally ambiguous: the
    # precedence tier is a filter, not a tie-break.
    rival = _signature(
        modules=modules,
        source="protocol.machine_code",
        cause="quota",
        scope="availability-domain",
        machine_code="provider.rate_limited",
    )
    codes = classifier.classify_acp_failure(
        signal=both,
        candidate=_candidate(modules=modules, signatures=(coded, rival), identity=_identity()),
    )
    assert isinstance(codes, classifier.AcpNonEligibleFailure)
    assert codes.reason == "ambiguous"


def test_redundant_duplicate_dispositions_are_not_ambiguous() -> None:
    """Two signatures that agree are redundant, not a conflict."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    first = _signature(
        modules=modules,
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("limit",),
    )
    second = _signature(
        modules=modules,
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("limit reached",),
    )
    verdict = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp", protocol_message="limit reached", turn_started=True
        ),
        candidate=_candidate(modules=modules, signatures=(first, second), identity=_identity()),
    )
    assert isinstance(verdict, classifier.AcpAvailabilityFailure)
    assert verdict.cause == "quota"


def test_declared_domain_override_supplies_the_hold_key() -> None:
    """A domain signature's `hold_key` override is what the hold is scoped by."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    override = _signature(
        modules=modules,
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("shared pool",),
        hold_key="shared-router-pool",
    )
    verdict = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp", protocol_message="shared pool exhausted", turn_started=True
        ),
        candidate=_candidate(modules=modules, signatures=(override,), identity=_identity()),
    )
    assert isinstance(verdict, classifier.AcpAvailabilityFailure)
    assert verdict.hold_key == "shared-router-pool"
    assert verdict.availability_key == "codex"


def test_an_unmatched_failure_keeps_its_own_identity() -> None:
    """No signature matched and no status marker: the failure stays what it was."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    verdict = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp-protocol-error",
            protocol_message="an unremarkable provider hiccup",
            turn_started=True,
        ),
        candidate=_candidate(modules=modules, identity=_identity()),
    )
    assert isinstance(verdict, classifier.AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"
    assert verdict.original_identity == "acp-protocol-error"


def test_a_status_only_signature_cannot_rescue_a_generic_400() -> None:
    """A signature naming nothing but the status is not an exact discriminator."""
    modules = _modules()
    classifier = modules["_acp_failure_classifier"]
    signals = modules["_acp_failure_signals"]
    status_only = _signature(
        modules=modules,
        source="protocol.message",
        cause="model_unavailable",
        scope="candidate",
        all_literals=("400", "bad request"),
    )
    verdict = classifier.classify_acp_failure(
        signal=signals.AcpFailureSignal(
            original_identity="acp", protocol_message=_GENERIC_400, turn_started=True
        ),
        candidate=_candidate(modules=modules, signatures=(status_only,), identity=_identity()),
    )
    assert isinstance(verdict, classifier.AcpNonEligibleFailure)
    assert verdict.reason == "generic_http_400"
