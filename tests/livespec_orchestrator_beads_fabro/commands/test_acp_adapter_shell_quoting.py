"""Adapter env values survive the POSIX tokenization their consumer applies.

Binds `SPECIFICATION/contracts.md` section "ACP node adapter configuration"
(v083): each `env` VALUE MUST be shell-quoted such that POSIX shell
tokenization of the rendered string recovers that value BYTE-FOR-BYTE.

WHY EVERY ASSERTION HERE TOKENIZES RATHER THAN MATCHING THE STRING. Fabro
splits `acp.command` with POSIX rules before it launches the process, and an
unquoted JSON object does not survive that split: every quote character is
consumed as shell quoting, so `{"model":"gpt-5.6-terra"}` reaches the adapter
as `{model:gpt-5.6-terra}` and its own `JSON.parse` rejects it (release
0.82.0 could not start a single Codex-backed node; work-item bd-ib-qulf). A
string-shape assertion CANNOT catch that regression — a quoted value and an
unquoted one differ by two characters that a substring check reads straight
past, and the only observation that discriminates them is what the tokenizer
hands back. So the property under test is the round trip, not the render.

The tokenizer used here is `shlex.split` rather than the package's own
`parse_adapter_string`, deliberately: that function is the renderer's inverse
and is itself under test, so grading the renderer against it would pass a
matching pair of bugs. `shlex.split` is the same POSIX tokenization the Rust
consumer applies (`shlex::split` in fabro's `AcpProcessSpec::from_command_attr`).
"""

from __future__ import annotations

import json
import shlex
from itertools import takewhile

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import builtin_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    AcpAdapter,
    parse_adapter_string,
    render_adapter,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._codex_model_tiers import CodexModelTier
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    CODEX_ADAPTER_BASE,
    CODEX_ADAPTER_COMMAND,
    codex_adapter,
)

# The JSON objects the three cases below must recover INTACT, restated here
# rather than imported: a test that built its expectation from the renderer's
# own `json.dumps` call could not tell a deliberate change from a regression.
_UNPINNED_CONFIG = '{"approval_policy":"never","sandbox_mode":"danger-full-access"}'
_PINNED_CONFIG = (
    '{"approval_policy":"never","model":"gpt-5.4-mini",'
    '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}'
)
_TERRA_CONFIG = (
    '{"approval_policy":"never","model":"gpt-5.6-terra",'
    '"model_reasoning_effort":"xhigh","sandbox_mode":"danger-full-access"}'
)

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_WORKFLOW_INPUTS = {
    "implement_adapter": f"ANTHROPIC_MODEL=claude-opus-5 {_CLAUDE}",
    "review_adapter": _CLAUDE,
}


def _tokenized_env(*, rendered: str) -> dict[str, str]:
    """The env map a POSIX shell would hand the adapter process.

    The leading `KEY=value` tokens are the env prefix fabro strips off an
    `acp.command`; the first token without an `=` is the command, which ends
    the prefix and is what `takewhile` stops on.
    """
    assignments = takewhile(lambda token: "=" in token, shlex.split(rendered))
    return {key: value for key, _, value in (token.partition("=") for token in assignments)}


def test_a_pinned_tier_renders_a_codex_config_that_survives_shell_tokenization() -> None:
    """A pinned tier's CODEX_CONFIG comes back byte-for-byte and parses as JSON."""
    recovered = _tokenized_env(
        rendered=codex_adapter(tier=CodexModelTier(model="gpt-5.4-mini", reasoning_effort="high"))
    )["CODEX_CONFIG"]

    assert recovered == _PINNED_CONFIG
    assert json.loads(recovered) == {
        "approval_policy": "never",
        "model": "gpt-5.4-mini",
        "model_reasoning_effort": "high",
        "sandbox_mode": "danger-full-access",
    }


def test_an_un_pinned_tier_renders_a_codex_config_that_survives_shell_tokenization() -> None:
    """The opt-out carries the posture object, so it needs the same quoting.

    The un-pinned base string is the one an operator reads as "no pins at
    all", which is exactly why it is easy to assume it carries no JSON — it
    carries the sandbox and approval posture, and dies identically without
    the quoting.
    """
    recovered = _tokenized_env(
        rendered=codex_adapter(tier=CodexModelTier(model="", reasoning_effort=""))
    )["CODEX_CONFIG"]

    assert recovered == _UNPINNED_CONFIG
    assert json.loads(recovered) == {
        "approval_policy": "never",
        "sandbox_mode": "danger-full-access",
    }
    assert _tokenized_env(rendered=CODEX_ADAPTER_BASE)["CODEX_CONFIG"] == _UNPINNED_CONFIG


