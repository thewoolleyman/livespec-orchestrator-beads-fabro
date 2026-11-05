"""The registered groom variant, read back through the registry that names it.

`SPECIFICATION/contracts.md` requires a repository that grooms through a
factory run to register the groom variant in its own `dispatcher.workflows`
table, and holds a registered variant to the reserved workflow's ACP node
names and its input token set — a registered variant is that workflow's peer,
not its exception.

EVERY ASSERTION HERE GOES THROUGH THE PRODUCTION PATH, not around it. The
directory is not spelled and then checked for existence; it is RESOLVED by the
same `resolve_workflow_variant` -> `workflow_toml` pair a dispatch resolves it
with, and the kind is read by the same reader the groom door reads it with. A
test that read the payload off a hardcoded path would pass just as happily with
the registry entry deleted, which is the one thing that would actually break a
groom dispatch.

The node set and the input set are compared AGAINST THE BUNDLE rather than
against a list written here. Peer parity is a relation between two payloads, so
a restated expectation would keep agreeing with itself while the two drifted
apart; read both and compare, and a node the bundle gains or loses is a failure
here rather than a silent divergence.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _config, _workflow_variant_kind
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    resolve_workflow_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    GROOM_ONLY_ACP_NODES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    RESERVED_WORKFLOW_NAME,
    workflow_registry,
)

# The ONE adapter input the ratified groom-kind adjustment subtracts, derived
# from the groom-only node that rides it so the two cannot drift apart.
_GROOM_ONLY_ADAPTER_INPUT = f"{sorted(GROOM_ONLY_ACP_NODES)[0]}_adapter"

# `commands/_config.py` sits at `.claude-plugin/scripts/<package>/commands/`, so
# the repository root is four directories above it. Derived from the imported
# module rather than from this test file's own location so the anchor cannot
# drift if the test tree is reshaped.
_REPO_ROOT = Path(_config.__file__).resolve().parents[4]

_GROOM_VARIANT_NAME = "groom-work-item"
_GROOM_VARIANT_DIRECTORY = ".fabro/workflows/groom-work-item"
_BUNDLE_DIRECTORY = ".claude-plugin/.fabro/workflows/implement-work-item"
_GROOM_PR_ADAPTER = (
    "ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high "
    "npx -y @agentclientprotocol/claude-agent-acp"
)

# A DOT node declaration: a name at the start of a line followed by its
# attribute block. An edge line (`a -> b [...]`) cannot match, because the
# `^`-anchored name must be followed by the bracket with only whitespace
# between, and an edge has its arrow and target there instead.
_NODE_DECLARATION = re.compile(r"(?m)^[ \t]*(?P<node>\w+)[ \t]*\[(?P<attrs>[^\]]*)\]")
_ACP_BACKEND = 'backend="acp"'


def _acp_nodes(*, directory: str) -> set[str]:
    """Every node in one payload's graph that the adapter layer has to address."""
    graph = (_REPO_ROOT / directory / "workflow.fabro").read_text(encoding="utf-8")
    return {
        match.group("node")
        for match in _NODE_DECLARATION.finditer(graph)
        if _ACP_BACKEND in match.group("attrs")
    }


def _declared_inputs(*, directory: str) -> set[str]:
    """Every name one payload's `[run.inputs]` table declares."""
    manifest = (_REPO_ROOT / directory / "workflow.toml").read_text(encoding="utf-8")
    return set(workflow_declared_inputs(committed_text=manifest))


def test_the_registry_resolves_the_groom_variant_to_a_target_local_directory() -> None:
    """The registry entry, and the path a dispatch would actually run from."""
    registry = workflow_registry(block=dispatcher_block(cwd=_REPO_ROOT))

    # The reserved name is never read from the registry and registering it is a
    # pre-run refusal, so its absence here is part of what makes the entry below
    # resolvable at all.
    assert RESERVED_WORKFLOW_NAME not in registry
    assert registry.get(_GROOM_VARIANT_NAME) == _GROOM_VARIANT_DIRECTORY

    variant = resolve_workflow_variant(cwd=_REPO_ROOT, name=_GROOM_VARIANT_NAME)

    assert variant.name == _GROOM_VARIANT_NAME
    assert variant.directory == _GROOM_VARIANT_DIRECTORY

    resolved = workflow_toml(
        args=argparse.Namespace(workflow=None, repo=_REPO_ROOT),
        variant_directory=variant.directory,
    )

    # TARGET-LOCAL: under the repository's own `.fabro/`, not the plugin's.
    assert resolved == _REPO_ROOT / _GROOM_VARIANT_DIRECTORY / "workflow.toml"
    assert resolved.is_file()
    assert (resolved.parent / "workflow.fabro").is_file()


