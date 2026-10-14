"""A BUILT-IN Codex adapter routes to Codex, though its key is not the triple.

`bd-ib-meejjz`. The routing decision reads each resolved candidate's
`candidate_key` for the agent that leads it, because
`_acp_structured_identity` derives that key as the canonical
`<agent>/<provider>/<model>` triple. A BUILT-IN candidate is identified a
different way: `_acp_builtin_candidates` keys it on a DIGEST of the adapter's
exact rendered bytes, `builtin-<domain>-<digest>`, precisely so that nothing
infers an identity from command text. The un-pinned Codex opt-out postures are
built-ins, so a dispatch resolving to one renders a key that names no agent at
all.

WHY THAT IS A HOLE RATHER THAN A GAP IN COVERAGE. It fails in the UNSAFE
direction. A dispatch that genuinely launches the Codex adapter would be read
as routing no node to Codex, so its credential would go ungraded, unprojected
and unenforced -- which is the one outcome scoping the gate must not produce,
and the direct negation of "a dispatch that routes at least one node to Codex
... grades, projects and enforces the Codex credential exactly as it did
before".

THE KEY IS NOT HAND-SPELLED HERE. It comes from `builtin_acp_identities`
itself, so the case cannot pass against a key shape this build stopped
producing -- the same reason that module digests the bytes instead of parsing
a model name.

AND PROVENANCE IS READ FROM THE CALLER'S FACT, NOT FROM THE SPELLING. The
control below is an operator who chose `codex` as their own
`availability_key` on a candidate this build did not render: that is the
"explicitly identified candidates MUST NOT be broadened to unrelated
identities" case `_acp_dispatch_coverage` records, and reading `builtin` off
the key text rather than off the rendered-bytes table is exactly how a build
would get it wrong.
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


def _builtin_identity(*, domain: str) -> Any:
    """The identity THIS BUILD renders for `domain`'s built-in ACP adapter.

    Taken from the production table rather than spelled here, so the case reads
    the key shape the build actually produces. The workflow inputs handed in are
    the Anthropic side's source, which is what makes both domains resolvable
    from one call.
    """
    builtins = importlib.import_module(f"{_PACKAGE}._acp_builtin_candidates")
    identities = builtins.builtin_acp_identities(
        workflow_inputs={"implement_adapter": "claude-code-acp"}
    )
    return next(identity for identity in identities.values() if identity.availability_key == domain)


def _rendered(*, identity: Any, builtin: bool) -> Any:
    """One rendered candidate carrying `identity` and its provenance fact."""
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    coverage = importlib.import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    return coverage.RenderedCandidate(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
            identity=identity,
        ),
        builtin=builtin,
    )


def test_a_builtin_codex_candidate_routes_to_codex_despite_its_digest_key() -> None:
    """The un-pinned Codex opt-out keeps its credential graded and enforced."""
    routing = _routing()
    builtins = importlib.import_module(f"{_PACKAGE}._acp_builtin_candidates")
    codex = _builtin_identity(domain=builtins.CODEX_DOMAIN)

    # The precondition that makes this case worth writing: the built-in key
    # genuinely does NOT name the agent, so a reader of the triple alone misses
    # it.
    catalog = importlib.import_module(f"{_PACKAGE}._acp_agent_catalog")
    assert not codex.candidate_key.startswith(catalog.CODEX_AGENT_ID)

    decision = routing.codex_routing_for_candidates(
        candidates=(
            _rendered(identity=_builtin_identity(domain=builtins.ANTHROPIC_DOMAIN), builtin=True),
            _rendered(identity=codex, builtin=True),
        )
    )

    assert decision.routes_codex is True
    assert codex.candidate_key in decision.detail


def test_a_builtin_anthropic_dispatch_still_routes_no_node_to_codex() -> None:
    """The CONTROL against recognising every built-in as a Codex launch."""
    routing = _routing()
    builtins = importlib.import_module(f"{_PACKAGE}._acp_builtin_candidates")

    decision = routing.codex_routing_for_candidates(
        candidates=(
            _rendered(identity=_builtin_identity(domain=builtins.ANTHROPIC_DOMAIN), builtin=True),
        )
    )

    assert decision.routes_codex is False


def test_an_operator_key_spelling_the_codex_domain_is_not_a_builtin_codex_launch() -> None:
    """Provenance is the caller's fact; a vendor word in a key is not a claim.

    The candidate below carries the built-in Codex identity VALUES while
    declaring, through `builtin=False`, that this build did not render its
    adapter. That is an operator's own candidate, and broadening the Codex
    routing onto it would re-impose the gate on a dispatch launching something
    else entirely -- the mirror of the hole the first case closes, in the
    over-strict direction.
    """
    routing = _routing()
    builtins = importlib.import_module(f"{_PACKAGE}._acp_builtin_candidates")

    decision = routing.codex_routing_for_candidates(
        candidates=(
            _rendered(identity=_builtin_identity(domain=builtins.CODEX_DOMAIN), builtin=False),
        )
    )

    assert decision.routes_codex is False
