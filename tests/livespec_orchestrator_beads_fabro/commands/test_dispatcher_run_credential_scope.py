"""Which ACP nodes the run-scoped provisioned credential reaches.

The review node is the case acceptance criterion 5 names, so it is asserted through the
adapter the Dispatcher actually resolves for it rather than against a hand-written env
mapping — a mapping written by the test could agree with a predicate that is wrong about
what a resolved adapter looks like.

The narrowness of the name set is asserted directly, because a false positive here is the
expensive direction: it would conclude a node opted OUT of the run credential when it
asked for nothing at all.

THE MODULE IS IMPORTED INSIDE EACH TEST BODY, NOT AT THE TOP. A top-level import of a
module that does not exist yet makes the first run die at COLLECTION, which proves only
that the module is missing; the existence assertion below fails as a genuine assertion
instead, and the parametrized cases name the three env variables LITERALLY so they can be
collected before the module exists. `test_the_capability_name_set_is_exactly_these_three`
is what keeps those literals from drifting away from the constant they mirror.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_CLAUDE_ACP = "npx -y @agentclientprotocol/claude-agent-acp"
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_credential_scope"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_run_credential_scope.py"
)

# Mirrored literally so the parametrized cases can be collected before the module exists;
# `test_the_capability_name_set_is_exactly_these_three` binds them to the real constant.
_CAPABILITY_ENV_NAMES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")


def _scope() -> Any:
    return importlib.import_module(_MODULE_NAME)


def test_the_run_credential_scope_module_declares_its_two_public_predicates() -> None:
    """The seam exists and exposes exactly what criterion 5 is asserted through."""
    assert _MODULE_PATH.is_file()

    scope = _scope()

    assert callable(scope.run_scoped_credential_applies)
    assert callable(scope.requested_capability_env_name)


def test_the_capability_name_set_is_exactly_these_three() -> None:
    """Narrow by design: a broader set would wrongly exclude nodes that asked nothing."""
    assert _scope().CAPABILITY_CREDENTIAL_ENV_NAMES == _CAPABILITY_ENV_NAMES


def test_the_review_adapter_this_repo_resolves_requests_no_credential_of_its_own(
    tmp_path: Path, resolve_test_acp_nodes: Any
) -> None:
    """Criterion 5's default arm, read off the RESOLUTION rather than off a literal.

    The adapter is resolved exactly as a dispatch resolves it, so this asserts what the
    review node really receives; an env mapping written by the test could agree with a
    predicate that is wrong about the shape a resolved adapter has. The implementer node
    is the control: both come back from the same resolution, so "the review node takes
    the run credential" is a statement about parity rather than about one lucky node.
    """
    scope = _scope()
    resolution = resolve_test_acp_nodes(repo=tmp_path)

    review = resolution.nodes["review"].adapter
    implement = resolution.nodes["implement"].adapter

    assert scope.run_scoped_credential_applies(adapter_env=review.env)
    assert scope.requested_capability_env_name(adapter_env=review.env) is None
    assert scope.run_scoped_credential_applies(adapter_env=implement.env)


@pytest.mark.parametrize("env_name", _CAPABILITY_ENV_NAMES)
def test_a_node_declaring_its_own_credential_key_has_requested_another_capability(
    env_name: str,
) -> None:
    scope = _scope()
    adapter = AcpAdapter(command=_CLAUDE_ACP, env={env_name: "a-value-never-read"})

    assert scope.requested_capability_env_name(adapter_env=adapter.env) == env_name
    assert not scope.run_scoped_credential_applies(adapter_env=adapter.env)


def test_the_capability_test_reads_names_and_never_values() -> None:
    """A node declaring a credential must not leak one through this surface."""
    scope = _scope()
    secret = "sk-ant-the-adapters-own-key"
    adapter = AcpAdapter(command=_CLAUDE_ACP, env={"ANTHROPIC_API_KEY": secret})

    answer = scope.requested_capability_env_name(adapter_env=adapter.env)

    assert answer == "ANTHROPIC_API_KEY"
    assert secret not in str(answer)


@pytest.mark.parametrize(
    "env",
    [
        pytest.param({}, id="no-env-at-all"),
        pytest.param({"ANTHROPIC_MODEL": "claude-opus-4-8"}, id="model-pin-only"),
        pytest.param({"CLAUDE_CODE_EFFORT_LEVEL": "high"}, id="effort-pin-only"),
        pytest.param({"ANTHROPIC_BASE_URL": "https://example.invalid"}, id="base-url-only"),
        pytest.param({"TOKEN_BUDGET": "1000"}, id="a-name-that-merely-says-token"),
    ],
)
def test_a_node_that_pins_anything_other_than_a_credential_still_takes_the_run_credential(
    env: dict[str, str],
) -> None:
    """The narrow direction: a broad secret-smell scan would wrongly exclude these.

    `TOKEN_BUDGET` is the case `_acp_candidate_secrets` deliberately refuses on committed
    data; here the same spelling must NOT read as a capability request, because concluding
    a node opted out when it did not is the expensive mistake.
    """
    assert _scope().run_scoped_credential_applies(adapter_env=env)
