"""The PER-DISPATCH layer in the structured form, under the same refusal rules.

Binds `SPECIFICATION/contracts.md` section "ACP node adapter configuration":
the per-dispatch layer is "an explicit `--acp-node <node>=<value>` argument on
`dispatcher.py dispatch`, `dispatcher.py loop` and the `drive` operation's
`impl:<id>` action, whose value MAY be either form -- a legacy adapter string
(the manual form) or a JSON object in the structured form -- under the same
refusal rules before claim."

EVERY CASE DRIVES `prepare_acp_nodes`, WHICH IS THE SEAM A DISPATCH USES. That
is deliberate rather than incidental: the claim is about what a `--acp-node`
argument DOES to a dispatch, and the per-dispatch overlay parser is an
implementation detail of that. Driving the parser directly would also make
these cases depend on its signature, so they would report a change of shape
rather than a change of behaviour.

"THE SAME REFUSAL RULES" IS THE HALF WORTH TESTING, and it is why these cases
re-assert faults that already have coverage at the repository layer. The two
layers reach the renderer by different routes, so a fault refusing at one is
no evidence at all about the other. The dispatch layer is also the one an
operator reaches for under time pressure, which is the worst moment for an
unresolvable agent to resolve silently.

THE RENDERED BYTES ARE READ OFF THE JOURNAL RECORD, which is the merged,
post-resolution answer -- so a structured value that reached the merge
UNRENDERED shows up as JSON text in a node's adapter rather than as a passing
assertion about an overlay field.

THE WORKFLOW DEFAULT IS A SENTINEL NO CASE SHOULD RENDER. A dispatch value
that silently failed to apply would leave the default standing, which is a
plausible, green, wrong result; making the default unmistakable turns that
into a visible failure.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_V107_IMPLEMENTER = f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"
_CODEX_PATH = "/opt/livespec/codex-acp/bin/codex-acp"

# Every adapter input carries the same unmistakable sentinel, so a node whose
# dispatch override failed to apply renders `WORKFLOW=<node>` rather than
# something that could be mistaken for a real adapter.
_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "WORKFLOW=implement placeholder-adapter"
fix_adapter = "WORKFLOW=fix placeholder-adapter"
review_fix_adapter = "WORKFLOW=review_fix placeholder-adapter"
pr_adapter = "WORKFLOW=pr placeholder-adapter"
review_adapter = "WORKFLOW=review placeholder-adapter"
disposition_adapter = "WORKFLOW=disposition placeholder-adapter"
dod_gate_adapter = "WORKFLOW=dod_gate placeholder-adapter"
proof_capture_adapter = "WORKFLOW=proof_capture placeholder-adapter"
proof_verify_adapter = "WORKFLOW=proof_verify placeholder-adapter"

[run.environment]
id = "livespec-ci"
"""


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, *, record: dict[str, Any]) -> None:
        self.records.append(record)


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _prepared(*, tmp_path: Path, override: str) -> Any:
    """One dispatch's resolved nodes for a `--acp-node` value, or its refusal."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_WORKFLOW_TOML, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}), encoding="utf-8"
    )
    journal = _Journal()
    outcome = _module(name="_dispatcher_acp_nodes").prepare_acp_nodes(
        repo=repo,
        committed=committed,
        overrides=(override,),
        journal=journal,
        work_item_id="bd-ib-kc7vzk",
    )
    if isinstance(outcome, str):
        return outcome
    [record] = [entry for entry in journal.records if entry["stage"] == "acp-nodes"]
    return record["acp_nodes"]


def _rendered(*, tmp_path: Path, value: str, node: str = "implement") -> str:
    """The node's merged adapter bytes; a refusal here FAILS rather than passes.

    A rendered adapter and a refusal are both strings, so a helper returning
    whichever came back would let an `isinstance(result, str)` assertion pass
    on a perfectly successful resolution. The two are separated here for that
    reason, and each case says which one it expects.
    """
    nodes = _prepared(tmp_path=tmp_path, override=f"{node}={value}")
    assert not isinstance(nodes, str), f"expected a resolution, got refusal: {nodes}"
    adapter = nodes[node]["adapter"]
    assert isinstance(adapter, str)
    return adapter


def _refusal(*, tmp_path: Path, value: str, node: str = "implement") -> str:
    """The refusal a bad `--acp-node` value produces, asserted to BE one."""
    outcome = _prepared(tmp_path=tmp_path, override=f"{node}={value}")
    assert isinstance(outcome, str), f"expected a refusal, got a resolution: {outcome!r}"
    return outcome


def test_a_structured_dispatch_value_renders_and_replaces_the_workflow_default(
    tmp_path: Path,
) -> None:
    """The ratified v107 bytes, reached through the per-dispatch layer."""
    value = json.dumps({"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"})

    assert _rendered(tmp_path=tmp_path, value=value) == _V107_IMPLEMENTER


def test_a_structured_dispatch_value_replaces_the_environment_it_overrides(
    tmp_path: Path,
) -> None:
    """A rendered structured value is a COMPLETE adapter, not a patch.

    Merging the workflow default's own variable into a rendered Codex command
    line would prefix another provider's environment onto it, which is the
    defect the complete-adapter rule exists to prevent.
    """
    value = json.dumps({"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"})

    rendered = _rendered(tmp_path=tmp_path, value=value)

    assert "WORKFLOW=implement" not in rendered
    assert rendered.endswith(_CODEX_PATH)


def test_the_legacy_string_form_still_resolves_and_still_merges_env(tmp_path: Path) -> None:
    """The control: the new spelling is ADDITIVE, the old one is unchanged.

    Scenario 87 requires a per-dispatch STRING to merge its env over the less
    specific layers, so a build that treated every dispatch value as a complete
    adapter would break it. The structured cases alone could not tell that
    apart.
    """
    rendered = _rendered(tmp_path=tmp_path, value="ANTHROPIC_MODEL=claude-haiku-4-5 uvx some-acp")

    assert rendered == "ANTHROPIC_MODEL=claude-haiku-4-5 WORKFLOW=implement uvx some-acp"


def test_a_structured_dispatch_value_naming_an_unknown_agent_refuses(tmp_path: Path) -> None:
    """The catalog resolution refuses here exactly as at the repository layer."""
    refusal = _refusal(
        tmp_path=tmp_path, value=json.dumps({"agent": "no-such-agent", "model": "x"})
    )

    assert "no-such-agent" in refusal


def test_a_structured_dispatch_codex_value_without_effort_refuses(tmp_path: Path) -> None:
    """The every-Codex-candidate-is-pinned rule binds this layer too."""
    refusal = _refusal(
        tmp_path=tmp_path, value=json.dumps({"agent": "codex-acp", "model": "gpt-5.5"})
    )

    assert "effort" in refusal


def test_a_structured_dispatch_value_mixing_the_two_forms_refuses(tmp_path: Path) -> None:
    """The closed two-form grammar binds this layer too."""
    refusal = _refusal(
        tmp_path=tmp_path,
        value=json.dumps({"agent": "claude-acp", "model": "x", "command": "uvx acp"}),
    )

    assert "implement" in refusal


def test_a_dispatch_value_opening_with_a_brace_that_is_not_json_refuses(
    tmp_path: Path,
) -> None:
    """A malformed structured value refuses rather than becoming a command."""
    refusal = _refusal(tmp_path=tmp_path, value='{"agent": "claude-acp",}')

    assert "implement" in refusal
