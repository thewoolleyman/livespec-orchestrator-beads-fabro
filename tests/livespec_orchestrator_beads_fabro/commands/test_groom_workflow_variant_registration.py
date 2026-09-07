"""The registered groom variant, read back through the registry that names it.

`SPECIFICATION/contracts.md` requires a repository that grooms through a
factory run to register the groom variant in its own `dispatcher.workflows`
table, and holds a registered variant to the reserved workflow's six ACP node
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    RESERVED_WORKFLOW_NAME,
    workflow_registry,
)

# `commands/_config.py` sits at `.claude-plugin/scripts/<package>/commands/`, so
# the repository root is four directories above it. Derived from the imported
# module rather than from this test file's own location so the anchor cannot
# drift if the test tree is reshaped.
_REPO_ROOT = Path(_config.__file__).resolve().parents[4]

_GROOM_VARIANT_NAME = "groom-work-item"
_GROOM_VARIANT_DIRECTORY = ".fabro/workflows/groom-work-item"
_BUNDLE_DIRECTORY = ".claude-plugin/.fabro/workflows/implement-work-item"

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


def test_the_groom_variant_declares_the_bundles_six_acp_nodes() -> None:
    """Peer parity for the names the adapter, model and timeout layers address."""
    bundle_nodes = _acp_nodes(directory=_BUNDLE_DIRECTORY)

    # A control on the reader itself: the bundle's six are what these layers
    # resolve against, so a parse that returned some other count would make the
    # comparison below meaningless rather than false.
    assert bundle_nodes == {"implement", "fix", "review_fix", "pr", "review", "disposition"}
    assert _acp_nodes(directory=_GROOM_VARIANT_DIRECTORY) == bundle_nodes


def test_the_groom_variant_declares_the_bundles_input_token_set() -> None:
    """The bundle's whole set, opting out of none of it, plus its own kind."""
    bundle_inputs = _declared_inputs(directory=_BUNDLE_DIRECTORY)
    variant_inputs = _declared_inputs(directory=_GROOM_VARIANT_DIRECTORY)

    # Same control shape as the node reader: prove the scan sees a real table
    # before believing what it says about the two.
    assert "sandbox_check_suite" in bundle_inputs
    assert bundle_inputs <= variant_inputs

    # The ONE addition is the variant's declaration of what it is, which is not
    # a projection of anything and which the reserved workflow deliberately does
    # not carry. Anything else appearing here would be a token the bundle does
    # not declare, which the peer clause forbids.
    assert variant_inputs - bundle_inputs == {_workflow_variant_kind.WORKFLOW_KIND_INPUT_NAME}
