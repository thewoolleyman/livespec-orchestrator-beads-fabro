"""The `config_options` capability gate applies to the SELECTED candidate alone.

Binds the sentence `SPECIFICATION/contracts.md` ends its in-protocol model and
effort selection clause with: "A dispatch with no selected protocol-configured
candidate MUST NOT require this capability, and an unselected fallback's options
never gate a dispatch." The fallback-priority clause says the same thing from the
other side -- the remaining gate "applies only to a dispatch whose selected
candidates use it".

WHY AN UNSELECTED FALLBACK MUST NOT GATE. Under spec v127 the Dispatcher renders
exactly ONE candidate per node and the engine never learns the others exist, so a
fallback's `config_options` is a request no engine is ever asked to honour on
this dispatch. Refusing on it refuses a dispatch that would have run correctly,
and the refusal names a capability the running configuration does not need --
which reads as a factory that needs a deployment rather than as a gate pointed at
the wrong candidate. The cost is paid by exactly the configuration this feature
exists to encourage: declaring a protocol-configured fallback behind a healthy
environment-mechanism primary would make every dispatch of that node refuse until
the factory was upgraded for a candidate it was not going to run.

THE THREE CASES ARE ONE CLAIM AND NONE IS REDUNDANT. A gate reading the PRIMARY
alone satisfies the first two and fails the third; a gate reading the WHOLE CHAIN
satisfies the first and third and fails the second; only a gate reading the
SELECTION satisfies all three. The middle case asserts on the reader's CALL COUNT
rather than on the returned value, because a gate that consulted the capability
list and happened to find the capability would return `None` exactly as a gate
that correctly owed no read does.
"""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_CAPABILITY = "acp.candidate_config_options.v1"
_FACTORY = "hp"
_NODE = "implement"

_HELD_DOMAIN = "helddomain"
_HELD_KEY = "claudeopus5"
_OPTIONS_DOMAIN = "glmdomain"
_OPTIONS_KEY = "glm52"

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "npx -y claude-acp"
review_adapter = "npx -y claude-acp"

[run.environment]
id = "livespec-ci"
"""

_WORKFLOW_GRAPH = """digraph implement {
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="{{ inputs.implement_adapter }}", timeout="60s"]
    review    [backend="acp", acp.command="{{ inputs.review_adapter }}", timeout="60s"]
    start -> implement
    implement -> review
    review -> exit
}
"""


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


class _Reader:
    """A recording capability reader, so "never consulted" is observable."""

    def __init__(self, *, capabilities: frozenset[str] | None) -> None:
        self.capabilities = capabilities
        self.calls = 0

    def __call__(self) -> frozenset[str] | None:
        self.calls += 1
        return self.capabilities


def _options_candidate() -> dict[str, Any]:
    """A PROTOCOL-mechanism agent, which is what carries `config_options`.

    Its identity fields are overridden per-field so the hold below can name a
    domain without depending on whatever key the catalog derives.
    """
    return {
        "agent": "glm-acp-agent",
        "model": "glm-5.2",
        "availability_key": _OPTIONS_DOMAIN,
        "candidate_key": _OPTIONS_KEY,
    }


def _env_candidate() -> dict[str, Any]:
    """An ENVIRONMENT-mechanism agent: the model rides the adapter, no options."""
    return {
        "agent": "claude-acp",
        "model": "claude-opus-5",
        "effort": "high",
        "availability_key": _HELD_DOMAIN,
        "candidate_key": _HELD_KEY,
    }


def _manual_review() -> dict[str, Any]:
    """`review` as a plain manual adapter, so only `implement` is under test."""
    return {
        "display_name": "Review adapter",
        "candidate_key": "reviewmodel",
        "availability_key": "reviewdomain",
        "command": "review-acp",
        "args": ["--stdio"],
    }


def _repo(*, tmp_path: Path, node: dict[str, Any]) -> Path:
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_WORKFLOW_GRAPH, encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Operator",
                    "operator_email": "operator@example.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"acp_nodes": {_NODE: node, "review": _manual_review()}}
                },
            }
        ),
        encoding="utf-8",
    )
    return repo


def _domain_hold(*, hold_key: str) -> Any:
    records = _module(name="_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="acp-obs-0123456789abcdef",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at="2026-10-16T10:00:00Z",
        expires_at="2026-10-16T22:00:00Z",
    )


def _selection(*, repo: Path, holds: tuple[Any, ...]) -> Any:
    """This dispatch's per-node selection, through the real resolution path."""
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")
    ledger_module = _module(name="_acp_hold_ledger")
    preflight = _module(name="_acp_candidate_preflight")
    verdicts = _module(name="_acp_preflight_verdict")
    selection = _module(name="_acp_node_selection")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = sources.repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, graph_text, builtin_pairs = resolved
    verdict = verdicts.build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger_module.AcpHoldLedger(
            holds=holds, unobservable=(), observation_ids=frozenset()
        ),
        inputs=preflight.PreflightInputs(holds=holds, builtin_pairs=builtin_pairs),
    )
    selected = selection.select_acp_candidates(chains=chains, verdict=verdict)
    assert not isinstance(selected, str), selected
    return selected


