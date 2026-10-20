"""A succeeded ACP turn can be the provider-limit attempt a terminal releases."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / ("livespec_orchestrator_beads_fabro")
    / "commands"
)
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify"
_REFUSAL = "Selected model is at capacity. Please try a different model."


def _rendered() -> RenderedCandidate:
    """The resolved built-in Codex candidate which actually ran the review."""
    signatures = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures"
    )
    identity = AcpCandidateIdentity(
        display_name="Codex ACP fallback",
        candidate_key="gpt-5.6-terra",
        availability_key="codex",
    )
    return RenderedCandidate(
        candidate=AcpCandidate(
            adapter=AcpAdapter(command="codex-acp", args=(), env={}),
            identity=identity,
            signatures=signatures.builtin_availability_signatures(availability_key="codex"),
        ),
        builtin=True,
    )


def test_a_succeeded_turn_capacity_refusal_mints_a_candidate_scoped_release() -> None:
    """The selected Codex candidate is released by its final recorded output."""
    assert (_COMMANDS / "_dispatcher_provider_limit_classify.py").is_file()
    module: Any = importlib.import_module(_MODULE)
    assert hasattr(module, "ProviderLimitAttempt")

    release = module.classified_release(
        attempt=module.ProviderLimitAttempt(
            signal=AcpFailureSignal(
                original_identity="review|succeeded|unmatched",
                turn_final_output="The review began." + _REFUSAL,
                turn_succeeded=True,
            )
        ),
        rendered=_rendered(),
        node_attempt="review",
        factory="gmktec",
        run_id="01M5C0FBAE8FVZK15XN9WHVM6H",
        recovery_source="refs/heads/needs-human/01M5C0FBAE8FVZK15XN9WHVM6H",
    )

    assert release is not None
    assert release.source == "turn.final_output"
    assert release.matched is not None
    assert release.matched.cause == "provider_capacity"
    assert release.matched.scope == "candidate"
