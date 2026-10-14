"""Whether ONE dispatch routes any node to Codex (`bd-ib-meejjz`).

The host Codex credential is graded before the claim, graded and projected
after it, and enforced in the sandbox on every adapter launch. All three
applied to EVERY dispatch, including one whose every resolved ACP node runs
`claude-acp` -- so dispatches were refused as a Codex token aged although no
run would have used it, and every node timeout was capped by a credential
nothing consumed. This module is the predicate that decides which dispatches
owe any of that, and it is the ONE place the decision is made.

THE THREE FAIL-CLOSED ARMS ARE THE POINT, and each is asserted here because
each is a direction an almost-correct predicate gets backwards. A dispatch
whose candidates CANNOT BE RESOLVED has not been observed at all, so it keeps
today's protection rather than earning an exemption from an absent
measurement. An IDENTITY-LESS candidate is the conservative legacy posture --
an arbitrary adapter this build never rendered -- so nothing about it says
which provider it spends. And a candidate naming the Codex agent routes Codex
however many Claude candidates stand beside it: ANY, never EVERY, because one
Codex launch is one credential use.

THE NEGATIVE ARM IS THE ONE THE WORK-ITEM EXISTS FOR, and it is asserted over
the shape this repository actually dispatches: eight resolved candidates, all
`claude-acp/anthropic/...`. A predicate that answered `True` there would leave
every surface exactly as it was and the whole change inert, while every other
assertion in this file still passed.

Everything is PURE: candidates are built in memory, no file is read, no
configuration is resolved and no adapter is launched.
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

# The two keys this repository's own resolution renders today, measured
# 2026-10-14 through `resolve_dispatch_candidates`: eight candidates, every one
# of them `claude-acp/anthropic/...`.
_CLAUDE_SONNET_KEY = "claude-acp/anthropic/claude-sonnet-4-6"
_CLAUDE_OPUS_KEY = "claude-acp/anthropic/claude-opus-5"

# The canonical triple a STRUCTURED Codex entry derives, which is the only
# spelling a pinned Codex adapter reaches a dispatch under.
_CODEX_PINNED_KEY = "codex-acp/openai/gpt-5.5"

# The key the BUILT-IN un-pinned Codex bases carry. It is a digest of the
# rendered bytes rather than a parsed name, so it does NOT begin with the agent
# id -- which is exactly why the account domain has to be read too.
_BUILTIN_CODEX_KEY = "builtin-codex-0000000000000000"


def _routing() -> Any:
    """Import the module under test, proving its file exists first."""
    assert (_COMMANDS / f"{_MODULE}.py").is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _candidate(*, key: str | None, domain: str = "anthropic") -> Any:
    """One rendered candidate, with `key=None` for the identity-less posture."""
    coverage = importlib.import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    identity = (
        None
        if key is None
        else schema.AcpCandidateIdentity(
            display_name="candidate", candidate_key=key, availability_key=domain
        )
    )
    return coverage.RenderedCandidate(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
            identity=identity,
        ),
        builtin=key is not None and key.startswith("builtin-"),
    )


def test_an_all_claude_resolution_routes_no_node_to_codex() -> None:
    """The shape this repository dispatches: no Codex routing, and it says why.

    The detail is asserted because the gate journals it as the reason it was not
    applied, and a record saying only "not applied" cannot be audited against
    the routing that decided it.
    """
    routing = _routing()

    decided = routing.codex_routing_for(
        candidates=(
            _candidate(key=_CLAUDE_SONNET_KEY),
            _candidate(key=_CLAUDE_OPUS_KEY),
        )
    )

    assert decided.routes_codex is False
    assert _CLAUDE_SONNET_KEY in decided.detail
    assert _CLAUDE_OPUS_KEY in decided.detail


def test_one_codex_candidate_among_claude_candidates_routes_codex() -> None:
    """ANY, never EVERY: one Codex launch is one credential use.

    The discriminator against the case above is a single added candidate, so a
    predicate that answered on the majority -- or on the first node in order --
    would pass that test and fail this one.
    """
    routing = _routing()

    decided = routing.codex_routing_for(
        candidates=(
            _candidate(key=_CLAUDE_OPUS_KEY),
            _candidate(key=_CODEX_PINNED_KEY, domain="codex"),
            _candidate(key=_CLAUDE_SONNET_KEY),
        )
    )

    assert decided.routes_codex is True
    assert _CODEX_PINNED_KEY in decided.detail


def test_a_builtin_un_pinned_codex_candidate_routes_codex() -> None:
    """The built-in Codex bases, whose key names a DIGEST rather than the agent.

    `_acp_builtin_candidates` keys a built-in identity on a digest of its own
    rendered bytes precisely so that nothing infers an identity from command
    text, so `builtin-codex-<digest>` does not begin with `codex-acp`. What it
    does carry is the Codex agent's own account domain as its availability key,
    and reading that is what keeps the un-pinned opt-out postures protected. A
    predicate reading the candidate key alone reports this dispatch as
    all-Claude and launches it with no graded credential and no use deadline.
    """
    routing = _routing()

    decided = routing.codex_routing_for(
        candidates=(
            _candidate(key=_CLAUDE_OPUS_KEY),
            _candidate(key=_BUILTIN_CODEX_KEY, domain="codex"),
        )
    )

    assert decided.routes_codex is True
    assert _BUILTIN_CODEX_KEY in decided.detail


def test_an_identity_less_candidate_routes_codex() -> None:
    """The legacy posture says nothing about which provider it spends.

    An identity-less candidate is an arbitrary adapter this build never
    rendered, so there is no key to read and no provenance to consult. Treating
    the absence of an identity as the absence of Codex is the fail-OPEN
    direction.
    """
    routing = _routing()

    decided = routing.codex_routing_for(
        candidates=(_candidate(key=_CLAUDE_OPUS_KEY), _candidate(key=None))
    )

    assert decided.routes_codex is True
    assert "identity" in decided.detail


def test_an_unresolvable_resolution_routes_codex_and_is_the_unmeasured_default() -> None:
    """`None` is the absence of a measurement, and the module's own default.

    `resolve_dispatch_candidates` returns `None` when the resolution could not
    be READ, which supports no verdict about candidates. The same value is
    published as `UNMEASURED_CODEX_ROUTING` so a caller wiring no routing at all
    inherits the protected answer rather than the exempt one.
    """
    routing = _routing()

    decided = routing.codex_routing_for(candidates=None)

    assert decided.routes_codex is True
    assert routing.UNMEASURED_CODEX_ROUTING.routes_codex is True
    assert routing.UNMEASURED_CODEX_ROUTING.detail == decided.detail


def test_an_empty_resolution_routes_codex() -> None:
    """An empty candidate set is unreadable rather than empty.

    `resolve_dispatch_candidates` never returns one -- it answers `None`
    instead -- but a caller assembling candidates another way can, and an empty
    set covers nothing, which would read as a confident "no Codex" about a
    dispatch whose adapters were never observed.
    """
    routing = _routing()

    decided = routing.codex_routing_for(candidates=())

    assert decided.routes_codex is True
