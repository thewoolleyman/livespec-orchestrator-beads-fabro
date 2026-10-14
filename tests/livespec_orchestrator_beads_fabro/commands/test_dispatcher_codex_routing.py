"""WHETHER one dispatch routes ANY node to the Codex agent (`bd-ib-meejjz`).

The host Codex credential is graded before the claim, graded and projected
again after it, and enforced in the sandbox on every adapter launch. Each of
those three applies whether or not the dispatch would ever reach a Codex
adapter, and since `b7d80ca7` every factory node in this repository resolves to
`claude-acp`. This module answers the one question that scopes all three, so
the answer cannot differ between them.

THE THREE FAIL-CLOSED ARMS CARRY THE WEIGHT, because each is a direction an
almost-correct reading gets backwards:

- An UNREADABLE resolution is not an answer about candidates. `None` says the
  dispatch's adapters were never observed, so the domains it spends are real
  but invisible; reporting "no Codex here" for it would retire the protection
  on exactly the dispatches nothing can see.
- An IDENTITY-LESS candidate is the conservative legacy posture: an arbitrary
  adapter whose command this build did not render and whose agent therefore
  cannot be read off a key. It may well be a Codex adapter.
- An EMPTY resolution cannot arrive here as an answer at all --
  `resolve_dispatch_candidates` renders it as `None` -- but a reader that
  accepted one would report "routes no node to Codex" for a dispatch that
  overrides no adapter and runs whatever the graph itself bakes in.

The POSITIVE arm is asserted on the DERIVED key shape rather than on a
hand-spelled string: `_acp_structured_identity` derives `candidate_key` as
`<agent>/<provider>/<model>`, so a candidate routed to Codex is recognised by
the agent id leading that triple. An operator may override the key per field,
and an override that no longer names the agent is deliberately NOT matched --
the same reasoning `_acp_dispatch_coverage` records for `builtin`, one level
on: a key is read for what it says, never inferred from the vendor word
somebody happened to spell inside it.

Everything here is PURE: candidates are built in memory, no file is read and
no adapter is launched.
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
_MODULE = "_dispatcher_codex_routing"


def _routing() -> Any:
    """Import the module under test, proving its file exists first."""
    assert (_COMMANDS / f"{_MODULE}.py").is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _rendered(*, candidate_key: str | None) -> Any:
    """One rendered candidate, identified by `candidate_key` or identity-less."""
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    coverage = importlib.import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    identity = (
        None
        if candidate_key is None
        else schema.AcpCandidateIdentity(
            display_name="candidate",
            candidate_key=candidate_key,
            availability_key="account.example",
        )
    )
    return coverage.RenderedCandidate(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
            identity=identity,
        ),
        builtin=True,
    )


def test_a_candidate_key_naming_the_codex_agent_routes_to_codex() -> None:
    """One `codex-acp/...` key among all-Claude siblings routes the dispatch."""
    routing = _routing()
    catalog = importlib.import_module(f"{_PACKAGE}._acp_agent_catalog")
    decision = routing.codex_routing_for_candidates(
        candidates=(
            _rendered(candidate_key="claude-acp/anthropic/claude-opus-4-5"),
            _rendered(candidate_key=f"{catalog.CODEX_AGENT_ID}/openai/gpt-5.1"),
        )
    )
    assert decision.routes_codex is True
    assert f"{catalog.CODEX_AGENT_ID}/openai/gpt-5.1" in decision.detail


def test_an_identity_less_candidate_routes_to_codex() -> None:
    """The conservative legacy posture keeps today's protection, fail-closed."""
    decision = _routing().codex_routing_for_candidates(
        candidates=(
            _rendered(candidate_key="claude-acp/anthropic/claude-opus-4-5"),
            _rendered(candidate_key=None),
        )
    )
    assert decision.routes_codex is True
    assert "identity" in decision.detail


def test_unresolvable_candidates_route_to_codex() -> None:
    """An unobservable dispatch keeps the protection it had before this change."""
    decision = _routing().codex_routing_for_candidates(candidates=None)
    assert decision.routes_codex is True
    assert "could not be resolved" in decision.detail


def test_wholly_claude_candidates_route_no_node_to_codex() -> None:
    """The case this whole work-item exists for: every node on `claude-acp`."""
    decision = _routing().codex_routing_for_candidates(
        candidates=(
            _rendered(candidate_key="claude-acp/anthropic/claude-opus-4-5"),
            _rendered(candidate_key="claude-acp/anthropic/claude-sonnet-4-5"),
        )
    )
    assert decision.routes_codex is False
    assert "claude-acp/anthropic/claude-opus-4-5" in decision.detail


def test_a_key_merely_containing_the_agent_word_routes_no_node_to_codex() -> None:
    """A key is read for what it NAMES, never for a vendor word spelled inside it.

    The mirror of `_acp_dispatch_coverage`'s `builtin` rule: an operator who put
    the agent's own word in the middle of a key has not declared a Codex launch,
    and broadening onto it would re-impose the gate on a dispatch that renders no
    Codex adapter at all.
    """
    decision = _routing().codex_routing_for_candidates(
        candidates=(_rendered(candidate_key="claude-acp/anthropic/codex-acp-lookalike"),)
    )
    assert decision.routes_codex is False
