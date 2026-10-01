"""The WORKFLOW layer's built-in defaults, expressed structurally.

Binds `SPECIFICATION/contracts.md` section "Built-in ACP node defaults": "The
workflow's own declared inputs ... MUST express the built-in defaults as
structured entries in the grammar of §'ACP node adapter configuration', never as
class-shaped tiers", with `implement` / `fix` / `review_fix` / `proof_capture`
taking `{"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"}` and
`pr` taking `{"agent": "claude-acp", "model": "claude-haiku-4-5", "effort":
"high"}`; and those entries "MUST render, literally" the v107 adapter strings --
"the v107 bytes, byte for byte".

THE BYTE TARGETS ARE THE RATIFIED LITERALS, WRITTEN OUT. A test importing the
catalog's or the renderer's own constants could not tell a deliberate change
from a regression, and the contract's whole claim is that a reader can predict
these strings from the specification alone. So they are transcribed here and the
render has to meet them.

THE COMMITTED WORKFLOW IS GRADED, NOT JUST THE RENDERER. A renderer that turns a
structured entry into the right bytes proves nothing about what this
repository's `workflow.toml` actually declares -- the criterion is that the
DEFAULT ENTRIES are structured, so the committed file is read and its four
named inputs are parsed as structured entries. A unit test on the renderer alone
would pass unchanged against a workflow that still declared raw strings.

AND THE RENDER IS ASSERTED THROUGH THE SEAM THE DISPATCH USES. `prepare_acp_nodes`
reads the committed inputs and hands them down; if the structured values reached
the merge unrendered, a node's `acp.command` would be a JSON object. So the
end-to-end case resolves the real workflow text through the real reader.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WORKFLOW_TOML = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_V107_IMPLEMENTER = f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"
_V107_PUBLISH = f"ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"

# The ratified built-in entry per input, from the contract's own table.
_STRUCTURED_DEFAULTS: dict[str, tuple[dict[str, str], str]] = {
    "implement_adapter": (
        {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"},
        _V107_IMPLEMENTER,
    ),
    "fix_adapter": (
        {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"},
        _V107_IMPLEMENTER,
    ),
    "review_fix_adapter": (
        {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"},
        _V107_IMPLEMENTER,
    ),
    "pr_adapter": (
        {"agent": "claude-acp", "model": "claude-haiku-4-5", "effort": "high"},
        _V107_PUBLISH,
    ),
}


def _module(*, name: str) -> Any:
    """Import a commands module, asserting its file exists first.

    The `is_file` assertion fails as a genuine assertion before the import can
    fail as a collection error, which is what keeps the Red honest.
    """
    assert (_COMMANDS / f"{name}.py").is_file(), f"{name} module is not implemented"
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _committed_adapter_inputs() -> dict[str, str]:
    """This repository's own committed `[run.inputs]` adapter declarations."""
    return dict(
        _module(name="_dispatcher_acp_nodes").workflow_adapter_inputs(
            committed_text=_WORKFLOW_TOML.read_text(encoding="utf-8")
        )
    )


def test_the_committed_workflow_declares_the_four_defaults_structurally() -> None:
    """The criterion's subject: what `workflow.toml` actually declares.

    Each value must PARSE as the ratified structured entry, not merely contain
    an agent name -- a raw adapter string mentioning `claude-acp` would satisfy
    a substring check while remaining exactly the class-shaped spelling the
    contract says these inputs must no longer use.
    """
    declared = _committed_adapter_inputs()

    for name, (entry, _) in _STRUCTURED_DEFAULTS.items():
        assert name in declared, f"the committed workflow declares no {name}"
        value = declared[name]
        assert value.lstrip().startswith("{"), (
            f"{name} must be a STRUCTURED entry, but the committed workflow declares "
            f"the manual form: {value!r}"
        )
        assert (
            json.loads(value) == entry
        ), f"{name} must declare the ratified built-in entry {entry!r}; got {value!r}"


def test_each_structured_default_renders_the_v107_bytes_exactly() -> None:
    """ "The v107 bytes, byte for byte" -- through the real catalogs."""
    catalogs = _module(name="_acp_catalogs").builtin_catalogs()
    declared = _committed_adapter_inputs()

    rendered = _module(name="_acp_workflow_defaults").rendered_workflow_defaults(
        declared=declared, catalogs=catalogs
    )

    assert not isinstance(rendered, str), rendered
    for name, (_, expected) in _STRUCTURED_DEFAULTS.items():
        assert rendered[name] == expected, f"{name} rendered {rendered[name]!r}"


def test_a_manual_input_passes_through_byte_for_byte() -> None:
    """A workflow input the catalogs do not cover is left exactly as declared.

    The `review` default carries a context-window suffix (`claude-opus-4-8[1m]`)
    that no catalog model declares, so a build that re-rendered every input
    rather than only the structured ones would refuse this repository's own
    committed workflow.
    """
    catalogs = _module(name="_acp_catalogs").builtin_catalogs()
    manual = "ANTHROPIC_MODEL=claude-opus-4-8[1m] CLAUDE_CODE_EFFORT_LEVEL=high " + _CLAUDE

    rendered = _module(name="_acp_workflow_defaults").rendered_workflow_defaults(
        declared={"review_adapter": manual}, catalogs=catalogs
    )

    assert not isinstance(rendered, str), rendered
    assert rendered["review_adapter"] == manual


def test_a_structured_input_naming_an_unknown_model_refuses() -> None:
    """A workflow default is resolved, not trusted: an unresolvable one refuses."""
    catalogs = _module(name="_acp_catalogs").builtin_catalogs()

    refusal = _module(name="_acp_workflow_defaults").rendered_workflow_defaults(
        declared={"pr_adapter": json.dumps({"agent": "claude-acp", "model": "nope-9"})},
        catalogs=catalogs,
    )

    assert isinstance(refusal, str), refusal
    assert "pr_adapter" in refusal


def test_a_value_opening_with_a_brace_that_is_not_json_refuses() -> None:
    """A malformed structured entry refuses rather than becoming a command.

    Passing it through would make `{` the node's executable, and the failure
    would surface inside a sandbox with nothing pointing back at the input.
    """
    catalogs = _module(name="_acp_catalogs").builtin_catalogs()

    refusal = _module(name="_acp_workflow_defaults").rendered_workflow_defaults(
        declared={"pr_adapter": '{"agent": "claude-acp",}'}, catalogs=catalogs
    )

    assert isinstance(refusal, str), refusal
    assert "pr_adapter" in refusal


def test_a_read_only_node_input_renders_its_read_only_posture() -> None:
    """The posture is a property of the NODE, and the input names the node.

    `disposition` performs no writes, so a structured entry on its input must
    render the read-only environment -- the same rule Scenario 90 states for a
    review node routed to Codex.
    """
    catalogs = _module(name="_acp_catalogs").builtin_catalogs()
    entry = json.dumps({"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"})

    rendered = _module(name="_acp_workflow_defaults").rendered_workflow_defaults(
        declared={"disposition_adapter": entry, "implement_adapter": entry}, catalogs=catalogs
    )

    assert not isinstance(rendered, str), rendered
    assert "INITIAL_AGENT_MODE=read-only" in rendered["disposition_adapter"]
    assert "INITIAL_AGENT_MODE=agent-full-access" in rendered["implement_adapter"]