def test_the_resolved_variant_declares_the_groom_kind() -> None:
    """Read by the reader the Dispatcher's groom door reads it with."""
    variant = resolve_workflow_variant(cwd=_REPO_ROOT, name=_GROOM_VARIANT_NAME)

    kind = _workflow_variant_kind.variant_kind(repo=_REPO_ROOT, variant=variant)

    assert kind == _workflow_variant_kind.WORKFLOW_KIND_GROOM
    assert _workflow_variant_kind.groom_variant_names(repo=_REPO_ROOT) == (_GROOM_VARIANT_NAME,)


def test_the_groom_variant_declares_the_bundles_acp_nodes() -> None:
    """Peer parity for the names the adapter, model and timeout layers address.

    Parity is about DECLARATION, not reachability. The variant declares
    `dod_gate` and deliberately routes no edge to it, which is the latitude the
    peer clause grants a groom-kind variant: declaring it keeps a target that
    pins `dispatcher.acp_nodes.dod_gate` dispatchable through this graph, while
    reaching it would gate a groom run on the quality of a Definition of Done
    the run has not written yet.

    THE ONE ASYMMETRY IS `pr`, AND IT RUNS THE OTHER WAY. Since v121 the bundle
    publishes through COMMAND stages, so it declares no ACP `pr` node at all,
    while the groom variant keeps one because what it publishes is a filing plan
    for the host rather than a Git branch. So the variant's ACP set is the
    bundle's PLUS the groom-only publisher, and `GROOM_ONLY_ACP_NODES` is read
    off the module that owns that scoping rather than respelled here.
    """
    bundle_nodes = _acp_nodes(directory=_BUNDLE_DIRECTORY)

    # A control on the reader itself: these are what the layers resolve against,
    # so a parse that returned some other set would make the comparison below
    # meaningless rather than false.
    assert bundle_nodes == {
        "dod_gate",
        "implement",
        "fix",
        "review_fix",
        "proof_capture",
        "proof_verify",
        "review",
        "disposition",
    }
    assert {"pr"} == GROOM_ONLY_ACP_NODES
    assert _acp_nodes(directory=_GROOM_VARIANT_DIRECTORY) == bundle_nodes | GROOM_ONLY_ACP_NODES


def test_the_groom_variant_declares_the_bundles_input_token_set() -> None:
    """The bundle's whole set, opting out of none of it, plus two of its own.

    The ratified groom-kind adjustment is exactly one token wide: "subtract
    `pr_adapter` from the groom variant's referenced and rendered sets before
    comparison. No other token is excluded." So the variant's additions are its
    KIND declaration -- which is not a projection of anything and which the
    reserved workflow deliberately does not carry -- and the publication adapter
    its ACP filing-plan node still rides.
    """
    bundle_inputs = _declared_inputs(directory=_BUNDLE_DIRECTORY)
    variant_inputs = _declared_inputs(directory=_GROOM_VARIANT_DIRECTORY)

    # Same control shape as the node reader: prove the scan sees a real table
    # before believing what it says about the two.
    assert "sandbox_check_suite" in bundle_inputs
    assert bundle_inputs <= variant_inputs

    # Anything else appearing here would be a token the bundle does not declare
    # and the ratified adjustment does not name, which the peer clause forbids.
    assert variant_inputs - bundle_inputs == {
        _workflow_variant_kind.WORKFLOW_KIND_INPUT_NAME,
        _GROOM_ONLY_ADAPTER_INPUT,
    }
    # And the subtraction is the ratified one in BOTH directions: with that one
    # token removed the two sets are the SAME minus the kind, so a variant that
    # had quietly dropped some other input would still be caught.
    assert (variant_inputs - {_GROOM_ONLY_ADAPTER_INPUT}) - bundle_inputs == {
        _workflow_variant_kind.WORKFLOW_KIND_INPUT_NAME
    }


def test_the_groom_filing_plan_publisher_retains_its_haiku_default() -> None:
    """Groom `pr` files a plan through ACP and keeps its inexpensive default."""
    manifest = (_REPO_ROOT / _GROOM_VARIANT_DIRECTORY / "workflow.toml").read_text(encoding="utf-8")

    declared = workflow_declared_inputs(committed_text=manifest)

    assert declared[_GROOM_ONLY_ADAPTER_INPUT] == _GROOM_PR_ADAPTER