def test_an_explicit_acp_nodes_table_renders_a_codex_config_that_survives_tokenization() -> None:
    """The GENERIC renderer needs the quoting too, and it is the one that died.

    The run that could not start was the `review` node, whose adapter comes
    from an explicit `dispatcher.acp_nodes` table rather than from the
    `dispatcher.codex_models` shorthand — a different renderer on a different
    code path. Fixing only the shorthand would repair the `pr` node and leave
    this one emitting bare JSON, so this case is the negative control on the
    scope of the fix rather than a second flavour of the same assertion.
    """
    overlays = repository_acp_overlays(
        catalogs=builtin_catalogs(),
        block={
            "acp_nodes": {
                "review": {
                    "command": CODEX_ADAPTER_COMMAND,
                    "env": {"CODEX_CONFIG": _TERRA_CONFIG, "INITIAL_AGENT_MODE": "read-only"},
                    "args": [],
                }
            }
        },
    )
    assert not isinstance(overlays, str), overlays
    resolution = resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS, repository=overlays, dispatch={}
    )
    assert not isinstance(resolution, str), resolution

    recovered = _tokenized_env(rendered=resolution.nodes["review"].rendered)
    assert recovered["CODEX_CONFIG"] == _TERRA_CONFIG
    assert recovered["INITIAL_AGENT_MODE"] == "read-only"
    assert json.loads(recovered["CODEX_CONFIG"])["model"] == "gpt-5.6-terra"


def test_an_env_value_carrying_an_apostrophe_survives_shell_tokenization() -> None:
    """A naive single-quote wrap breaks here, which is why the rule is a round trip.

    `model` is operator-supplied and validated against no alphabet, and an
    apostrophe closes a naive wrap early — yielding an UNPARSEABLE command
    string rather than a wrong-but-parseable one, so the failure surfaces as
    a launch error nobody can trace back to the value.
    """
    rendered = render_adapter(
        adapter=AcpAdapter(command=CODEX_ADAPTER_COMMAND, env={"MODEL": "o'brien's-5"})
    )

    assert _tokenized_env(rendered=rendered)["MODEL"] == "o'brien's-5"
    assert shlex.split(rendered)[-1] == CODEX_ADAPTER_COMMAND


def test_re_rendering_an_already_rendered_adapter_does_not_double_quote_it() -> None:
    """Idempotence, and it is load-bearing rather than a nicety.

    Every shorthand-expanded adapter takes exactly this path in a real
    dispatch: `codex_adapter` renders it, `overlay_from_string` parses it back
    into an overlay, and the three-layer merge renders it again. A parse that
    kept the quote characters as part of the value would quote them a second
    time and hand the adapter `'{"model":...}'` with the quotes INSIDE the
    JSON — a different failure with the same fatal outcome.
    """
    once = codex_adapter(tier=CodexModelTier(model="gpt-5.5", reasoning_effort="low"))
    twice = render_adapter(adapter=parse_adapter_string(text=once))

    assert twice == once
    assert render_adapter(adapter=parse_adapter_string(text=twice)) == once
    assert _tokenized_env(rendered=twice)["CODEX_CONFIG"].startswith('{"approval_policy"')


def test_an_unbalanced_quote_falls_back_to_whitespace_tokenization() -> None:
    """A malformed adapter string is not adjudicated here, it is passed on.

    POSIX tokenization REFUSES an unterminated quote, and this module is not
    where that refusal belongs: fabro applies the same tokenizer to the same
    bytes and reports it against the command it actually tried to run. Falling
    back to the whitespace split preserves the pre-quoting behaviour instead
    of turning a bad configuration value into a crash inside resolution.
    """
    parsed = parse_adapter_string(text="ALPHA='unterminated BETA=2 acp")

    assert parsed.env == {"ALPHA": "'unterminated", "BETA": "2"}
    assert parsed.command == "acp"