def _assert_gate_takes_the_selection() -> None:
    """Prove the gate is asked about the SELECTION before reaching for it.

    Run FIRST in every case so the Red fails on a genuine assertion rather than
    on a `TypeError` from an unexpected keyword. The parameter it reads is the
    whole claim of this slice: a gate handed the declared CHAINS cannot tell a
    selected candidate from one the dispatch passed over, so the input it
    accepts is what decides whether the clause can be honoured at all.
    """
    gate = _module(name="_acp_capability_gate")
    assert "acp_capability_refusal" in gate.__all__, sorted(gate.__all__)
    parameters = inspect.signature(gate.acp_capability_refusal).parameters
    assert "selected" in parameters, sorted(parameters)
    # The whole-chain input is GONE rather than merely joined by the selection:
    # a gate still offered the chains is one a caller can still gate the wrong
    # candidate through.
    assert "chains" not in parameters, sorted(parameters)


def _refusal(*, repo: Path, holds: tuple[Any, ...], reader: _Reader) -> str | None:
    """One gate call, through the module's DECLARED public surface."""
    _assert_gate_takes_the_selection()
    gate = _module(name="_acp_capability_gate")
    return gate.acp_capability_refusal(
        selected=_selection(repo=repo, holds=holds),
        factory_name=_FACTORY,
        capabilities=reader,
    )


def test_a_selected_candidate_carrying_options_refuses_without_the_capability(
    tmp_path: Path,
) -> None:
    """The POSITIVE CONTROL: position zero asks for options and is gated."""
    repo = _repo(tmp_path=tmp_path, node=_options_candidate())
    reader = _Reader(capabilities=frozenset())

    refusal = _refusal(repo=repo, holds=(), reader=reader)

    assert refusal is not None
    assert _CAPABILITY in refusal
    assert _NODE in refusal


def test_an_unselected_fallbacks_options_never_gate_the_dispatch(tmp_path: Path) -> None:
    """The selected primary takes its model in the environment, so nothing is owed.

    The gate is not merely expected to admit -- it must not ASK. A dispatch whose
    rendered candidate makes no in-protocol request owes no round trip, and a
    gate that read the list and found the capability would return `None` while
    still refusing this very configuration against a factory that lacked it.
    """
    repo = _repo(
        tmp_path=tmp_path,
        node={**_env_candidate(), "fallbacks": [_options_candidate()]},
    )
    reader = _Reader(capabilities=None)

    refusal = _refusal(repo=repo, holds=(), reader=reader)

    assert refusal is None
    assert reader.calls == 0


def test_a_selected_fallback_carrying_options_is_gated_like_any_selection(
    tmp_path: Path,
) -> None:
    """A held primary moves the selection ONTO the options-carrying candidate.

    This is what keeps the gate pointed at the SELECTION rather than at position
    zero: the same chain as the case above, graded with the primary held, now
    renders the protocol-configured candidate and genuinely owes the capability.
    """
    repo = _repo(
        tmp_path=tmp_path,
        node={**_env_candidate(), "fallbacks": [_options_candidate()]},
    )
    reader = _Reader(capabilities=frozenset())

    refusal = _refusal(repo=repo, holds=(_domain_hold(hold_key=_HELD_DOMAIN),), reader=reader)

    assert refusal is not None
    assert _CAPABILITY in refusal
    assert reader.calls == 1
