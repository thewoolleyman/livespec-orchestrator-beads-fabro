"""The refusal paths a well-formed workflow default never reaches.

Companion to `test_acp_workflow_defaults`, which grades this repository's own
committed defaults. These cases cover the decisions a correct workflow cannot
exercise -- the ones a VENDORED workflow, or a workflow mid-edit, reaches.

EACH REFUSAL HAS TO NAME THE INPUT, which is the property worth asserting
rather than the refusal itself. A structured default is resolved at dispatch
time, far from the file that declares it, so a message carrying only "unknown
key 'modle'" leaves an operator grepping nine adapter inputs for it. The key a
refusal is built from is therefore `workflow input <name>`, and these cases
read that name back out.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _rendered(*, declared: dict[str, str]) -> Any:
    return _module(name="_acp_workflow_defaults").rendered_workflow_defaults(
        declared=declared, catalogs=_module(name="_acp_catalogs").builtin_catalogs()
    )


def test_a_structured_default_carrying_an_unknown_key_refuses_naming_the_input() -> None:
    """The closed grammar applies to the WORKFLOW layer too, not only to a repo."""
    refusal = _rendered(
        declared={
            "pr_adapter": json.dumps(
                {"agent": "claude-acp", "model": "claude-opus-5", "modle": "typo"}
            )
        }
    )

    assert isinstance(refusal, str), refusal
    assert "workflow input pr_adapter" in refusal
    assert "modle" in refusal


def test_a_structured_default_mixing_the_two_forms_refuses_naming_the_input() -> None:
    """`agent` beside a manual field is the mixed form, refused at every layer."""
    refusal = _rendered(
        declared={
            "pr_adapter": json.dumps({"agent": "claude-acp", "model": "x", "command": "uvx acp"})
        }
    )

    assert isinstance(refusal, str), refusal
    assert "workflow input pr_adapter" in refusal


def test_a_structured_default_with_no_model_refuses_naming_the_input() -> None:
    """`model` is required of every agent, at the workflow layer as elsewhere."""
    refusal = _rendered(declared={"pr_adapter": json.dumps({"agent": "claude-acp"})})

    assert isinstance(refusal, str), refusal
    assert "workflow input pr_adapter" in refusal
    assert "model" in refusal


def test_the_first_faulty_input_refuses_and_the_order_is_stable() -> None:
    """Two faults refuse on the SAME one every time.

    Inputs are visited in sorted order, so a workflow with two broken defaults
    produces one reproducible message rather than whichever the dict happened
    to yield first -- the same property `parse_node_chains` gives the
    repository layer.
    """
    broken = json.dumps({"agent": "nope", "model": "x"})
    both = {"pr_adapter": broken, "fix_adapter": broken}

    first = _rendered(declared=both)
    again = _rendered(declared=dict(reversed(list(both.items()))))

    assert isinstance(first, str), first
    assert first == again
    assert "workflow input fix_adapter" in first
